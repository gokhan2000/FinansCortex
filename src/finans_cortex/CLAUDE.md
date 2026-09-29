# src/finans_cortex — veri katmanı ve strateji motorları

> Bu dosya, Claude bu klasördeki bir dosyaya dokunduğunda kendiliğinden okunur.
> Buradaki kurallar ölçüme dayanır; geri almadan önce gerekçeyi okuyun.

---

## Modüller

```
instruments.py      Enstrüman kayıt defteri (code ↔ Dukascopy sembolü)
storage.py          DuckDB katmanı, şema, 1h/4H/1g görünümleri
ingest.py           Dukascopy → DuckDB, yıl yıl, idempotent
quality.py          Delik + hayalet bar tespiti
indicators.py       Chandelier Exit (Normal/Maverick, use_close) + MACD
strategy.py         4H yön + 15dk zamanlama, look-ahead korumalı
backtest.py         Vektörel backtest motoru (Sharpe/MaxDD/maliyet)
akis.py             ORTAK: kural akışı dili (Dugum / Adim). Motorlar
                    `sema(cfg)` ve `izle(bars, islem, cfg, tf)` verir.
perf.py             ORTAK: işlem listesi → günlük sermaye eğrisi + ölçüler
                    (Sharpe, kâr faktörü, MaxDD...). Her strateji motoru kullanır.
gelistir.py         ORTAK: geliştirme motoru — teşhis (zayıf nokta bulguları),
                    parametre taraması (ayar/kontrol + komşu), karşılaştırma
ema_two_close.py    Strateji 1: EMA 10 iki kapanış (stop/hedef, işlem işlem) + canlı durum
heikin_range.py     Strateji 2: Heikin Ashi + Chandelier Exit + Range Filter
                    (ikili sinyal, tolerans penceresi) + canlı durum
bist.py             BIST 30: canlı sinyal (ham fiyat) + backtest geçmişi
                    (düzeltilmiş fiyat, temizlenip `bars_bist` tablosuna yazılır)
strategy_store.py   Kayıtlı varyantlar: config/stratejiler.json (atomik yazma)
erisim.py           Uzaktan erişim parolası (PBKDF2 özeti; parola saklanmaz)
bildirim.py         Adresi e-postayla yollar (SMTP; parola DPAPI ile şifreli)
```

---

## Enstrümanlar ve veri

**9 enstrüman** (öncelik global; BIST sonraya bırakıldı):
EURUSD, XAUUSD (spot ons altın), XAGUSD (spot ons gümüş), BRENT, WTI, DJ, DAX,
FTSE, **BTCUSD**

**BTCUSD tuzağı:** tek 7/24 enstrüman. Diğer 8'i hafta sonu kapalı; BTC değil.
Grafikte "Cumartesi'yi gizle" (`rangebreaks`) kuralı BTC'ye uygulanırsa **gerçek
veri ekrandan silinir**. Bu yüzden `Instrument.session` alanı var ve kural ona
bağlı (`session == "24x7"` ise rangebreaks boş). Ölçüldü: 2 haftada BTC'de 384
hafta sonu barı var. Yeni kripto eklerken aynı şeye dikkat edin.

**Kaynak: Dukascopy** (`dukascopy-python`). Yahoo/yfinance **elendi** — ölçülerek:
- Spot ons altın/gümüş Yahoo'da yok (404), sadece vadeli var → roll sıçraması sorunu
- Yahoo 15dk geçmişi = **2,5 ay** (Yahoo kendi hata mesajıyla söyledi: "must be
  within the last 60 days"). Dukascopy'de **11+ yıl**.

Kullanıcının iki kesin şartı: **ons altın/gümüş zorunlu**, **15dk göstergeler zorunlu**.
Yahoo ikisini de karşılayamadı. Ayrıntı: `docs/VERI_KAYNAGI_BULGULARI.md`.

**Mevcut veri:** 2.501.928 adet 15dk barı, 184 MB. XAUUSD 2003'e, EURUSD 2012'ye,
diğerleri 2015'e kadar geriye gidiyor.

**BIST 30 (15 Eylül 2026):** yalnızca **canlı sinyal** için, Yahoo'dan (`bist.py`).
Son 5 gün 15dk (1 saatte 1 ay) çekilir, veritabanına YAZILMAZ, kapanmamış bar
atılır. 30 hissenin 30'u da geliyor (~3 sn). Backtest için yetersiz (Yahoo 15dk
geçmişi ~60 gün). Hisse listesi `bist.BIST30` — **her çeyrek başı güncellenmeli**
(şu an 01.07-30.09.2026 dönemi).

---

## Mimari — anayasadan SAPMALAR ve gerekçeleri

| Anayasa diyor | Yapılan | Neden |
|---|---|---|
| TimescaleDB | **DuckDB tek dosya** | Tüm veri 184 MB. Bu boyut için sunucu süreci gereksiz; ayrıca işyerine tek dosya taşınıyor. Docker kurumsal makinede sorun. Faz 2'de canlı akış gelince TimescaleDB'ye geçilebilir. |
| Taban granülarite 1dk | **15dk** | 1dk, 15dk/4H hedefi için gereksiz ve 15 kat satır demek. Yahoo zaten 1dk'yı 7 günle sınırlıyor. |
| Pandas yerine Polars | Polars (ingest+gösterge+analiz) | Korundu. Backtrader'a geçilirse pandas yalnızca adaptör katmanında kullanılacak. |
| Backtrader | **~150 satırlık vektörel motor** | Pandas isterdi, bakımı durmuş, strateji tek pozisyonlu ve sinyaller zaten vektörel. Faz 2'de (çoklu pozisyon, portföy riski) yeniden değerlendirilmeli. |

**Korunan ilkeler:** her şey UTC; veri sağlayıcı pluggable (Dukascopy'ye özgü kod
yalnızca `ingest.py`'de); tek gerçek kaynak (üst zaman dilimleri saklanmaz,
görünüm olarak türetilir); arayüz veri katmanından ayrık (`app.py` hiç SQL yazmaz).

**DuckDB tek yazıcıya izin verir.** Arayüz salt-okunur bağlantı tuttuğu için,
güncelleme öncesi o bağlantı kapatılmalı (`refresh_data()` bunu yapıyor).
Aksi halde yazma bağlantısı açılmaz.

---

## Strateji motoru yapısı

**Her strateji kendi motoruyla gelir (17 Eylül 2026).** `strategies.BASE`
(`ui/strategies.py`) sözlüğündeki her kayıt bir motor modülü (`ema_two_close`,
`heikin_range`), kendi parametre denetimleri, kuralları, zaman dilimleri,
görünecek bölümleri ve backtest grafiğine çizilecek eğrileri taşır. Ortak
performans hesabı `perf.py`'de (iki motor da oradan `metrics`/`daily_equity`
alır).

**Yeni strateji eklemek:** motor modülü + `strategies.BASE`'e kayıt +
`strategy_store.CONFIGS`'e bir satır + kural akışı için `sema(cfg)` ve
`izle(bars, islem, cfg, tf)` fonksiyonları. Kayıtlı varyantlar hangi motorla
açılacağını kayıttaki `temel` alanından bulur.

**Kural akışı dili (`akis.py`):** `Dugum` = şemadaki kutu; `Adim` = o sinyalde
kutunun sonucu + gerçek değerler + `isaretler` (o adımın mum grafiğindeki
karşılığı: `Isaret` ok / nokta / çizgi / bölge — örn. Chandelier'ın yandığı
mum, giriş noktası, stop çizgisi). Adım işaret vermezse grafikte bir şey
çıkmaz, bozulmaz. `ui/akis.py` stratejiyi TANIMAZ — şemayı
çizer, adımları oynatır. Yeni strateji = iki fonksiyon yazmak; ekran
kendiliğinden çalışır. EMA tarafında kurulum barı `kurulum` sütunundan bulunur;
geri çekilme girişinde kurulum ile giriş AYNI bar değildir.

**`ema.prepare`'daki `kurulum` sütunu** vektörel hesaplanır ve simülasyon
döngüsüyle birebir aynıdır (doğrulandı: kırılım girişlerinin %100'ü bir
kurulum barına denk geliyor, yön uyuşmazlığı 0).

**Canlı sinyal** (`signal_state` / `recent_state`): backtest döngüsünün aynısı,
tek fark gün sürüyorsa son bar "gün sonu" sayılmaz. Doğrulandı: 3 varlık × 2
giriş türünde 2.400 rastgele geçmiş kesimde canlı durum = backtest'teki açık
işlem, **0 uyuşmazlık**. BIST'te gün 18:00 TR'de biter.

**Tuzak — Heikin Ashi fiyatından işlem yapılamaz.** HA kapanışı dört fiyatın
ortalamasıdır; TradingView'de HA grafiğinde alınan backtestlerin şişkin
çıkmasının sebebi budur. Kodda sinyal HA'dan, **işlem gerçek kapanıştan**.
Doğrulandı: 9 varlık × (4h + 1g) = 4.039 işlemin giriş/çıkış fiyatlarında
gerçek `close`'a göre **0 sapma**.

**Strateji 2 çıkış seçenekleri (22 Eylül 2026, Strateji 2.1 için):**
`HeikinConfig.kar_al` / `zarar_kes` (%, 0 = kapalı) ve `tek_ters`. Bar içi
kurallar Strateji 1 ile aynı (seviyeden; boşlukta açılıştan; aynı barda ikisi
de görülürse zarar; giriş barında kontrol yok). `zarar_kes` açıkken işlemin
`stop` alanı Chandelier çizgisi değil bu seviyedir (R buna göre). Doğrulandı:
varsayılan ayarla işlemler eski motorla birebir aynı; 2.1'in 5.285 işleminde
kural ihlali / kaçırılan tetik 0.

---

## Strateji 2 trend filtresi (23 Eylül 2026)

`HeikinConfig.trend_filter` = ortalama periyodu, **0 = kapalı**. Açıkken giriş
yalnız fiyatın ortalamaya göre bulunduğu yönde olur. Geliştirme motorunun
teşhisi bunu ölçüp öneriyordu ama motorda karşılığı yoktu (bkz.
`docs/STRATEJI_GECMISI.md`).

**İki nokta — değiştirmeden önce okuyun:**
1. Ortalama **gerçek kapanıştan** hesaplanır, Heikin Ashi fiyatından değil.
   Teşhisteki ölçüt de öyle (`ewm_mean(span=N)`); ikisi ayrı hesaplanırsa
   ekran "şunu öner"ip motor başka bir şey uygular.
2. `trend_filter` **`GOSTERGE_PARAMLARI` içindedir**, çünkü `prepare` içinde
   hesaplanır. Listeden çıkarılırsa tarama farklı periyotları aynı hazırlanmış
   çerçeveyle ölçer — patlamaz, sessizce yanlış sonuç verir.

**Doğrulandı:** kapalıyken eski motorla birebir aynı (Strateji 2: 4.046 işlem,
Strateji 2.1: 4.492 işlem, **0 sapma**). Açıkken (200, 4 saat) işlemlerin %43'ü
elenir ve giriş yönü ortalamanın yanlış tarafında olan **0 işlem** vardır
(EMA200 bağımsız hesaplanıp karşılaştırıldı). Kural akışı: 4 ayar × 9 varlık ×
son 6 işlem = 216 işlem hatasız çizildi; `trend` kutusu yalnız filtre açıkken
belirir. Eski kayıtlı varyantlar (alanı olmayan JSON) sorunsuz yüklenir —
`to_config` bilinmeyen/eksik alanları eler, `trend_filter` 0 olur.

---

## Strateji 2 — 15 dakikalık Chandelier teyidi (23 Eylül 2026)

`HeikinConfig.onay_15m` (varsayılan **kapalı**): 4 saatlik/günlük ikili sinyal
oluştuğunda 15 dakikalık grafikteki Chandelier yönü de aynı olmalı, değilse
işlem açılmaz. Aynı CE ayarları ve aynı `heikin` seçimi 15dk barlara uygulanır.
Kullanıcı isteği (Strateji 2.4).

**Kapanış hizası — bu kuralın can alıcı noktası.** 4 saatlik bar `ts`'te
başlar, `ts + 4sa`'te kapanır; karar o anda verilir. Teyit için o anda
**kapanmış** son 15dk barı kullanılır: 15dk barlarına `ts + 15dk` (kapanış)
damgası vurulur ve `join_asof(backward)` ile eşleşme yapılır. Eşitlik dahildir
— 16:00'da kapanan 15dk barı, 16:00'da kapanan 4 saatlik barın karar anında
hazırdır. Bar aralığı `prepare`'a dışarıdan verilmez, bar damgalarının
**ortancasından** türetilir (hafta sonu boşlukları aykırı değer).
*Doğrulandı: 1.771 işlemin hiçbirinde karar anından sonra kapanan bar
kullanılmadı (0 ileriye bakma), giriş yönü 15dk Chandelier ile ters olan
0 işlem.*

**Veri yolu (çok zaman dilimli ilk kural).** `prepare(df, cfg, bars_15m=None)`
üçüncü bir çerçeve alır; `onay_15m` açık ama çerçeve yoksa **hata yükselir** —
sessizce kapanmaz, yoksa ekranlar farklı sonuç gösterirdi. Dört yol beslenir:
`run`/`recent_state` bağlantıdan kendisi okur (`onay_oku`), `run_bars` ve
`gelistir.hazirla(..., yardimci=)` dışarıdan alır. **Kapalıyken hiç sorgu
atılmaz** — 15dk veri 9 varlıkta 2,5 milyon satırdır. `onay_serisi` ham 15dk
çerçevesini tüketip yalnız yön sütununu döndürür (bellekte tutulmaz).

`onay_15m` **`GOSTERGE_PARAMLARI` içindedir** (prepare'i etkiler) — trend
filtresiyle aynı gerekçe.

**Doğrulandı:** kapalıyken eski motorla birebir aynı (Strateji 2.3 ayarıyla
4h+1g toplam 2.421 işlemde 0 sapma). Açıkken işlemlerin %15'i elenir.

---

## Strateji 3 — Chandelier tek başına (23 Eylül 2026)

Kullanıcı: *"Strateji 2'yi kopyalayıp Strateji 3 yapalım, içinde Range Filter
hiç olmasın."* Parametreyle kapatılamıyordu, çünkü giriş kuralı "iki gösterge
birden" üzerine kuruluydu.

**Ayrı modül YAZILMADI.** `HeikinConfig.rf_kullan` (varsayılan `True`) eklendi;
`False` iken giriş Chandelier'in yön değiştirdiği barda olur, çıkış ters
yöndeki Chandelier sinyalidir — sistem sürekli piyasada kalır (al-sat/sat-al).
Strateji 3, `strategies.BASE`'e **`chandelier_ha`** anahtarıyla kendi kartı
olarak kayıtlı; motoru aynı modül, `cfg=HeikinConfig(rf_kullan=False)`.
Gerekçe: döngü mantığının (kâr al, zarar kes, trend filtresi, 15dk teyit,
fitilli mum) tamamı ortak — kopyalansaydı her düzeltme iki yerde yapılırdı.

`rf_kullan=False` iken **anlamsızlaşanlar:** `tolerance`, bekleyen sinyal
("onaylanacak ikinci gösterge yok"), `tek_ters`. Şemada `uyum` kutusu
çizilmez, `sinyal` kutusu tek göstergeyi anlatır; arayüzde Range Filter
denetimleri hiç gösterilmez (yoksa "kapattım ama değişmedi" yanılgısı olur).

`rf_kullan` **`ARAMA_UZAYI`'nda YOKTUR** — bilerek: o parametre stratejinin
kimliği, taramanın Strateji 3'ü sessizce Strateji 2'ye çevirmesi istenmez.

**Doğrulandı:** Strateji 2 ailesinin tamamı (2, 2.1–2.5 × 4 saat + günlük,
**20.024 işlem**) eski motorla birebir aynı, **0 sapma**. Strateji 3'ün
girişlerinin %100'ü Chandelier'in o barda o yöne döndüğü bar (4 saat + günlük,
**0 kural ihlali**). Kural akışı son 10 işlemde hatasız.

**Ölçüm — Range Filter gerçekten iş yapıyor** (9 varlık, tüm geçmiş):

| | İşlem | Net | Kâr faktörü | İşlem başına |
|---|---|---|---|---|
| Strateji 2, 4 saat | 3.440 | +%563 | 1,11 | 16,4 bp |
| Strateji 3, 4 saat | 11.694 | +%226 | 1,02 | **1,9 bp** |
| Strateji 2, günlük | 608 | +%818 | 1,42 | 134,6 bp |
| Strateji 3, günlük | 2.179 | +%125 | 1,03 | **5,7 bp** |

RF çıkınca işlem 3,4 katına çıkıyor, işlem başına kenar neredeyse sıfırlanıyor.
Videonun "tek gösterge sayılmaz" ısrarı ölçümle doğrulanmış oldu.

---

## Strateji 2/3'e 15 dakika zaman dilimi (23 Eylül 2026)

Kullanıcı istedi, açıldı (`BAR_HOURS`'a `"15m": 0.25`, `TF_SWING`'e "15 dakika").
Doğrulandı: backtest, canlı sinyal ve kural akışı 15 dakikada hatasız
(Strateji 2 ve 3, 45 günde 48 / 156 işlem, 0 hata).

**Ama ölçüm karşı çıkıyor** — aynı kural, farklı bar boyu, 9 varlık, tüm geçmiş:

| Bar | İşlem | Brüt | Net |
|---|---|---|---|
| 15 dakika | 45.580 | **−%345** | −%2.098 |
| 1 saat | 11.872 | +%156 | −%299 |
| 4 saat | 3.440 | +%694 | +%563 |
| Günlük | 608 | +%842 | +%818 |

15 dakikada **brüt bile eksi**: sorun maliyet değil, o granülerlikte sinyalin
kendisi gürültü. Seçenek duruyor ama beklenti buna göre kurulmalı.

**Tuzak:** çalışma zaman dilimi 15 dakika iken `onay_15m` **etkisizdir** —
teyit barı ile karar barı aynı bar olur, hiçbir sinyal elenmez (ölçüldü: 48
işlem, teyit açık/kapalı aynı). Bozuk değil, tanımı gereği böyle.

---

## BIST 30 backtest verisi (23 Eylül 2026)

Kullanıcı: *"BIST 30 hisseleri içinde ayrı bir backtest yapma olanağımız
olsun."* Eski not "Yahoo geçmişi yetersiz" diyordu — **o 15 dakika içindi.**
Ölçüldü: **günlük 26 yıl** (2000'den, 6.781 bar/hisse), **saatlik ~3 yıl**,
15 dakika ~3 ay (backtest'e yetmez).

**Ayrı tablo: `bars_bist` (code, timeframe, ts).** `instruments` tablosuna
kayıt AÇILMAZ — 30 hisse, 9 küresel varlığın listelerine (ana ekran şeridi,
Grafikler, Geliştir varsayılanı) karışmasın. Zaman dilimi türetilmez de:
günlüğü saatlikten üretmek mümkün değil, geçmişleri farklı.

### Veri BOZUK — temizlenmeden kullanılamaz

Yahoo'nun düzeltilmiş BIST serisi eskiye gidildikçe bozuluyor (30 hisse
tarandı, 13'ünde bozuk bar var):

| Sorun | Örnek |
|---|---|
| **2005 para reformu** (1 YTL = 1.000.000 TL) | TUPRS'un 2002 kapanışı **196.000.000** |
| **Negatif fiyat** | EREGL 2000-2004 arası **−15.153** |
| **Sahte sıçrama** | MGROS 04.08.2009'da tek günde **+%304** (BIST günlük limiti %10) |

`bist.temizle()` kuralı: bozuk bar = fiyat ≤ 0, ya da < 0,01, ya da tek barda
|%50|'den büyük hareket. **Son bozuk bardan SONRASI** alınır (aradan bar
silmek boşluk bırakır, göstergeyi yine bozar), ve hiçbir şekilde 2005'ten
öncesi alınmaz. Sonuç: **30/30 hisse kullanılabilir, 145.588 günlük bar**,
en kötü gün −%27, en iyi +%37 — hepsi makul.

`auto_adjust` yalnız **backtest** modunda açık (`fetch(..., gecmis=True)`);
canlı sinyalde ham fiyat kullanılır, ekranda görünen fiyatla aynı olsun diye.

### Tuzak — tablo yoksa salt-okunur bağlantı çöker

Şema yalnızca okuma-yazma bağlantısında kurulur; arayüz salt-okunur bağlanır.
BIST verisi hiç indirilmemiş bir veritabanında `bars_bist` **yoktur** ve sorgu
`CatalogException` verir → Veri Merkezi, indirme düğmesine basılmadan önce
çökerdi. `storage.bist_var(con)` bunu sorar; yoksa boş çerçeve döner.
*Doğrulandı: tablosuz veritabanında 5 ekran + 4 strateji × her bölüm, 0 hata.*

**Maliyet ayrı:** `backtest.bist_cost_for` → spread 10 bp + komisyon 5 bp/yön
= **20 bp gidiş-dönüş** (küresel varlıklarda 1-10 bp). Bu da TAHMİN; kullanıcı
kendi aracı kurumunun oranını yazmalı. Motorların `run_bars`'ı artık
`cost_bp` alabiliyor.

**Ölçüldü:** 30 hisse × (günlük + saatlik) indirme **12 saniye**, 326.135 bar,
ikinci çalıştırma +0 satır (idempotent).

---

## ÖLÇÜ DÜZELTMESİ — yıllık getiri, piyasada geçen süre (24 Eylül 2026)

Kullanıcı: *"senede 2-3 sinyal vermişler, onda da doğru dürüst kazanç yok...
basit bazı şeyleri kaçırıyoruz."* Haklıydı ve **ölçü yanlış olduğu için
göremiyorduk.**

`gelistir.olcu` yalnızca `getiri_%` veriyordu: işlem getirilerinin **toplamı**.
23 yıllık XAUUSD ile 9 yıllık BTCUSD'nin toplamları yan yana konunca devasa ve
kıyaslanamaz bir sayı çıkıyor. Strateji 2.6 için **+%1.245** yazıyordu; yıllık
karşılığı **%8,3** ve al-tut **%16,0** — yani strateji al-tut'un yarısını
kazandırıyordu ve bunu ekranda görmek mümkün değildi.

**Eklenen ölçüler:**

| Ölçü | Ne söyler |
|---|---|
| `yillik_%` | Portföy eğrisinden bileşik yıllık getiri |
| `piyasada_%` | Sermayenin pozisyonda geçirdiği süre (varlık-günü oranı) |
| `islem_yil` | Varlık başına yılda kaç işlem |
| `kos()["al_tut"]` | Aynı havuzun al-tut'u (yıllık + MaxDD), **aynı yöntemle** |

**Tuzak — varlıkların geçmişi eşit uzunlukta değil.** `piyasada_%` ve
`islem_yil` "varlık sayısı × havuz süresi" ile bölünürse yanlış çıkar
(işlem/yıl 2,5 yerine 1,4 gösteriyordu, çünkü havuz süresi en uzun varlığa
göredir). Doğrusu her varlığın KENDİ süresinin toplamı; `kos()` bunu
`havuz = {"varlik_gun", "n_varlik"}` içinde verir ve `olcu(..., havuz)` alır.
*Doğrulandı: elle hesapla birebir aynı — 2,5 işlem/yıl, %47,2 piyasada.*

**Tarama amacı:** `AMACLAR`'ın başına "Yıllık getiri %" eklendi ve varsayılan
oldu; eski toplam "Net kar % (toplam)" adıyla duruyor. Yanlış ölçüyle tarama
yapmak yanlış yere götürür.

**Hemen işe yaradı:** Strateji 2.6'ya trend filtresi eklemek yıllık getiriyi
%8,3 → %5,6 düşürüyor. Toplam getiri ölçüsüyle bu görünmüyordu.

---

## İKİNCİ ÖLÇÜ DÜZELTMESİ — günlük değerleme, portföy ağırlığı, BTC (24 Eylül 2026)

Kullanıcı: *"ne yaptıysak kâra geçen sistem kuramadık, mantık hatamız mı var?"*
Strateji kodunda hata yok (look-ahead yok, fiyatlar gerçek). Ölçüde iki hata vardı:

1. **`perf.daily_equity` kârı/zararı yalnız ÇIKIŞ gününde yazıyordu.** Açık
   pozisyonun düşüşü eğride görünmüyordu; al-tut ise her gün değerleniyordu.
   Artık açık pozisyon her gün kapanıştan değerlenir; günlük getirilerin
   çarpımı işlemin getirisine birebir eşittir. *Doğrulandı: 32 koşu (8 varlık ×
   S2 4s/1g, 2.6-benzeri, EMA 1s) son sermaye farkı 0; MaxDD 32/32'de eskisi
   kadar ya da daha derin.*
2. **`gelistir._portfoy_gunluk` "o gün verisi olanların ortalaması"ydı.** Hafta
   sonu yalnız BTC açık → 402 günde portföy %100 BTC. Artık varlık ilk-son günü
   arasında payını korur, kapalı gün getirisi 0. Yeni varlık başlayınca para
   yeniden eşit bölünür. **Ortak başlangıç ZORUNLU DEĞİL, bilerek:** BIST'te
   DSTKF 2025'te başlıyor, havuzu 1 yıla indirirdi. Ekran havuzun tam olduğu
   tarihi yazar (`havuz["tam_baslangic"]`). *Doğrulandı: el hesabı; tek
   varlıkta eskiyle aynı.* 8 varlık al-tut: %10,9 → **%10,5**.

**BTC hesaplardan çıkarıldı** (kullanıcı: "BTC'ye hiçbir zaman girmem").
`Instrument.hesapta=False`, `instruments.HESAP_KODLARI`: Backtest, Geliştir,
sinyal listesi bunu kullanır. Veri güncellenir, grafikte/ana ekranda görünür.

**Kullanıcı kararı:** her varlığa **eşit para** (oynaklığa göre pay DEĞİL).
Hedef piyasa VİOP; yalnız Brent forex'te. Yedekler: `yedek/*_olcu_duzeltmesi_oncesi.py`,
`yedek/*_btc_oncesi.py`.

## Doğrulanmış olanlar (tekrar test etmeye gerek yok)

- **İdempotentlik:** aynı veri ikinci kez yazılınca `+0 satır`
- **4H hizalaması:** kovalar 00/04/08/12/16/20 UTC; OHLC'si 15dk'dan elle
  hesaplananla birebir aynı
- **ATR ısınması:** ilk 22 bar boş, Wilder yumuşatması
- **Ratchet:** trailing stop asla geri çekilmiyor (0 ihlal)
- **Look-ahead:** 8 enstrümanda da 0 ihlal (4H yönü `valid_from = kova + 4sa`
  damgasıyla `join_asof(backward)`). Backtest'te ayrıca pozisyon bir barın
  kapanışında belirlenip getirisi bir sonraki bardan işliyor
  (`pozisyon.shift(1) * bar_getirisi`)

## Geliştirme motoru (22 Eylül 2026)

Kullanıcı: *"kazandırma oranı yeterli değil, inceleyip artırmaya yönelik
fikirler veren bir motor gerek... programın en güçlü yanı burası olmalı."*
`gelistir.py` stratejiden bağımsız; motordan yalnızca `prepare`,
`hazir_simule(hazir, cfg, tf, bp)`, `ARAMA_UZAYI`, `GOSTERGE_PARAMLARI`
ister. Yeni strateji = bu dört şeyi vermek.

- **Havuz:** seçilen varlıklar tek portföy sayılır (her işlem aynı büyüklükte,
  günlük getiri varlıkların ortalaması). Doğrulandı: havuz tek tek
  `run_bars` sonuçlarıyla birebir aynı, ölçüler elle hesapla uyuşuyor.
- **Aşırı uyum:** her tarama satırı ayar (%70) / kontrol (%30) / **komşu
  ortalaması** ile gelir; sıralama KONTROL'e göredir. Komşu = bir parametre
  bir adım kaydırılınca ayar sonucu; tek başına parlayan nokta tesadüftür.
- **Hız:** kombinasyonlar gösterge parametrelerine göre gruplanır, `prepare`
  grup başına bir kez. Ölçüldü: prepare 1,3 sn / simulate 0,3 sn (9 varlık,
  4 saat, 11 yıl) → 60 kombinasyon ~16 sn.
- **Teşhis bulguları:** kazanma oranı ↔ başabaş oranı (ödül/kayıptan), yön,
  çıkış nedeni, varlık dağılımı, rejim (200 bar ortalamaya uzaklık + 50 bar
  oynaklık dilimleri), dönem bozulması. Bulgu ancak fark `ONEMLI_FARK_BP`'yi
  (5 bp) aşarsa yazılır — ilk sürüm −6,0 bp ile −6,0 bp'yi "zayıf nokta" diye
  gösteriyordu.

## Çözüldü — "enstruman kayitli degil" ve sessiz yanlış varlık (22 Eylül 2026)

Belirti: Kural akışı bir kez `enstruman kayitli degil: XAUUSD` verdi,
yenileyince geçti; tabloda 9 enstrüman duruyordu. **Sebep doğrulandı:**
`charts.get_connection` tek bir DuckDB bağlantısını `st.cache_resource` ile
TÜM oturumlar ve iş parçacıkları arasında paylaşıyordu. DuckDB'de sorgunun
sonucu bağlantının üzerinde durur; iki iş parçacığı aynı anda `execute`
ederse biri ötekinin sonucunu ezer ve `fetchone()` **None** döner. Streamlit
her betik çalışmasını ayrı bir iş parçacığında yürütür (yeniden çalıştırma
eskisi bitmeden başlayabilir; ikinci sekme ayrı bir oturumdur).

**Ölçüm — hata görünenden büyüktü.** 8 iş parçacığı × 400 çağrı, paylaşılan
bağlantıda: 61 görünür hata **ve 56 SESSİZ yanlış sonuç** — `instrument_id`
patlamadan başka bir enstrümanın kimliğini döndürdü (istenen XAUUSD → dönen
4 = BRENT). Yani ekranda hata yerine **başka varlığın barları** XAUUSD diye
çizilebilirdi. Bir tur da `int()` hatası verdi: gelen satır başka bir
sorgunun (`coverage`) satırıydı.

**Düzeltme:** `storage.thread_cursor(con)` — her çağrıya kendi `cursor()`'ı
(~0,3 ms, aynı veritabanı örneğini paylaşır, dosya ikinci kez açılmaz).
`get_connection()` artık bunu döndürür; paylaşılan kök `_root_connection()`
adıyla önbellekte kalır. Aynı yük: **0 hata, 0 sessiz yanlış**.

**İki tuzak (geri almadan önce okuyun):**
1. **Cursor TimeZone'u MİRAS ALMAZ.** Kök `SET TimeZone='UTC'` olsa bile yeni
   cursor işletim sisteminin dilimiyle (Europe/Istanbul) açılır. Ayarlanmazsa
   tüm damgalar 3 saat kayar ve 4H kovaları UTC hizasından çıkar. Bu yüzden
   `thread_cursor` her cursor'da UTC'yi kendisi kurar. Doğrulandı: sonuç kök
   bağlantıyla birebir aynı, ekrandaki giriş barı (19.08 15:00 TR) veritabanı
   UTC 12:00 barıyla eşleşiyor.
2. **Dosya kilidini yalnız KÖK bağlantının kapanması bırakır.** `refresh_data`
   bu yüzden `_root_connection().close()` çağırır; cursor kapatmak yetmez.
   Doğrulandı: 5 cursor açıkken kök kapatıldı, yazma bağlantısı açıldı.

## Bulunan ve düzeltilen veri bozukluğu

**Hayalet (donuk) bar:** piyasa kapalıyken beslemenin son fiyatı tekrar tekrar
yayınlaması. Belirtisi: gün boyu `max(high) == min(low)`, aralık %0,0.
EURUSD 120 gün (2012-14), WTI 51 gün (2013-14), BRENT 4 gün. Silindi.

Neden ölümcül: bu barlarda True Range = 0 → ATR yapay olarak çöker → Chandelier
stopları aşırı daralır → piyasa açılınca sahte sinyal.

**Yanlış alarm dersi:** kalite ölçütünün ilk sürümü %14-19 "eksik gün" verdi.
Doğrulanınca neredeyse hepsinin **Pazar** olduğu görüldü (forex Pazar 22:00
UTC'de açılır, o gün doğal olarak ~8 bar). Ölçüt hafta içine kısıtlandı.
Gerçek eksik oran %0-1,5 (tatiller). *Alarma inanmadan önce doğrula.*

---

## Veri güncellemesi takılma koruması (21 Eylül 2026)

`dukascopy_python` isteği `requests.get(...)` ile **zaman aşımsız** atıyor;
bağlantı bir kez asılı kalırsa güncelleme sonsuza kadar bekler. (Kullanıcının
o günkü "güncellemede kalıyor" şikâyetinin asıl sebebi başlatıcı hatasıydı —
bkz. `docs/KURULUM_VE_TASIMA.md` — ama bu açık da gerçekti.) `ingest.py`'de:
kütüphanenin modül içi `requests` adı zaman aşımlı sarmalayıcıyla değiştirildi
(bağlanma 8 sn, okuma 25 sn; global `requests` değişmez), yeniden deneme 7 → 2,
`backfill_all(sure_sn=...)` toplam süre sınırı (parçalar ARASINDA kontrol, yarım
yazma yok; dolunca kalan varlıklar atlanır, program eldeki veriyle açılır).
BASLAT/UZAKTAN `--sure 150`, arayüzdeki düğme 120 sn. Doğrulandı: cevap
vermeyen sunucuda istek 2,0 sn'de `ReadTimeout` ile koptu (deneme için okuma
2 sn); süre sınırı kalan 8 varlığı atladı; normal güncelleme ~15 sn.

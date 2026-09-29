# ui/ — arayüz (Streamlit)

> Bu dosya, Claude bu klasördeki bir dosyaya dokunduğunda kendiliğinden okunur.
> Grafik ve ekran kararlarının gerekçeleri burada; değiştirmeden önce okuyun.

---

## Ekran ölçüsü ve üst boşluk (21 Eylül 2026)

- Kullanıcının ekranı **1920×1200, Windows %125 ölçek** → tarayıcıda ~1536 px
  genişlik. "Küçük" görünmesi gereken şeyleri buna göre boyutla; %100'de
  küçük duran 13 px yazı onda "kocaman" görünüyor.
- **Üst boşluk yok:** `theme.global_css()` her sayfada `app.py`'den (parola
  ekranı dahil) basılır: Streamlit üst çubuğu 0 yükseklik, ana kap üst dolgu
  1,1 rem, kenar çubuğu başlığı daraltıldı. Çubuk 0 olunca içindeki "kenar
  çubuğunu AÇ" düğmesi -14 px'e kayıyordu → `position:fixed` ile sabitlendi
  (doğrulandı: gerçek tıklamayla açılıyor). `.streamlit/config.toml`
  `toolbarMode = "minimal"` → Deploy düğmesi ve geliştirici menüsü yok.
- **Strateji sayfası başlığı tek satır:** numara rozeti + ad solda, bölüm
  menüsü aynı satırda sağda. Kaynak/varyant satırı yalnızca Özet ve Kurallar'da.

---

## GELİŞTİRME TUZAĞI — modül önbelleği

**İkinci tuzak — aynı portta iki kopya (21 Eylül 2026):** Windows 8503'e iki
Streamlit kopyasının birden oturmasına izin verebiliyor. Claude'un unutulan
deneme sunucusu (`--server.headless true` olan) + kullanıcının BASLAT.bat'ı
aynı anda dinliyordu; tarayıcı ESKİ kopyaya bağlandı, yeni `app.py` eski
`theme` modülüyle çalıştı → `no attribute 'global_css'`. Önlem: BASLAT.bat
8503 doluysa açmaz ve "önce eski pencereyi kapatın" der. Claude: deneme
sunucularını 8505'te aç, iş bitince kapat, `Get-CimInstance Win32_Process`
ile streamlit kopyası kalmadığını doğrula.

`app.py` değişince Streamlit yeniden yükler, ama **`ui/` ve `src/` altındaki
içe aktarılmış modüller bellekte kalır.** CSS veya gösterge değiştirip "hiçbir
şey olmadı" derseniz sebebi budur. Sunucuyu yeniden başlatın. Bu bizi iki kez
yanılttı (`indicators.MACD_DEFAULT` ve `theme.css`).

---

## Modüller

```
theme.py        Renk paleti + neon CSS (tek görsel dil kaynağı)
home.py         Ana ekran: başlık, fiyat şeridi, ikon menü
charts.py       Grafikler ekranı (eski app.py'nin tamamı)
strategies.py   Stratejiler: liste → özet → menü (Sinyaller, BIST 30, Backtest, Kurallar)
backtest.py     ORTAK backtest paneli: Backtest menüsü + Stratejiler > Backtest
                (Tek backtest | Canlı parametre ayarı + Farklı kaydet)
akis.py         Kural akışı ekranı: SVG şema + mum grafiği, eş zamanlı animasyon
gelistir.py     Geliştir ekranı: teşhis (zayıf nokta kartları) + parametre
                taraması + "bunu dene" karşılaştırması (hesap src/gelistir.py'de)
auth.py         Parola kapısı (yalnız uzaktan erişimde devrede)
veri.py         Veri Merkezi: tazelik, tek tıkla güncelleme, kapsam, kalite
placeholder.py  Henüz yapılmamış ekranlar ("yakında")
```

---

## Ekran yapısı (22 Ağustos 2026)

Ana ekran + ikon menü kuruldu. Yönlendirme adres çubuğundaki **`?ekran=`**
parametresiyle: `home`, `grafikler` ve `stratejiler` (çalışan ekranlar),
`piyasalar`, `yaratma`, `backtest`, `veri`. Tanımsız değer "bilinmeyen ekran"
sayfasına düşer.

Menü kutucukları **Streamlit düğmesi değil, `<a>` bağlantısı**. Sebep: düğmenin
iç düzenine (SVG ikon + başlık + açıklama, kare oran, neon çerçeve) müdahale
edilemiyor. Bağlantı ile tam görsel denetim bizde; tarayıcı ileri/geri tuşları
ve yer imleri de bedava geliyor.

**Kenar çubuğu:** ana ekranda hiçbir şey yazılmaz, Streamlit de boş çubuğu
çizmez → giriş ekranı tertemiz. İç ekranlar kendi denetimlerini yazar, çubuk
kendiliğinden belirir. Ayrı bir aç/kapa bileşeni yazmaya gerek yok.

**Yeni ekran eklerken:** `ui/` altına dosya, `home.MENU` listesine satır
(`hazir=True`), `app.HAZIR` sözlüğüne kayıt. Başka yeri değiştirmeye gerek yok.

**Strateji kayıt defteri** (`strategies.BASE`): motor yapısı için bkz.
`src/finans_cortex/CLAUDE.md`. Backtest paneli hangi stratejiyle çalıştığını bu
kayıttan okur; önbellekli fonksiyonlara motor MODÜLÜ değil temel strateji
ANAHTARI (str) geçer — modül nesnesi hash'lenemez.

**Stratejiler ekranı üç katmanlı** (kullanıcı "ekran çok karışık" dedi):
`?ekran=stratejiler` → açıklamalı kart listesi (`<a>` bağlantı);
`&strateji=ema10` → özet; üstteki `st.segmented_control` menüsü → Sinyaller,
BIST 30, Backtest, Kurallar (`&bolum=`). Strateji İÇİ menü bilerek bağlantı
DEĞİL: bağlantı sayfayı yeniden yükler ve kenar çubuğu ayarları sıfırlanır.
Yeni strateji: `STRATEJILER` listesine kart, `_PAGES` sözlüğüne sayfa.

**Strateji 3 (23 Eylül 2026):** `chandelier_ha` anahtarıyla `BASE`'e eklendi,
motoru Strateji 2 ile AYNI modül (`rf_kullan=False`). Parametre panelinde
Range Filter denetimleri **hiç çizilmez** — kullanıcı "kaldırdım ama bir şey
değişmedi" sanmasın diye; `param_widgets` bunu `defaults.rf_kullan`'a bakarak
yapar ve değeri olduğu gibi geri verir. `strategy_store.CONFIGS`'e de satır
eklendi, yoksa 3'ün varyantları yüklenemezdi.

**Tuzak — `BASE` kaydında eksik alan (23 Eylül 2026):** Strateji 3'ün kaynak
videosu yok, `video`/`video_ad` alanları da yoktu; strateji sayfası bunları
koşulsuz okuyordu → `KeyError: 'video_ad'`, ekran hiç açılmadı. Artık video
satırı **isteğe bağlı** (`base.get("video")` yoksa yalnız `kaynak` yazılır).
Yeni bir temel strateji eklerken kaydın alanlarını mevcut biriyle karşılaştırın
(`set(BASE["heikin_range"]) - set(BASE[yeni])`). Denetim: her strateji × her
bölüm `streamlit.testing.v1.AppTest` ile çizdirilip exception aranır — 25
kombinasyon, tarayıcı gerekmiyor, ~1 dakika. Ekran ekleyen/değiştiren her
işten sonra bu tarama yapılmalı.

---

## Backtest paneli

**Tek panel, iki kapı** (`ui/backtest.py`): ana ekrandaki Backtest menüsü
(`render`) ve Stratejiler > strateji > Backtest (`panel`). Kullanıcı önce
"Stratejilerde backtest yapma, Backtest menüsüne koy, ben kontrol ederim,
zaman aralığı seçebileyim", hemen sonra "Stratejilerde de kalsın / ikisini
birleştirelim" dedi. Kurallar: kendiliğinden ÇALIŞMAZ (düğme); dönem iki
tarihle (+ hızlı seçim 1 ay…tümü); ayar değişince eski sonuç "önceki ayarlara
ait" uyarısıyla kalır; sonuçlar sekmelerde (Sonuç, İşlemler, Grafik, Sermaye
eğrisi, Karşılaştırma). Hüküm kutusu tarih aralığını açıkça yazar — kullanıcı
"zarar diyor ama son işlemler kârda" diye şaşırmıştı. Parametre denetimleri
tek yerde: `strategies.param_widgets()`. `strategies` → `backtest` importu
fonksiyon içinde (döngüsel import).

Strateji 1 panelinde parametreler (EMA, onay barı, R hedefi, stop penceresi,
break even, EMA çıkışı, gün içi) kenar çubuğundan değiştirilir. İşlem listesi
kapital ($) + kaldıraçla kârda/zararda yüzdesi, toplam kâr, toplam zarar ve net
sonuç hesaplar. Kapital her işlemde aynı (bileşik değil), spread dahil.
Rakamlar elle hesapla birebir doğrulandı.

**İşlem incelemesi** (17 Eylül 2026, kullanıcı: "ne zaman al vermiş ne zaman
sat vermiş, nasıl kazanmış nasıl kaybetmiş — hem tablo hem grafik").
Backtest > **İşlemler** sekmesinde tablo ile grafik BAĞLI: bir satıra
tıklayınca altında o işlemin grafiği açılır (giriş/çıkış, stop, hedef,
işlemin yolu, pozisyonun açık olduğu süre gölgeli) + sonuç, R ve **bar içi
en iyi/en kötü ara durum** (MFE/MAE — "stop biraz geniş olsa kurtulur
muydu"). Gösterim: son 10 işlem / **tüm işlemler** / iki tarih arası (TR
saati, giriş zamanına göre); üstüne yön (AL/SAT) ve sonuç (kazanan/kaybeden)
filtresi. Tabloda işlem no, süre ve **kümülatif $** var. Seçim anahtarı
filtreyi de taşır, yoksa filtre değişince satır numarası başka bir işleme denk
gelirdi. **Grafik** sekmesi "son N gün" değil: pencere boyu + pencerenin
bitişi kaydırıcısı ile tüm dönemde gezilir (4.000 barda kırpılır, kırpma
ekranda yazar). **Sermaye eğrisi** sekmesinde işlem başına kâr/zarar
çubukları var.

**Canlı parametre ayarı + Farklı kaydet** (panelde ikinci mod). Kaydırıcılar
oynadıkça net kâr/zarar, getiri, işlem, kazanan, kâr faktörü, düşüş ANINDA
değişir; yanında başlangıç değerlerine göre fark ve üç eğri (şimdiki /
başlangıç / al-tut). Hız: `st.fragment` (yalnız o bölüm yeniden çalışır) +
ham barlar `st.cache_resource`'ta (cache_data her okumada pickle kopyası
çıkarırdı) + `ema.run_bars`. **Aşırı uyum kontrolü:** aralık %70 ayar / %30
kontrol bölünür, yeniden simülasyon yok (işlemler giriş zamanına göre
bölünür). "Farklı kaydet" → `config/stratejiler.json`: varyant = temel +
parametreler; listede temelin altında "1.1, 1.2" (numara en büyük+1, silinen
numara tekrar kullanılmaz), Sinyaller/BIST 30/Backtest kendi parametreleriyle
çalışır, strateji sayfasında "Stratejiyi yönet" ile silinir. JSON seçildi
çünkü hafif taşımada `data/` kopyalanmıyor, `config/` gidiyor.

**İki piyasa, tek panel (23 Eylül 2026):** üstteki **Piyasa** seçicisi
"Küresel 8" (BTC hariç, `HESAP_KODLARI` sayısı) / "BIST 30". Backtest ve Geliştir aynı seçiciyi kullanır. BIST
seçilince: kodlar `bars_bist` kapsamından gelir, barlar ayrı tablodan okunur,
maliyet `bist_cost_for` (20 bp) olur, 15dk teyidi devre dışı kalır (BIST'te
15dk geçmiş yok). BIST'te yalnız **günlük ve 1 saat** var; başka bir zaman
dilimi seçiliyse panel bunu yazıp durur. Veri yoksa "Veri Merkezi'nden
indirin" der — çökmez.

**Tuzak:** BIST hisseleri `instruments` kayıt defterinde YOK (bilerek).
Grafikte hafta sonu gizleme `get_instrument(code).session` okuyordu →
`KeyError: bilinmeyen enstruman: AKBNK`. `_seans(code, piyasa)` bunu çözer.
Aynı hata zinciri dört fonksiyonda vardı (`_section_chart`, `_trade_list`,
`_trade_zoom`, `_section_trades`) — hepsi `piyasa` taşıyor artık.

**Zaman dilimi tuzağı (24 Eylül 2026)** — kullanıcı: *"mevcut veriler
backtest yapmıyor."* İki ayrı hata çıktı, ikisi de aynı kökten:

1. BIST'te yalnız **günlük ve 1 saat** var. Strateji 2'nin varsayılanı 4 saat
   olduğu için BIST seçilince panel uyarı yazıp **duruyordu**; kullanıcının
   kenar çubuğundan dilim değiştirmesi gerektiğini bilmesi gerekiyordu.
2. Panel BIST'te "1 gün / 1 saat" sunuyordu, ama **Strateji 1 gün içi bir
   stratejidir ve günlük barla çalışmaz** → motor `KeyError: '1d'` verdi.

Çözüm ikisinde de aynı: panel kendi dilimini seçer (kenar çubuğuna dokunmaz)
ve seçenekler **stratejinin desteklediği dilimler ∩ BIST'te olanlar**
kesişimidir. Kesişim boşsa açıkça "bu strateji BIST'te çalıştırılamıyor" der.
Aynı kural `ui/gelistir.py`'de de uygulandı. *Doğrulandı: 3 strateji × 2 ekran,
0 hata; gerçek tarayıcıda Strateji 1 / AKBNK / 1 saat 202 işlem çizdi.*

**Kilit mesajı:** `refresh_bist` yazma bağlantısını açamazsa (programın
başka bir kopyası dosyayı tutuyorsa) ham DuckDB IO hatası yerine Türkçe bir
açıklama verir — "başka bir pencere açık olabilir". Doğrulandı: ikinci bir
salt-okunur bağlantı açıkken mesaj çıkıyor. Aynı koruma `refresh_data`'da
yok; oraya da gerekirse eklenir.

**Sinyaller:** BIST'te seans kapalıyken açık sinyal görünmez, "Bugün sinyal
verenler" filtresi son kurulumları gösterir.

---

## Kural akışı sekmesi (20 Eylül 2026)

Kullanıcı: *"alım satım kurallarını akış şeması halinde göster; seçtiğim gerçek
bir sinyalde kurallar nasıl işlemiş animasyonlu görmek istiyorum"*, ve *"akış
şeması genel olsun, her stratejide çalışsın"*. Ortak dil
`src/finans_cortex/akis.py`'de; bu ekran stratejiyi tanımaz.

- Şema **o anki ayarları** gösterir: kapalı seçenekler (hedef, break even,
  geri çekilme, fitilli mum çıkışı) şemada hiç çizilmez; parametre değişince
  kutular da değişir.
- Çizim elle üretilen **SVG + CSS `animation-delay`** — JavaScript yok,
  yeniden çalıştırma yok, uzaktan bağlantıda da akıcı. "Oynat"a basınca
  sarmalayıcının sınıfı değişir (`r0`, `r1`…), tarayıcı animasyonu baştan
  oynatır. Hız: Yavaş/Normal/Hızlı.
- Renkler: geçti = yeşil, kural saglanmadı / zarar = turuncu, sırası
  gelmedi = soluk. "hayır" dalları sağda küçük kutular olarak durur;
  yalnızca o dala düşülmüşse yanar. Doğrulandı: kaybeden işlemde sonuç
  kutusu turuncu, kazananda yeşil.
- Sinyal listesi: seçilen varlıkta **son 20 işlem** (en yenisi üstte),
  `GUN` sözlüğü bar boyutuna göre ne kadar geriye bakılacağını söyler
  (15dk 45 gün … 1g 2500 gün). Açık işlem "ACIK" diye görünür.
- **Sıkıştırma (21 Eylül 2026)** — kullanıcı: *"kutular çok büyük, küçük
  adımları birleştir, ekranın üstü kalabalık, yan taraf iyi kullanılmamış,
  şemanın büyük kısmını ekranda göreyim"*. Yapılan: iki sütun (solda varlık +
  sinyal + hız/Oynat + seçili işlemin kartı + numaralı adım listesi; sağda
  şema), kutular iki satırlık (400×50, başlık + gerçek değer; değer yoksa
  parametre; tamamı fareyle ipucunda), SVG en fazla ~1:1 çizilir (büyümez).
  Aynı gün ikinci tur ("hâlâ dev gibi"): kutu **320×38**, başlık 11,5 px,
  değer 10 px, SVG **sabit piksel genişlik** (kolona göre büyümez), adım
  listesi 11 px (`!important` şart — Streamlit markdown `li` puntosunu
  dayatıyor).
  Motorlarda küçük adımlar birleşti: Strateji 2 11 → **6** kutu, Strateji 1
  10 → **7** kutu. Doğrulandı: 1280×720 dizüstü ekranında şemanın tamamı
  denetimlerle birlikte sığıyor. Eski hâller `yedek/*_sikistirmadan_once.py`.
- Geri çekilme girişinde animasyon "kurulumdan N bar sonra EMA'ya dönüş" diye
  yazar.
- **Mum grafiği (21 Eylül 2026, akşam)** — şema "havada duruyordu":
  "Chandelier 15:00'te yandı" yazıyor ama o bar görünmüyordu. Düzen değişti:
  denetimler + işlem kartı **üstte tek satır**, altında **solda şema (452 px),
  sağda işlemin mum grafiği (~590 px)**, adım listesi "Adımlar (yazılı)"
  katlanır kutusunda. (Üç sütun denendi: şema 300 px'e düşüp okunmaz oldu.)
  Grafik de elle SVG + CSS; motorun `Isaret`lerini (ok / nokta / çizgi /
  bölge) kutusuyla AYNI saniyede gösterir. Tek zaman tablosu
  `zamanlama()` hem şemayı hem grafiği sürer: iki kutu arasında grafikte
  çok bar varsa (giriş → çıkış) o geçişe ek süre verilir (Normal'de ≤3 sn),
  mumlar o sürede soldan sağa akar, stop çizgisi onlarla uzar. Pencere
  ilk işaretten 20 bar önce → son işaretten 8 bar sonra, en fazla 600 mum.
  Doğrulandı: 2 strateji × 9 varlık × 5 ayar = 900 işlem hatasız çizildi.
- **Giriş/çıkış belirginliği + Adım adım (21 Eylül 2026, gece)** —
  kullanıcı: *"nerede girdik nerede çıktık hiç anlamıyorum, neden girdik neden
  çıktık belli olsun; hıza adım adım seçeneği, space'e bastıkça ilerlesin"*.
  - `neden` taşıyan `Isaret` (nokta) = ANA OLAY: grafiğin üst bandında etiket
    kutusu ("GIRIS AL · fiyat · saat" + "neden: …"), dikey kesikli çizgi,
    halkalı büyük nokta. Giriş rengi yön (AL yeşil / SAT kırmızı), çıkış
    rengi işlemin sonucu. Strateji 2 çıkışında, çıkışı tetikleyen ters CE/RF
    okları da çizilir.
  - Hız listesinde **"Adim adim"**: ◀ / "Ileri ▶" düğmeleri + üstte o anki
    adımın şeridi (numara, kural, gerçek değer). O ana kadarki adımlar
    sabit, yalnız yeni adım canlanır; gelecek kutular soluk iskelet, gelecek
    mumlar HİÇ çizilmez (`adim_kesiti` + `sinir`). Sinyal/varlık değişince
    1. adıma döner.
  - **Klavye:** Streamlit'in `shortcut="Space"` düğme kısayolu denendi ve
    BIRAKILDI — "Adim adim" seçilince imleç seçim kutusunda kalıyor,
    Streamlit yazı alanı odaktayken kısayolu yok sayıyor, boşluk listeyi
    açıyordu. Yerine `st.html(..., unsafe_allow_javascript=True)` ile küçük
    bir dinleyici (`_TUS_DINLEYICI`): yakalama aşamasında boşluk / → =
    İleri, ← = geri; kapalı seçim kutusundaki imleci bırakır. Doğrulandı
    (imleç Hız kutusundayken boşluk → adım 2, liste açılmadı; → / ← doğru).
    **Test tuzağı:** önizleme panelinin `key` eylemi boş tuş adı (key="",
    keyCode 0) gönderiyor; gerçek klavyeyi taklit etmez — test için
    `KeyboardEvent('keydown', {key:' ', code:'Space', keyCode:32})`.
- **"Oynat" ikinci basışta oynamıyordu (eski hata, bulundu ve düzeltildi):**
  Streamlit aynı SVG öğesini yeniden kullanıyor; yalnız sınıf/gecikme
  değişince tarayıcı bitmiş CSS animasyonunu baştan başlatmaz. Çözüm: her
  basışta animasyon ADI değişir (`t0`/`t1` sınıfı → `dcin`/`dcin_`).
  Doğrulandı: basış başına yeni animasyon 0'dan başlıyor. **Test tuzağı:**
  önizleme paneli gizliyken tarayıcı animasyon saatini dondurur
  (`visibilityState = hidden`); ölçmek için `document.getAnimations()` ile
  `currentTime` elle sarılır.

---

## Geliştir sekmesi (22 Eylül 2026)

Kullanıcı: *"kazandırma oranını artırmaya yönelik fikirler veren bir motor...
kural akışı gibi ayrı bir sekmeye ekleyebilirsin."* Hesap
`src/finans_cortex/gelistir.py`'de; bu ekran yalnız sorar ve gösterir.

- Üstte varlıklar (varsayılan 9'u da), dönem, amaç. İki sekme: **Teşhis**
  (zayıf nokta kartları, şiddete göre renkli; parametre önerisi olan bulguda
  "Bunu dene" → şimdiki/önerilen ayar tüm-ayar-kontrol bölümleriyle yan yana)
  ve **Parametre taraması** (seçilen parametreler, en fazla kombinasyon,
  ilerleme çubuğu, kontrol bölümüne göre sıralı tablo).
- **Hiçbir şey kendiliğinden çalışmaz** (düğme): tarama dakikalar sürebilir.
- Beğenilen ayar "Farklı kaydet" ile varyant olur (Backtest panelindeki
  kayıt yeriyle aynı: `config/stratejiler.json`).
- Taranacak parametre listesi motorun `ARAMA_UZAYI`'ndan gelir; gösterge
  parametreleri yıldızla işaretlenir (taramayı yavaşlatır).

**Sonuçlar paneli (23 Eylül 2026)** — kullanıcı: *"bu rapordan çıkarılacak
sonuçlar olmalı, kullanıcı sonuçlardan stratejiyi güncelleyebilmeli."* Teşhis
bulgularının hepsi rapordu, azı uygulanabilirdi: Strateji 2'de 5 bulgunun 4'ü
çıkmaz sokaktı. Yapılan:

- Kartların altındaki tek tek "Bunu dene" düğmeleri kalktı; yerine **Sonuçlar**
  bölümü geldi: parametre önerisi taşıyan her bulgu bir onay kutusu, birkaçı
  birden işaretlenip **TEK seferde** denenir (tek tek denemek "ikisi birlikte
  ne yapar" sorusunu cevaplamıyordu). Etiketler ham alan adı değil ekrandaki
  adıyla yazılır (`SAT islemleri: kapali`) — `strategies.param_labels` +
  `param_text` üzerinden, tek kaynak.
- Aynı parametreye iki farklı değer önerilirse uyarı çıkar; zaten öyle ayarlı
  olanlar "bir şey değiştirmez" diye yazılır; seçim değişip de eski
  karşılaştırma duruyorsa "önceki seçime ait" uyarısı çıkar (Backtest
  panelindeki "önceki ayarlara ait" kuralının aynısı).
- Kaydetme iki kapılı: **kayıtlı varyant** üzerinde çalışılıyorsa "'X'
  stratejisini güncelle" (üzerine yazar, yeni kayıt açmaz), her durumda
  "Farklı kaydet". **Temel stratejiler (1 ve 2) güncellenemez** — onlar
  koddaki varsayılanlar, kaynak videonun kuralları; üzerine yazılırsa "video
  böyle diyordu" dayanağı kaybolur. Ekranda bunu söyleyen bir satır var.
- Hiçbir bulgunun karşılığı yoksa panel bunu açıkça yazar ("yeni bir kural
  yazılması gerekir"), boş kutu göstermez.
- **Sonraki adım (kullanıcıyla konuşuldu, 23.09.2026):** panelin yanına bir
  **yazı kutusu** — kullanıcı serbest yazar, yapay zekâ parametre önerisine
  çevirir, kullanıcı onaylar, aynı karşılaştırma/kaydetme akışına düşer.
  Karar: yapay zekâ **kod yazmaz**, yalnız önerir; internet/anahtar yoksa kutu
  kapanır, düğmeler çalışmaya devam eder. Şimdilik yapılmadı.

**Çok zaman dilimli kural — ekranların sorumluluğu (23 Eylül 2026):** Strateji
2'nin `onay_15m` kuralı 15 dakikalık veriyi de ister. Ekranlar bunu **yalnız
gerekiyorsa** yükler, çünkü 9 varlıkta 15dk veri 2,5 milyon satırdır ve
kullanıcının kuralı "programı yavaşlatacak yapılardan kaçınalım". Kural:
`cfg.onay_15m` kapalıysa **hiç okunmaz**. Geliştir ekranında `_yardimci()`
ayrıca kullanıcının onu *denemek* istediği durumu da yakalar (Sonuçlar'da
işaretlenmiş ya da taramaya konmuş) — yoksa motor "15dk veri verilmedi" diye
hata yükseltirdi. `ortak` demeti artık 7 elemanlı (sonuncu `yardimci`).

**Test tuzağı:** bu panelin onay kutuları tarayıcı otomasyonuyla tıklanamadı
(görünmez `<input>`, üstünde etiket katmanı; programatik `.click()` de geçmedi).
Doğrulama `streamlit.testing.v1.AppTest` ile yapıldı — gerçek tıklamayı sunucu
tarafında çalıştırır: "Teshis et" → 3 kutu → ikisi işaretle → "Secilenleri
dene" → karşılaştırma tablosu + her iki kaydetme düğmesi, exception yok.

## Grafik kararları ve gerekçeleri (değiştirmeden önce okuyun)

- **Mumlar yeşil/kırmızı** (kullanıcı referans görsel verdi). Kenar çubuğunda
  "Ayrık" seçeneği mavi/kırmızı — yeşil-kırmızı en yaygın renk körlüğünde
  ayırt edilemez.
- **Rozetler:** büyük harf B/S = MACD, küçük harf b/s = Chandelier. Boyut +
  harf büyüklüğü iki ayrı ayırt edici kanal.
- **Çakışma önleme:** yakın rozetler dikey kademeye ayrılır, gizlenmez.
- **Yoğunluk anahtarı:** sinyal sayısı 80'i geçince rozet yerine üçgen işaret.
  15dk/1 ay = 257 sinyal; rozet olarak fiyatı tamamen örtüyordu.
- **Çift eksen YOK** — 4H yön ve MACD ayrı panellerde.
- **Performans tuzağı:** `fig.add_annotation()` tek tek çağrılırsa plotly her
  seferinde tüm layout'u doğruluyor → 257 rozet **13,8 saniye**. Toplu
  `update_layout(annotations=[...])` ile **0,23 saniye**. Bunu geri almayın.
- **Saat dilimi:** veri UTC saklanır, ekranda **Türkiye (UTC+3)** gösterilir
  (anayasa 2.2). Çevrim yalnızca görüntüleme anında yapılır — hesap ve 4H kova
  hizalaması UTC'de kalır, yoksa kovalar 00/04/08... hizasından çıkardı.
  Kenar çubuğundan UTC'ye geçilebilir. *Not: günlük bar TR saatinde 03:00
  görünür, çünkü kova UTC gününe göre tanımlı.*
- **Eksen etiketi:** gün + saat:dakika (`%d.%m<br>%H:%M`). Günlük dilimde
  yalnızca tarih.
- **BTC hafta sonu:** `rangebreaks` enstrümanın `session` alanına bağlı; 7/24
  varlıkta boş (bkz. `src/finans_cortex/CLAUDE.md`).
- **Gösterge sinyali işaretleri:** mumun altına/üstüne küçük üçgenler.
  Strateji 1'de `kurulum` (EMA'nın iki kapanış koşulunun tamamlandığı bar),
  Strateji 2'de `ce_sig` / `rf_sig` (hangi göstergenin ne zaman yandığı).
  Böylece "bu sinyal neden işleme dönüşmedi" görülebiliyor. Kayıt defterinde
  `isaretler` alanı; 600 bardan geniş pencerede çizilmez (kalabalık olmasın).
- **Arayüz testi:** 9 enstrüman/zaman dilimi kombinasyonu, exception yok.

---

## Veri tazeliği — sık karşılaşılan sorun

**Arayüz yalnızca OKUR; veritabanını kimse kendiliğinden güncellemez.** Kullanıcı
bir kez 8 gün eski fiyata bakıp güncel sandı. Bunun için dört önlem var:

1. `BASLAT.bat` / `UZAKTAN.bat` arayüzü açmadan önce `scripts/backfill.py`
   çalıştırır (artımlı güncelleme ~16 saniye). Atlamak için: `/hizli`
2. **Veri Merkezi ekranı** (`?ekran=veri`, ana menüden tek tık) — güncelleme
   düğmesi, tazelik göstergesi, varlık bazında kapsam, kalite denetimi
3. Grafikler ekranının kenar çubuğunda ve Stratejiler > Sinyaller bölümünde
   **Verileri guncelle** düğmesi
4. En yeni bar 3 günden eskiyse ekranda sarı uyarı çıkar (eşik 3 gün, çünkü
   hafta sonu piyasa kapalı — Cuma kapanışından sonra 2 gün gecikme normaldir)

**Tazelik göstergesi (20 Eylül 2026):** ana ekranda başlığın sağında küçük
bir rozet — `● Veri: 20.09 22:45 - 31 dakika önce` — ve Grafikler ekranının
kenar çubuğunda güncelle düğmesinin hemen altında aynı satır. Rozet Veri
Merkezi'ne **bağlantıdır** (bayatsa sarıya döner ve "güncelleyin" der), yani
"veri eski" görüldüğü anda tek tıkla güncelleme ekranı açılır. Tek kaynak:
`charts.freshness()` / `charts.age_text()` — üç ekran aynı cümleyi kurar.

**Veri Merkezi (20 Eylül 2026)** kullanıcının sorusuyla doğdu: *"programı
uzaktan başlattık diyelim, verileri güncelleyecek bir tuş var mı?"*
`ui/veri.py`: son bar + yaş + toplam bar + dosya boyutu, büyük **Verileri
guncelle** düğmesi (hata olursa mesajı ekranda), varlık bazında kapsam tablosu
(ilk/son bar, yaş, bar sayısı) ve isteğe bağlı **kalite denetimi**
(`quality.report`, ~1 sn, yalnızca okur — silme yok). Güncelleme **uzaktan
bağlıyken de çalışır**: düğmeye işteki tarayıcıdan basılır, indirme ev
bilgisayarında olur. Doğrulandı: uzaktan tetiklenen güncelleme 1.000 bar
ekledi, yaş 2,9 gün → 15 dakikaya düştü. Güncelleme öncesi salt-okunur DuckDB
bağlantısı kapatılır (`refresh_data()`).

**Bağlantı iki katmanlı (22 Eylül 2026):** `charts.get_connection()` artık
paylaşılan bağlantıyı DEĞİL, her çağrıya `storage.thread_cursor` ile açılan
kendi kopyasını döndürür — paylaşılan tek bağlantı eş zamanlı kullanılınca
sorgular birbirinin sonucunu eziyordu ("enstruman kayitli degil: XAUUSD" ve
daha kötüsü sessizce yanlış varlık). Paylaşılan kök `_root_connection()`;
`refresh_data()` dosya kilidini bırakmak için **kökü** kapatmalı, cursor
kapatmak yetmez. Gerekçe ve ölçümler: `src/finans_cortex/CLAUDE.md`.

**Parola kapısı** (`auth.py`): `app.py`'de yönlendiriciden ÖNCE çağrılır;
yalnızca `FINANS_ERISIM` ortam değişkeni varsa devrede. Ayrıntı:
`docs/KURULUM_VE_TASIMA.md`.

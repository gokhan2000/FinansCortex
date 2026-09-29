# Strateji geçmişi ve sıradaki adımlar

> Denenen her stratejinin özeti, bulgular ve açık kararlar. Ayrıntılı ölçümler
> ilgili raporlarda (bkz. `docs/README.md`). Yeni strateji denendiğinde buraya
> bir bölüm eklenir.

---

## Chandelier Exit (Ağustos 2026): ELENDİ

### Tek başına 15dk'da kullanılamaz

11 yıl, 8 enstrüman ölçümü (Normal profil, ATR 22 / çarpan 3.0):

| | 15dk | 4H |
|---|---|---|
| Sinyal/ay | 92-111 | 6,3-7,5 |
| Pozisyon süresi | ~5 saat | ~3 gün |

Günde 4-5 gidiş-dönüş işlem; spread+komisyon sonrası taşınamaz.

### Asıl bulgu: yön değişimi bar başına sabit

Sinyal/bar oranı: EURUSD %5,19 (15dk) vs %5,11 (4H); XAUUSD %4,54 vs %4,62.
**Chandelier'ın yön değiştirme olasılığı bar boyutundan bağımsız ~%5.**
4H'ın sakin olması göstergenin trendi daha iyi görmesinden değil, 16 kat yavaş
örneklemesinden. → Parametre oynayarak 15dk düzelmez.

### Denenen çözüm ve sonucu

**İlk deneme başarısız:** 4H yönüyle aynı taraftaki *her* 15dk sinyalini almak.
8 enstrümanda da tam **2,1× azalma** çıktı — bağımsızlığın imzası (50/50 × 50/50).
Filtre yazı-turadan fazla bilgi katmıyordu.

**Düzeltme:** bir 4H trend bacağı boyunca yalnızca **İLK** hizalı 15dk sinyali
(`leg` mantığı). Sonuç: ayda 5,3-6,1 giriş, ~17× azalma. Frekans çözüldü.

**OLUMSUZ BULGU:** 15dk zamanlaması giriş fiyatını **kötüleştiriyor**.
8 enstrümanda da negatif: −4,3 bp (EURUSD) ile −23,6 bp (BRENT) arası,
işlemlerin yalnızca %20-27'sinde daha iyi fiyat. Mekanizma: 15dk BUY sinyali,
yukarı hareket zaten olduktan sonra oluşuyor → güçlenmiş fiyattan alıyorsunuz.

### Backtest sonucu

Tam rapor: `docs/BACKTEST_SONUCLARI.md`. Özet:

| | Maliyetsiz Sharpe | Maliyetli Sharpe |
|---|---|---|
| naive (4H kapanışından gir) | **0,00** | −0,06 |
| timed (15dk beklet) | **−0,02** | −0,12 |

**Sıfır maliyette bile ortalama Sharpe sıfır.** Strateji komisyona yenilmiyor;
kaybedecek kenarı hiç yok. Ortalama maksimum drawdown −58%, WTI'de −93%.

Öldürücü ayrıntı — long/short ayrımı:
- **Short tarafı 8/8 enstrümanda zarar** (−15,6% ile −87,4% arası)
- **Long tarafı 8/8 enstrümanda al-ve-tut'tan kötü** (XAUUSD 240% vs 288%)

Yani metallerdeki "başarı" sadece boğa piyasasının bir kısmını yakalamak, üstelik
hiçbir şey yapmamaktan daha kötü. "Giriş fiyatı 4-24 bp kötüleşiyor" sorusu da
böylece kapandı: timed, naive'den her ölçüde daha kötü.

---

## Strateji 1 — EMA 10 iki kapanış (15 Eylül 2026): ELENDİ

Kullanıcı bir YouTube videosundaki VİOP scalping sistemini "Stratejiler
ekranına 1. strateji" olarak istedi (Sidar Demirgil, `iNuqAD5ngro`). Kurallar
altyazıdan çıkarıldı: EMA 10, üstünde/altında 2 kapanış → giriş, stop son
dip/tepe, hedef 1:3, 1R'de break even, EMA'nın ters tarafında kapanışta çık,
gün içi. Kod `ema_two_close.py` — Chandelier motorundan farklı olarak işlem
işlem (stop/hedef yol bağımlı). Tam rapor: `docs/EMA_IKI_KAPANIS_SONUCLARI.md`.

Son 3 yıl, 15dk: **9/9 enstrümanda zarar**, ortalama −%90, ayda ~250 işlem.
**Maliyetsiz bile kenar yok** (kâr faktörü 0,98, işlem başına −0,1 bp).
Videonun övdüğü "geri çekilme" girişi kırılımdan kötü. 1 saatlik barda da
9/9 negatif. Chandelier'la aynı ders: bu frekansta spread her şeyi yiyor.

---

## Strateji 2 — Heikin Ashi ikili sinyal (17 Eylül 2026): KURULDU, ÖLÇÜLMEDİ

Kullanıcı bir YouTube videosunu (Kripton Gezegeni, `dkX7PkoBzok`) "strateji 2
olarak kaydedelim" dedi. Göstergeler videonun **açıklamasında** adıyla yazıyor
("Chandelier Exit - Range Filter Buy and Sell"); geri kalan kurallar otomatik
altyazıdan çıkarıldı. Tam kayıt: `docs/HEIKIN_ASHI_IKILI_SINYAL.md`.

Sistem: Heikin Ashi barlarında **iki gösterge aynı yönde ve birbirine yakın
barlarda** (tolerans ≤ 3 bar) sinyal verirse gir; tek başına sinyal veren
gösterge sayılmaz. Çıkış ters ikili sinyalde. 4 saat / günlük, pozisyon gece
taşınır (gün içi DEĞİL). Videodaki Chandelier ayarı periyot 1 / çarpan 1,8,
Range Filter 100 / 3,0.

Videonun "fitilli mumda çık" ve "stopu yükselt" tarifleri kodda seçenek
(`doji_exit`, `exit_chandelier`), varsayılanları kapalı — videonun net kuralı
ters ikili sinyal. Sinyal HA'dan, işlem gerçek kapanıştan (bkz.
`src/finans_cortex/CLAUDE.md`).

BIST 30 bölümü **yok**: Yahoo'nun saatlik BIST geçmişi ~1 ay, Range Filter'ın
100'lük örnekleme penceresi için yetersiz.

**Sonuç ölçülmedi.** Backtest'i kullanıcı çalıştırıyor (Stratejiler >
Strateji 2 > Backtest). Chandelier bu kez bir GİRİŞ osilatörü olarak değil,
ikinci bir göstergeyle teyitli olarak kullanılıyor — yani aşağıdaki
"seçenek 2"ye (Chandelier'ı asıl işinde kullan) yakın bir deneme.

### Strateji 2.1 (22 Eylül 2026): KURULDU, ÖLÇÜLMEDİ

Kullanıcı: *"%2 kâr gördü mü satsın, tek bir ters sinyalde satsın, %1
zarardaysa satsın."* Giriş Strateji 2'nin aynısı (CE + RF ikili sinyal);
yalnız çıkış değişti. Kayıtlı varyant (`config/stratejiler.json`,
`strateji-2-1`, 4 saat). Motorda üç yeni seçenek, varsayılanları kapalı:
`kar_al` (%), `zarar_kes` (%), `tek_ters`. Kurallar Strateji 1'le aynı:
kâr/zarar bar içi, seviyeden; bar seviyenin ötesinde açılırsa (boşluk)
açılıştan; aynı barda ikisi de görülürse ZARAR sayılır; giriş barında
kontrol yok (giriş kapanışta). Tek ters sinyal: CE ya da RF'den biri ters
yanınca bar kapanışında çıkılır. Doğrulandı: varsayılan ayarla Strateji 2
işlemleri eski motorla birebir aynı; 2.1'in 5.285 işleminde (9 varlık ×
4s + 1g) her çıkış kurala uyuyor, arada kaçırılan tetik yok.
Sonuç ölçülmedi — kullanıcı bakacak.

---

## Geliştirme motoru (22 Eylül 2026)

Artık her stratejide **Geliştir** sekmesi var: teşhis (zayıf noktalar,
rakamıyla) + parametre taraması. Sıralama daima **kontrol bölümüne** (son %30)
göre; komşu ortalaması tesadüfi tepeleri ayıklar. Ayrıntı:
`src/finans_cortex/CLAUDE.md` ve `ui/CLAUDE.md`. Aşağıdaki "masadaki
seçenekler"in çoğu (trend filtresi, sadece long, rejim filtresi) artık bu
sekmede ölçülebilir; trend ve oynaklık filtreleri motorda **henüz parametre
değil** — teşhis bunu "eklenmesi gereken yeni kural" diye yazar.

---

## Trend filtresi (23 Eylül 2026): EKLENDİ, ÖLÇÜLMEDİ

Geliştirme motorunun teşhisi bunu kendisi buldu: Strateji 2'de 9 varlık × 5 yıl
havuzunda **200 barlık ortalamanın trend yönünde açılan 727 işlem +23,3 bp,
tersine açılan 623 işlem −7,8 bp**. Ama motorda karşılığı yoktu — ekran
"eklenmesi gereken yeni bir kural" deyip tıkanıyordu. Kullanıcı (22.09.2026):
*"bu rapordan çıkarılacak sonuçlar olmalı, kullanıcı sonuçlardan stratejiyi
güncelleyebilmeli."*

`HeikinConfig.trend_filter` (ortalama periyodu, **0 = kapalı**): açıkken yalnız
fiyatın ortalamaya göre bulunduğu yönde işlem açılır. Ölçüt teşhisteki ile
birebir aynı — gerçek kapanış, `ewm_mean(span=N)`, Heikin Ashi fiyatından
değil. Yalnız Strateji 2'de var; Strateji 1'de teşhis hâlâ "motorda böyle bir
parametre yok" der.

**Doğrulandı:** filtre kapalıyken eski motorla birebir aynı (Strateji 2'nin
4.046 işlemi ve 2.1'in 4.492 işleminde 0 sapma); 200 ile 4 saatlik barlarda
işlemlerin %43'ü eleniyor ve giriş yönü ortalamanın yanlış tarafında olan
**0 işlem** var (EMA200 elle hesaplanıp karşılaştırıldı).

**Ölçülmedi:** kârlılığa etkisine kullanıcı bakacak (Geliştir > Teşhis >
Sonuçlar, ya da Backtest). Aşırı uyum uyarısı geçerli: işlem sayısı yarıya
inerken kontrol bölümünün de iyileşmesi gerekir.

*Oynaklık filtresi hâlâ yok* — teşhis onu da ölçüyor ("çalkantılı dilim
−40,2 bp / en iyi dilim +67,8 bp") ama uygulanabilir değil. Sıradaki en somut
aday bu.

---

## ÖNEMLİ BULGU — kâr al kuyruğu kesiyor (23 Eylül 2026)

Kullanıcı: *"Strateji 2'de ne kadar iyileştirme yaparsam yapayım kara
geçemedim, bu işte bir terslik yok mu?"* Var, ve parametre hatası değil —
**yön hatası**.

**Ölçüm (Strateji 2 temel, 9 varlık, 4 saat, tüm geçmiş, 3.440 işlem,
toplam +%563):**

| Dilim | Toplam kârın yüzdesi |
|---|---|
| En iyi %1 (34 işlem) | **%224** |
| En iyi %2 (68 işlem) | %325 |
| En iyi %5 (172 işlem) | %521 |
| En iyi %10 (344 işlem) | %712 |

En büyük 5 işlem: %127,8 · %70,9 · %62,3 · %59,3 · %56,9. **Kârın tamamı bir
avuç işlemden geliyor; geri kalan net olarak zarar.** Trend takip
sistemlerinin doğası bu.

**Sonuç:** üst tarafı kesen her "iyileştirme" tam da parayı kazandıran şeyi
siliyor. `kar_al` %4 açıkken +%4'ün üstünde biten 422 işlem (%12,3) %4'te
kesiliyor.

| Ayar (tüm geçmiş) | İşlem | Net | Kâr faktörü | MaxDD |
|---|---|---|---|---|
| Strateji 2 (temel, kâr al yok) | 3.440 | **+%563** | 1,11 | −%43,2 |
| 2.1 (kâr al %2 + zarar kes %1 + tek ters) | 4.496 | **−%330** | 0,87 | −%49,2 |
| 2.2 (kâr al %4) | 3.705 | +%9 | 1,00 | −%62,4 |
| 2.3 (kâr al %4 + trend 200) | 2.076 | +%56 | 1,02 | −%25,1 |
| 2.4 (2.3 + 15dk teyit) | 1.771 | +%6 | 1,00 | −%22,3 |
| 2.4'ün **kâr alsız** hâli | 1.684 | **+%358** | 1,14 | **−%18,7** |

Son satır bulgunun kanıtı: tek fark kâr alın kapatılması, sonuç %6 → %358 ve
düşüş de azalıyor. Son 5 yılda fark bu kadar belirgin değil (kuyruk işlemleri
o pencereye denk gelmiyor) — **dönem seçimi bu stratejide sonucu belirliyor,
kısa pencereye bakarak karar vermeyin.**

*Kullanıcı karar vermedi; ölçüm kendisine sunuldu.*

---

## Strateji 2.4 — 15 dakikalık Chandelier teyidi (23 Eylül 2026): KURULDU, ÖLÇÜM KULLANICIDA

Kullanıcı isteği: *"kural olarak 15 dakikalık Chandelier Exit'in de aynı yönde
olması gerektiğini ekleyelim."* 2.3'ün üzerine kuruldu (kâr al %4 + trend
filtresi 200 + 15dk teyit). Motor tarafı `onay_15m`; ayrıntı ve doğrulamalar
`src/finans_cortex/CLAUDE.md`.

Ölçülen: işlemlerin %15'i eleniyor; son 5 yılda **MaxDD −%22,7'den −%9,7'ye**
düşüyor (tüm varyantların en düşüğü). Kârlılık kararı kullanıcıda.

---

## Strateji 3 — Chandelier tek başına (23 Eylül 2026): KURULDU, ÖLÇÜLDÜ

Kullanıcı: *"Strateji 2'yi kopyalayıp Strateji 3 yapalım, içinde Range Filter
hiç olmasın. Bakalım işler nasıl olacak."*

**Sonuç: Range Filter işin büyük kısmını yapıyormuş.**

| 9 varlık, tüm geçmiş | İşlem | Net | Kâr faktörü | İşlem başına | MaxDD |
|---|---|---|---|---|---|
| Strateji 2 (CE+RF), 4 saat | 3.440 | +%563 | 1,11 | 16,4 bp | −%43 |
| Strateji 3 (yalnız CE), 4 saat | 11.694 | +%226 | 1,02 | **1,9 bp** | −%44 |
| Strateji 3 + trend 200, 4 saat | 5.854 | +%399 | 1,08 | 6,8 bp | −%35 |
| Strateji 2 (CE+RF), günlük | 608 | +%818 | 1,42 | 134,6 bp | −%60 |
| Strateji 3 (yalnız CE), günlük | 2.179 | +%125 | 1,03 | **5,7 bp** | −%80 |
| Strateji 3 + trend 200, günlük | 988 | +%143 | 1,08 | 14,5 bp | −%43 |

Range Filter çıkınca işlem sayısı **3,4 katına** çıkıyor ama işlem başına kenar
16,4 bp'den 1,9 bp'ye düşüyor (günlükte 134,6 → 5,7). Yani RF sinyallerin
çoğunu eliyor ve **elediklerinin çoğu kötü**. Videonun "tek başına sinyal veren
gösterge sayılmaz" kuralı ölçümle doğrulandı.

Not: Strateji 3 sürekli piyasadadır (her Chandelier dönüşünde yön değiştirir),
bu yüzden düşüşü de büyük. Trend filtresi eklemek belirgin düzeltiyor ama
Strateji 2'nin seviyesine çıkarmıyor.

**Kullanıcının sıradaki fikri:** *"göstergeleri tek tek açıp kapatabilen bir
motor kuralım"* — şu an her strateji kendi gösterge kümesiyle sabit. Böyle bir
motor bu tür soruları (hangi gösterge ne kadar katkı veriyor) yeni strateji
yazmadan cevaplardı. Yapılmadı, sonraya bırakıldı.

---

## BIST 30 backtest (23 Eylül 2026): AÇILDI, İLK ÖLÇÜM

Kullanıcı istedi. Veri katmanı ve temizleme kuralları
`src/finans_cortex/CLAUDE.md`'de. **İlk ölçüm — 30 hisse, günlük, 21 yıl,
145.558 bar, maliyet 20 bp:**

| | İşlem | Net | Kâr faktörü | İşlem başına |
|---|---|---|---|---|
| Strateji 2 (CE+RF) | 2.710 | **−%975** | 0,95 | −36 bp |
| Strateji 3 (yalnız CE) | 8.278 | +%5.327 | 1,19 | 64 bp |
| Strateji 2 + trend 200 | 1.382 | +%3.762 | 1,45 | 272 bp |

**Küresel varlıkların TAM TERSİ:** orada Range Filter'ı çıkarmak kenarı
öldürüyordu, BIST'te çıkarmak iyileştiriyor. Sebep araştırılmadı.

### Bu rakamlara inanmadan önce — üç ciddi uyarı

1. **Al-tut karşılaştırması yıkıcı.** Aynı dönemde 30 hissenin eşit ağırlıklı
   al-tut toplamı **+%1.438.835** (hisse başına ortalama ~%48.000). Strateji
   +%3.762. Türkiye'de nominal TL getirileri enflasyonla şişiyor; her şeyin
   yükseldiği bir piyasada zamanın yarısını SAT'ta geçirmek çok pahalı.
   *(Ölçüler birebir karşılaştırılabilir değil: al-tut bileşik, strateji her
   işlemde sabit büyüklük. Ama yön açık.)*
2. **Hayatta kalan yanlılığı.** `bist.BIST30` BUGÜNKÜ endeks üyeleri.
   Endeksten düşen/batan hisseler listede yok — hem al-tut'u hem stratejiyi
   olduğundan iyi gösterir.
3. **Maliyet tahmin.** 20 bp gidiş-dönüş varsayıldı. Gerçek aracı kurum
   oranı yazılmalı; 272 bp'lik işlem başına kenar maliyete duyarlı değil ama
   Strateji 3'ün 64 bp'si duyarlı.

**Reel getiri ölçülmedi** — TÜFE serisi projede yok. BIST sonuçları için
asıl karşılaştırma bu olmalı.

---

## Strateji 2.6 — sadece AL, günlük (24 Eylül 2026): ŞİMDİYE KADARKİ EN SAĞLAM SONUÇ

Kullanıcı: *"devasa program geliştirdik, birazcık kazanan bir strateji bile
geliştiremedik."* Geliştirme motorunun teşhisi baştan beri *"SAT tarafı zarar
ediyor"* diyordu; **günlük barda hiç denenmemişti.**

Videodaki Strateji 2, tek farkla: `allow_short=False`. 9 küresel varlık,
günlük bar, tüm geçmiş:

| Ayar | İşlem | Net | Kâr faktörü | Sharpe | MaxDD |
|---|---|---|---|---|---|
| Strateji 2 (olduğu gibi) | 608 | +%819 | 1,42 | 0,04 | −%60 |
| **2.6 — SAT kapalı** | 303 | **+%1.245** | **2,56** | **0,55** | **−%22** |

Tek anahtarla her ölçü birden iyileşiyor.

**Aşırı uyum kontrolünden geçen İLK varyant:**

| Bölüm | İşlem | Net | Kâr faktörü | Sharpe |
|---|---|---|---|---|
| Ayar (%70) | 122 | +%299 | 2,23 | 0,42 |
| **Kontrol (%30, görülmemiş)** | 181 | **+%946** | **2,70** | **0,77** |

Kontrol bölümü ayar bölümünden **iyi** — bugüne kadar hiçbir varyantta
görülmedi. 9 varlığın 8'i artıda (yalnız EURUSD −%18). Varlık bazında:
BTCUSD +%428, WTI +%226, BRENT +%218, XAUUSD +%104, XAGUSD +%103, DJ +%92,
DAX +%67, FTSE +%24.

**Neden inanılabilir:** parametre taramasıyla değil **mekanizmadan** bulundu —
uzun vadede yukarı yürüyen varlıklarda sürekli SAT tarafında olmak yapısal
olarak kaybettirir. Tarama sonucu "parlayan bir nokta" değil.

**Neden yine de temkinli olunmalı:**
- Al-tut hâlâ getiride önde (9 varlık toplamı +%7.082, ağırlıklı olarak BTC
  ve altın). 2.6'nın üstünlüğü getiride değil **riskte**: −%22 düşüş ve
  zamanın büyük kısmında piyasa dışında.
- O gün çok sayıda ayar denendi; ne kadar çok denenirse biri tesadüfen iyi
  görünür. Kontrol bölümü bunu azaltır, sıfırlamaz.
- 303 işlem / 9 varlık = varlık başına ~25-68 işlem. Az değil ama çok da değil.
- Maliyetler tahmin.

**DÜZELTME (24 Eylül 2026):** Yukarıdaki **+%1.245** yanıltıcıdır — işlem
getirilerinin toplamıdır, yıllık getiri değil. Doğru tablo:

| | Strateji 2.6 | Al-tut |
|---|---|---|
| **Yıllık getiri** | **%8,3** | **%16,0** |
| Maks. düşüş | −%22 | −%47 |
| Piyasada geçen süre | %47 | %100 |
| Yılda işlem (varlık başına) | **2,5** | — |

Yani 2.6 al-tut'u **getiriyle yenmiyor**; yarısı kadar kazandırıyor, yarısı
kadar düşüş yaşatıyor ve yılda 2-3 sinyal veriyor. Kullanıcının *"senede 2-3
sinyal, doğru dürüst kazanç yok"* tespiti doğruydu. Ölçüm altyapısı bu yüzden
düzeltildi (bkz. `src/finans_cortex/CLAUDE.md` — ölçü düzeltmesi).

**Muhtemel sebep (denenmedi):** Range Filter örnekleme periyodu **100 bar**.
Video bunu 4 saatlik grafik için veriyordu (~17 gün); günlükte aynı 100 bar
~5 ay oluyor ve filtre altı kat yavaşlıyor. Gösterge parametreleri bar boyuyla
ölçeklenmeliydi. Sıradaki test: günlükte RF ~20-25.

*Kullanıcı karar vermedi; varyant kaydedildi, inceleme kendisinde.*

---

## "Sinyalleri tersine çevirsek?" — ELENDİ, ölçümle (24 Eylül 2026)

Kullanıcı: *"birçoğu acayip zarar yazıyordu, o sinyaller geldiğinde tersine
işlem yapalım, kâra geçmez miyiz?"* Mantıklı bir fikir; ölçüldü, **çalışmıyor**
ve sebebi öğretici.

**Aritmetik:** `net = brüt − maliyet`, dolayısıyla `tersi = −brüt − maliyet`.
Spread/komisyon bir **işaret değil, her işlemde ödenen geçiş ücretidir** —
yön değişince o da yön değiştirmez. Tersine dönmek brüt kenarı kaybettirir
ama ücreti ödemeye devam ettirir.

| Ayar | Bar | İşlem | Brüt | Maliyet | Net | **Tersi** |
|---|---|---|---|---|---|---|
| Strateji 2 | 15dk | 45.580 | −%344 | %1.753 | −%2.097 | **−%1.408** |
| Strateji 3 | 15dk | 148.992 | −%2.075 | %5.791 | −%7.866 | **−%3.716** |
| Strateji 2 | 1sa | 11.872 | **+%156** | %455 | −%299 | **−%611** |
| Strateji 3 | 1sa | 39.565 | **+%325** | %1.515 | −%1.190 | **−%1.840** |
| Strateji 2.1 | 4sa | 4.496 | −%160 | %170 | −%330 | **−%10** |

Tersine çevrilmiş hiçbiri artıya geçmiyor. En kötü ayar olan 2.1'in tersi bile
ancak başabaşa yaklaşıyor (−%10) — ve o da bir **üst sınır**, çünkü 2.1'de
kâr al / zarar kes var; işaret dönünce stop ve hedef de yer değiştirir, gerçek
tersi için yeniden simülasyon gerekir.

**Asıl bulgu — kaybın kaynağı "yanlış olmak" değil, "çok işlem yapmak":**
1 saatlik satırlara bakın, brüt **artı** (+%156, +%325). Yani sinyalin gerçek
bir kenarı var; onu maliyet yiyor. Bu stratejiler yanlış değil, **pahalı**.
Çözüm sinyali ters çevirmek değil, işlem sayısını düşürmek / seçiciliği
artırmak.

Tersine çevirmenin işe yaraması için `brüt < −maliyet` olmalı: sinyalin gidiş-
dönüş maliyetinden **daha fazla** ters yönde bilgi taşıması gerekir. Ölçülen
hiçbir durumda bu olmadı.

---

## Ölçü düzeltmesi 2 + BTC çıkarıldı (24 Eylül 2026)

Kullanıcı: *"nerede yanlış yapıyoruz, mantık hatamız mı var?"* Strateji kodu
temiz; ölçüde iki hata düzeltildi (açık pozisyon artık her gün değerleniyor;
portföy ağırlığı hafta sonu BTC'ye %100 veriyordu). BTC hiçbir hesapta yok.
Ayrıntı: `src/finans_cortex/CLAUDE.md` — ikinci ölçü düzeltmesi. **Bu tarihten
önceki MaxDD/Sharpe/yıllık rakamları eski ölçüyle** — kullanıcı yeniden bakacak.

Teşhiste konuşulan eksikler (yapılmadı, sırada): kalibrasyon stratejisi
(12 aylık momentum — bilinen sonucu platform veriyor mu?), VİOP maliyet
modeli (vadeli: swap yok ama fiyatta faiz farkı + vade devri), boştaki paranın
faizi. Kullanıcı oynaklığa göre pay vermeyi istemedi: **eşit para**.

## Sırada ne var

Anayasa 3.4 adım 1 ("tek strateji, güvenilir backtest sonucu") **tamamlandı ve
sonuç olumsuz**. Bu bir başarısızlık değil — backtest'in işi tam olarak buydu.

Sıradaki karar kullanıcıya ait. Masadaki seçenekler:

1. **Hipotezi test et: sistemi flat kalabilir yap.** Mevcut kurgu her an piyasada
   (long_bar% + short_bar% = 100). Trend takip sistemleri, yatay dönemlerde
   DIŞARIDA durup güçlü trendlere binerek kazanır. Bir trend gücü filtresi
   (ADX vb.) eklemek en somut ve ucuz sonraki deneme.
2. **Chandelier'ı asıl işinde kullan.** LeBeau'nun tasarımında Chandelier bir
   ÇIKIŞ aracıdır (trailing stop); girişi başka bir yöntem verir. Biz onu iki
   yönlü sürekli-piyasada bir giriş osilatörü gibi kullandık.
3. **Sadece long.** Short tarafı 8/8 zarar ettiğine göre short'u tamamen kapatmak
   test edilebilir — ama long da al-tut'u yenemediği için tek başına yetmez.
4. **Farklı strateji ailesine geç** (anayasa 3.4 adım 2: çoklu strateji
   karşılaştırması).
5. **BIST'e geç** — o zaman bedelsiz/temettü düzeltmesi, seans takvimi, vergi
   katmanı gündeme gelir (bkz. anayasa açık konular).

### Henüz karara bağlanmamış
- **Strateji 2.6'nın (sadece AL, günlük) incelenmesi** — en sağlam sonuç;
  kullanıcı Backtest ve Karşılaştırma sekmelerinden kendisi bakacak.
  Sıradaki denenmemiş adım: aynı "SAT kapalı" anahtarının BIST'te ve
  Strateji 3'te ne yaptığı.
- **BIST'te enflasyon/reel getiri** — nominal TL sonuçları yanıltıyor. TÜFE
  ya da dolar bazlı bir karşılaştırma eklenmeli.
- **Gösterge aç/kapa motoru** (kullanıcı fikri, 23.09.2026) — bir stratejinin
  göstergelerini tek tek devre dışı bırakıp katkısını ölçebilmek. Strateji 3
  bunun elle yapılmış tek örneği.
- **Kâr alı kapatmak** (yukarıdaki bulgu) — en somut aday; Strateji 2.4'ün
  kâr alsız hâli ayrı bir varyant olarak kaydedilmedi, kullanıcı isterse
  Geliştir > Sonuçlar ya da Backtest > Farklı kaydet ile kurulur.
- **Trend filtresinin etkisi** — Geliştir > Teşhis > Sonuçlar'dan tek tıkla
  denenir; kullanıcı bakacak. (Seçenek 1 "sistemi flat kalabilir yap"ın ucuz
  bir sürümü: trende ters sinyallerde dışarıda kalınır.)
- **Strateji 2 ve 2.1'in backtest'i** — kullanıcı çalıştırıp bakacak
  (Stratejiler > Strateji 2 / 2.1 > Backtest). Yukarıdaki seçenekler bunun
  sonucuna göre anlam kazanır.
- Yukarıdaki 5 seçenekten hangisi
- Chandelier ATR periyodu / çarpan optimizasyonu (yapılmadı; ama short'un 8/8
  negatif olması yapısal görünüyor, parametrik değil)
- Maverick profili backtest'te hiç çalıştırılmadı
- Algolab hesabı (Faz 2, BIST canlı veri)

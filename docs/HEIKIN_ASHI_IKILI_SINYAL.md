# Strateji 2 — Heikin Ashi ikili sinyal (Chandelier Exit + Range Filter)

**Kaynak video:** Kripton Gezegeni, "İhtiyacınız olan TEK Heikin Ashi Al-Sat
STRATEJİSİ! KOLAY Sinyaller ve MAXİMUM KAZANÇ!"
<https://www.youtube.com/watch?v=dkX7PkoBzok> (20:42, Türkçe)

**Kod:** `src/finans_cortex/heikin_range.py`
**Ekran:** Stratejiler → *2 · Heikin Ashi ikili sinyal*
**Tarih:** 17 Eylül 2026

---

## 1. Kurallar nereden çıkarıldı

İki kaynaktan:

1. **Video açıklaması** göstergeleri adıyla veriyor — bu, otomatik altyazının
   bıraktığı bütün belirsizliği kapattı:
   > İndikatör İsmi: **Chandelier Exit - Range Filter Buy and Sell**
2. **Otomatik altyazı** (yalnızca makine üretimi Türkçe var, insan altyazısı
   yok). Konuşma dili ve ASR hataları yüzünden metin yer yer bozuk; kurallar
   tekrar eden ifadelerden ve ekranda anlatılan akıştan çıkarıldı.

Altyazıdaki karşılıkları (ASR bozuk hâli → kastedilen):
*"hain aşımı / Ayçin aşımı / hakim aşımı"* → **Heikin Ashi**,
*"bujiler / duyumlar / dostumun"* → **doji**,
*"kültür / indikatör"* → **gösterge**.

## 2. Videodaki sistem

| | |
|---|---|
| Grafik | **Heikin Ashi** mumları |
| Zaman dilimi | **4 saatlik** ve günlük ("5 dakikalık yazıyor ama dikkate almayın" — bu, Range Filter scriptinin adı) |
| Gösterge 1 | **Chandelier Exit** — videoda periyot **1**, çarpan **1,8**; "Use Close Price for Extremums" açık bırakılıyor |
| Gösterge 2 | **Range Filter Buy and Sell** — ayarlarına dokunulmuyor: örnekleme **100**, çarpan **3,0** |
| Giriş | İki gösterge **aynı yönde** ve **birbirine yakın** barlarda sinyal verirse |
| Tolerans | Aynı bar ya da 1–2 bar sonra "mükemmel", **3 bara kadar** kabul; *"1 2 3 4 — bunda burada girmiyoruz"*, "beş gün sonra yandığı için iyi bir sinyal almıyoruz" |
| Tek gösterge | Sayılmaz: *"bunu tek başına al sinyali vermiş ancak diğer gösterge vermemiş"* → işlem yok |
| Çıkış | Ters yöndeki **ikili sinyal** |
| Ek çıkış 1 | Uzun fitilli / ince gövdeli mum (videoda "doji") trend dönüşü uyarısı: *"ilk gelen uzun fitilli durumunda çıkış yapılabilir"* |
| Ek çıkış 2 | *"stopu yükselterek ilerleyebiliriz"* — takip eden stop |

Videonun kendi vurgusu: **iki göstergenin aynı anda yanması** hatalı sinyali
azaltıyor; ikisi ayrı ayrı zaten "güçlü" ama tek başlarına yanıltıyor.

## 3. Kodda ne değişti, neden

| Videodaki | Koddaki | Neden |
|---|---|---|
| Göz kararı "uzun fitilli mum" | `doji_body`: gövde / (yüksek−düşük) oranı eşiği (varsayılan 0,25) | Ölçülebilir olmayan kural backtest edilemez |
| "Stopu yükselterek ilerle" | `exit_chandelier`: Chandelier yönü pozisyonun tersine dönünce çık | Chandelier'in asıl tasarımı zaten takip eden stop (LeBeau) |
| Ek çıkışların ikisi de anlatılıyor | Varsayılan **kapalı** | Videonun asıl/net kuralı ters ikili sinyal; diğerleri "yapılabilir" |
| Heikin Ashi grafiğinde al-sat | **Sinyal HA'dan, işlem gerçek fiyattan** | HA fiyatı bir ortalamadır, o fiyattan işlem yapılamaz — bkz. bölüm 4 |
| "4 saatlik / günlük" | `4h`, `1d` (+ `1h` açık) | 4H kovalarımız 00/04/08/12/16/20 UTC hizalı (storage.py) |

Videoda geçen Chandelier ayarı altyazıda **"bunu bir yapıyoruz, bunu da 1,8
olarak güncelliyoruz"** diye geçiyor; periyot 1 / çarpan 1,8 okuması budur.
Bu iki değer arayüzden değiştirilebilir — TradingView'deki everget sürümünün
kendi varsayılanı 22 / 3,0'dır.

## 4. Backtest dürüstlüğü — en önemli madde

**Heikin Ashi barında alım satım yapılamaz.** HA kapanışı dört fiyatın
ortalaması, HA açılışı bir önceki barın ortalamasıdır; piyasada o fiyatlar
yoktur. TradingView'de Heikin Ashi grafiğinde alınan backtest sonuçlarının
gerçeğe göre şişkin çıkmasının sebebi tam olarak budur.

Bu yüzden kodda:

- Göstergeler HA barlarından hesaplanır (video böyle diyor),
- **giriş ve çıkış fiyatı her zaman barın GERÇEK kapanışıdır**,
- karar barın kapanışında verilir, işlem aynı kapanıştan yapılır,
- maliyet olarak işlem başına `backtest.DEFAULT_COSTS` gidiş-dönüş spread'i
  düşülür.

Doğrulandı: 9 varlık × (4 saat + günlük) = **4.039 işlemin** giriş ve çıkış
fiyatlarının tamamı ilgili barın gerçek `close` değeriyle birebir aynı,
**0 sapma**.

## 5. Uygulanan eşleştirme mantığı

Her gösterge sinyal verdiğinde `(yön, bar)` olarak saklanır. İki göstergenin
son sinyali aynı yöndeyse ve aralarındaki fark toleransı aşmıyorsa,
**ikincisinin geldiği barda** ikili sinyal oluşur; çift tüketilir (aynı çift
ikinci kez sayılmaz).

- Pozisyondayken ters ikili sinyal gelirse çıkılır ve **aynı barda ters
  yönde** pozisyon açılır.
- `allow_short` kapalıysa ters sinyal yalnızca çıkıştır.
- Bir gösterge yandı, diğeri henüz yanmadı ve tolerans penceresi hâlâ açıksa
  canlı sinyal listesinde **"△ AL bekliyor / ▽ SAT bekliyor"** görünür.

Isınma: Range Filter iki üstel ortalama zinciri kullandığı için ilk
`3 × örnekleme` bar (varsayılanda 300 bar) işlem üretmez.

## 6. Ne ölçülmedi

Bu doküman **kuralların** ve **kodun** kaydıdır; performans yargısı
içermez. Backtest'i kullanıcı kendisi çalıştırıyor:
Stratejiler → *2 · Heikin Ashi ikili sinyal* → **Backtest**
(tek backtest ya da canlı parametre ayarı, istenen tarih aralığıyla).

Sonuçlar not edilmek istenirse bu dosyaya bir "Sonuçlar" bölümü eklenir —
Strateji 1'de `docs/EMA_IKI_KAPANIS_SONUCLARI.md` böyle oluştu.

**Varyant 2.1 (22 Eylül 2026):** aynı giriş; çıkış %2 kâr al, %1 zarar kes,
tek ters sinyalde çık. Kurallar ve doğrulama: `STRATEJI_GECMISI.md` >
"Strateji 2.1".

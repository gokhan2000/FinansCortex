# Strateji 1 — EMA 10 iki kapanış: backtest sonuçları

**Tarih:** 15 Eylül 2026
**Kaynak:** Sidar Demirgil, "En Çok Kazandıran VİOP Scalping Sistemim"
(https://www.youtube.com/watch?v=iNuqAD5ngro). Kurallar videonun altyazısından çıkarıldı.
**Kod:** `src/finans_cortex/ema_two_close.py` · **Rapor:** `python scripts/ema_report.py`
**Arayüz:** Ana ekran → Stratejiler

## Kurallar (videodan)

1. EMA 10
2. EMA üstünde art arda 2 kapanış → long, altında 2 kapanış → short
3. Giriş: kırılım (2. kapanışta) veya geri çekilme (EMA'ya geri dokununca)
4. Stop: son dip / son tepe (kodda: son 10 barın en düşüğü / en yükseği)
5. Hedef 1:3 risk/ödül · 1R'de break even
6. Fiyat EMA'nın ters tarafında kapatırsa çık
7. Gün içi: gece pozisyon taşıma, açılıştan sonra ilk 30 dk işlem yok

## Videodan sapmalar

- Video BIST30 VİOP'ta 5dk sinyal + 1dk giriş kullanıyor; bizde en küçük bar 15dk.
- Gün sonu 22:00 UTC (01:00 TR) kabul edildi. Ölçüldü: altın, endeksler ve petrol
  her gün 21:00-22:00 UTC arası kapalı.
- Aynı bar içinde hem stop hem hedef görülürse stop sayılır (kötümser).

## Doğrulama (XAUUSD, son 1 yıl)

Kurulum ihlali 0 · günü aşan işlem 0 · stop yanlış tarafta 0.
Hedef çıkışları tam +3,0R, stop çıkışları tam −1,0R, break even çıkışları ~0R.

## Sonuç: son 3 yıl, 15dk, maliyetli — 9/9 enstrümanda ZARAR

| | Kırılım | Geri çekilme |
|---|---|---|
| Ortalama getiri | −%90,9 | −%90,0 |
| Ortalama Sharpe | −6,06 | −8,52 |
| Kazanan işlem | %23 | %15 |
| Kâr faktörü | 0,68 | 0,53 |
| Ayda işlem | ~250 | ~220 |

Videonun "risk/ödülü her zaman daha iyi" dediği geri çekilme girişi, kırılımdan
**daha kötü** çıktı.

## Kaybın sebebi: maliyet mi, kenar yokluğu mu?

| Senaryo (15dk kırılım, son 3 yıl) | Ort. getiri | Ort. Sharpe | Kâr faktörü | İşlem başı | Pozitif |
|---|---|---|---|---|---|
| Varsayılan (maliyetli) | −%90,9 | −6,06 | 0,68 | −4,1 bp | 0/9 |
| **Maliyetsiz** | **−%12,0** | **−0,28** | **0,98** | **−0,1 bp** | 2/9 |
| EMA çıkışı kapalı (yalnız stop/hedef) | −%86,6 | −4,34 | 0,74 | −3,9 bp | 0/9 |
| 1 saatlik bar | −%48,6 | −1,43 | 0,84 | −3,2 bp | 0/9 |

**Maliyetsiz bile kenar sıfır** (işlem başına −0,1 bp). Chandelier'daki bulguyla
aynı tablo: sinyal yazı-turadan fazla bilgi taşımıyor, sonra ayda ~250 işlemin
spread'i sermayeyi eritiyor.

Tek istisna XAUUSD: maliyetsiz +%52 (Sharpe 0,93). Ancak 3 bp maliyetle −%89,5.
Altın bu dönemde +%124 yükseldi; bu, kenardan çok boğa piyasasının izi olabilir.

Çıkışların ~%78'i "EMA'nın ters tarafında kapanış". 15dk'da EMA 10 çok sık
kesiliyor; işlemler hedefe varmadan 1-2 barda kesiliyor.

## Açık sorular

- Videodaki asıl ortam VİOP 5dk/1dk; bizde bu çözünürlük yok. BIST verisi gelince
  aynı kod orada da denenmeli (maliyet yapısı farklı).
- Gerçek spread rakamları (`backtest.DEFAULT_COSTS`) hâlâ tahmin.

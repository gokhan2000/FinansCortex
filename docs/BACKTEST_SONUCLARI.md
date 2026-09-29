# Backtest Sonuçları — Chandelier Exit Elendi

**Tarih:** 14 Ağustos 2026
**Veri:** 2,50 milyon 15dk barı, 8 enstrüman, 2003-2026 (enstrümana göre 11-23 yıl)
**Betikler:** `scripts/backtest_report.py`, `src/finans_cortex/backtest.py`
**Profil:** Normal (ATR 22 / çarpan 3,0)

> **Özet: Strateji çalışmıyor. Sebebi işlem maliyeti değil — sinyalde kenar (edge) yok.**

---

## 1. Mimari sapma: Backtrader kullanılmadı

Anayasa 3.1 Backtrader diyordu. Faz 1'de kullanılmadı:

1. Backtrader pandas ister; veri Polars/DuckDB'de. Her testte dönüşüm maliyeti
   ve iki kütüphanenin her yere sızma riski.
2. Backtrader'ın aktif bakımı yıllardır durmuş.
3. Strateji tek pozisyonlu, sinyaller zaten vektörel. Olay-döngüsü motoru
   gereksiz ağır; ~150 satırlık vektörel hesap hem hızlı hem denetlenebilir.

**Backtrader Faz 2'de yeniden değerlendirilmeli** (çoklu pozisyon, piramitleme,
portföy seviyesi risk). O zaman gerçekten kazanç sağlar.

Look-ahead koruması: pozisyon bir barın kapanışında belirlenir, getirisi bir
sonraki bardan işler (`pozisyon.shift(1) * bar_getirisi`).

---

## 2. Ana sonuç (tahmini maliyetle)

| Enstrüman | Mod | İşlem | Getiri % | Sharpe | MaxDD % | Kazanan % | Kâr faktörü |
|---|---|---|---|---|---|---|---|
| EURUSD | naive | 1.234 | −43,4 | −0,41 | −44,2 | 30,9 | 0,85 |
| EURUSD | timed | 916 | −36,7 | −0,34 | −38,2 | 32,8 | 0,87 |
| XAUUSD | naive | 1.749 | +254,5 | **0,35** | −33,5 | 32,7 | 1,16 |
| XAUUSD | timed | 1.275 | +76,2 | 0,20 | −34,0 | 34,0 | 1,13 |
| XAGUSD | naive | 877 | +92,5 | **0,31** | −53,8 | 30,2 | 1,14 |
| XAGUSD | timed | 655 | +6,2 | 0,15 | −74,8 | 32,8 | 1,13 |
| BRENT | naive | 977 | −77,0 | −0,10 | −82,2 | 31,5 | 0,96 |
| WTI | naive | 1.225 | −89,0 | −0,11 | −93,0 | 30,2 | 0,95 |
| DJ | naive | 956 | −47,8 | −0,22 | −49,5 | 30,1 | 0,91 |
| DAX | naive | 973 | −44,2 | −0,14 | −62,2 | 29,6 | 0,94 |
| FTSE | naive | 896 | −36,3 | −0,15 | −46,6 | 30,7 | 0,94 |

**Ortalama:** naive Sharpe −0,06 · timed Sharpe −0,12
Maksimum drawdown ortalama **−58%**, WTI'de −93%.

---

## 3. Teşhis: maliyet mi, sinyal mi?

Maliyet varsayımları tahmindir (bkz. bölüm 6), o yüzden maliyet sıfırlanıp
tekrar çalıştırıldı:

| | Maliyetsiz Sharpe | Maliyetli Sharpe |
|---|---|---|
| naive | **0,00** | −0,06 |
| timed | **−0,02** | −0,12 |

**Sıfır maliyette bile ortalama Sharpe sıfır.** Strateji komisyona yenilmiyor;
kaybedecek kenarı hiç yok. Maliyet varsayımlarını düzeltmek sonucu değiştirmez.

Maliyetsiz pozitif olan: yalnızca XAUUSD (0,41) ve XAGUSD (0,43). 8'de 2 —
gürültüden ayırt edilemez.

---

## 4. Öldürücü bulgu: long/short ayrımı

Metallerdeki pozitif sonuç gerçek bir kenar mı, yoksa boğa piyasası mı?

| Enstrüman | Long getiri % | Short getiri % | **Al-ve-tut %** |
|---|---|---|---|
| EURUSD | −25,6 | −20,3 | −5,3 |
| XAUUSD | +240,4 | −47,9 | **+287,7** |
| XAGUSD | +186,4 | −15,6 | **+201,8** |
| BRENT | +60,2 | −81,8 | **+141,0** |
| WTI | +44,2 | −87,4 | **+131,6** |
| DJ | +44,4 | −82,7 | **+127,3** |
| DAX | +48,5 | −74,4 | **+123,0** |
| FTSE | +25,2 | −41,1 | **+66,4** |

İki şey birden görünüyor:

1. **Short tarafı 8 enstrümanın 8'inde de zarar ediyor** (−15,6% ile −87,4% arası).
   Strateji düşüş trendlerini yakalayamıyor, sadece kanıyor.
2. **Long tarafı 8 enstrümanın 8'inde de al-ve-tut'tan kötü.** XAUUSD'de 240% vs
   288%, WTI'de 44% vs 132%.

Yani metallerdeki "başarı", boğa piyasasının bir kısmını yakalamaktan ibaret —
üstelik hiçbir şey yapmadan elde tutmaktan daha kötü. EURUSD'de ise strateji
aktif olarak değer yok ediyor (long −25,6% + short −20,3%, al-tut −5,3%).

---

## 5. Muhtemel kök sebep: sistem hiç boşta kalmıyor

Mevcut kurgu **her an piyasada** — ya long ya short, asla flat değil
(long_bar% + short_bar% = 100). Trend takip sistemlerinin para kazanma şekli,
yatay/gürültülü dönemlerde **dışarıda durup** sadece güçlü trendlere binmektir.

Ayrıca: Chandelier Exit, LeBeau'nun tasarımında bir **ÇIKIŞ** aracıdır (trailing
stop). Pozisyona başka bir yöntemle girilir, Chandelier ne zaman çıkılacağını
söyler. Biz onu iki yönlü, sürekli-piyasada bir giriş osilatörü gibi kullandık.
Yaygın bir uyarlama ama tasarım amacına aykırı.

Bu, sonraki denemeler için somut ve test edilebilir bir hipotez:
**bir trend gücü filtresi ekleyip sistemi zamanın çoğunda flat tutmak.**

---

## 6. Bu sonuçların sınırları — dürüstlük notu

Aşağıdakiler test EDİLMEDİ; sonuç bunlara göre değişebilir:

- **Parametre optimizasyonu yapılmadı.** ATR 22 / çarpan 3,0 klasik varsayılan.
  Ancak short tarafının 8/8 negatif olması yapısal görünüyor, parametrik değil.
- **Maliyet modeli tahmindir** (`DEFAULT_COSTS`), gerçek aracı kurum
  spread/komisyonuyla doğrulanmalı. Bölüm 3 bunun sonucu değiştirmediğini gösteriyor.
- **Pozisyon boyutlandırma yok** — her işlem sermayenin tamamı varsayıldı.
  Sharpe bundan etkilenmez, drawdown etkilenir.
- **Tek çıkış kuralı test edildi** (4H trend dönüşü). Chandelier'ın kendi trailing
  stop'unu çıkış olarak kullanan kurgu denenmedi.
- **Maverick profili** (ATR 14 / 2,0) bu raporda çalıştırılmadı. Daha sık işlem
  ürettiği için maliyetli ortamda daha kötü olması beklenir.

---

## 7. Sonuç

Anayasa 3.4'ün sırası "1) tek strateji, güvenilir backtest sonucu" diyordu.
**Adım 1 tamamlandı ve sonuç olumsuz:** Chandelier Exit, bu kurguyla, bu 8
enstrümanda kenar üretmiyor.

Bu bir başarısızlık değil, backtest'in tam olarak yapması gereken şey — parayı
riske atmadan önce stratejiyi elemek. Anayasa 3.5'teki "canlıya alınacak hiçbir
strateji bu adımdan geçmeden onaylanmayacak" kuralı işledi.

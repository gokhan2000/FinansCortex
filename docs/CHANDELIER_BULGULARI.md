# Chandelier Exit — İlk Ölçüm Bulguları

**Tarih:** 14 Ağustos 2026
**Veri:** 2,50 milyon adet 15dk barı, 8 enstrüman, Dukascopy (temizlenmiş)
**Betik:** `scripts/signal_report.py`
**Parametreler:** Normal = ATR 22 / çarpan 3.0 · Maverick = ATR 14 / çarpan 2.0

---

## 1. Veri temizliği — bulunan ve düzeltilen bozukluk

Dolumdan sonra kalite kontrolü **hayalet (donuk) bar** tespit etti: piyasa
kapalıyken beslemenin son fiyatı tekrar tekrar bar olarak yayınlaması.

| Enstrüman | Hayalet gün | Bar | Yıllar |
|---|---|---|---|
| EURUSD | 120 | 11.385 | 2012-2014 |
| WTI | 51 | 3.469 | 2013-2014 |
| BRENT | 4 | 4 | 2015-2016 |

Belirtisi: gün boyunca `max(high) == min(low)`, günlük aralık %0,0, günde tek
bir farklı kapanış değeri.

**Neden ölümcül:** bu barlarda True Range = 0. ATR yapay olarak çöker, Chandelier
stopları aşırı daralır, piyasa açılınca sahte sinyal üretir. Toplam verinin
yalnızca %0,6'sı ama tamamı ATR'yi bozacak yerde.

Silindi (`scripts/clean_ghost_bars.py --apply`). Temizlik sonrası: hayalet 0,
mantık hatası 0, hafta içi eksik gün oranı %0-1,5 (tatiller).

### Yanlış alarm notu
Kalite ölçütünün ilk sürümü %14-19 "eksik gün" veriyordu. Doğrulanınca bunların
neredeyse tamamının **Pazar** olduğu görüldü — forex Pazar 22:00 UTC'de açıldığı
için o gün doğal olarak ~8 bar içerir. Ölçüt hafta içine kısıtlandı. *Ders: alarma
inanmadan önce doğrula.*

---

## 2. Sinyal frekansı — "15dk çok gürültü olur" doğrulandı

Normal profil (ATR 22 / 3.0):

| Enstrüman | 15dk sinyal/ay | 4H sinyal/ay | Gürültü katsayısı |
|---|---|---|---|
| EURUSD | 111,2 | 7,0 | 15,9× |
| XAUUSD | 92,5 | 6,3 | 14,7× |
| XAGUSD | 97,2 | 6,3 | 15,4× |
| BRENT | 97,9 | 7,0 | 14,0× |
| WTI | 106,3 | 7,5 | 14,2× |
| DJ | 91,9 | 6,9 | 13,3× |
| DAX | 91,7 | 7,0 | 13,1× |
| FTSE | 93,9 | 6,4 | 14,7× |

Ortalama pozisyon tutma süresi:
- **15dk: ~4,5-5,5 saat** → günde ~4-5 gidiş-dönüş işlem
- **4H: ~70-87 saat** (~3-3,6 gün) → 4 günde bir pozisyon

Günde 4-5 işlem, spread + komisyon sonrası hiçbir trend stratejisinin
taşıyamayacağı bir tempodur. **15dk tek başına yön kaynağı olarak kullanılamaz.**

---

## 3. Asıl bulgu: yön değişimi bar başına sabit

Sinyal sayısını bar sayısına bölünce:

| | 15dk | 4H |
|---|---|---|
| EURUSD | 19.473 / 375.217 = **%5,19** | 1.233 / 24.113 = **%5,11** |
| XAUUSD | 25.741 / 567.178 = **%4,54** | 1.748 / 37.800 = **%4,62** |

Chandelier Exit'in yön değiştirme olasılığı **bar başına ~%5 ve zaman diliminden
bağımsız**. 4H'ın "daha az gürültülü" olmasının sebebi göstergenin trendi daha iyi
görmesi değil — sadece 16 kat daha yavaş örneklemesi.

**Sonuç:** gürültüyü azaltan şey gösterge değil, bar boyutu. Dolayısıyla 15dk'yı
yön kaynağı yapıp parametre oynayarak düzeltmeye çalışmak yanlış yol. Doğru yapı:

```
4H  -> YÖN   (yavaş, ayda ~7 sinyal, trendi tanımlar)
15dk -> ZAMANLAMA (yalnızca 4H yönü ile aynı taraftaki girişler)
```

Kullanıcının hem 15dk hem 4H istemesi bu yüzden tesadüf değil; ikisi farklı iş yapar.

---

## 4. Maverick profili

Maverick (ATR 14 / 2.0) her zaman diliminde Normal'in **~1,8 katı** sinyal üretiyor
(4H'ta 7 → 13/ay). Beklenen davranış: dar stop = erken çıkış = daha çok işlem.
Anlamlı karşılaştırma ancak komisyon/spread modellenmiş backtest ile yapılabilir —
şu an yalnızca sinyal sayısı biliniyor, kârlılık bilinmiyor.

---

## 5. Henüz bilinmeyen

Bu rapor **yalnızca sinyal frekansını** ölçer. Hiçbir kârlılık iddiası içermez.
Sharpe, Maximum Drawdown ve komisyon/spread sonrası getiri için backtest motoru
gerekiyor (anayasa 3.1, 3.5) — bir sonraki adım.

---

# EK: 4H Yön + 15dk Zamanlama — 14 Ağustos 2026

**Betik:** `scripts/combined_report.py`, `src/finans_cortex/strategy.py`

## 6. Look-ahead doğrulaması

04:00-08:00 aralığını kapsayan 4H barı 08:00'de kapanır; yönü ancak o andan
sonra bilinebilir. Her 4H barına `valid_from = bucket + 4 saat` damgası vurulup
15dk barlarıyla `join_asof(backward)` ile eşleştirildi.

**8 enstrümanda da ihlal sayısı 0.** Ortalama gecikme 2,2-3,2 saat (0-4 saat
arası düzgün dağılımın beklenen değeri ~2 saat; fazlası hafta sonu boşlukları).
Maksimum gecikme 71-147 saat — hafta sonu ve tatil kapanışları, beklenen.

## 7. İlk deneme başarısızdı — ve nedeni öğreticiydi

İlk kurgu: 4H yönüyle aynı taraftaki **her** 15dk sinyalini giriş saymak.

| | Sonuç |
|---|---|
| Ham 15dk | ayda 92-111 sinyal |
| 4H hizalı | ayda 43-52 sinyal |
| Azalma | **8 enstrümanda da tam 2,1×** |

8 farklı varlık sınıfında aynı sayının çıkması tesadüf değil: 4H yönü 50/50,
15dk sinyali 50/50 ve ikisi **bağımsızsa** yarısı elenir — yani 2,0×. Ölçülen
2,1×, filtrenin yazı-turadan fazla bilgi katmadığını gösteriyor. (Hafif fazlalık,
15dk sinyallerinin biraz daha sık trende KARŞI çıkmasından; pullback'ler.)

**Hata neredeydi:** pozisyon 4H trendine aittir. Tek bir trend bacağı içinde
onlarca giriş üretmek, 15dk'yı yön kaynağı gibi kullanmak demekti.

**Düzeltme:** bir trend bacağı boyunca yalnızca **İLK** hizalı 15dk sinyali
giriş sayılır (`leg` mantığı, `strategy.py`).

| | Ham 15dk | 4H hizalı | Bacak başı tek | Toplam azalma |
|---|---|---|---|---|
| EURUSD | 111,2 | 52,4 | **6,0** | 18,5× |
| XAUUSD | 92,5 | 43,4 | **5,3** | 17,5× |
| XAGUSD | 97,2 | 45,9 | **5,3** | 18,3× |
| BRENT | 97,9 | 45,8 | **5,8** | 16,9× |
| WTI | 106,3 | 49,7 | **6,1** | 17,4× |
| DJ | 91,9 | 43,0 | **5,6** | 16,4× |
| DAX | 91,7 | 42,8 | **5,6** | 16,4× |
| FTSE | 93,9 | 44,0 | **5,3** | 17,7× |

Ayda ~5-6 giriş, 4H'ın kendi temposuyla (~7/ay) uyumlu. Frekans sorunu çözüldü.

## 8. OLUMSUZ BULGU: 15dk zamanlaması giriş fiyatını KÖTÜLEŞTİRİYOR

Karşılaştırma: bacağı başlatan 4H barının kapanışından girmek (naif) ile ilk
hizalı 15dk sinyalinden girmek (zamanlanmış). Pozitif bp = zamanlama kazandırdı.

| Enstrüman | İşlem | Ort. bp | Medyan bp | Kazandıran % |
|---|---|---|---|---|
| EURUSD | 1.053 | **−4,3** | −5,1 | 24,8 |
| XAUUSD | 1.463 | **−14,0** | −12,7 | 22,3 |
| XAGUSD | 739 | **−23,4** | −22,1 | 20,3 |
| BRENT | 805 | **−23,6** | −23,8 | 23,6 |
| WTI | 1.001 | **−23,5** | −18,9 | 26,6 |
| DJ | 781 | **−10,4** | −9,9 | 24,8 |
| DAX | 778 | **−12,1** | −13,1 | 25,1 |
| FTSE | 742 | **−10,9** | −10,9 | 26,3 |

**8 enstrümanda da negatif. İşlemlerin yalnızca %20-27'sinde daha iyi fiyat.**

Mekanizması açık: 15dk BUY sinyali, fiyat 15dk short_stop'unu yukarı kırdığında
oluşur — yani yukarı hareket ZATEN olduktan sonra. Trend yönünde beklemek,
güçlenmiş fiyattan almak demektir. Gümüş/petrolde −23 bp, tipik spread+komisyon
mertebesinde; önemsiz bir maliyet değil.

### Ama bu "15dk gereksiz" demek DEĞİL

Daha kötü giriş fiyatı ≠ daha kötü kârlılık. Teyit beklemek, hemen dönen sahte
bacakları elemiş olabilir; o zaman ödenen 4-24 bp bir sigorta primidir. Bu ölçüm
yalnızca **giriş fiyatına** bakar, pozisyonun sonrasına bakmaz.

**Bu soruyu ancak kâr/zarar hesaplayan bir backtest çözer.** İki alternatif yan
yana test edilmeli:
- A: 4H bacağı başlar başlamaz 4H kapanışından gir
- B: ilk hizalı 15dk sinyalini bekle (mevcut kurgu)

Şu an B'nin A'ya göre 4-24 bp daha pahalı girdiğini biliyoruz; daha çok mu
kazandırdığını **bilmiyoruz**.

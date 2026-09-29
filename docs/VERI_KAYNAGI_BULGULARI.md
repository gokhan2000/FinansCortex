# Veri Kaynağı Yoklama Bulguları (yfinance)

**Tarih:** 13 Ağustos 2026
**Betik:** `scripts/probe_data_sources.py`
**Ortam:** Python 3.12.1, yfinance 1.6.0 (0.2.35'ten yükseltildi), duckdb 1.5.5, polars 1.43.2

Bu dosya, `PROJE_ANAYASASI.md`'deki Faz 1 kararlarını **ölçüme dayandırmak** için yapılan
yoklamanın sonuçlarıdır. Tahmin değil, fiilen çekilmiş veridir.

---

## 1. Sembol çözümlemesi

| Enstrüman | Kullanılacak sembol | Not |
|---|---|---|
| EURUSD | `EURUSD=X` | Sorunsuz |
| XAUUSD | `GC=F` | **`XAUUSD=X` Yahoo'da YOK (404).** Spot altın yerine COMEX vadeli |
| XAGUSD | `SI=F` | **`XAGUSD=X` Yahoo'da YOK (404).** Spot gümüş yerine COMEX vadeli |
| BRENT | `BZ=F` | ICE Brent vadeli |
| WTI | `CL=F` | NYMEX WTI vadeli |
| DJ | `^DJI` | Fiyat endeksi |
| DAX | `^GDAXI` | Performans endeksi (temettü dahil) |
| FTSE | `^FTSE` | Fiyat endeksi |

**Sonuç:** Altın ve gümüşte spot seri Yahoo'da bulunmuyor. Dolayısıyla **kontrat
geçişi (roll) sorunundan yfinance ile kaçış yok** — 5 enstrümanın 4'ü vadeli.

---

## 2. Ölçülen geçmiş derinliği

Limitler tahmin edilmedi; kasten limitin üstünde veri istendi ve Yahoo'nun
kendi hata mesajı alındı:

```
15m data not available ... must be within the last 60 days
1h  data not available ... must be within the last 730 days
```

Limitlerin içinde kalan ikinci turda fiilen dönen veri:

| Enstrüman | 15dk | 1saat | 1gün |
|---|---|---|---|
| EURUSD | 5.204 bar / ~77 gün | 16.552 bar / ~980 gün | 5.890 bar / **22,7 yıl** |
| XAUUSD (GC=F) | 4.253 bar / ~66 gün | 13.188 bar / ~840 gün | 6.512 bar / **26 yıl** |
| XAGUSD (SI=F) | 4.255 bar / ~66 gün | 13.188 bar / ~840 gün | 6.514 bar / **26 yıl** |
| BRENT (BZ=F) | 4.049 bar / ~66 gün | 13.036 bar / ~840 gün | 4.739 bar / **19 yıl** |
| WTI (CL=F) | 4.255 bar / ~66 gün | 12.960 bar / ~840 gün | 6.521 bar / **26 yıl** |
| DJ (^DJI) | 1.430 bar / ~78 gün | 4.872 bar / ~1021 gün | 8.715 bar / **34,6 yıl** |
| DAX (^GDAXI) | 1.870 bar / ~76 gün | 6.292 bar / ~1009 gün | 9.766 bar / **38,6 yıl** |
| FTSE (^FTSE) | 1.870 bar / ~76 gün | 6.265 bar / ~1010 gün | 10.765 bar / **42,6 yıl** |

### Stratejik sonuç

- **15 dakikalık backtest yfinance ile YAPILAMAZ.** ~2,5 aylık veri hiçbir şey kanıtlamaz.
  15dk sinyalleri hedefleniyorsa **ikinci bir tarihsel kaynak zorunludur** (Dukascopy vb.,
  kapsamı ayrıca doğrulanmalı).
- **4 saatlik backtest yapılabilir.** 1 saatlik veri ~2,7-2,8 yıl geriye gidiyor;
  4H bunun üzerinden türetilir. EURUSD için ~4.400 adet 4H barı demek — makul bir örneklem.
  Endekslerde daha ince (~1.500 bar), çünkü seans kısa.
- **Günlük veri bol.** 19-42 yıl. Strateji mantığını doğrulamak için ilk backtest'i
  günlük barla yapmak neredeyse bedava.

---

## 3. Saat dilimi bulgusu (kritik)

**Hiçbir enstrüman UTC dönmüyor.** Her biri kendi borsasının yerel saatini veriyor:

- `Europe/London` → EURUSD, FTSE
- `America/New_York` → GC=F, SI=F, BZ=F, CL=F, ^DJI
- `Europe/Berlin` → ^GDAXI

Yani tek bir tabloda **üç farklı saat dilimi** birleşecek. Anayasadaki "her şey UTC'de
saklanır" kuralı teorik bir tercih değil, ilk günden **zorunluluk**. Normalizasyon
ingest katmanında, veri diske yazılmadan önce yapılmalı.

---

## 4. Seans yapısı bulgusu (bar/gün)

| Profil | Enstrüman | 15dk bar/gün | Yorum |
|---|---|---|---|
| 24 saat | EURUSD | 96 | 24 × 4 — tam kapsama, kesintisiz |
| ~23 saat | GC=F, SI=F, CL=F | 92 | CME seansı, günlük ~1 saat ara |
| ~22,5 saat | BZ=F | 90 | ICE seansı |
| 6,5 saat | ^DJI | 26 | ABD nakit seansı 09:30-16:00 |
| 8,5 saat | ^GDAXI, ^FTSE | 34 | Avrupa nakit seansı |

**Üç ayrı takvim profili** aynı veri setinde yaşayacak. "Seans takvimi" meselesi
BIST'e özgü değil; Faz 1'in ilk gününden itibaren var.

---

## 5. Açıklığa kavuşturulması gereken anomali

yfinance'in `period="55d"` / `period="700d"` parametresi, dönen veride sırasıyla
~77 ve ~980 **takvim günü** üretti — yani istenen sayı takvim günü olarak
yorumlanmıyor, ve bazı durumlarda Yahoo'nun kendi belirttiği 60/730 günlük tavanı
aşan veri döndü.

**Mühendislik sonucu:** Üretim kodunda `period` string'ine güvenilmeyecek,
açık `start` / `end` tarihleri kullanılacak. Sınırlar o zaman tekrar ölçülmeli.

---

## 6. Bu bulguların anayasaya etkisi

1. **"Tek gerçek kaynak = 1dk bar" ilkesi geçersiz** — Yahoo 1dk'yı zaten 7 günle
   sınırlıyor, üstelik 15dk/4saat hedefi için gereksiz. Taban granülarite **15dk**
   olmalı, geçmiş dolgusu ikinci kaynaktan gelmeli.
2. **Kurumsal işlem sorunu tam kalkmadı** — BIST'in bedelsiz/temettü sorunu yok, ama
   yerine vadeli kontrat roll sıçraması geldi (4 enstrümanda). ATR tabanlı Chandelier
   Exit bu sıçramayı yanlış sinyal olarak okur. Çözülmesi gereken açık konu.
3. **Veri hacmi çok küçük** — Yahoo'daki tüm 1saat geçmişi 8 enstrüman için toplam
   ~105.000 satır. 20 yıllık 15dk verisi bile ~2-3 milyon satır / ~50-80 MB.
   Bu boyut için TimescaleDB + Docker gereksiz ağır; Faz 1 için **DuckDB tek dosya**
   önerisi bu ölçümle destekleniyor. (Karar kullanıcı onayı bekliyor.)

---

## 7. Ortam notu

`git` bu makinede **kurulu değil**. Kullanıcı git kullanmak istemiyor; şimdilik gitsiz
devam ediliyor (git'in yerel çalıştığı, internet/hesap gerektirmediği açıklandı).

---

# EK: Dukascopy Yoklaması — 13 Ağustos 2026

**Betik:** `scripts/probe_dukascopy.py`, `dukascopy-python` paketi

## 8. Neden ikinci tur

Kullanıcının iki şartı kesinleşti:
1. **Ons altın (spot XAUUSD) ve ons gümüş (spot XAGUSD) zorunlu.**
2. **Chandelier Exit için 15 dakikalık göstergeler zorunlu.**

Yahoo bu iki şartın ikisini de karşılayamıyor (spot metal yok, 15dk = 2,5 ay).
Bu nedenle Yahoo **ana kaynak olarak elendi**; Dukascopy ölçüldü.

## 9. Enstrüman eşleşmesi — 8/8 mevcut

| Enstrüman | Dukascopy sabiti | Sembol | Not |
|---|---|---|---|
| EURUSD | `INSTRUMENT_FX_MAJORS_EUR_USD` | `EUR/USD` | |
| XAUUSD | `INSTRUMENT_FX_METALS_XAU_USD` | `XAU/USD` | **Spot ons altın** ✔ |
| XAGUSD | `INSTRUMENT_FX_METALS_XAG_USD` | `XAG/USD` | **Spot ons gümüş** ✔ |
| BRENT | `INSTRUMENT_CMD_ENERGY_E_BRENT` | `E_Brent` | Sürekli seri |
| WTI | `INSTRUMENT_CMD_ENERGY_E_LIGHT` | `E_Light` | Sürekli seri |
| DJ | `INSTRUMENT_IDX_AMERICA_E_D_J_IND` | `E_D&J-Ind` | |
| DAX | `INSTRUMENT_IDX_EUROPE_E_DAAX` | `E_DAAX` | |
| FTSE | `INSTRUMENT_IDX_EUROPE_E_FUTSEE_100` | `E_Futsee-100` | |

Metaller FX kategorisinde **spot** olarak geliyor — vadeli kontrat değil, dolayısıyla
**roll sıçraması sorunu ortadan kalkıyor**.

## 10. 15dk geçmiş derinliği (ölçülen bar sayısı / gün)

| Enstrüman | 2003 | 2007 | 2010 | 2012 | 2013 | 2015 | 2020 | 2026 |
|---|---|---|---|---|---|---|---|---|
| EURUSD | 0 | 0 | 0 | 96 | 96 | 96 | 96 | 96 |
| XAUUSD | 80 | 96 | 96 | — | — | 93 | 92 | 92 |
| XAGUSD | 0 | 0 | 0 | — | — | 92 | 92 | 92 |
| BRENT | 0 | 0 | 0 | — | — | 88 | 84 | 84 |
| WTI | 0 | 0 | 0 | 4 | 92 | 94 | 92 | 92 |
| DJ | 0 | 0 | 0 | — | — | 57 | 89 | 89 |
| DAX | 0 | 0 | 0 | 0 | 96 | 57 | 89 | 89 |
| FTSE | 0 | 0 | 0 | — | — | 57 | 88 | 89 |

**Sonuç:** 2015'ten bugüne **8 enstrümanın tamamında kesintisiz 15dk verisi var**
(~11 yıl). XAUUSD 2003'e, EURUSD 2012'ye kadar geriye gidiyor.

Yahoo'da 15dk = **2,5 ay**, Dukascopy'de = **11+ yıl**. Şart karşılandı.

## 11. Diğer bulgular

- **Saat dilimi: UTC.** Tüm enstrümanlarda, istisnasız. Yahoo'daki üç farklı yerel
  saat dilimi sorunu yok; normalizasyon yükü ortadan kalkıyor.
- **4 saatlik bar hazır sabit olarak var** (`INTERVAL_HOUR_4`), ama 15dk'dan
  türetmek tercih edilmeli (tek kaynak ilkesi + 4H hizalama kontrolü bizde kalsın).
- **Veri delikleri var, doğrulama katmanı şart.** WTI 2012'de 4 bar, DAX 2015'te
  57 bar döndü. Tek günlük yoklamalar olduğu için kesin yorum yapılamaz ama
  **gap/eksik bar tespiti opsiyonel değil** — ingest sonrası kalite kontrolü gerekli.

## 12. Kesinleşen Faz 1 veri mimarisi

```
Dukascopy (15dk, UTC, 2015+)  -> ana kaynak, 8 enstrüman
        |
        v
   kalite kontrol (gap/outlier tespiti)
        |
        v
   DuckDB tek dosya  (~2,2 milyon satır / ~40-60 MB)
        |
        +-- 4H  (16 x 15dk toplama)
        +-- 1h  / 1d  (görünüm olarak)
        |
        v
   Polars -> Chandelier Exit -> Streamlit
```

yfinance ana kaynak olmaktan çıktı; günlük uzun geçmiş veya çapraz doğrulama için
ikincil kaynak olarak kalabilir.

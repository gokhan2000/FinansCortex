"""Ortak (dinamik) stop-loss katmani -- her strateji icin ayni.

Kullanici (18 Ekim 2026): *"butun stratejilere dinamik olarak stop-loss koyalim;
yuzde veya su kadar miktar veya su tutara dusarse stop-loss olsun."*

Strateji motorlarina dokunmaz: motorun urettigi ISLEM LISTESI uzerinde
calisir. Her islem icin giristen sonraki barlara bakilir; stop seviyesine
dokunan ilk barda islem o seviyeden kapatilir, getiri maliyet dahil yeniden
hesaplanir, sermaye egrisi ve olculer yeniden uretilir. Sonraki islemler
etkilenmez (motorlar islemleri arka arkaya, ust uste binmeden uretir).

Kar al ayni modlarla, ters yonde (lehte); sira kotumser: once stop, sonra kar al.

Modlar
    yuzde : giris fiyatinin %X'i kadar ters yonde (AL'da asagi, SAT'ta yukari)
    puan  : giristen X FIYAT BIRIMI kadar ters yonde (ornegin altinda 30 dolar)
    seviye: mutlak fiyat; AL'da fiyat X'e dusunce, SAT'ta X'e cikinca. Seviye
            girisin ters tarafinda degilse (AL'da giristen yukarida) o islem
            icin yok sayilir -- stop olamaz, anlik cikis olurdu.

Mum ici Chandelier cikisi (`ce_ic`) stop-loss'tan SONRA, kar al'dan ONCE denenir.

Kurallar (Strateji 2.1'in `zarar_kes` mantigiyla ayni, kotumser):
    - Giris bari haric (giris kapanista; barin tepe/dibi giristen ONCEDIR).
    - Bar seviyenin otesinde ACILIRSA (bosluk) cikis acilistan, seviyeden degil.
    - Orijinal cikis barinda da stop goruldüyse stop kazanir (kotumser).
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import timedelta

import polars as pl

KAPALI, YUZDE, PUAN, SEVIYE = "kapali", "yuzde", "puan", "seviye"
MODLAR = {"Kapali": KAPALI, "Yuzde (%)": YUZDE,
          "Miktar (fiyat birimi)": PUAN, "Fiyat seviyesi": SEVIYE}
NEDEN = "stop_loss"


@dataclass(frozen=True)
class StopAyar:
    """Hashable (Streamlit onbellek anahtari olarak kullanilir)."""
    mod: str = KAPALI
    deger: float = 0.0
    alt_cikis: bool = False
    """Alt zaman diliminde cikis (23.10.2026): pozisyon acikken 15 dakikalik
    Chandelier pozisyonun TERSINE doner donmez (o 15dk barin kapanisinda) cik;
    4 saatlik / gunluk mumun kapanmasini bekleme. Yalniz Strateji 2/3; 15dk
    veri yalniz bu secenek acikken okunur. Zaten ters durumda giren islem
    icin, 15dk yon once lehe donup SONRA tekrar dondugunde tetiklenir."""
    ce_ic: bool = False
    """Mum ici Chandelier cikisi (23.10.2026): pozisyon yonundeki Chandelier
    cizgisine (bir onceki barin degeri, mum acilirken bilinir) fiyat mum
    ICINDE dokunur dokunmaz cik -- mumun kapanmasini bekleme. Yalniz
    Chandelier sutunu olan sonuclarda (Strateji 2/3) etkilidir; HA olceginde
    hesaplanan cizgi gercek fiyata uygulandigi icin YAKLASIKTIR."""

    @property
    def acik(self) -> bool:
        return self.mod != KAPALI and self.deger > 0

    @property
    def herhangi(self) -> bool:
        return self.acik or self.ce_ic or self.alt_cikis


KAR_NEDEN = "kar_al"
CE_IC_NEDEN = "chandelier_ic"
ALT_NEDEN = "alt_dilim"


def seviye(ayar: StopAyar, giris: float, yon: int,
           kar: bool = False) -> float | None:
    """Islem icin stop (kar=True ise kar al) fiyati; gecersizse None."""
    if not ayar.acik:
        return None
    ters = 1 if kar else -1       # kar al lehte, stop aleyhte yonde
    if ayar.mod == YUZDE:
        s = giris * (1 + ters * yon * ayar.deger / 100.0)
    elif ayar.mod == PUAN:
        s = giris + ters * yon * ayar.deger
    else:
        s = ayar.deger
        if (s - giris) * yon * ters <= 0:   # seviye yanlis tarafta
            return None
    return s if s > 0 else None


def aciklama(ayar: StopAyar) -> str:
    if not ayar.acik:
        return "kapali"
    d = ("{:.4f}".format(ayar.deger)).rstrip("0").rstrip(".").replace(".", ",")
    return {YUZDE: "%{} ters yonde".format(d),
            PUAN: "{} fiyat birimi ters yonde".format(d),
            SEVIYE: "fiyat {} seviyesinde".format(d)}[ayar.mod]


def _alt_dene(t: dict, bar_ici: bool, orijinal_cikis, a_ts, a_dir, a_cl,
              bar_dt, g: float, d: int, cost: float) -> dict:
    """15dk Chandelier pozisyonun tersine donduyse (ilk donus) o barin
    kapanisinda cik. Bar-ici bir cikis (stop/Chandelier/kar al) zaten varsa,
    alt dilim ancak o mumun BASLAMASINDAN once kapanmis bir 15dk barla onu
    gecebilir (mum icinde sira bilinemez -> kotumser: bar-ici cikis kazanir)."""
    limit = t["cikis_ts"] if bar_ici else orijinal_cikis
    giris_kapanis = t["giris_ts"] + bar_dt
    k = bisect_right(a_ts, giris_kapanis)       # giris kapanisindan SONRA
    while k < len(a_ts) and a_ts[k] <= limit:
        if a_dir[k] == -d and (k == 0 or a_dir[k - 1] != -d):
            px = a_cl[k]
            return dict(t, cikis_ts=a_ts[k] - timedelta(minutes=15),
                        cikis=px, neden=ALT_NEDEN,
                        stop=t["stop"], hedef=float("nan"),
                        getiri=(px - g) * d / g - cost, R=float("nan"))
        k += 1
    return t


def trades_uygula(trades: pl.DataFrame, bars: pl.DataFrame, ayar: StopAyar,
                  cost_bp: float, kar: StopAyar = StopAyar(),
                  alt: pl.DataFrame | None = None,
                  bar_saat: float = 0.0) -> pl.DataFrame:
    """`ayar`: stop-loss, `kar`: kar al (ayni modlar; 18.10.2026 eklendi).

    Bar icinde sira kotumser: once stop (bosluk, sonra seviye), sonra kar al.
    Ayni barda ikisi de goruluyorsa ZARAR sayilir (Strateji 1/2.1 ile ayni)."""
    if not (ayar.herhangi or kar.acik) or trades.is_empty():
        return trades
    ts = bars["ts"].to_list()
    o, h, lo = (bars[c].to_list() for c in ("open", "high", "low"))
    ce_l = ce_s = None
    if ayar.ce_ic and "long_stop" in bars.columns:
        ce_l = bars["long_stop"].to_list()
        ce_s = bars["short_stop"].to_list()
    a_ts = a_dir = a_cl = None
    if (ayar.alt_cikis and alt is not None and not alt.is_empty()
            and bar_saat >= 1):
        a_ts = alt["ts_onay"].to_list()
        a_dir = alt["ce15_dir"].to_list()
        a_cl = alt["close"].to_list()
    bar_dt = timedelta(hours=bar_saat)
    cost = cost_bp / 10000.0
    satirlar = []
    j = 0
    for t in trades.to_dicts():
        # Islem listesi zaman sirali: bar indeksini ileri dogru tasi.
        while j < len(ts) and ts[j] < t["giris_ts"]:
            j += 1
        i0 = j
        i1 = i0
        k = i0
        while k < len(ts) and ts[k] <= t["cikis_ts"]:
            i1 = k
            k += 1
        d, g = t["yon"], t["giris"]
        orijinal_cikis = t["cikis_ts"] + bar_dt     # motor cikisi: mum kapanisi
        bar_ici = False
        sl = seviye(ayar, g, d)
        tp = seviye(kar, g, d, kar=True)
        for i in range(i0 + 1, i1 + 1):
            px = neden = None
            if sl is not None:
                if (o[i] <= sl) if d == 1 else (o[i] >= sl):
                    px, neden = o[i], NEDEN
                elif (lo[i] <= sl) if d == 1 else (h[i] >= sl):
                    px, neden = sl, NEDEN
            if px is None and ce_l is not None:
                lv = (ce_l if d == 1 else ce_s)[i - 1]
                if lv == lv and lv > 0:           # NaN degil
                    if (o[i] <= lv) if d == 1 else (o[i] >= lv):
                        px, neden = o[i], CE_IC_NEDEN
                    elif (lo[i] <= lv) if d == 1 else (h[i] >= lv):
                        px, neden = lv, CE_IC_NEDEN
            if px is None and tp is not None:
                if (o[i] >= tp) if d == 1 else (o[i] <= tp):
                    px, neden = o[i], KAR_NEDEN
                elif (h[i] >= tp) if d == 1 else (lo[i] <= tp):
                    px, neden = tp, KAR_NEDEN
            if px is not None:
                risk = abs(g - sl) if sl is not None else float("nan")
                t = dict(t, cikis_ts=ts[i], cikis=px, neden=neden,
                         stop=sl if sl is not None else float("nan"),
                         hedef=tp if tp is not None else float("nan"),
                         getiri=(px - g) * d / g - cost,
                         R=(px - g) * d / risk if risk == risk and risk > 0
                         else float("nan"))
                bar_ici = True
                break
        if a_ts is not None:
            t = _alt_dene(t, bar_ici, orijinal_cikis, a_ts, a_dir, a_cl,
                          bar_dt, g, d, cost)
        satirlar.append(t)
    return pl.DataFrame(satirlar, schema=trades.schema)


def uygula(res, ayar: StopAyar, motor, kar: StopAyar = StopAyar(),
           alt: pl.DataFrame | None = None, bar_saat: float = 0.0):
    """`motor`: strateji modulu (daily_equity / metrics icin)."""
    if not (ayar.herhangi or kar.acik) or res.trades.is_empty():
        return res
    trades = trades_uygula(res.trades, res.bars, ayar, res.cost_bp, kar, alt,
                           bar_saat)
    daily = motor.daily_equity(trades, res.bars)
    return replace(res, trades=trades, daily=daily,
                   metrics=motor.metrics(trades, daily, res.bars))

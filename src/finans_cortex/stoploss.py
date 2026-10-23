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
from dataclasses import dataclass, replace

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
        return self.acik or self.ce_ic


KAR_NEDEN = "kar_al"
CE_IC_NEDEN = "chandelier_ic"


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


def trades_uygula(trades: pl.DataFrame, bars: pl.DataFrame, ayar: StopAyar,
                  cost_bp: float, kar: StopAyar = StopAyar()) -> pl.DataFrame:
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
                break
        satirlar.append(t)
    return pl.DataFrame(satirlar, schema=trades.schema)


def uygula(res, ayar: StopAyar, motor, kar: StopAyar = StopAyar()):
    """`motor`: strateji modulu (daily_equity / metrics icin)."""
    if not (ayar.herhangi or kar.acik) or res.trades.is_empty():
        return res
    trades = trades_uygula(res.trades, res.bars, ayar, res.cost_bp, kar)
    daily = motor.daily_equity(trades, res.bars)
    return replace(res, trades=trades, daily=daily,
                   metrics=motor.metrics(trades, daily, res.bars))

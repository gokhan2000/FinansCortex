"""Ortak (dinamik) stop-loss katmani -- her strateji icin ayni.

Kullanici (18 Ekim 2026): *"butun stratejilere dinamik olarak stop-loss koyalim;
yuzde veya su kadar miktar veya su tutara dusarse stop-loss olsun."*

Strateji motorlarina dokunmaz: motorun urettigi ISLEM LISTESI uzerinde
calisir. Her islem icin giristen sonraki barlara bakilir; stop seviyesine
dokunan ilk barda islem o seviyeden kapatilir, getiri maliyet dahil yeniden
hesaplanir, sermaye egrisi ve olculer yeniden uretilir. Sonraki islemler
etkilenmez (motorlar islemleri arka arkaya, ust uste binmeden uretir).

Modlar
    yuzde : giris fiyatinin %X'i kadar ters yonde (AL'da asagi, SAT'ta yukari)
    puan  : giristen X FIYAT BIRIMI kadar ters yonde (ornegin altinda 30 dolar)
    seviye: mutlak fiyat; AL'da fiyat X'e dusunce, SAT'ta X'e cikinca. Seviye
            girisin ters tarafinda degilse (AL'da giristen yukarida) o islem
            icin yok sayilir -- stop olamaz, anlik cikis olurdu.

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

    @property
    def acik(self) -> bool:
        return self.mod != KAPALI and self.deger > 0


def seviye(ayar: StopAyar, giris: float, yon: int) -> float | None:
    """Islem icin stop fiyati; gecersizse None."""
    if not ayar.acik:
        return None
    if ayar.mod == YUZDE:
        s = giris * (1 - yon * ayar.deger / 100.0)
    elif ayar.mod == PUAN:
        s = giris - yon * ayar.deger
    else:
        s = ayar.deger
        if (s - giris) * yon >= 0:        # girisin ters tarafinda degil
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
                  cost_bp: float) -> pl.DataFrame:
    if not ayar.acik or trades.is_empty():
        return trades
    ts = bars["ts"].to_list()
    o, h, lo = (bars[c].to_list() for c in ("open", "high", "low"))
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
        if sl is not None:
            for i in range(i0 + 1, i1 + 1):
                if d == 1:
                    gap, vurdu = o[i] <= sl, lo[i] <= sl
                else:
                    gap, vurdu = o[i] >= sl, h[i] >= sl
                if gap or vurdu:
                    px = o[i] if gap else sl
                    risk = abs(g - sl)
                    t = dict(t, cikis_ts=ts[i], cikis=px, neden=NEDEN,
                             stop=sl, hedef=float("nan"),
                             getiri=(px - g) * d / g - cost,
                             R=(px - g) * d / risk if risk > 0 else
                             float("nan"))
                    break
        satirlar.append(t)
    return pl.DataFrame(satirlar, schema=trades.schema)


def uygula(res, ayar: StopAyar, motor):
    """`motor`: strateji modulu (daily_equity / metrics icin)."""
    if not ayar.acik or res.trades.is_empty():
        return res
    trades = trades_uygula(res.trades, res.bars, ayar, res.cost_bp)
    daily = motor.daily_equity(trades, res.bars)
    return replace(res, trades=trades, daily=daily,
                   metrics=motor.metrics(trades, daily, res.bars))

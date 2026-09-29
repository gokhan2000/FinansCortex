"""Islem listesinden performans: gunluk sermaye egrisi ve olculer.

Stratejiden BAGIMSIZ. Her strateji motoru (ema_two_close, heikin_range, ...)
kendi kurallariyla bir islem listesi uretir; buradan sonrasi ortaktir --
ayni olculer ayni sekilde hesaplansin, arayuz de tek bir sozluk sekli gorsun.

Bu dosya once ema_two_close.py icindeydi; Strateji 2 eklenirken ayni kodu
kopyalamamak icin ayrildi. ema_two_close bu isimleri disa aktarmaya devam
ediyor (eski cagrilar bozulmasin).

ISLEM LISTESI SOZLESMESI (TRADE_SCHEMA)
    giris_ts/cikis_ts  UTC, kapanis damgasi
    yon                1 uzun, -1 kisa
    giris/cikis        GERCEK fiyat (Heikin Ashi gibi turetilmis fiyat DEGIL)
    stop/hedef         bilgi amacli; yoksa None
    neden              cikis nedeni etiketi
    getiri             oransal, MALIYET DAHIL (spread dusulmus)
    R                  getiri / baslangic riski; risk tanimsizsa NaN
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

import polars as pl

# Gunluk kesim 22:00 UTC: ts + 2 saatin takvim gunu = islem gunu.
DAY_ROLL = timedelta(hours=2)

TRADE_SCHEMA = {
    "giris_ts": pl.Datetime("us", "UTC"),
    "cikis_ts": pl.Datetime("us", "UTC"),
    "yon": pl.Int8,
    "giris": pl.Float64,
    "cikis": pl.Float64,
    "stop": pl.Float64,
    "hedef": pl.Float64,
    "neden": pl.Utf8,
    "getiri": pl.Float64,
    "R": pl.Float64,
}


@dataclass
class Result:
    bars: pl.DataFrame
    trades: pl.DataFrame
    daily: pl.DataFrame
    metrics: dict
    cost_bp: float


def daily_equity(trades: pl.DataFrame, bars: pl.DataFrame) -> pl.DataFrame:
    """Islem gunu bazinda getiri, sermaye egrisi ve al-tut karsilastirmasi.

    Acik pozisyon HER GUN o gunun kapanisindan degerlenir (24 Eylul 2026).
    Eskiden islem yalniz CIKIS gununde yaziliyordu: pozisyon %30 dusup
    toparlansa egride hic gorunmuyordu, al-tut ise her gun degerleniyordu --
    MaxDD/Sharpe iki taraf icin farkli olcuyle hesaplaniyordu.

    Islemin degeri V = 1 + yon*(fiyat - giris)/giris; cikis gununde
    V = 1 + getiri (maliyet dahil). Gunluk getiri V/V_onceki - 1, yani gunluk
    getirilerin carpimi islemin getirisine BIREBIR esittir: son sermaye eski
    yontemle ayni, yalniz yol farkli. `bars` icinde `tday` sutunu olmalidir
    (islem gunu; bkz. DAY_ROLL).
    """
    days = bars.group_by("tday", maintain_order=True).agg(
        pl.col("close").last().alias("close")
    )
    if trades.is_empty():
        per = pl.DataFrame(schema={"tday": pl.Date, "ret": pl.Float64})
    else:
        per = (
            trades.with_row_index("_i")
            .with_columns(
                (pl.col("giris_ts") + DAY_ROLL).dt.date().alias("_g"),
                (pl.col("cikis_ts") + DAY_ROLL).dt.date().alias("_c"),
            )
            .with_columns(pl.date_ranges("_g", "_c").alias("tday"))
            .explode("tday")
            .join(days.select("tday", pl.col("close").alias("_kap")),
                  on="tday", how="inner")
            .sort("_i", "tday")
            .with_columns(
                pl.when(pl.col("tday") == pl.col("_c"))
                .then(1 + pl.col("getiri"))
                .otherwise(1 + pl.col("yon") * (pl.col("_kap") - pl.col("giris"))
                           / pl.col("giris"))
                .alias("_v")
            )
            .with_columns(
                (pl.col("_v") / pl.col("_v").shift(1).over("_i").fill_null(1.0))
                .alias("_r")
            )
            .group_by("tday")
            .agg((pl.col("_r").product() - 1).alias("ret"))
        )
    d = (
        days.join(per, on="tday", how="left")
        .with_columns(pl.col("ret").fill_null(0.0))
        .sort("tday")
    )
    return d.with_columns(
        (1 + pl.col("ret")).cum_prod().alias("equity"),
        (pl.col("close") / pl.col("close").first()).alias("al_tut"),
    )


def metrics(trades: pl.DataFrame, daily: pl.DataFrame, bars: pl.DataFrame) -> dict:
    nan = float("nan")
    span = (bars["ts"][-1] - bars["ts"][0]).total_seconds() / 86400
    months = span / 30.44
    years = span / 365.25

    out = {
        "islem": trades.height,
        "islem_ay": round(trades.height / months, 1) if months > 0 else nan,
        "kazanan_%": nan, "kar_faktoru": nan, "getiri_%": nan, "CAGR_%": nan,
        "Sharpe": nan, "MaxDD_%": nan, "ort_R": nan, "ort_islem_bp": nan,
        "long_%": nan, "short_%": nan,
        "al_tut_%": round(100 * float(bars["close"][-1] / bars["close"][0] - 1), 1),
        "nedenler": {},
    }
    if trades.is_empty() or daily.height < 2:
        return out

    r = trades["getiri"]
    wins = r.filter(r > 0)
    losses = r.filter(r < 0)
    gross_win = float(wins.sum()) if wins.len() else 0.0
    gross_loss = abs(float(losses.sum())) if losses.len() else 0.0

    eq = daily["equity"]
    total = float(eq[-1] - 1.0)
    dr = daily["ret"]
    sd = float(dr.std())
    peak = eq.cum_max()
    cagr = ((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 and total > -1 else nan

    def side(direction: int) -> float:
        s = trades.filter(pl.col("yon") == direction)["getiri"]
        return round(100 * (float((s + 1).product()) - 1), 1) if s.len() else 0.0

    mean_r = trades["R"].mean()

    out.update({
        "kazanan_%": round(100.0 * wins.len() / r.len(), 1),
        "kar_faktoru": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "getiri_%": round(100 * total, 1),
        "CAGR_%": round(100 * cagr, 2) if cagr == cagr else nan,
        "Sharpe": round(float(dr.mean()) / sd * math.sqrt(252), 2) if sd > 0 else nan,
        "MaxDD_%": round(100 * float(((eq - peak) / peak).min()), 1),
        "ort_R": round(float(mean_r), 2) if mean_r is not None else nan,
        "ort_islem_bp": round(float(r.mean()) * 10000, 1),
        "long_%": side(1),
        "short_%": side(-1),
        "nedenler": dict(trades.group_by("neden").len().sort("len", descending=True).iter_rows()),
    })
    return out

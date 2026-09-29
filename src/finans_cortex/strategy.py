"""Çok zaman dilimli Chandelier Exit stratejisi.

Ölçüm sonucu (docs/CHANDELIER_BULGULARI.md): Chandelier'in yön değiştirme
olasılığı bar başına ~%5 ve zaman diliminden BAĞIMSIZ. Yani 15dk'nın gürültülü
olmasının sebebi göstergenin kötülüğü değil, bar boyutu. Parametre oynayarak
düzelmez; iki zaman dilimini farklı işlerde kullanmak gerekir:

    4H   -> YÖN        (ayda ~7 sinyal, trendi tanımlar)
    15dk -> ZAMANLAMA  (yalnızca 4H yönüyle aynı taraftaki girişler alınır)

--------------------------------------------------------------------------
LOOK-AHEAD BIAS -- bu modülün en kritik yeri
--------------------------------------------------------------------------
04:00-08:00 aralığını kapsayan 4H barı 08:00'de KAPANIR. Yönü ancak o andan
itibaren bilinebilir. 05:15'teki bir 15dk barına bu barın yönünü bağlamak
geleceği görmek olur ve backtest'i sessizce şişirir.

Bu yüzden her 4H barına `valid_from = bucket_başlangıcı + 4 saat` damgası
vurulur ve 15dk barlarıyla `join_asof(strategy="backward")` ile eşleştirilir.
Böylece her 15dk barı, o an FİİLEN KAPANMIŞ en son 4H barının yönünü görür.
"""

from __future__ import annotations

from datetime import timedelta

import polars as pl

from . import indicators, storage
from .indicators import ChandelierConfig


def trend_frame(
    con, code: str, config: ChandelierConfig = indicators.NORMAL
) -> pl.DataFrame:
    """4H yön serisi. `valid_from` = yönün bilinebilir hâle geldiği an."""
    df4 = storage.read_bars(con, code, "4h")
    if df4.is_empty():
        return df4

    out = indicators.chandelier_exit(df4, config)
    return out.select(
        (pl.col("ts") + timedelta(hours=4)).alias("valid_from"),
        pl.col("direction").alias("trend"),
        pl.col("close").alias("trend_close"),
    ).sort("valid_from")


def combined_signals(
    con,
    code: str,
    entry_config: ChandelierConfig = indicators.NORMAL,
    trend_config: ChandelierConfig = indicators.NORMAL,
) -> pl.DataFrame:
    """15dk barlarına 4H yönünü ekler ve hizalı girişleri işaretler.

    Dönen sütunlar:
        signal        -- ham 15dk Chandelier sinyali (BUY/SELL)
        trend         -- o an geçerli 4H yönü (1 / -1)
        entry         -- yalnızca 15dk sinyali 4H yönüyle AYNI taraftaysa dolu
    """
    df15 = storage.read_bars(con, code, "15m")
    if df15.is_empty():
        return df15

    df15 = indicators.chandelier_exit(df15, entry_config).sort("ts")
    trend = trend_frame(con, code, trend_config)
    if trend.is_empty():
        return df15

    merged = df15.join_asof(
        trend, left_on="ts", right_on="valid_from", strategy="backward"
    )

    merged = merged.with_columns(
        pl.when(
            (pl.col("signal") == "BUY") & (pl.col("trend") == 1)
        )
        .then(pl.lit("LONG"))
        .when(
            (pl.col("signal") == "SELL") & (pl.col("trend") == -1)
        )
        .then(pl.lit("SHORT"))
        .otherwise(None)
        .alias("aligned")
    )

    # --------------------------------------------------------------------
    # BACAK (leg) mantığı -- ilk sürümün hatası buradaydı.
    #
    # Her hizalı 15dk sinyalinde yeni giriş üretmek, tek bir 4H trendi içinde
    # onlarca işlem demekti; ölçüm bunun ayda 43-52 sinyalde kaldığını ve
    # filtrenin yazı-tura kadar bilgi kattığını gösterdi (8 enstrümanda da
    # tam 2,1x azalma = bağımsızlık).
    #
    # Doğrusu: pozisyon 4H trendine aittir. Bir trend bacağı boyunca YALNIZCA
    # İLK hizalı 15dk sinyali giriş sayılır; gerisi aynı pozisyonun içindeki
    # gürültüdür. 15dk'nın işi yön seçmek değil, giriş ANINI iyileştirmek.
    # --------------------------------------------------------------------
    merged = merged.with_columns(
        (pl.col("trend") != pl.col("trend").shift(1))
        .fill_null(True)
        .cum_sum()
        .alias("leg")
    )

    return merged.with_columns(
        pl.when(
            pl.col("aligned").is_not_null()
            & (pl.col("aligned").is_not_null().cum_sum().over("leg") == 1)
        )
        .then(pl.col("aligned"))
        .otherwise(None)
        .alias("entry")
    )


def summarise(df: pl.DataFrame) -> dict:
    """Ham 15dk sinyali, hizalı sinyal ve bacak başına tek girişi karşılaştırır."""
    if df.is_empty() or "entry" not in df.columns:
        return {}

    raw = df.filter(pl.col("signal").is_not_null()).height
    aligned = df.filter(pl.col("aligned").is_not_null()).height
    entries = df.filter(pl.col("entry").is_not_null()).height
    span_days = (df["ts"][-1] - df["ts"][0]).total_seconds() / 86400
    months = span_days / 30.44

    return {
        "bar": df.height,
        "ham_ay": round(raw / months, 1) if months else 0.0,
        "hizali_ay": round(aligned / months, 1) if months else 0.0,
        "giris_ay": round(entries / months, 1) if months else 0.0,
        "giris": entries,
        "long": df.filter(pl.col("entry") == "LONG").height,
        "short": df.filter(pl.col("entry") == "SHORT").height,
    }


def timing_benefit(df: pl.DataFrame) -> dict:
    """15dk zamanlaması, doğrudan 4H kapanışından girmeye göre daha iyi mi?

    Karşılaştırma: bacağı başlatan 4H barının kapanışı (naif giriş) ile
    ilk hizalı 15dk sinyalinin kapanışı (zamanlanmış giriş).

    LONG'da daha DÜŞÜK fiyat, SHORT'ta daha YÜKSEK fiyat iyidir. Sonuç baz
    puan (bp) cinsinden; pozitif = zamanlama kazandırdı.

    UYARI: bu bir kârlılık ölçüsü DEĞİLDİR. Yalnızca giriş fiyatını
    karşılaştırır; pozisyonun sonrasında ne olduğunu hesaba katmaz.
    """
    e = df.filter(pl.col("entry").is_not_null())
    if e.is_empty():
        return {}

    # trend_close: bacağı başlatan 4H barının kapanışı
    naive = e["trend_close"]
    timed = e["close"]
    sign = e["entry"].replace_strict({"LONG": 1.0, "SHORT": -1.0}, default=0.0)

    # LONG: (naif - zamanlanmis)/naif  -> pozitifse daha ucuza girdik
    bp = ((naive - timed) / naive * 10000.0) * sign

    return {
        "islem": e.height,
        "ort_bp": round(float(bp.mean()), 1),
        "medyan_bp": round(float(bp.median()), 1),
        "kazandiran_%": round(100.0 * float((bp > 0).mean()), 1),
    }

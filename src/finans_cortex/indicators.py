"""Chandelier Exit göstergesi (Chuck LeBeau).

Anayasa 3.2 + 3.3. Tek sınıf, iki parametre seti -- Normal ve Maverick modları
ayrı kod değil, ayrı `ChandelierConfig` nesneleridir.

Mantık:
    long_stop  = N-barlık en yüksek tepe  -  ATR(N) * çarpan
    short_stop = N-barlık en düşük dip    +  ATR(N) * çarpan

Kritik ayrıntı: stoplar RATCHET'lidir. Uzun pozisyonda stop yalnızca yukarı
gidebilir, asla aşağı inmez (trailing stop olmasının tüm anlamı budur). Bu
özyineleme -- her bar bir öncekine bakar -- vektörleştirilemez, sıralı hesaplanır.

ATR, Wilder yumuşatması ile hesaplanır (ilk değer N barlık TR ortalaması, sonrası
özyinelemeli). Basit hareketli ortalama DEĞİL; TradingView/ta-lib ile uyumlu olsun diye.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl


@dataclass(frozen=True)
class ChandelierConfig:
    """Bir strateji profili. Kod tekrarı yerine parametre farkı."""

    name: str
    atr_period: int
    atr_multiplier: float
    lookback: int | None = None
    """Tepe/dip penceresi. None ise atr_period kullanılır (klasik davranış)."""
    use_close: bool = False
    """True ise tepe/dip KAPANIŞLARDAN alınır (fitiller yok sayılır).

    TradingView'deki yaygın "Chandelier Exit" (everget) sürümünün varsayılanı
    budur: `Use Close Price for Extremums = true`. Bizim klasik profillerimiz
    high/low kullandığı için varsayılan False bırakıldı; o sürümü taklit eden
    stratejiler (bkz. heikin_range.py) True verir."""

    @property
    def window(self) -> int:
        return self.lookback if self.lookback is not None else self.atr_period


# Klasik LeBeau parametreleri. Anayasa 4'te "netleşmedi" diye duruyordu;
# başlangıç noktası olarak alınıp backtest'te optimize edilecek.
NORMAL = ChandelierConfig(name="normal", atr_period=22, atr_multiplier=3.0)

# Maverick: aynı mantık, daha dar stop ve daha tepkisel ATR.
# Daha çok işlem, daha erken çıkış, daha yüksek işlem maliyeti demektir --
# backtest'te Normal ile yan yana konup Sharpe/Drawdown karşılaştırılacak.
MAVERICK = ChandelierConfig(name="maverick", atr_period=14, atr_multiplier=2.0)

PROFILES = {c.name: c for c in (NORMAL, MAVERICK)}


def true_range(df: pl.DataFrame) -> pl.Series:
    """TR = max(h-l, |h-önceki kapanış|, |l-önceki kapanış|)."""
    prev_close = pl.col("close").shift(1)
    return df.select(
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - prev_close).abs(),
            (pl.col("low") - prev_close).abs(),
        ).alias("tr")
    )["tr"]


def wilder_atr(tr: np.ndarray, period: int) -> np.ndarray:
    """Wilder yumuşatması: ilk değer SMA, sonrası (önceki*(n-1) + yeni)/n."""
    n = len(tr)
    atr = np.full(n, np.nan)
    if n < period:
        return atr

    # tr[0] önceki kapanış olmadığı için NaN; tohum period+1'den başlar.
    seed = np.nanmean(tr[1 : period + 1])
    atr[period] = seed
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def chandelier_exit(
    df: pl.DataFrame, config: ChandelierConfig = NORMAL
) -> pl.DataFrame:
    """Girdiye atr / long_stop / short_stop / direction / signal sütunları ekler.

    direction:  1 = uzun eğilim,  -1 = kısa eğilim
    signal:     'BUY' / 'SELL' yalnızca yön DEĞİŞTİĞİ barda, aksi hâlde None.

    Girdi ts'e göre artan sıralı olmalıdır.
    """
    if df.height == 0:
        return df

    period = config.atr_period
    window = config.window
    mult = config.atr_multiplier

    tr = true_range(df).to_numpy()
    atr = wilder_atr(tr, period)

    src_hi = "close" if config.use_close else "high"
    src_lo = "close" if config.use_close else "low"
    base = df.with_columns(
        pl.col(src_hi).rolling_max(window_size=window).alias("_hh"),
        pl.col(src_lo).rolling_min(window_size=window).alias("_ll"),
    )

    # Döngüde numpy skaler erişimi (atr[i] gibi) Python listesine göre kat kat
    # yavaş; 140 bin barda saniyeler farkeder. Hesap aynı, erişim ucuzladı.
    hh = base["_hh"].to_list()
    ll = base["_ll"].to_list()
    close = df["close"].to_list()
    atr_l = atr.tolist()
    n = df.height

    nan = float("nan")
    long_stop = [nan] * n
    short_stop = [nan] * n
    direction = [0] * n

    prev_dir = 1
    prev_ls = prev_ss = nan
    for i in range(n):
        a, h_i, l_i = atr_l[i], hh[i], ll[i]
        if (a != a or h_i is None or h_i != h_i
                or l_i is None or l_i != l_i):
            direction[i] = prev_dir
            # Bu barın stopu yazılmadı; bir sonraki bar "önceki stop yok"
            # görmeli (eski sürümde dizideki NaN bunu sağlıyordu).
            prev_ls = prev_ss = nan
            continue

        ls = h_i - a * mult
        ss = l_i + a * mult

        # RATCHET: fiyat stopun üstünde kaldığı sürece stop geri çekilmez.
        if prev_ls == prev_ls and close[i - 1] > prev_ls:
            ls = max(ls, prev_ls)
        if prev_ss == prev_ss and close[i - 1] < prev_ss:
            ss = min(ss, prev_ss)

        long_stop[i] = ls
        short_stop[i] = ss

        # Yön yalnızca karşı taraftaki stop kırıldığında değişir.
        if prev_ss == prev_ss and close[i] > prev_ss:
            prev_dir = 1
        elif prev_ls == prev_ls and close[i] < prev_ls:
            prev_dir = -1
        direction[i] = prev_dir
        prev_ls, prev_ss = ls, ss

    long_stop = np.array(long_stop)
    short_stop = np.array(short_stop)
    direction = np.array(direction, dtype=np.int8)

    # Sinyal yalnızca yönün DEĞİŞTİĞİ barda üretilir. Python listesi olarak
    # kuruluyor: numpy'nin object dizisi Polars'ta Utf8'e cast edilemiyor.
    flips = np.diff(direction, prepend=direction[0]) != 0
    signal = [
        ("BUY" if d == 1 else "SELL") if f else None
        for f, d in zip(flips, direction)
    ]

    return df.with_columns(
        pl.Series("atr", atr),
        pl.Series("long_stop", long_stop),
        pl.Series("short_stop", short_stop),
        pl.Series("direction", direction),
        pl.Series("signal", signal, dtype=pl.Utf8),
    )


@dataclass(frozen=True)
class MacdConfig:
    """MACD parametreleri. Klasik Appel ayarlari 12/26/9."""

    name: str = "macd"
    fast: int = 12
    slow: int = 26
    signal: int = 9


MACD_DEFAULT = MacdConfig()


def macd(df: pl.DataFrame, config: MacdConfig = MACD_DEFAULT) -> pl.DataFrame:
    """MACD cizgisi, sinyal cizgisi, histogram ve kesisim sinyalleri ekler.

        macd        = EMA(fast) - EMA(slow)
        macd_signal = EMA(signal) of macd
        macd_hist   = macd - macd_signal

    Kesisim: histogramin isaret degistirdigi bar. Yukari kesis = BUY,
    asagi kesis = SELL.

    EMA'da `adjust=False` kullaniliyor -- ozyinelemeli klasik EMA tanimi,
    ta-lib/TradingView ile uyumlu. adjust=True farkli (ve burada yanlis)
    bir isinma davranisi verir.
    """
    if df.height == 0:
        return df

    out = df.with_columns(
        (
            pl.col("close").ewm_mean(span=config.fast, adjust=False)
            - pl.col("close").ewm_mean(span=config.slow, adjust=False)
        ).alias("macd")
    )
    out = out.with_columns(
        pl.col("macd").ewm_mean(span=config.signal, adjust=False)
        .alias("macd_signal")
    )
    out = out.with_columns(
        (pl.col("macd") - pl.col("macd_signal")).alias("macd_hist")
    )

    # Isinma: yavas EMA oturana kadar kesisimler guvenilmez.
    warmup = config.slow + config.signal

    hist = out["macd_hist"].to_numpy()
    n = len(hist)
    sig = [None] * n
    for i in range(1, n):
        if i < warmup:
            continue
        if hist[i - 1] <= 0 < hist[i]:
            sig[i] = "BUY"
        elif hist[i - 1] >= 0 > hist[i]:
            sig[i] = "SELL"

    return out.with_columns(pl.Series("macd_cross", sig, dtype=pl.Utf8))


def signals_only(df: pl.DataFrame) -> pl.DataFrame:
    """Yalnızca yön değişimi olan barlar -- inceleme/raporlama için."""
    return df.filter(pl.col("signal").is_not_null()).select(
        "ts", "close", "atr", "long_stop", "short_stop", "direction", "signal"
    )

"""Strateji 2 -- Heikin Ashi + Chandelier Exit + Range Filter.

Kaynak: Kripton Gezegeni, "Ihtiyaciniz olan TEK Heikin Ashi Al-Sat Stratejisi"
https://www.youtube.com/watch?v=dkX7PkoBzok
Kurallar videonun altyazisindan ve aciklamasindan damitildi (17.09.2026).
Video aciklamasi indikatorleri adiyla veriyor:
    "Indikator Ismi: Chandelier Exit - Range Filter Buy and Sell"

--------------------------------------------------------------------------
VIDEODAKI KURALLAR
--------------------------------------------------------------------------
1. Grafik HEIKIN ASHI mumuna cevrilir; iki gosterge de bu mumlar uzerinde
   calisir. Video 4 saatlik ve gunluk grafikleri oneriyor ("5 dakikalik
   yaziyor ama dikkate almayin" -- kastedilen scriptin adi).
2. Gosterge 1: Chandelier Exit (everget). Videoda carpan 1,8'e, periyot 1'e
   cekiliyor; "Use Close Price for Extremums" acik kaliyor.
3. Gosterge 2: Range Filter Buy and Sell (Guikroth). Ayarlar degistirilmez:
   ornekleme 100, carpan 3,0.
4. GIRIS: iki gosterge AYNI yonde ve BIRBIRINE YAKIN barlarda sinyal
   verirse. Video toleransi soyle tarif ediyor: ayni anda ya da 1-2 bar
   sonra cok iyi, 3 bara kadar kabul, "1 2 3 4 bar sonra yandiysa girmiyoruz".
   Tek basina sinyal veren gosterge dikkate ALINMAZ.
5. CIKIS: ters yonde ayni ikili sinyal. Ek olarak video iki sey daha
   soyluyor: (a) uzun fitilli / ince govdeli Heikin Ashi mumu trend donusu
   uyarisidir, "ilk gelen uzun fitilli dojide cikilabilir"; (b) "stopu
   yukselterek ilerlenebilir" -- yani takip eden stop. Ikisi de kodda
   secenek olarak duruyor, varsayilanlari KAPALI (videonun asil kurali
   ters sinyal).

--------------------------------------------------------------------------
BIZIM VERIMIZE UYARLAMA -- ve backtest durustlugu
--------------------------------------------------------------------------
- SINYAL Heikin Ashi barlarindan, ISLEM GERCEK fiyattan. Heikin Ashi fiyati
  bir ortalamadir, o fiyattan alim satim YAPILAMAZ. TradingView'de Heikin
  Ashi grafiginde alinan backtest sonuclarinin sisirilmis cikmasinin sebebi
  tam olarak budur. Burada giris/cikis her zaman barin GERCEK kapanisidir.
- Karar barin KAPANISINDA verilir, islem ayni kapanistan yapilir. Bar ici
  yol izlenmez (bu sistemde bar ici stop/hedef yok).
- 4 saatlik kovalar 00/04/08/12/16/20 UTC hizalidir (storage.py). Broker'in
  4H bari farkli hizalanmissa sinyaller de farkli cikar.
- Maliyet: islem basina backtest.DEFAULT_COSTS gidis-donus spread'i.
- Videonun "fitilli mum" ve "stop yukseltme" tarifleri goz kararidir;
  kodda olculebilir hale getirildi (govde/menzil orani, Chandelier stopu).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from . import backtest, storage
from .akis import ATLANDI, GECTI, KALDI, Adim, Dugum, Isaret
from .indicators import ChandelierConfig, chandelier_exit
from .perf import (  # noqa: F401  -- ortak performans katmani disa aktariliyor
    DAY_ROLL, TRADE_SCHEMA, Result, daily_equity, metrics)

# Gosterimde Turkiye saati kullanilir; hesap ve saklama UTC kalir.
TZ_TR = "Europe/Istanbul"

# Video 4 saatlik ve gunlugu oneriyor; 1 saat de acik birakildi.
# 15 dakika kullanici istegiyle acildi (23.09.2026). OLCULDU: bu stratejide
# 15 dakikada BRUT sonuc bile eksi (9 varlik, tum gecmis: brut -%345, net
# -%2.098; 4 saatte brut +%694). Yani kucuk barda sinyalin kendisi gurultu --
# secenek duruyor ama beklentiyi buna gore kurun.
BAR_HOURS = {"15m": 0.25, "1h": 1, "4h": 4, "1d": 24}

# 15 dakikalik teyit bari (bkz. HeikinConfig.onay_15m). Veritabaninin taban
# granularitesi 15 dakikadir (anayasadan sapma, gerekcesi CLAUDE.md'de).
ONAY_TF = "15m"
ONAY_BAR = timedelta(minutes=15)


@dataclass(frozen=True)
class HeikinConfig:
    """Varsayilanlar videodaki degerlerdir."""

    heikin: bool = True
    """Gostergeler Heikin Ashi barlarindan hesaplansin mi (video: evet)."""
    ce_period: int = 1
    ce_mult: float = 1.8
    ce_use_close: bool = True
    rf_period: int = 100
    rf_mult: float = 3.0
    tolerance: int = 3
    """Iki gostergenin sinyali arasinda en fazla kac bar olabilir. 0 = ayni bar."""
    allow_short: bool = True
    exit_chandelier: bool = False
    """Chandelier yonu pozisyonun tersine donunce cik (takip eden stop)."""
    doji_exit: bool = False
    """Uzun fitilli / ince govdeli Heikin Ashi mumunda cik."""
    doji_body: float = 0.25
    """Fitilli mum esigi: govde / (yuksek-dusuk) bu orandan kucukse doji."""
    # --- Strateji 2.1 (kullanici, 22.09.2026: "%2 kar gordu mu satsin, tek
    # bir ters sinyalde satsin, %1 zarardaysa satsin"). Varsayilan kapali:
    # Strateji 2'nin sonucu degismez.
    kar_al: float = 0.0
    """Kar al, % (0 = kapali). Bar ici: en yuksek (SAT'ta en dusuk) girisin bu
    kadar otesine degerse o seviyeden cikar."""
    zarar_kes: float = 0.0
    """Zarar kes, % (0 = kapali). Bar ici, seviyeden; bar seviyenin otesinde
    acilirsa (bosluk) acilistan. Ayni barda ikisi de gorulurse ZARAR sayilir."""
    tek_ters: bool = False
    """Tek ters sinyalde cik: CE ya da RF'den biri ters yonde yanarsa bar
    kapanisinda cikar (ikincisinin onayi beklenmez)."""
    # --- Trend filtresi (22 Eylul 2026). Gelistirme motorunun teshisi bunu
    # olcup oneriyordu ama motorda karsiligi yoktu: 5 yilda trend yonunde
    # acilan 727 islem +23,3 bp, tersine acilan 623 islem -7,8 bp.
    # Varsayilan 0 = KAPALI -> Strateji 2 ve 2.1'in sonuclari degismez.
    rf_kullan: bool = True
    """Range Filter giriste kullanilsin mi (kullanici, 23.09.2026).

    KAPALI = Strateji 3: giris YALNIZ Chandelier Exit'in yon degistirdigi
    barda olur, ikinci gosterge aranmaz. Cikis da ters yondeki Chandelier
    sinyalidir -- yani sistem surekli piyasada kalir ve her donuste yon
    degistirir (al-sat/sat-al). `tolerance` bu durumda anlamsizdir; iki
    gosterge arasi pencere diye bir sey kalmaz."""
    onay_15m: bool = False
    """15 dakikalik Chandelier Exit de ayni yonde mi (kullanici, 23.09.2026).

    CALISTIGI ZAMAN DILIMINDEN BAGIMSIZ bir teyit: 4 saatlik (ya da gunluk)
    ikili sinyal olustugunda, ayni anda 15 dakikalik grafikteki Chandelier
    yonu de islemin yonunde olmali; degilse islem ACILMAZ. Ayni CE ayarlari
    (periyot/carpan/kapanistan) ve ayni `heikin` secimi 15 dakikalik barlara
    uygulanir.

    KAPANIS HIZASI: 4 saatlik bar 16:00'da kapanirsa, o anda KAPANMIS son 15
    dakikalik bar kullanilir (15:45 barinin kapanisi). Ileriye bakma yok --
    karar ani ile veri ani ayni. `prepare`'a 15 dakikalik cerceve verilmezse
    hata yukselir; sessizce kapanmaz (ekranlar arasi sonuc farki olmasin)."""
    trend_filter: int = 0
    """Trend filtresi: ustel ortalama periyodu (0 = kapali). Acikken yalniz
    fiyatin ortalamaya gore bulundugu YONDE islem acilir -- fiyat ortalamanin
    ustundeyse AL, altindaysa SAT. Teshisteki olcutun aynisi: gercek kapanis
    ve `ewm_mean(span=N)`; Heikin Ashi fiyatindan DEGIL."""


def warmup_bars(cfg: HeikinConfig) -> int:
    """Gostergelerin oturmasi icin gereken en az bar sayisi.

    Range Filter iki ustel ortalama zinciri kullanir (per ve 2*per-1); uc kat
    periyot pratikte oturmaya yeter. Chandelier'in ATR'si cok daha hizli.
    """
    return max(3 * cfg.rf_period, 5 * cfg.ce_period,
               3 * cfg.trend_filter, 30)


# --------------------------------------------------------------------------
# GOSTERGELER
# --------------------------------------------------------------------------
def heikin_ashi(df: pl.DataFrame) -> pl.DataFrame:
    """ha_open/ha_high/ha_low/ha_close sutunlarini ekler.

        ha_close = (o+h+l+c) / 4
        ha_open  = (onceki ha_open + onceki ha_close) / 2   (ilk bar: (o+c)/2)
        ha_high  = max(h, ha_open, ha_close)
        ha_low   = min(l, ha_open, ha_close)

    ha_open ozyinelemelidir (her bar bir oncekine bakar), vektorlestirilemez.
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()

    ha_close = (o + h + lo + c) / 4.0
    ha_open = np.empty(len(o))
    if len(o):
        ha_open[0] = (o[0] + c[0]) / 2.0
        for i in range(1, len(o)):
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0

    return df.with_columns(
        pl.Series("ha_open", ha_open),
        pl.Series("ha_close", ha_close),
        pl.Series("ha_high", np.maximum(h, np.maximum(ha_open, ha_close))),
        pl.Series("ha_low", np.minimum(lo, np.minimum(ha_open, ha_close))),
    )


def range_filter(src: np.ndarray, period: int, mult: float) -> dict[str, np.ndarray]:
    """Range Filter Buy and Sell (Guikroth) -- Pine kaynagindaki mantik.

        avrng  = EMA(|src - src[-1]|, period)
        smrng  = EMA(avrng, period*2 - 1) * mult
        filt   = src yukaridaysa max(onceki, src-smrng),
                 asagidaysa    min(onceki, src+smrng)

    Sinyal: fiyat filtrenin ustune gecip filtre YUKSELMEYE basladiysa AL,
    altina gecip filtre DUSMEYE basladiysa SAT. Sinyal yalnizca yon
    DEGISTIGINDE uretilir (Pine'daki CondIni mantigi) -- yoksa her bar
    tekrar ederdi.

    Donen: filt (filtre cizgisi), smrng (yumusatilmis menzil),
    dir (yon +1/-1/0), sig (sinyal +1/-1/0).
    """
    n = len(src)
    filt = np.full(n, np.nan)
    smrng = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int8)
    signal = np.zeros(n, dtype=np.int8)
    if n == 0:
        return {"filt": filt, "smrng": smrng, "dir": direction, "sig": signal}

    diff = np.abs(np.diff(src, prepend=src[0]))
    avrng = _ema(diff, period)
    smrng[:] = _ema(avrng, period * 2 - 1) * mult

    filt[0] = src[0]
    up = dn = 0
    cond = 0
    for i in range(1, n):
        r = smrng[i]
        prev = filt[i - 1]
        if np.isnan(r):
            filt[i] = prev
            continue
        if src[i] > prev:
            filt[i] = prev if src[i] - r < prev else src[i] - r
        else:
            filt[i] = prev if src[i] + r > prev else src[i] + r

        if filt[i] > filt[i - 1]:
            up, dn = up + 1, 0
        elif filt[i] < filt[i - 1]:
            up, dn = 0, dn + 1

        long_cond = src[i] > filt[i] and src[i] != src[i - 1] and up > 0
        short_cond = src[i] < filt[i] and src[i] != src[i - 1] and dn > 0

        if long_cond:
            signal[i] = 1 if cond == -1 else 0
            cond = 1
        elif short_cond:
            signal[i] = -1 if cond == 1 else 0
            cond = -1
        direction[i] = cond

    return {"filt": filt, "smrng": smrng, "dir": direction, "sig": signal}


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    """Klasik ozyinelemeli EMA (adjust=False), ilk deger tohum.

    Pine'daki ta.ema ile ayni davranis. Ozyineleme Polars'in (Rust) ewm_mean
    islevine biniyor; Python dongusu canli parametre ayarinda hissedilir
    olacak kadar yavasti.
    """
    if len(x) == 0:
        return np.empty(0)
    return pl.Series(x).ewm_mean(alpha=2.0 / (span + 1.0), adjust=False).to_numpy()


def onay_serisi(bars_15m: pl.DataFrame, cfg: HeikinConfig) -> pl.DataFrame:
    """15 dakikalik Chandelier yonu + o barin KAPANIS damgasi.

    Donen: ts_onay (bar kapanisi, UTC) ve ce15_dir sutunlari. Ham 15 dakikalik
    cerceve burada tuketilir; cagiran tarafta tutulmaz (9 varlikta 2,5 milyon
    satir demek -- yalnizca yon gerekiyor)."""
    if bars_15m is None or bars_15m.is_empty():
        return pl.DataFrame(schema={"ts_onay": pl.Datetime(time_zone="UTC"),
                                    "ce15_dir": pl.Int8})
    d = bars_15m.sort("ts")
    if cfg.heikin:
        d = heikin_ashi(d)
        src = d.select(
            pl.col("ha_open").alias("open"), pl.col("ha_high").alias("high"),
            pl.col("ha_low").alias("low"), pl.col("ha_close").alias("close"))
    else:
        src = d.select("open", "high", "low", "close")
    ce = chandelier_exit(src, ChandelierConfig(
        name="onay15", atr_period=cfg.ce_period, atr_multiplier=cfg.ce_mult,
        use_close=cfg.ce_use_close))
    return pl.DataFrame({
        "ts_onay": d["ts"] + ONAY_BAR,
        "ce15_dir": ce["direction"].cast(pl.Int8),
    }).sort("ts_onay")


def prepare(df: pl.DataFrame, cfg: HeikinConfig,
            bars_15m: pl.DataFrame | None = None) -> pl.DataFrame:
    """Heikin Ashi, iki gosterge ve islem gunu sutunlarini ekler.

    Gostergeler HA barlarindan (cfg.heikin) ya da gercek barlardan hesaplanir;
    `close`/`open`/`high`/`low` sutunlari HER ZAMAN gercek fiyat kalir --
    islem fiyatlari oradan okunur.
    """
    df = df.sort("ts")
    if df.height == 0:
        return df
    df = heikin_ashi(df)

    if cfg.heikin:
        src = df.select(
            pl.col("ha_open").alias("open"), pl.col("ha_high").alias("high"),
            pl.col("ha_low").alias("low"), pl.col("ha_close").alias("close"))
    else:
        src = df.select("open", "high", "low", "close")

    ce = chandelier_exit(src, ChandelierConfig(
        name="video", atr_period=cfg.ce_period, atr_multiplier=cfg.ce_mult,
        use_close=cfg.ce_use_close))
    rf = range_filter(src["close"].to_numpy(), cfg.rf_period, cfg.rf_mult)

    ce_dir = ce["direction"].to_numpy()
    ce_sig = np.zeros(len(ce_dir), dtype=np.int8)
    if len(ce_dir):
        flips = np.diff(ce_dir, prepend=ce_dir[0]) != 0
        ce_sig[flips] = ce_dir[flips]

    body = (src["close"] - src["open"]).abs()
    rng = src["high"] - src["low"]

    n = df.height
    warm = warmup_bars(cfg)

    # Trend yonu GERCEK kapanistan hesaplanir (HA'dan degil): teshisteki
    # olcut de oyle, ikisi ayni seyi soylesin diye. 0 = filtre kapali.
    if cfg.trend_filter > 0:
        trend_ema = df["close"].ewm_mean(span=cfg.trend_filter,
                                         adjust=False).to_numpy()
        trend_dir = np.sign(df["close"].to_numpy() - trend_ema).astype(np.int8)
    else:
        trend_ema = np.full(n, np.nan)
        trend_dir = np.zeros(n, dtype=np.int8)

    out_ek = []
    if cfg.onay_15m:
        onay = onay_serisi(bars_15m, cfg)
        if onay.is_empty():
            raise ValueError(
                "onay_15m acik ama 15 dakikalik veri verilmedi "
                "(prepare(..., bars_15m=...)).")
        # Calisilan barin KAPANIS damgasi: bar araligi barlardan turetilir
        # (prepare zaman dilimini disaridan almaz). Hafta sonu bosluklari
        # aykiri deger oldugu icin ORTANCA alinir.
        adim = df["ts"].diff().drop_nulls().median()
        kapanis = df["ts"] + adim
        # backward: kapanis anina kadar KAPANMIS son 15 dakikalik bar.
        # Esitlik dahildir -- 16:00'da kapanan 15 dakikalik bar, 16:00'da
        # kapanan 4 saatlik barin karar aninda hazirdir.
        eslesme = (pl.DataFrame({"kapanis": kapanis})
                   .join_asof(onay, left_on="kapanis", right_on="ts_onay",
                              strategy="backward"))
        out_ek.append(eslesme["ce15_dir"].fill_null(0).alias("ce15_dir"))
    else:
        out_ek.append(pl.Series("ce15_dir", np.zeros(n, dtype=np.int8)))

    return df.with_columns(
        *out_ek,
        pl.Series("trend_dir", trend_dir),
        pl.Series("trend_ema", trend_ema),
        (pl.col("ts") + DAY_ROLL).dt.date().alias("tday"),
        pl.Series("ce_dir", ce_dir),
        pl.Series("ce_sig", ce_sig),
        ce["long_stop"], ce["short_stop"],
        pl.Series("filt", rf["filt"]),
        pl.Series("rf_dir", rf["dir"]),
        pl.Series("rf_sig", rf["sig"]),
        (rng.is_not_null() & (rng > 0) & (body / rng <= cfg.doji_body))
        .fill_null(False).alias("doji"),
        pl.Series("hazir", np.arange(n) >= warm),
    )


# --------------------------------------------------------------------------
# SIMULASYON
# --------------------------------------------------------------------------
def simulate(df: pl.DataFrame, cfg: HeikinConfig, cost_bp: float = 0.0) -> pl.DataFrame:
    """Islem listesi. Girdi `prepare` ciktisi olmalidir."""
    rows, _ = _loop(df, cfg, cost_bp)
    if not rows:
        return pl.DataFrame(schema=TRADE_SCHEMA)
    return pl.DataFrame(rows, schema=TRADE_SCHEMA, orient="row")


def _loop(
    df: pl.DataFrame, cfg: HeikinConfig, cost_bp: float, live: bool = False
) -> tuple[list, dict | None]:
    """Simulasyon dongusu. Donen: (islem satirlari, dongu sonundaki durum).

    live=True: son bardaki acik pozisyon kapatilmaz (canli sinyal listesi
    icin). live=False (backtest): son bar "veri_sonu" diye kapatilir ki
    getiri hesabi eksik kalmasin.

    Eslesme mantigi: her gosterge sinyal verdiginde (yon, bar) olarak
    saklanir. Iki gostergenin son sinyali AYNI yonde ve aralarindaki fark
    toleransi asmiyorsa, ikincisinin geldigi barda ikili sinyal olusur ve
    ciftin ikisi de tuketilir (ayni cift tekrar sayilmasin).
    """
    n = df.height
    if n == 0:
        return [], None

    ts = df["ts"].to_list()
    o = df["open"].to_list()
    h = df["high"].to_list()
    lo = df["low"].to_list()
    c = df["close"].to_list()
    ce_sig = df["ce_sig"].to_list()
    rf_sig = df["rf_sig"].to_list()
    ce_dir = df["ce_dir"].to_list()
    long_stop = df["long_stop"].to_list()
    short_stop = df["short_stop"].to_list()
    doji = df["doji"].to_list()
    ready = df["hazir"].to_list()
    trend_dir = df["trend_dir"].to_list()
    ce15_dir = df["ce15_dir"].to_list()

    tol = cfg.tolerance
    cost = cost_bp / 10000.0

    rows = []
    pos = 0
    e_px = stop = risk = 0.0
    target = None
    e_i = 0
    ce_fire = rf_fire = None      # (yon, bar)
    last_pair = None              # (yon, bar) -- alinmasa bile son ikili sinyal

    def close_trade(i: int, why: str, px: float | None = None) -> None:
        nonlocal pos
        px = c[i] if px is None else px
        move = (px - e_px) * pos
        rows.append((ts[e_i], ts[i], pos, e_px, px, stop, target, why,
                     move / e_px - cost,
                     move / risk if risk > 0 else float("nan")))
        pos = 0

    def open_trade(i: int, d: int) -> None:
        nonlocal pos, e_px, stop, risk, e_i, target
        pos, e_px, e_i = d, c[i], i
        if cfg.zarar_kes > 0:
            # Sabit % zarar kes: stop Chandelier cizgisi degil bu seviye.
            stop = c[i] * (1 - d * cfg.zarar_kes / 100.0)
        else:
            s = long_stop[i] if d == 1 else short_stop[i]
            stop = None if s is None or s != s else s
        target = (c[i] * (1 + d * cfg.kar_al / 100.0)
                  if cfg.kar_al > 0 else None)
        risk = abs(c[i] - stop) if stop is not None else 0.0

    def bar_ici(i: int) -> tuple[float, str] | None:
        """Zarar kes / kar al bu barda tetiklendi mi. Giris bari haric (giris
        kapanista; o barin tepe/dibi girisTEN ONCE olmustur). Kotumser sira:
        once bosluk, sonra zarar, en son kar (Strateji 1 ile ayni kural)."""
        if i <= e_i:
            return None
        sl = stop if cfg.zarar_kes > 0 else None
        if pos == 1:
            if sl is not None and o[i] <= sl:
                return o[i], "zarar_kes"
            if sl is not None and lo[i] <= sl:
                return sl, "zarar_kes"
            if target is not None and o[i] >= target:
                return o[i], "kar_al"
            if target is not None and h[i] >= target:
                return target, "kar_al"
        else:
            if sl is not None and o[i] >= sl:
                return o[i], "zarar_kes"
            if sl is not None and h[i] >= sl:
                return sl, "zarar_kes"
            if target is not None and o[i] <= target:
                return o[i], "kar_al"
            if target is not None and lo[i] <= target:
                return target, "kar_al"
        return None

    for i in range(n):
        if ce_sig[i]:
            ce_fire = (ce_sig[i], i)
        if rf_sig[i]:
            rf_fire = (rf_sig[i], i)

        pair = 0
        if not cfg.rf_kullan:
            # Strateji 3: tek gosterge. Chandelier yon degistirdigi barda
            # sinyal olusur; eslestirilecek ikinci gosterge yoktur.
            if ce_sig[i]:
                pair = ce_sig[i]
                ce_fire = rf_fire = None
        elif (ce_fire and rf_fire and ce_fire[0] == rf_fire[0]
                and abs(ce_fire[1] - rf_fire[1]) <= tol
                and max(ce_fire[1], rf_fire[1]) == i):
            pair = ce_fire[0]
            ce_fire = rf_fire = None

        if not ready[i]:
            continue
        if pair:
            last_pair = (pair, i)

        if pos != 0:
            vur = bar_ici(i)
            if vur is not None:
                close_trade(i, vur[1], vur[0])
            elif pair == -pos:
                close_trade(i, "ters_sinyal")
            elif cfg.tek_ters and (ce_sig[i] == -pos or rf_sig[i] == -pos):
                close_trade(i, "tek_ters")
            elif cfg.exit_chandelier and ce_dir[i] == -pos:
                close_trade(i, "chandelier")
            elif cfg.doji_exit and doji[i] and i > e_i:
                close_trade(i, "doji")

        if pos == 0 and pair and (pair == 1 or cfg.allow_short):
            # Trend filtresi: fiyat ortalamanin hangi tarafindaysa yalniz o
            # yonde islem acilir. Kapaliyken (0) hicbir sinyal elenmez.
            if cfg.trend_filter > 0 and trend_dir[i] != pair:
                continue
            # 15 dakikalik Chandelier teyidi: kucuk zaman dilimi de ayni
            # yonde olmali. 0 = o anda teyit verisi yok -> islem acilmaz.
            if cfg.onay_15m and ce15_dir[i] != pair:
                continue
            open_trade(i, pair)

    if pos != 0 and not live:
        close_trade(n - 1, "veri_sonu")

    # Bekleyen: bir gosterge sinyal verdi, digeri henuz vermedi ve tolerans
    # penceresi hala acik. Canli listede "bekliyor" diye gorunur.
    pend = 0
    pend_ts = None
    if cfg.rf_kullan:
        for fire in (ce_fire, rf_fire):
            if fire and (n - 1) - fire[1] <= tol:
                pend, pend_ts = fire[0], ts[fire[1]]

    state = {
        "pos": pos,
        "giris_ts": ts[e_i] if pos else None,
        "giris": e_px if pos else None,
        "stop": stop if pos else None,
        "hedef": target if pos else None,
        "break_even": False,
        "bekleyen": pend,
        "bekleyen_ts": pend_ts,
        "bekleyen_seviye": None,
        "bekleyen_stop": None,
        "son_kurulum": (None if last_pair is None
                        else (last_pair[0], ts[last_pair[1]])),
        "yeni": (pos != 0 and e_i == n - 1) or (pend != 0 and pend_ts == ts[n - 1]),
        "son_ts": ts[n - 1],
        "son_fiyat": c[n - 1],
    }
    return rows, state


# --------------------------------------------------------------------------
# CALISTIRMA
# --------------------------------------------------------------------------
def run(
    con,
    code: str,
    timeframe: str = "4h",
    cfg: HeikinConfig = HeikinConfig(),
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Result:
    """Tek enstruman backtest'i. Donem: `days` ya da `start`/`end` (UTC)."""
    if timeframe not in BAR_HOURS:
        raise ValueError("desteklenmeyen zaman dilimi: {}".format(timeframe))
    return run_bars(storage.read_bars(con, code, timeframe), code, timeframe,
                    cfg, days, start, end,
                    bars_15m=onay_oku(con, code, cfg))


def onay_oku(con, code: str, cfg: HeikinConfig,
             start: datetime | None = None) -> pl.DataFrame | None:
    """15 dakikalik teyit cercevesi -- yalniz gerekiyorsa okunur.

    Kapali oldugunda hic sorgu atilmaz: teyit kapaliyken program eskisi kadar
    hizli kalir (9 varlikta 15 dakikalik veri 2,5 milyon satirdir)."""
    if not cfg.onay_15m:
        return None
    return storage.read_bars(con, code, ONAY_TF, start=start)


def run_bars(
    bars: pl.DataFrame,
    code: str,
    timeframe: str,
    cfg: HeikinConfig = HeikinConfig(),
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    bars_15m: pl.DataFrame | None = None,
    cost_bp: float | None = None,
) -> Result:
    """`run` ile ayni; ham bar cercevesi disaridan gelir (canli ayar ekrani).

    Gostergeler TUM gecmis uzerinde hesaplanip SONRA kesilir -- secilen
    donemin basinda isinma boslugu kalmaz.
    """
    # cost_bp disaridan gelebilir: BIST hisselerinin maliyeti ayri
    # tablodadir (backtest.bist_cost_for), kuresel varlik degiller.
    if cost_bp is None:
        cost_bp = backtest.cost_for(code).roundtrip_bp
    empty = Result(bars, pl.DataFrame(schema=TRADE_SCHEMA), pl.DataFrame(), {},
                   cost_bp)
    if bars.is_empty():
        return empty

    bars = prepare(bars, cfg, bars_15m)
    if days:
        bars = bars.filter(pl.col("ts") >= bars["ts"][-1] - timedelta(days=days))
    if start is not None:
        bars = bars.filter(pl.col("ts") >= start)
    if end is not None:
        bars = bars.filter(pl.col("ts") < end)
    if bars.is_empty():
        return empty

    trades = simulate(bars, cfg, cost_bp)
    daily = daily_equity(trades, bars)
    return Result(bars, trades, daily, metrics(trades, daily, bars), cost_bp)


# --------------------------------------------------------------------------
# CANLI SINYAL
# --------------------------------------------------------------------------
def signal_state(
    bars: pl.DataFrame, cfg: HeikinConfig, timeframe: str = "4h",
    day_over: bool = True, bars_15m: pl.DataFrame | None = None,
) -> dict | None:
    """Stratejinin su anki durumu: acik pozisyon, bekleyen sinyal ya da bos.

    `bars`: ham bar cercevesi (ts/open/high/low/close, UTC, kapanmis barlar).
    `timeframe`/`day_over` yalnizca arayuzun tek bir cagri sekli kullanmasi
    icin var; bu strateji gun ici degildir, pozisyon gece de tasinir.
    Yeterli bar yoksa None.
    """
    if bars.height <= warmup_bars(cfg):
        return None
    _, state = _loop(prepare(bars, cfg, bars_15m), cfg, 0.0, live=True)
    return state


def recent_state(
    con, code: str, timeframe: str, cfg: HeikinConfig, now: datetime,
    days: int | None = None,
) -> dict | None:
    """Veritabanindaki son donemle canli durum.

    Okunacak gun sayisi gostergelerin isinmasindan turetilir: Range Filter
    100'luk ornekleme ile 4 saatlik barda ~300 bar = ~50 gun ister; guvenli
    tarafta kalmak icin iki kati alinir.
    """
    if days is None:
        need = warmup_bars(cfg) * 2 + 60
        days = int(need * BAR_HOURS.get(timeframe, 4) / 24) + 30
    bas = now - timedelta(days=days)
    bars = storage.read_bars(con, code, timeframe, start=bas)
    if bars.is_empty():
        return None
    return signal_state(bars, cfg, timeframe,
                        bars_15m=onay_oku(con, code, cfg, start=bas))


# --------------------------------------------------------------------------
# KURAL AKISI (bkz. akis.py) -- arayuz bu ikisini cagirir, stratejiyi tanimaz
# --------------------------------------------------------------------------
def _f(v, basamak: int = 2) -> str:
    """Turk bicimi sayi: 4.312,50"""
    if v is None or v != v:
        return "-"
    metin = "{:,.{}f}".format(v, basamak)
    return metin.replace(",", " ").replace(".", ",").replace(" ", ".")


def _fiyat(v) -> str:
    if v is None or v != v:
        return "-"
    return _f(v, 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2)


def sema(cfg: HeikinConfig = HeikinConfig()) -> list[Dugum]:
    """Stratejinin kural semasi. Metinler PARAMETRELERI tasir, sinyali degil.

    Kullanici "kutular cok, kucuk adimlari birlestir" dedi (21.09.2026):
    iki gosterge tek kutuda, yon + tolerans tek kutuda, giris + stop tek
    kutuda, cikis kosulu + cikis tek kutuda. SAT izni yalnizca SAT kapaliyken
    ayri bir kural oldugu icin o zaman cizilir.
    """
    dugumler = [
        Dugum("bar", "baslangic", "Bar kapandi \u00b7 {} mum".format(
            "Heikin Ashi" if cfg.heikin else "normal")),
    ]
    if cfg.rf_kullan:
        dugumler += [
            Dugum("sinyal", "kosul", "Iki gosterge de sinyal verdi mi?",
                  "Chandelier ATR {} \u00b7 {}  +  Range Filter {} \u00b7 {}".format(
                      cfg.ce_period, _f(cfg.ce_mult, 1),
                      cfg.rf_period, _f(cfg.rf_mult, 1)),
                  hayir="Tek gosterge sayilmaz"),
            Dugum("uyum", "kosul",
                  "Ayni yonde ve en fazla {} bar arayla mi?".format(cfg.tolerance),
                  "video: ayni bar ya da 1-3 bar sonra",
                  hayir="Sayilmaz, bekle"),
        ]
    else:
        dugumler.append(Dugum(
            "sinyal", "kosul", "Chandelier yon degistirdi mi?",
            "ATR {} · carpan {} · tek gosterge".format(
                cfg.ce_period, _f(cfg.ce_mult, 1)),
            hayir="Yon ayni, bekle"))
    if cfg.onay_15m:
        dugumler.append(Dugum(
            "onay15", "kosul", "15 dakikalik Chandelier ayni yonde mi?",
            "kucuk zaman dilimi teyidi", hayir="Teyit yok, alinmaz"))
    if cfg.trend_filter > 0:
        dugumler.append(Dugum(
            "trend", "kosul", "Islem yonu trendle ayni mi?",
            "fiyat {} barlik ortalamanin dogru tarafinda mi".format(
                cfg.trend_filter),
            hayir="Trende ters, alinmaz"))
    if not cfg.allow_short:
        dugumler.append(Dugum("izin", "kosul", "AL yonunde mi?",
                              "SAT islemleri kapali", hayir="Yalnizca cikis"))
    dugumler += [
        Dugum("giris", "islem",
              "GIRIS + stop" + (" + hedef" if cfg.kar_al > 0 else ""),
              "gercek kapanistan \u00b7 " + _giris_ozeti(cfg)),
        Dugum("cikis", "kosul", "Cikis kosulu olustu mu?", _cikis_ozeti(cfg),
              hayir="Pozisyon devam"),
        Dugum("sonuc", "bitis", "Sonuc", "maliyet (spread) dusulmus"),
    ]
    return dugumler


def _giris_ozeti(cfg: HeikinConfig) -> str:
    """Giris kutusunun parametre satiri: stop ve hedef nereye konur."""
    stop = ("zarar kes %{}".format(_f(cfg.zarar_kes, 1)) if cfg.zarar_kes > 0
            else "stop = Chandelier cizgisi")
    if cfg.kar_al > 0:
        stop += " \u00b7 kar al %{}".format(_f(cfg.kar_al, 1))
    return stop


def _cikis_ozeti(cfg: HeikinConfig) -> str:
    parcalar = []
    if cfg.kar_al > 0:
        parcalar.append("kar %{}".format(_f(cfg.kar_al, 1)))
    if cfg.zarar_kes > 0:
        parcalar.append("zarar %{}".format(_f(cfg.zarar_kes, 1)))
    parcalar.append("TEK ters sinyal" if cfg.tek_ters else "ters ikili sinyal")
    if cfg.exit_chandelier:
        parcalar.append("Chandelier donusu")
    if cfg.doji_exit:
        parcalar.append("fitilli mum")
    return " / ".join(parcalar)


def izle(bars: pl.DataFrame, islem: dict, cfg: HeikinConfig = HeikinConfig(),
         timeframe: str = "4h") -> list[Adim]:
    """Secilen islemde her dugumun ne oldugu -- GERCEK degerlerle.

    `bars` prepare() ciktisi (gosterge sutunlari dolu), `islem` bir islem
    satiri (sozluk). Giris bari damgadan bulunur; iki gostergenin o
    civarda ne zaman yandigi geriye dogru taranarak cikarilir.
    """
    d = int(islem["yon"])
    yon_ad = "AL" if d == 1 else "SAT"
    ts = bars["ts"]
    i = int((ts < islem["giris_ts"]).sum())
    if i >= bars.height:
        return [Adim(x.kod, ATLANDI, "") for x in sema(cfg)]

    bas = max(0, i - max(cfg.tolerance, 0))
    dilim = bars.slice(bas, i - bas + 1)
    zamanlar = dilim["ts"].to_list()

    def son_yanma(seri):
        for k in range(len(seri) - 1, -1, -1):
            if seri[k] == d:
                return k
        return None

    ce_k = son_yanma(dilim["ce_sig"].to_list())
    rf_k = son_yanma(dilim["rf_sig"].to_list())
    satir = bars.row(i, named=True)

    def saat(t) -> str:
        """Ekranda Turkiye saati (veri UTC saklanir, gosterimde cevrilir)."""
        return t.astimezone(ZoneInfo(TZ_TR)).strftime("%d.%m %H:%M")

    adimlar = [Adim("bar", GECTI, "{} \u00b7 kapanis {}".format(
        saat(satir["ts"]), _fiyat(satir["close"])), satir["ts"],
        (Isaret("bolge", satir["ts"], bitis=satir["ts"], renk="notr"),))]

    parca = []
    parca.append("Chandelier {} {}".format(yon_ad, saat(zamanlar[ce_k]))
                 if ce_k is not None else "Chandelier yanmadi")
    if cfg.rf_kullan:
        parca.append("Range F. {} {}".format(yon_ad, saat(zamanlar[rf_k]))
                     if rf_k is not None else "Range F. yanmadi")
    iki_de = (ce_k is not None and rf_k is not None if cfg.rf_kullan
              else ce_k is not None)
    _cift = ((ce_k, "CE"), (rf_k, "RF")) if cfg.rf_kullan else ((ce_k, "CE"),)
    oklar = tuple(Isaret("ok", zamanlar[k], etiket=ad, yon=d)
                  for k, ad in _cift if k is not None)
    adimlar.append(Adim("sinyal", GECTI if iki_de else KALDI,
                        " \u00b7 ".join(parca), isaretler=oklar))

    if not cfg.rf_kullan:
        pass                  # tek gostergede 'uyum' kutusu yok
    elif iki_de:
        fark = abs(ce_k - rf_k)
        adimlar.append(Adim(
            "uyum", GECTI, "ikisi de {} \u00b7 {}".format(
                yon_ad, "ayni bar" if fark == 0 else "{} bar arayla".format(
                    fark)),
            isaretler=(Isaret("bolge", zamanlar[min(ce_k, rf_k)],
                              bitis=zamanlar[max(ce_k, rf_k)]),)))
    elif cfg.rf_kullan:
        adimlar.append(Adim("uyum", ATLANDI, ""))

    if cfg.onay_15m:
        d15 = satir.get("ce15_dir") or 0
        adimlar.append(Adim(
            "onay15", GECTI if d15 == d else ATLANDI,
            "15 dakikalik Chandelier {}".format(
                "AL" if d15 == 1 else "SAT" if d15 == -1 else "teyit yok")))
    if cfg.trend_filter > 0:
        ema_v = satir.get("trend_ema")
        if ema_v is None or ema_v != ema_v:
            adimlar.append(Adim("trend", ATLANDI, ""))
        else:
            adimlar.append(Adim("trend", GECTI, "fiyat {} · {} ortalama {} · {}".format(
                _fiyat(satir["close"]), cfg.trend_filter, _fiyat(ema_v),
                "ustunde" if satir["close"] > ema_v else "altinda")))
    if not cfg.allow_short:
        adimlar.append(Adim("izin", GECTI, "AL yonu, islem aciliyor"))

    stop = islem.get("stop")
    stop_metin = ("{} {} (%{})".format(
        "zarar kes" if cfg.zarar_kes > 0 else "stop",
        _fiyat(stop), _f(abs(islem["giris"] - stop) / islem["giris"] * 100, 2))
        if stop is not None and stop == stop else "stop yok")
    if iki_de and not cfg.rf_kullan:
        giris_neden = "Chandelier {} yonune dondu".format(yon_ad)
    elif iki_de:
        giris_neden = "CE + RF ikisi de {} ({})".format(
            yon_ad, "ayni bar" if ce_k == rf_k else "{} bar arayla".format(
                abs(ce_k - rf_k)))
    else:
        giris_neden = "ikili sinyal"
    giris_isaret = [Isaret("nokta", islem["giris_ts"], islem["giris"],
                           etiket="GIRIS " + yon_ad, yon=d,
                           neden=giris_neden)]
    if stop is not None and stop == stop:
        giris_isaret.append(Isaret("cizgi", islem["giris_ts"], stop,
                                   bitis=islem["cikis_ts"],
                                   etiket=("zarar kes" if cfg.zarar_kes > 0
                                           else "stop"), renk="stop"))
    hedef = islem.get("hedef")
    if hedef is not None and hedef == hedef:
        stop_metin += " \u00b7 hedef {}".format(_fiyat(hedef))
        giris_isaret.append(Isaret("cizgi", islem["giris_ts"], hedef,
                                   bitis=islem["cikis_ts"], etiket="kar al",
                                   renk="hedef"))
    adimlar.append(Adim("giris", GECTI, "{} {} @ {} \u00b7 {}".format(
        yon_ad, saat(islem["giris_ts"]), _fiyat(islem["giris"]), stop_metin),
        islem["giris_ts"], tuple(giris_isaret)))

    saat_sayi = (islem["cikis_ts"] - islem["giris_ts"]).total_seconds() / 3600
    sure = ("{:.0f} saat".format(saat_sayi) if saat_sayi < 48
            else "{} gun".format(_f(saat_sayi / 24, 1)))
    neden = {"ters_sinyal": "ters ikili sinyal",
             "chandelier": "Chandelier dondu",
             "doji": "fitilli mum",
             "kar_al": "kar al",
             "zarar_kes": "zarar kes",
             "tek_ters": "tek ters sinyal",
             "veri_sonu": "henuz yok \u2014 islem ACIK"}.get(
                 islem["neden"], islem["neden"])
    if islem["neden"] == "veri_sonu":
        adimlar.append(Adim("cikis", ATLANDI, "{} \u00b7 {} suruyor".format(
            neden, sure)))
    else:
        adimlar.append(Adim("cikis", GECTI, "{} \u00b7 {} @ {} \u00b7 {}".format(
            neden, saat(islem["cikis_ts"]), _fiyat(islem["cikis"]), sure),
            islem["cikis_ts"],
            (Isaret("nokta", islem["cikis_ts"], islem["cikis"],
                    etiket="CIKIS", yon=-d,
                    neden=_cikis_nedeni(islem, bars)),)
            + _cikis_oklari(bars, islem, cfg)))

    getiri = islem["getiri"] * 100
    r = islem.get("R")
    adimlar.append(Adim(
        "sonuc", GECTI if getiri > 0 else KALDI,
        "{}%{}{}{}".format("+" if getiri > 0 else "-", _f(abs(getiri), 2),
                           "" if r is None or r != r else
                           " \u00b7 {} R".format(_f(r, 2)),
                           " (su an)" if islem["neden"] == "veri_sonu" else ""),
        isaretler=(Isaret("bolge", islem["giris_ts"],
                          bitis=islem["cikis_ts"]),)))
    return adimlar


def _cikis_oklari(bars: pl.DataFrame, islem: dict,
                  cfg: HeikinConfig) -> tuple[Isaret, ...]:
    """Cikisi tetikleyen gostergeler grafikte gorunsun: cikis barindan
    tolerans kadar geriye bakip ters yonde yanan son CE / RF sinyali."""
    if islem["neden"] not in ("ters_sinyal", "chandelier", "tek_ters"):
        return ()
    ters = -int(islem["yon"])
    j = min(int((bars["ts"] < islem["cikis_ts"]).sum()), bars.height - 1)
    # Tek ters sinyal cikis barinda yanmistir; ikili sinyal tolerans kadar geri.
    bas = (j if islem["neden"] == "tek_ters"
           else max(0, j - max(cfg.tolerance, 0)))
    dilim = bars.slice(bas, j - bas + 1)
    sutunlar = ((("ce_sig", "CE"),) if islem["neden"] == "chandelier"
                else (("ce_sig", "CE"), ("rf_sig", "RF")))
    oklar = []
    for sutun, ad in sutunlar:
        seri = dilim[sutun].to_list()
        for k in range(len(seri) - 1, -1, -1):
            if seri[k] == ters:
                oklar.append(Isaret("ok", dilim["ts"][k], etiket=ad, yon=ters))
                break
    return tuple(oklar)


def _cikis_nedeni(islem: dict, bars: pl.DataFrame | None = None) -> str:
    """Grafikteki CIKIS kutusunun 'neden' satiri."""
    ters_ad = "SAT" if int(islem["yon"]) == 1 else "AL"
    fark = abs(islem["cikis"] - islem["giris"]) / islem["giris"] * 100
    if islem["neden"] == "kar_al":
        return "fiyat hedefe degdi: %{} kar".format(_f(fark, 2))
    if islem["neden"] == "zarar_kes":
        return "fiyat zarar kese degdi: %{} zarar".format(_f(fark, 2))
    if islem["neden"] == "tek_ters":
        yanan = []
        if bars is not None:
            j = min(int((bars["ts"] < islem["cikis_ts"]).sum()),
                    bars.height - 1)
            satir = bars.row(j, named=True)
            yanan = [ad for sutun, ad in (("ce_sig", "CE"), ("rf_sig", "RF"))
                     if satir[sutun] == -int(islem["yon"])]
        return "tek ters sinyal: {} {}".format(
            " + ".join(yanan) or "gosterge", ters_ad)
    return {"ters_sinyal": "ters ikili sinyal: CE + RF ikisi de {}".format(
                ters_ad),
            "chandelier": "Chandelier {} yonune dondu".format(ters_ad),
            "doji": "fitilli (kararsiz) mum"}.get(islem["neden"],
                                                  islem["neden"])


# --------------------------------------------------------------------------
# GELISTIRME MOTORU (bkz. gelistir.py) -- tarama bu ikisini kullanir
# --------------------------------------------------------------------------
# prepare'i etkileyen parametreler: tarama bunlar degismedikce gostergeleri
# yeniden hesaplamaz (prepare ~1,3 sn / simulate ~0,3 sn, 9 varlik 4 saatlik).
# `trend_filter` de buradadir: `prepare` icinde hesaplanir, dolayisiyla
# degistiginde hazirlanmis cerceve yeniden uretilmelidir. Listeden cikarilirsa
# tarama farkli periyotlari ayni cerceveyle olcer -- sessiz yanlis sonuc.
GOSTERGE_PARAMLARI = frozenset({
    "heikin", "ce_period", "ce_mult", "ce_use_close", "rf_period", "rf_mult",
    "doji_body", "trend_filter", "onay_15m"})

# Taramada denenecek degerler. Aralik dar tutuldu: her ek deger hem sure hem
# asiri uyum riski demek.
ARAMA_UZAYI = {
    "kar_al": [0.0, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0],
    "zarar_kes": [0.0, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
    "tek_ters": [False, True],
    "tolerance": [0, 1, 2, 3, 5],
    "allow_short": [True, False],
    "ce_period": [1, 3, 5, 10, 22],
    "ce_mult": [1.0, 1.4, 1.8, 2.2, 3.0],
    "rf_period": [50, 100, 150, 200],
    "rf_mult": [2.0, 2.5, 3.0, 3.5, 4.0],
    "exit_chandelier": [False, True],
    "doji_exit": [False, True],
    "heikin": [True, False],
    "trend_filter": [0, 100, 200, 300],
    "onay_15m": [False, True],
}


def hazir_simule(hazir: pl.DataFrame, cfg: HeikinConfig, timeframe: str,
                 cost_bp: float) -> pl.DataFrame:
    """Ortak imza (bkz. gelistir.py). Bu strateji zaman dilimine bakmaz."""
    return simulate(hazir, cfg, cost_bp)

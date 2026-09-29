"""Strateji 1 -- EMA 10 iki kapanis.

Kaynak: Sidar Demirgil, "En Cok Kazandiran VIOP Scalping Sistemim"
https://www.youtube.com/watch?v=iNuqAD5ngro
Kurallar videonun altyazisindan damitildi (15.09.2026).

--------------------------------------------------------------------------
VIDEODAKI KURALLAR
--------------------------------------------------------------------------
1. Ustel hareketli ortalama, EMA 10 ("9 da olur 10 da, fark etmez").
2. EMA'nin USTUNDE art arda 2 kapanis -> uzun, ALTINDA 2 kapanis -> kisa.
3. Iki giris turu:
     kirilim       ikinci kapanista hemen gir
     geri cekilme  ikinci kapanistan sonra fiyat EMA'ya geri gelince gir
                   (videoya gore risk/odulu "her zaman daha iyi")
4. Stop: uzunda son dip, kisada son tepe.
5. Hedef: risk/odul 1:2,5 - 1:3.
6. Hedefe gelinmediyse bile fiyat EMA'nin ters tarafinda kapatirsa cik.
7. 1R kara gelince stop giris fiyatina cekilir (break even).
8. Gun ici sistem: aksam pozisyon tasinmaz (gece haberi / gap riski) ve
   acilistan sonra ilk yarim saat islem yapilmaz.

--------------------------------------------------------------------------
BIZIM VERIMIZE UYARLAMA -- videodan sapmalar
--------------------------------------------------------------------------
- Video BIST30 VIOP'ta 5dk sinyal + 1dk giris kullaniyor. Bizde en kucuk
  bar 15dk; sinyal ve islem ayni barlarda (15dk ya da 1 saat).
- VIOP 10:00-18:00 seansli; bizim enstrumanlar ~23 saat isleyen CFD'ler.
  "Gun" 22:00 UTC'de biter. Olculdu: altin, endeksler ve petrol her gun
  21:00-22:00 UTC arasi kapali; forex'in gunluk devri de bu saatte.
- Son dip/tepe "son N bar icindeki en dusuk/en yuksek" olarak tanimli.
  Videoda goz karariyla seciliyor; kodda sabit bir pencere sart.

--------------------------------------------------------------------------
BACKTEST DURUSTLUGU
--------------------------------------------------------------------------
- Kurulum barin KAPANISINDA bilinir; stop/hedef bir SONRAKI bardan itibaren
  kontrol edilir.
- Geri cekilme girisinde seviye, bir onceki barin EMA'sidir (o an bilinen
  deger). Bar o seviyenin otesinde acilirsa acilistan dolar.
- Ayni bar icinde hem stop hem hedef gorulurse STOP sayilir. Bar icinde
  hangisinin once oldugu bilinemez; iyimser varsayim sonucu sisirir.
- Bar stopun otesinde acilirsa (gap) stoptan degil ACILIS fiyatindan cikar.
- Maliyet: islem basina backtest.DEFAULT_COSTS gidis-donus spread'i.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from . import backtest, storage
from .akis import ATLANDI, GECTI, KALDI, Adim, Dugum, Isaret
# Ortak performans katmani: islem listesinden sonrasi her stratejide ayni.
# Eski cagrilar (ema.metrics, ema.daily_equity, ...) calismaya devam etsin
# diye buradan disa aktariliyor.
from .perf import (  # noqa: F401
    DAY_ROLL, TRADE_SCHEMA, Result, daily_equity, metrics)

ENTRY_TYPES = ("kirilim", "geri_cekilme")

# Gosterimde Turkiye saati; hesap ve saklama UTC kalir.
TZ_TR = "Europe/Istanbul"

BAR_MINUTES = {"15m": 15, "1h": 60}


@dataclass(frozen=True)
class EmaConfig:
    """Varsayilanlar videodaki degerlerdir."""

    ema_period: int = 10
    confirm_bars: int = 2
    entry: str = "kirilim"
    rr_target: float = 3.0
    """Hedef, riskin kati. 0 = sabit hedef yok (cikis EMA kapanisina kalir)."""
    swing_lookback: int = 10
    """Son dip/tepe penceresi, bar."""
    breakeven_r: float = 1.0
    """Bu kadar R kara gelince stop giris fiyatina. 0 = kapali."""
    exit_on_ema: bool = True
    intraday: bool = True
    skip_open_minutes: int = 30
    pullback_wait_bars: int = 8
    """Geri cekilme girisinde EMA'ya donus icin en fazla beklenen bar."""


def prepare(df: pl.DataFrame, cfg: EmaConfig) -> pl.DataFrame:
    """EMA, islem gunu ve kurulum sutunlarini ekler.

    EMA'da adjust=False: ozyinelemeli klasik tanim, TradingView ile uyumlu.

    `kurulum` (+1 AL / -1 SAT / 0): art arda `confirm_bars` kapanisin TAM
    olarak tamamlandigi bar. Simulasyon bunu kendi dongusunde sayiyor;
    buradaki sutun ARAYUZ icin -- grafikte "sinyal ne zaman olustu, neden
    islem acilmadi" gorulebilsin diye. Ayni tanim, vektorel hesap:
    isaret serisinin ardisik bloklari (rle) icinde kacinci bar oldugumuz.
    Kapanis EMA'ya tam esitse iki sayac da sifirlanir (dongudeki davranis).
    """
    out = df.sort("ts").with_columns(
        pl.col("close").ewm_mean(span=cfg.ema_period, adjust=False).alias("ema"),
        (pl.col("ts") + DAY_ROLL).dt.date().alias("tday"),
    )
    yon = (pl.col("close") > pl.col("ema")).cast(pl.Int8) - (
        pl.col("close") < pl.col("ema")).cast(pl.Int8)
    return out.with_columns(yon.alias("_yon")).with_columns(
        (pl.int_range(pl.len()).over(pl.col("_yon").rle_id()) + 1).alias("_say")
    ).with_columns(
        pl.when((pl.col("_yon") != 0) & (pl.col("_say") == cfg.confirm_bars))
        .then(pl.col("_yon")).otherwise(0).cast(pl.Int8).alias("kurulum")
    ).drop("_yon", "_say")


def simulate(
    df: pl.DataFrame, cfg: EmaConfig, timeframe: str = "15m", cost_bp: float = 0.0
) -> pl.DataFrame:
    """Islem islem simulasyon. Girdi `prepare` ciktisi olmalidir.

    Stop/hedef yol bagimli oldugu icin vektorel degil, sirali hesaplanir.
    """
    rows, _ = _loop(df, cfg, timeframe, cost_bp)
    if not rows:
        return pl.DataFrame(schema=TRADE_SCHEMA)
    return pl.DataFrame(rows, schema=TRADE_SCHEMA, orient="row")


def _loop(
    df: pl.DataFrame,
    cfg: EmaConfig,
    timeframe: str,
    cost_bp: float,
    live: bool = False,
    day_over: bool = True,
) -> tuple[list, dict | None]:
    """Simulasyon dongusu. Donen: (islem satirlari, dongu sonundaki durum).

    live=True (canli sinyal listesi): gun hala suruyorsa verinin son bari
    "gun sonu" SAYILMAZ -- acik pozisyon kapatilmaz, son barda olusan kurulum
    da alinir. Backtest'te (live=False) son bardaki acik islem "veri_sonu"
    diye kapatilir.
    """
    if cfg.entry not in ENTRY_TYPES:
        raise ValueError("bilinmeyen giris turu: {}".format(cfg.entry))

    n = df.height
    warm = max(3 * cfg.ema_period, cfg.swing_lookback)
    if n <= warm + 1:
        return [], None

    # Python listeleri: dongude numpy skaler erisimi belirgin sekilde yavas.
    ts = df["ts"].to_list()
    o = df["open"].to_list()
    h = df["high"].to_list()
    lo = df["low"].to_list()
    c = df["close"].to_list()
    e = df["ema"].to_list()
    day = df["tday"].to_list()

    last_of_day = [day[i] != day[i + 1] for i in range(n - 1)] + [not live or day_over]
    bar_in_day = [0] * n
    for i in range(1, n):
        if day[i] == day[i - 1]:
            bar_in_day[i] = bar_in_day[i - 1] + 1
    skip = math.ceil(cfg.skip_open_minutes / BAR_MINUTES[timeframe])

    k = cfg.confirm_bars
    lb = cfg.swing_lookback
    rr = cfg.rr_target
    be_r = cfg.breakeven_r
    cost = cost_bp / 10000.0
    pullback = cfg.entry == "geri_cekilme"

    rows = []
    up = dn = 0            # EMA'nin ustunde / altinda art arda kapanis sayisi
    pos = 0                # 1 uzun, -1 kisa, 0 disarida
    e_px = stop = stop0 = risk = 0.0
    target = None
    e_i = 0
    be_done = False
    pend = 0               # bekleyen geri cekilme emrinin yonu
    pend_stop = 0.0
    pend_until = 0
    last_setup = None      # (yon, bar) -- alinmasa bile en son kurulum

    for i in range(n):
        if c[i] > e[i]:
            up, dn = up + 1, 0
        elif c[i] < e[i]:
            up, dn = 0, dn + 1
        else:
            up = dn = 0
        if i < warm:
            continue

        filled_now = False

        # 1) Bekleyen geri cekilme emri. Seviye = onceki barin EMA'si.
        if pend != 0:
            level = e[i - 1]
            broken = (c[i - 1] - e[i - 1]) * pend < 0
            new_day = cfg.intraday and day[i] != day[i - 1]
            if (broken or new_day or i > pend_until
                    or (cfg.intraday and last_of_day[i])):
                pend = 0
            elif (pend == 1 and lo[i] <= level) or (pend == -1 and h[i] >= level):
                px = min(o[i], level) if pend == 1 else max(o[i], level)
                if (px - pend_stop) * pend > 0:
                    pos, e_px, stop, stop0, e_i = pend, px, pend_stop, pend_stop, i
                    risk = abs(px - pend_stop)
                    target = px + pend * rr * risk if rr > 0 else None
                    be_done = False
                    filled_now = True
                pend = 0

        # 2) Acik pozisyonu yonet.
        if pos != 0:
            xp = None
            why = ""
            hit = "break_even" if be_done else "stop"
            if pos == 1:
                if filled_now:
                    # Dolum bari: yalniz stop -- barin dibi dolumdan sonra
                    # olmus sayilir (kotumser).
                    if lo[i] <= stop:
                        xp, why = stop, hit
                elif o[i] <= stop:
                    xp, why = o[i], hit
                elif lo[i] <= stop:
                    xp, why = stop, hit
                elif target is not None and o[i] >= target:
                    xp, why = o[i], "hedef"
                elif target is not None and h[i] >= target:
                    xp, why = target, "hedef"
            else:
                if filled_now:
                    if h[i] >= stop:
                        xp, why = stop, hit
                elif o[i] >= stop:
                    xp, why = o[i], hit
                elif h[i] >= stop:
                    xp, why = stop, hit
                elif target is not None and o[i] <= target:
                    xp, why = o[i], "hedef"
                elif target is not None and lo[i] <= target:
                    xp, why = target, "hedef"

            if xp is None and cfg.exit_on_ema and (c[i] - e[i]) * pos < 0:
                xp, why = c[i], "ema"
            if xp is None and (dn if pos == 1 else up) == k:
                xp, why = c[i], "ters_sinyal"
            if xp is None and cfg.intraday and last_of_day[i]:
                # Backtest'te verinin son bari da "gun sonu" gorunur; o islem
                # aslinda hala acik, ayri etiketlenir.
                xp, why = c[i], ("veri_sonu" if i == n - 1 and not live
                                 else "gun_sonu")

            if xp is None:
                if be_r > 0 and not be_done and not filled_now:
                    peak = h[i] if pos == 1 else lo[i]
                    if (peak - e_px) * pos >= be_r * risk:
                        stop, be_done = e_px, True   # bir SONRAKI bardan gecerli
            else:
                move = (xp - e_px) * pos
                rows.append((ts[e_i], ts[i], pos, e_px, xp, stop0, target, why,
                             move / e_px - cost, move / risk))
                pos = 0

        # 3) Yeni kurulum -- barin KAPANISINDA bilinir.
        if up == k or dn == k:
            last_setup = (1 if up == k else -1, i)
        if pos == 0 and (up == k or dn == k):
            d = 1 if up == k else -1
            if bar_in_day[i] >= skip and not (cfg.intraday and last_of_day[i]):
                j = max(0, i - lb + 1)
                stp = min(lo[j:i + 1]) if d == 1 else max(h[j:i + 1])
                if pullback:
                    pend, pend_stop, pend_until = d, stp, i + cfg.pullback_wait_bars
                elif (c[i] - stp) * d > 0:
                    pos, e_px, stop, stop0, e_i = d, c[i], stp, stp, i
                    risk = abs(c[i] - stp)
                    target = c[i] + d * rr * risk if rr > 0 else None
                    be_done = False

    # Bekleyen emir bir sonraki barda iptal olacak durumdaysa bekleyen sayilmaz.
    if pend != 0 and ((c[n - 1] - e[n - 1]) * pend < 0 or n > pend_until
                      or (cfg.intraday and last_of_day[n - 1])):
        pend = 0
    pend_i = pend_until - cfg.pullback_wait_bars

    state = {
        "pos": pos,
        "giris_ts": ts[e_i] if pos else None,
        "giris": e_px if pos else None,
        "stop": stop if pos else None,
        "hedef": target if pos else None,
        "break_even": be_done if pos else False,
        "bekleyen": pend,
        "bekleyen_ts": ts[pend_i] if pend else None,
        "bekleyen_seviye": e[n - 1] if pend else None,
        "bekleyen_stop": pend_stop if pend else None,
        "son_kurulum": (None if last_setup is None
                        else (last_setup[0], ts[last_setup[1]])),
        "yeni": (pos != 0 and e_i == n - 1) or (pend != 0 and pend_i == n - 1),
        "son_ts": ts[n - 1],
        "son_fiyat": c[n - 1],
    }
    return rows, state


def run(
    con,
    code: str,
    timeframe: str = "15m",
    cfg: EmaConfig = EmaConfig(),
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Result:
    """Tek enstruman backtest'i.

    Donem: `days` = son kac gun, ya da `start` (dahil) / `end` (haric) UTC.
    Hicbiri verilmezse tum gecmis.

    EMA tum gecmis uzerinde hesaplanip SONRA kesilir -- secilen donemin
    basinda isinma boslugu kalmaz.
    """
    if timeframe not in BAR_MINUTES:
        raise ValueError("desteklenmeyen zaman dilimi: {}".format(timeframe))
    return run_bars(storage.read_bars(con, code, timeframe), code, timeframe,
                    cfg, days, start, end)


def run_bars(
    bars: pl.DataFrame,
    code: str,
    timeframe: str,
    cfg: EmaConfig = EmaConfig(),
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    cost_bp: float | None = None,
) -> Result:
    """`run` ile ayni; ham bar cercevesi disaridan gelir.

    Canli parametre ayari her kaydirici hareketinde yeniden hesaplar; barlari
    her seferinde veritabanindan okumamak icin onbellekten verir.
    """
    # cost_bp disaridan gelebilir: BIST hisselerinin maliyeti ayri
    # tablodadir (backtest.bist_cost_for), kuresel varlik degiller.
    if cost_bp is None:
        cost_bp = backtest.cost_for(code).roundtrip_bp
    if bars.is_empty():
        return Result(bars, pl.DataFrame(schema=TRADE_SCHEMA), pl.DataFrame(), {}, cost_bp)

    bars = prepare(bars, cfg)
    if days:
        bars = bars.filter(pl.col("ts") >= bars["ts"][-1] - timedelta(days=days))
    if start is not None:
        bars = bars.filter(pl.col("ts") >= start)
    if end is not None:
        bars = bars.filter(pl.col("ts") < end)
    if bars.is_empty():
        return Result(bars, pl.DataFrame(schema=TRADE_SCHEMA), pl.DataFrame(), {}, cost_bp)

    trades = simulate(bars, cfg, timeframe, cost_bp)
    daily = daily_equity(trades, bars)
    return Result(bars, trades, daily, metrics(trades, daily, bars), cost_bp)


# --------------------------------------------------------------------------
# CANLI SINYAL
# --------------------------------------------------------------------------
def signal_state(
    bars: pl.DataFrame, cfg: EmaConfig, timeframe: str, day_over: bool
) -> dict | None:
    """Stratejinin su anki durumu: acik pozisyon, bekleyen emir ya da bos.

    `bars`: ham bar cercevesi (ts/open/high/low/close, UTC, kapanmis barlar).
    `day_over`: son barin islem gunu bitti mi. Bittiyse gun ici kurali acik
    pozisyonu kapatmistir; bitmediyse pozisyon hala acik gosterilir.
    Yeterli bar yoksa None.
    """
    if bars.height == 0:
        return None
    _, state = _loop(prepare(bars, cfg), cfg, timeframe, 0.0,
                     live=True, day_over=day_over)
    return state


def day_over_utc(last_ts: datetime, now: datetime) -> bool:
    """Global enstrumanlar: islem gunu 22:00 UTC'de biter."""
    return (now + DAY_ROLL).date() > (last_ts + DAY_ROLL).date()


def recent_state(
    con, code: str, timeframe: str, cfg: EmaConfig, now: datetime, days: int = 30
) -> dict | None:
    """Veritabanindaki son `days` gunle canli durum.

    Tum gecmisi okumaya gerek yok: EMA 10 birkac gunde oturur, pozisyonlar
    gun icidir.
    """
    bars = storage.read_bars(con, code, timeframe, start=now - timedelta(days=days))
    if bars.is_empty():
        return None
    return signal_state(bars, cfg, timeframe, day_over_utc(bars["ts"][-1], now))


# --------------------------------------------------------------------------
# KURAL AKISI (bkz. akis.py) -- arayuz bu ikisini cagirir, stratejiyi tanimaz
# --------------------------------------------------------------------------
def _f(v, basamak: int = 2) -> str:
    """Turk bicimi sayi: 4.312,50"""
    if v is None or v != v:
        return "-"
    return "{:,.{}f}".format(v, basamak).replace(
        ",", " ").replace(".", ",").replace(" ", ".")


def _fiyat(v) -> str:
    if v is None or v != v:
        return "-"
    return _f(v, 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2)


def sema(cfg: EmaConfig = EmaConfig()) -> list[Dugum]:
    """Kural semasi. Kapali secenekler (hedef, break even...) hic cizilmez --
    sema her zaman O ANKI ayarlarin kurallarini gosterir.

    Kullanici "kutular cok, kucuk adimlari birlestir" dedi (21.09.2026):
    "EMA'nin bir tarafinda" + "art arda k kapanis" tek kutu, giris + stop +
    hedef tek kutu, cikis kosulu + cikis tek kutu.
    """
    dugumler = [
        Dugum("bar", "baslangic", "Bar kapandi \u00b7 EMA {}".format(
            cfg.ema_period)),
        Dugum("kurulum", "kosul",
              "EMA'nin ayni tarafinda art arda {} kapanis?".format(
                  cfg.confirm_bars),
              "ust taraf = AL, alt taraf = SAT",
              hayir="Sayac sifirlandi"),
    ]
    if cfg.intraday:
        dugumler.append(Dugum(
            "seans", "kosul", "Gun ici filtre uygun mu?",
            "acilistan {} dk sonra \u00b7 gun sonunda yeni islem yok".format(
                cfg.skip_open_minutes),
            hayir="Islem acilmaz"))
    if cfg.entry == "geri_cekilme":
        dugumler.append(Dugum(
            "gericekilme", "kosul", "Fiyat EMA'ya geri dondu mu?",
            "en fazla {} bar beklenir".format(cfg.pullback_wait_bars),
            hayir="Emir iptal"))
    hedef = (" + hedef" if cfg.rr_target > 0 else "")
    dugumler.append(Dugum(
        "giris", "islem", "GIRIS + stop" + hedef,
        "stop = son {} bar dibi/tepesi{}".format(
            cfg.swing_lookback,
            " \u00b7 hedef 1:{}".format(_f(cfg.rr_target, 1))
            if cfg.rr_target > 0 else "")))
    if cfg.breakeven_r > 0:
        dugumler.append(Dugum(
            "be", "kosul", "{} R kara gelindi mi?".format(
                _f(cfg.breakeven_r, 1)),
            "gelindiyse stop giris fiyatina cekilir",
            hayir="Stop yerinde kalir"))
    dugumler += [
        Dugum("cikis", "kosul", "Cikis kosulu olustu mu?", _cikis_ozeti(cfg),
              hayir="Pozisyon devam"),
        Dugum("sonuc", "bitis", "Sonuc", "maliyet (spread) dusulmus"),
    ]
    return dugumler


def _cikis_ozeti(cfg: EmaConfig) -> str:
    parcalar = ["stop"]
    if cfg.rr_target > 0:
        parcalar.append("hedef")
    if cfg.exit_on_ema:
        parcalar.append("EMA ters kapanis")
    parcalar.append("ters sinyal")
    if cfg.intraday:
        parcalar.append("gun sonu")
    return " / ".join(parcalar)


def izle(bars: pl.DataFrame, islem: dict, cfg: EmaConfig = EmaConfig(),
         timeframe: str = "15m") -> list[Adim]:
    """Secilen islemde her dugumun ne oldugu -- GERCEK degerlerle.

    `bars` prepare() ciktisidir: ema ve kurulum sutunlari dolu. Kurulum
    bari, girise kadar geriye bakilarak bulunur (geri cekilme girisinde
    kurulum ile giris AYNI bar degildir).
    """
    kodlar = [x.kod for x in sema(cfg)]
    d = int(islem["yon"])
    yon_ad = "AL" if d == 1 else "SAT"
    ts = bars["ts"]
    i = int((ts < islem["giris_ts"]).sum())
    if i >= bars.height:
        return [Adim(k, ATLANDI, "") for k in kodlar]

    def saat(t) -> str:
        return t.astimezone(ZoneInfo(TZ_TR)).strftime("%d.%m %H:%M")

    # Kurulum bari: giris barindan geriye dogru ilk "kurulum == yon".
    kurulum_i = i
    if "kurulum" in bars.columns:
        geri = bars.slice(max(0, i - cfg.pullback_wait_bars - 2),
                          min(i, cfg.pullback_wait_bars + 2) + 1)
        kurulumlar = geri["kurulum"].to_list()
        geri_ts = geri["ts"].to_list()
        for k in range(len(kurulumlar) - 1, -1, -1):
            if kurulumlar[k] == d:
                kurulum_i = int((ts < geri_ts[k]).sum())
                break

    kur = bars.row(kurulum_i, named=True)
    k = cfg.confirm_bars
    onay = bars.slice(max(0, kurulum_i - k + 1), min(k, kurulum_i + 1))
    kapanislar = " \u00b7 ".join(_fiyat(v) for v in onay["close"].to_list())

    onay_ts = onay["ts"].to_list()
    adimlar = [
        Adim("bar", GECTI, "{} \u00b7 kapanis {}".format(
            saat(kur["ts"]), _fiyat(kur["close"])), kur["ts"],
            (Isaret("bolge", kur["ts"], bitis=kur["ts"], renk="notr"),)),
        Adim("kurulum", GECTI, "{} {} EMA {} \u2192 {}".format(
            kapanislar, ">" if d == 1 else "<", _fiyat(kur["ema"]), yon_ad),
            isaretler=tuple(Isaret("ok", t, etiket=str(n), yon=d)
                            for n, t in enumerate(onay_ts, 1))),
    ]
    if cfg.intraday:
        adimlar.append(Adim("seans", GECTI, "{} \u00b7 uygun".format(
            saat(kur["ts"]))))
    if cfg.entry == "geri_cekilme":
        bekleme = i - kurulum_i
        adimlar.append(Adim(
            "gericekilme", GECTI,
            "{} bar sonra EMA'ya dondu".format(bekleme) if bekleme
            else "ayni barda dondu",
            isaretler=(Isaret("bolge", kur["ts"], bitis=islem["giris_ts"],
                              renk="notr"),)))

    stop = islem.get("stop")
    hedef = islem.get("hedef")
    parca = ["{} {} @ {}".format(yon_ad, saat(islem["giris_ts"]),
                                 _fiyat(islem["giris"]))]
    giris_neden = "{} kapanis EMA {}{}".format(
        cfg.confirm_bars, "ustunde" if d == 1 else "altinda",
        " + EMA'ya geri donus" if cfg.entry == "geri_cekilme" else "")
    isaret = [Isaret("nokta", islem["giris_ts"], islem["giris"],
                     etiket="GIRIS " + yon_ad, yon=d, neden=giris_neden)]
    if stop is not None and stop == stop:
        parca.append("stop {}".format(_fiyat(stop)))
        isaret.append(Isaret("cizgi", islem["giris_ts"], stop,
                             bitis=islem["cikis_ts"], etiket="stop",
                             renk="stop"))
    if cfg.rr_target > 0 and hedef is not None and hedef == hedef:
        parca.append("hedef {}".format(_fiyat(hedef)))
        isaret.append(Isaret("cizgi", islem["giris_ts"], hedef,
                             bitis=islem["cikis_ts"], etiket="hedef",
                             renk="hedef"))
    adimlar.append(Adim("giris", GECTI, " \u00b7 ".join(parca),
                        islem["giris_ts"], tuple(isaret)))

    if cfg.breakeven_r > 0:
        oldu = islem["neden"] == "break_even"
        adimlar.append(Adim(
            "be", GECTI if oldu else ATLANDI,
            "stop girise cekildi" if oldu else "{} R'ye ulasilmadi".format(
                _f(cfg.breakeven_r, 1))))

    neden = {"stop": "stop", "hedef": "hedef",
             "ema": "EMA ters kapanis", "ters_sinyal": "ters kurulum",
             "break_even": "girisdeki stop", "gun_sonu": "gun sonu",
             "veri_sonu": "henuz yok \u2014 islem ACIK"}.get(
                 islem["neden"], islem["neden"])
    dakika = (islem["cikis_ts"] - islem["giris_ts"]).total_seconds() / 60
    sure = ("{:.0f} dk".format(dakika) if dakika < 120
            else "{:.0f} saat".format(dakika / 60))
    if islem["neden"] == "veri_sonu":
        adimlar.append(Adim("cikis", ATLANDI, "{} \u00b7 {} suruyor".format(
            neden, sure)))
    else:
        adimlar.append(Adim("cikis", GECTI, "{} \u00b7 {} @ {} \u00b7 {}".format(
            neden, saat(islem["cikis_ts"]), _fiyat(islem["cikis"]), sure),
            islem["cikis_ts"],
            (Isaret("nokta", islem["cikis_ts"], islem["cikis"],
                    etiket="CIKIS", yon=-d, neden={
                        "stop": "fiyat stopa degdi",
                        "hedef": "hedef fiyata ulasildi",
                        "ema": "kapanis EMA'nin ters tarafinda",
                        "ters_sinyal": "ters yonde {} kapanis".format(
                            cfg.confirm_bars),
                        "break_even": "girise cekilen stopa degdi",
                        "gun_sonu": "gun sonu, pozisyon kapatildi",
                    }.get(islem["neden"], neden)),)))

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


# --------------------------------------------------------------------------
# GELISTIRME MOTORU (bkz. gelistir.py) -- tarama bu ikisini kullanir
# --------------------------------------------------------------------------
GOSTERGE_PARAMLARI = frozenset({"ema_period", "confirm_bars"})

ARAMA_UZAYI = {
    "ema_period": [5, 10, 14, 20, 30, 45],
    "confirm_bars": [1, 2, 3],
    "entry": ["kirilim", "geri_cekilme"],
    "rr_target": [0.0, 1.5, 2.0, 3.0, 4.0],
    "swing_lookback": [5, 10, 20],
    "breakeven_r": [0.0, 0.5, 1.0, 2.0],
    "exit_on_ema": [True, False],
    "intraday": [True, False],
}


def hazir_simule(hazir: pl.DataFrame, cfg: EmaConfig, timeframe: str,
                 cost_bp: float) -> pl.DataFrame:
    """Ortak imza (bkz. gelistir.py)."""
    return simulate(hazir, cfg, timeframe, cost_bp)

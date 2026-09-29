"""BIST 30 -- canli sinyal taramasi icin veri.

KAYNAK: Yahoo Finance (yfinance). Dukascopy'de BIST hissesi yok.

Yahoo global veri kaynagi olarak elenmisti (docs/VERI_KAYNAGI_BULGULARI.md):
15dk gecmisi ~60 gunle sinirli, backtest icin YETERSIZ. Ama sinyal icin son
birkac gun yeter: EMA 10'un oturmasi ~30 bar ister, 5 gun ~160 bar demek.

VERITABANINA YAZILMAZ. Tarama her istekte taze cekilir (arayuzde birkac
dakikalik onbellek). "Tek gercek kaynak" ilkesi saklanan veri icindir; bu
gecici bir goruntuleme verisi.

UYARILAR
- Yahoo BIST fiyatlari ~15 dk gecikmeli olabilir.
- Yahoo henuz KAPANMAMIS bari da dondurur. Sinyal kapanmis bar uzerinden
  verilmeli; yoksa bar kapanana kadar fiyat degisip sinyal kaybolabilir.
  Kapanmamis son bar atilir.
- Temettu/bedelsiz duzeltmesi yapilmaz (auto_adjust=False). Birkac gunluk
  pencerede bolunme olursa EMA bozulur; nadir, kabul edildi.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import polars as pl

TR = ZoneInfo("Europe/Istanbul")

# Borsa Istanbul donemsel degisiklik duyurusu: 01.07-30.09.2026 doneminde
# BIST 30'a giren/cikan yok (2. ceyrekte VAKBN girdi, ULKER cikti).
# Her ceyrek basinda (Ocak/Nisan/Temmuz/Ekim) kontrol edilmeli.
BIST30_DONEM = "01.07.2026 - 30.09.2026"
BIST30 = (
    "AEFES", "AKBNK", "ASELS", "ASTOR", "BIMAS", "DSTKF", "EKGYO", "ENKAI",
    "EREGL", "FROTO", "GARAN", "GUBRF", "ISCTR", "KCHOL", "KRDMD", "MGROS",
    "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TAVHL", "TCELL", "THYAO",
    "TOASO", "TRALT", "TTKOM", "TUPRS", "VAKBN", "YKBNK",
)

SESSION_CLOSE_TR = time(18, 0)

# zaman dilimi -> (Yahoo araligi, cekilecek donem, bar dakikasi)
# CANLI SINYAL icin kisa donem (hizli olsun): 15dk 5 gun, 1 saat 1 ay.
_YAHOO = {"15m": ("15m", "5d", 15), "1h": ("60m", "1mo", 60)}

# BACKTEST icin en uzun donem (23.09.2026'da olculdu, GARAN/THYAO/ASELS/
# EREGL/SASA): gunluk "max" -> 6.781 bar, 2000-05-10'dan bugune (26 yil);
# saatlik "730d" -> 6.254 bar, ~3 yil (Yahoo'nun saatlik siniri).
# 15 dakika backtest icin YOK: Yahoo ~3 ay veriyor, gosterge isinmasi bile
# zor kapanir.
_YAHOO_GECMIS = {"1d": ("1d", "max", 1440), "1h": ("60m", "730d", 60)}


def fetch(
    timeframe: str = "15m",
    codes: tuple[str, ...] = BIST30,
    now: datetime | None = None,
    gecmis: bool = False,
) -> tuple[dict[str, pl.DataFrame], list[str]]:
    """Barlari ceker. Donen: ({kod: bar cercevesi (UTC)}, alinamayan kodlar).

    gecmis=False: canli sinyal icin son birkac gun, HAM fiyat.
    gecmis=True : backtest icin en uzun donem, DUZELTILMIS fiyat (bedelsiz
                  ve temettu duzeltmesi -- bkz. asagidaki not).
    """
    import yfinance as yf  # yalniz bu taramada gerekli; uygulama acilisini yavaslatmasin

    tablo = _YAHOO_GECMIS if gecmis else _YAHOO
    if timeframe not in tablo:
        raise ValueError("BIST'te desteklenmeyen zaman dilimi: {}".format(timeframe))
    interval, period, minutes = tablo[timeframe]
    now = now or datetime.now(timezone.utc)
    tickers = [c + ".IS" for c in codes]
    # BACKTEST icin auto_adjust=True sart: Turk hisselerinde bedelsiz ve
    # temettu sik; duzeltilmemis seride fiyat bir gunde yariya duser ve bu
    # SAHTE bir trend donusu sinyali uretir. Canli sinyalde ham fiyat
    # kullanilir (ekranda gorunen fiyatla ayni olsun).
    raw = yf.download(tickers, period=period, interval=interval,
                      group_by="ticker", auto_adjust=gecmis, progress=False,
                      threads=True)

    out: dict[str, pl.DataFrame] = {}
    failed: list[str] = []
    for code, ticker in zip(codes, tickers):
        try:
            sub = raw[ticker].dropna(subset=["Open", "High", "Low", "Close"])
        except KeyError:
            failed.append(code)
            continue
        if sub.empty:
            failed.append(code)
            continue

        pdf = sub.reset_index()
        pdf = pdf[[pdf.columns[0], "Open", "High", "Low", "Close", "Volume"]]
        pdf.columns = ["ts", "open", "high", "low", "close", "volume"]
        df = pl.from_pandas(pdf).with_columns(
            pl.col("ts").dt.convert_time_zone("UTC").dt.cast_time_unit("us"),
            pl.col("volume").cast(pl.Float64),
        )
        # Kapanmamis son bar atilir.
        df = df.filter(pl.col("ts") + timedelta(minutes=minutes) <= now).sort("ts")
        if df.is_empty():
            failed.append(code)
            continue
        out[code] = df
    return out, failed


# --------------------------------------------------------------------------
# BACKTEST VERISI -- indirme, TEMIZLEME, saklama (23 Eylul 2026)
# --------------------------------------------------------------------------
# Yahoo'nun duzeltilmis BIST serisi eskiye gidildikce BOZULUYOR. Olculdu
# (30 hisse, "max"):
#   * 2005 PARA REFORMU: 1 yeni lira = 1.000.000 eski lira. Duzeltme bu
#     kirilimi asamiyor -- TUPRS'un 2002 kapanisi 196.000.000 cikiyor.
#   * NEGATIF FIYAT: EREGL 2000-2004 arasi -15.153 gibi degerler veriyor.
#     13/30 hissede bozuk bar var.
#   * SICRAMA: MGROS 04.08.2009'da tek gunde +%304 (4,14 -> 16,76). BIST'te
#     gunluk fiyat limiti %10; bu gercek olamaz, duzeltme hatasi.
# Kural: bozuk bardan SONRAsi alinir, hicbir sekilde 2005'ten oncesi degil.
# Sonuc: 30/30 hisse kullanilabilir, 145.588 gunluk bar, en kotu gun -%27.
TEMIZ_TABAN = datetime(2005, 1, 3, tzinfo=timezone.utc)
MAKUL_HAREKET = 0.5      # tek barda |%50|'den buyuk hareket = veri hatasi


def temizle(df: pl.DataFrame, taban: datetime | None = TEMIZ_TABAN) -> pl.DataFrame:
    """Bozuk barlarin SONRASINI dondurur (aradan bar silmez).

    Aradan silmek bosluk birakir ve gostergeyi yine bozar; bu yuzden son
    bozuk barin tarihinden itibaren kesilir.
    """
    if df.is_empty():
        return df
    d = df.sort("ts").with_columns(
        (pl.col("close") / pl.col("close").shift(1) - 1).alias("_r"))
    bozuk = d.filter(
        (pl.min_horizontal("open", "high", "low", "close") <= 0)
        | (pl.col("close") < 0.01)
        | (pl.col("_r").abs() > MAKUL_HAREKET))
    if bozuk.height:
        d = d.filter(pl.col("ts") > bozuk["ts"][-1])
    if taban is not None:
        d = d.filter(pl.col("ts") >= taban)
    return d.drop("_r")


def backfill(con, timeframes: tuple[str, ...] = ("1d",),
             codes: tuple[str, ...] = BIST30) -> dict:
    """BIST gecmisini indirir, temizler, veritabanina yazar (idempotent).

    Donen: {"eklenen": n, "hisse": n, "alinamayan": [...], "atlanan": [...]}
    """
    from . import storage
    eklenen = 0
    alinamayan: list[str] = []
    atlanan: list[str] = []
    hisse = set()
    for tf in timeframes:
        veri, basarisiz = fetch(tf, codes, gecmis=True)
        alinamayan += ["{}/{}".format(k, tf) for k in basarisiz]
        for kod, df in veri.items():
            temiz = temizle(df, TEMIZ_TABAN if tf == "1d" else None)
            if temiz.height < 200:
                atlanan.append("{}/{} ({} bar)".format(kod, tf, temiz.height))
                continue
            eklenen += storage.upsert_bist_bars(con, kod, tf, temiz)
            hisse.add(kod)
    return {"eklenen": eklenen, "hisse": len(hisse),
            "alinamayan": alinamayan, "atlanan": atlanan}


def day_over(last_ts: datetime, now: datetime) -> bool:
    """BIST seansi 18:00 TR'de biter; ertesi gun ya da 18:00 sonrasi = bitti."""
    n = now.astimezone(TR)
    return n.date() > last_ts.astimezone(TR).date() or n.time() >= SESSION_CLOSE_TR

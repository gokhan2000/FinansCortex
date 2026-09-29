"""Dukascopy -> DuckDB veri çekme katmanı.

Anayasa 2.1: "Veri sağlayıcı katmanı pluggable olmalı." Dukascopy'ye özgü her şey
bu dosyada kapalı kalır; dışarıya yalnızca `backfill_instrument` / `backfill_all`
görünür. Sağlayıcı değişirse yalnızca `_fetch_chunk` yeniden yazılır.

Tasarım kuralları:
  * Yıl yıl parçalanır. Üç sebep: fetch'in limit=30000 sınırının altında kalmak
    (1 yıllık 15dk ~25.000 bar), ilerlemeyi görebilmek, ve kesinti hâlinde
    kaldığı yerden devam edebilmek.
  * Her parça yazıldıktan sonra commit edilir; 20 dakikalık dolum yarıda kesilse
    bile o ana kadarki veri kalıcıdır.
  * Yeniden çalıştırmak güvenlidir (upsert). Eksik parçalar tamamlanır.
  * TAKILMA KORUMASI (21 Eylül 2026): kullanıcı "sistem sürekli takılıyor,
    verileri güncellemede kalıyor" dedi. Sebep: dukascopy_python isteği
    `requests.get(...)` ile ZAMAN AŞIMSIZ atıyor; bağlantı bir kez asılı
    kalırsa güncelleme sonsuza kadar bekliyordu. Üç katman:
      1. Kütüphanenin kendi `requests`'i zaman aşımlı bir sarmalayıcıyla
         değiştirilir (bağlanma 8 sn, okuma 25 sn). Kütüphane dosyasına
         dokunulmaz; yalnızca onun modül içindeki `requests` adı.
      2. Yeniden deneme 7'den 2'ye iner (kütüphane her hatada 1 sn uyuyup
         tekrar deniyor; 7 deneme x 33 sn ~ 4 dk olurdu).
      3. `backfill_all(son_an=...)`: toplam süre sınırı. Süre dolunca kalan
         varlıklar ATLANIR (yarım yazma yok -- kontrol parçalar arasında),
         program eldeki veriyle açılır; bir sonraki güncelleme kaldığı
         yerden devam eder.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import dukascopy_python as dk
import polars as pl
import requests as _requests

from . import storage
from .instruments import INSTRUMENTS, Instrument, get

# Kütüphane her sayfa için INFO log basıyor ve kök logger'a basicConfig ile
# handler ekliyor; ilerleme çıktısını tamamen boğuyor. Hem seviyeyi yükseltip
# hem propagate'i kapatmak gerekiyor -- tek başına setLevel yetmedi.
_dk_log = logging.getLogger("DUKASCRIPT")
_dk_log.setLevel(logging.WARNING)
_dk_log.propagate = False

OHLC = ("open", "high", "low", "close")

# --- Takilma korumasi (bkz. modul basligi) ---------------------------------
BAGLANTI_SN = 8      # sunucuya baglanma
OKUMA_SN = 25        # cevap bekleme (bir yillik 15dk parca ~1-3 sn gelir)
DENEME = 2           # kutuphanenin yeniden deneme sayisi


class _ZamanAsimliRequests:
    """dukascopy_python'un modul icindeki `requests` adinin yerine gecer.

    Yalnizca `get` cagrisina zaman asimi ekler; geri kalan her sey (istisna
    siniflari vb.) gercek `requests` modulune yonlendirilir. Surecteki baska
    kutuphaneler (yfinance) etkilenmez -- global `requests` degismiyor.
    """

    def __getattr__(self, ad):
        return getattr(_requests, ad)

    @staticmethod
    def get(*args, **kwargs):
        kwargs.setdefault("timeout", (BAGLANTI_SN, OKUMA_SN))
        return _requests.get(*args, **kwargs)


dk.requests = _ZamanAsimliRequests()


class SureDoldu(Exception):
    """Toplam guncelleme suresi doldu (kalan isler atlandi)."""


def _fetch_chunk(
    inst: Instrument, start: datetime, end: datetime
) -> pl.DataFrame:
    """Tek bir zaman aralığını çeker ve normalize eder.

    Sağlayıcıya özgü tek yer burasıdır. Dönen çerçeve şema garantisi verir:
    ts (UTC) + open/high/low/close/volume, ts'e göre tekil ve sıralı.
    """
    raw = dk.fetch(
        inst.source_symbol, dk.INTERVAL_MIN_15, dk.OFFER_SIDE_BID, start, end,
        max_retries=DENEME,
    )
    if raw is None or raw.empty:
        return pl.DataFrame()

    df = pl.from_pandas(raw.reset_index())

    # Index adı sürüme göre 'timestamp' ya da 'index' olabilir.
    ts_col = next(
        (c for c in ("timestamp", "index", "ts") if c in df.columns), None
    )
    if ts_col is None:
        raise RuntimeError(
            "zaman sutunu bulunamadi, gelen sutunlar: {}".format(df.columns)
        )
    if ts_col != "ts":
        df = df.rename({ts_col: "ts"})

    if "volume" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("volume"))

    df = df.select(
        pl.col("ts"),
        *[pl.col(c).cast(pl.Float64) for c in OHLC],
        pl.col("volume").cast(pl.Float64),
    )

    # NOT NULL kısıtı için eksik OHLC satırlarını at.
    df = df.drop_nulls(subset=list(OHLC))

    # Aynı yazma partisinde tekrar eden anahtar olursa DuckDB ON CONFLICT hata
    # verir ("cannot affect row a second time"), bu yüzden burada tekilleştiriyoruz.
    return df.unique(subset=["ts"], keep="last").sort("ts")


def _year_chunks(start: datetime, end: datetime):
    """[start, end) aralığını yıl sınırlarında böler."""
    cursor = start
    while cursor < end:
        next_year = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
        stop = min(next_year, end)
        yield cursor, stop
        cursor = stop


def backfill_instrument(
    con,
    code: str,
    until: datetime | None = None,
    full: bool = False,
    son_an: float | None = None,
) -> int:
    """Tek enstrümanı doldurur. Dönen değer: eklenen yeni bar sayısı.

    `full=False` (varsayılan) ise veritabanındaki son bardan devam eder.
    `son_an`: time.monotonic() cinsinden süre sınırı; aşılırsa bir sonraki
    parçaya GEÇİLMEZ, SureDoldu fırlatılır (o ana kadar yazılan kalıcıdır).
    """
    inst = get(code)
    end = until or datetime.now(timezone.utc)

    start = datetime.combine(
        inst.history_start, datetime.min.time(), tzinfo=timezone.utc
    )
    if not full:
        seen = storage.last_ts(con, code)
        if seen is not None:
            # Son bar yeniden çekilir; kısmi/canlı bar ihtimaline karşı üzerine yazılır.
            start = max(start, seen)

    if start >= end:
        print("  {:<8} guncel".format(code), flush=True)
        return 0

    total = 0
    for chunk_start, chunk_end in _year_chunks(start, end):
        if son_an is not None and time.monotonic() > son_an:
            raise SureDoldu(code)
        try:
            df = _fetch_chunk(inst, chunk_start, chunk_end)
        except Exception as exc:  # noqa: BLE001 - tek yil patlarsa dolum durmasin
            print("  {:<8} {} HATA: {}".format(
                code, chunk_start.year, type(exc).__name__), flush=True)
            continue

        added = storage.upsert_bars(con, code, df)
        con.commit()
        total += added
        # flush zorunlu: cikti dosyaya yonlendirildiginde Python tamponluyor ve
        # uzun dolum boyunca hicbir ilerleme gorunmuyor.
        print("  {:<8} {}  {:>6} bar cekildi, {:>6} yeni".format(
            code, chunk_start.year, len(df), added), flush=True)

    return total


def backfill_all(con, until: datetime | None = None, full: bool = False,
                 sure_sn: float | None = None) -> int:
    """Tum enstrumanlar. `sure_sn` verilirse toplam sure siniri: dolunca
    kalan varliklar atlanir ve bu soylenir (hata degil, eldeki veriyle
    devam edilir)."""
    son_an = time.monotonic() + sure_sn if sure_sn else None
    grand_total = 0
    for n, inst in enumerate(INSTRUMENTS):
        print("{}".format(storage.describe(inst)), flush=True)
        try:
            grand_total += backfill_instrument(con, inst.code, until=until,
                                               full=full, son_an=son_an)
        except SureDoldu:
            kalan = [i.code for i in INSTRUMENTS[n:]]
            print("\n  SURE DOLDU ({:.0f} sn): {} atlandi. Program eldeki veriyle "
                  "acilacak;\n  bir sonraki guncelleme kaldigi yerden devam "
                  "eder.".format(sure_sn, ", ".join(kalan)), flush=True)
            break
    return grand_total

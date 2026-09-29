"""DuckDB depolama katmanı.

Anayasa 2.2 TimescaleDB diyordu; ölçüm sonrası Faz 1 için DuckDB'ye çevrildi
(bkz. docs/VERI_KAYNAGI_BULGULARI.md bölüm 12). Gerekçe: 8 enstrümanın 11 yıllık
15dk verisi ~2,2 milyon satır / ~50 MB. Bu boyut için sunucu süreci gereksiz;
ayrıca tek dosya olması "işyerine az veri taşıma" şartını doğrudan karşılıyor.

Faz 2'de Algolab canlı akışı geldiğinde TimescaleDB'ye geçiş gerekebilir. O geçişin
tek bir dosyayla sınırlı kalması için sistemin geri kalanı bu modülün fonksiyonlarını
çağırır, asla doğrudan SQL yazmaz.

Tasarım kuralları:
  * Her şey UTC. Bağlantı açılırken oturum saat dilimi UTC'ye sabitlenir.
  * Tek ham tablo: 15 dakikalık barlar. Üst zaman dilimleri VIEW olarak türetilir,
    ayrıca saklanmaz (anayasa 2.2 "tek gerçek kaynak" ilkesi).
  * Yazma idempotent: (instrument_id, ts) birincil anahtar + ON CONFLICT.
    Aynı dolum komutu kaç kez çalışırsa çalışsın veri bozulmaz, tekrar etmez.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl

from .instruments import INSTRUMENTS, Instrument

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "market.duckdb"

# 4 saatlik bar sınırı. 4 saat günü tam böldüğü ve epoch UTC gece yarısında
# başladığı için kovalar 00/04/08/12/16/20 UTC'ye oturur.
#
# ÖNEMLİ: 4H barın evrensel bir başlangıcı yoktur; birçok broker NY kapanışına
# hizalar ve TAMAMEN farklı barlar üretir -> farklı ATR -> farklı Chandelier
# sinyalleri. Buradaki tercih "00:00 UTC hizalı"dır ve bilinçlidir.
TIMEFRAME_VIEWS = {
    "bars_1h": "1 hour",
    "bars_4h": "4 hours",
    "bars_1d": "1 day",
}

_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS instrument_id_seq START 1;

CREATE TABLE IF NOT EXISTS instruments (
    instrument_id  INTEGER PRIMARY KEY DEFAULT nextval('instrument_id_seq'),
    code           TEXT NOT NULL UNIQUE,
    source_symbol  TEXT NOT NULL,
    category       TEXT NOT NULL,
    tags           TEXT[],
    session        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bars_15m (
    instrument_id  INTEGER NOT NULL,
    ts             TIMESTAMPTZ NOT NULL,
    open           DOUBLE NOT NULL,
    high           DOUBLE NOT NULL,
    low            DOUBLE NOT NULL,
    close          DOUBLE NOT NULL,
    volume         DOUBLE,
    PRIMARY KEY (instrument_id, ts)
);

-- BIST hisseleri AYRI durur (23 Eylul 2026, kullanici istegi: "BIST 30
-- hisseleri icinde ayri bir backtest"). Gerekcesi:
--   * Kaynak farkli (Yahoo, duzeltilmis fiyat) -- Dukascopy akisina karismaz
--   * Zaman dilimi TUREVLENMEZ: gunluk 26 yil, saatlik ~3 yil geriye gider;
--     gunlugu saatlikten uretmek mumkun degil. Bu yuzden timeframe sutunu
--     birincil anahtarin parcasi.
--   * 9 kuresel varligin listelerine (ana ekran, Grafikler, Gelistir)
--     karismasin diye `instruments` tablosuna KAYIT ACILMAZ.
CREATE TABLE IF NOT EXISTS bars_bist (
    code           TEXT NOT NULL,
    timeframe      TEXT NOT NULL,
    ts             TIMESTAMPTZ NOT NULL,
    open           DOUBLE NOT NULL,
    high           DOUBLE NOT NULL,
    low            DOUBLE NOT NULL,
    close          DOUBLE NOT NULL,
    volume         DOUBLE,
    PRIMARY KEY (code, timeframe, ts)
);
"""


def connect(
    db_path: Path | str | None = None, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Bağlantı açar, şemayı ve görünümleri hazırlar.

    read_only=True: DuckDB tek yazıcıya izin verir. Arayüz açıkken dolum
    betiğinin kilitlenmemesi için okuyucular salt-okunur açmalıdır. Şema ve
    görünümler dosyada zaten kalıcı olduğu için kurulum adımları atlanır.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        con = duckdb.connect(str(path), read_only=True)
        con.execute("SET TimeZone='UTC'")
        return con

    con = duckdb.connect(str(path))
    con.execute("SET TimeZone='UTC'")
    con.execute(_SCHEMA)
    _sync_instruments(con)
    _create_views(con)
    return con


def thread_cursor(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Ayni veritabanina baglanan, IS PARCACIGINA OZEL bir kopya dondurur.

    Tek bir DuckDB baglantisi es zamanli kullanilamaz: sorgunun sonucu
    baglantinin uzerinde durur, iki is parcacigi ayni anda `execute` ederse
    biri otekinin sonucunu ezer ve `fetchone()` None doner. Streamlit her
    betik calismasini ayri bir is parcaciginda yurutur (yeniden calistirma
    eskisi bitmeden baslayabilir, ikinci sekme de ayri bir oturumdur), bu
    yuzden paylasilan baglanti "enstruman kayitli degil: XAUUSD" gibi
    rastgele hatalar veriyordu. `cursor()` ucuz (~0,3 ms) ve ayni veritabani
    ornegini paylasir; veri iki kez acilmaz.

    TimeZone MIRAS ALINMAZ: yeni kopya isletim sisteminin saat dilimiyle
    (Europe/Istanbul) baslar. Ayarlanmazsa tum damgalar 3 saat kayar ve 4H
    kovalari UTC hizasindan cikar (anayasa: her sey UTC saklanir). Olculdu:
    ayarlandiginda sonuc kok baglantiyla birebir ayni.
    """
    cur = con.cursor()
    cur.execute("SET TimeZone='UTC'")
    return cur


def _sync_instruments(con: duckdb.DuckDBPyConnection) -> None:
    """Kayıt defterini tabloya yansıtır. Yeni enstrüman eklemek güvenlidir."""
    for inst in INSTRUMENTS:
        con.execute(
            """
            INSERT INTO instruments (code, source_symbol, category, tags, session)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (code) DO UPDATE SET
                source_symbol = excluded.source_symbol,
                category      = excluded.category,
                tags          = excluded.tags,
                session       = excluded.session
            """,
            [inst.code, inst.source_symbol, inst.category,
             list(inst.tags), inst.session],
        )


def _create_views(con: duckdb.DuckDBPyConnection) -> None:
    """Üst zaman dilimlerini 15dk'dan türetilen görünüm olarak tanımlar.

    arg_min/arg_max kullanılıyor: kovadaki ilk barın açılışı ve son barın kapanışı
    ts'e göre kesin biçimde seçilir; satır sırasına güvenilmez.
    """
    for view, width in TIMEFRAME_VIEWS.items():
        con.execute(
            """
            CREATE OR REPLACE VIEW {view} AS
            SELECT
                instrument_id,
                time_bucket(INTERVAL '{width}', ts) AS ts,
                arg_min(open, ts)  AS open,
                max(high)          AS high,
                min(low)           AS low,
                arg_max(close, ts) AS close,
                sum(volume)        AS volume,
                count(*)           AS bar_count
            FROM bars_15m
            GROUP BY instrument_id, 2
            """.format(view=view, width=width)
        )

    # Kod tarafının koda göre sorgu yapabilmesi için okunabilir birleşim.
    con.execute(
        """
        CREATE OR REPLACE VIEW v_bars_15m AS
        SELECT i.code, b.ts, b.open, b.high, b.low, b.close, b.volume
        FROM bars_15m b JOIN instruments i USING (instrument_id)
        """
    )


def instrument_id(con: duckdb.DuckDBPyConnection, code: str) -> int:
    row = con.execute(
        "SELECT instrument_id FROM instruments WHERE code = ?", [code]
    ).fetchone()
    if row is None:
        raise KeyError("enstruman kayitli degil: {}".format(code))
    return int(row[0])


def upsert_bars(
    con: duckdb.DuckDBPyConnection, code: str, df: pl.DataFrame
) -> int:
    """Barları idempotent şekilde yazar. Dönen değer: tablodaki net artış.

    `df` sütunları: ts (UTC), open, high, low, close, volume.
    Aynı veriyi tekrar yazmak satır sayısını değiştirmez.
    """
    if df.is_empty():
        return 0

    iid = instrument_id(con, code)
    before = con.execute(
        "SELECT count(*) FROM bars_15m WHERE instrument_id = ?", [iid]
    ).fetchone()[0]

    con.register("_incoming", df)
    con.execute(
        """
        INSERT INTO bars_15m (instrument_id, ts, open, high, low, close, volume)
        SELECT ?, ts, open, high, low, close, volume FROM _incoming
        ON CONFLICT (instrument_id, ts) DO UPDATE SET
            open   = excluded.open,
            high   = excluded.high,
            low    = excluded.low,
            close  = excluded.close,
            volume = excluded.volume
        """,
        [iid],
    )
    con.unregister("_incoming")

    after = con.execute(
        "SELECT count(*) FROM bars_15m WHERE instrument_id = ?", [iid]
    ).fetchone()[0]
    return int(after - before)


def coverage(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Enstrüman başına ilk/son bar ve toplam sayı."""
    return con.execute(
        """
        SELECT i.code,
               count(b.ts)  AS bars,
               min(b.ts)    AS first_ts,
               max(b.ts)    AS last_ts
        FROM instruments i
        LEFT JOIN bars_15m b USING (instrument_id)
        GROUP BY i.code
        ORDER BY i.code
        """
    ).pl()


def last_ts(con: duckdb.DuckDBPyConnection, code: str) -> datetime | None:
    """Dolumun kaldığı yerden devam edebilmesi için son yazılan bar."""
    row = con.execute(
        "SELECT max(ts) FROM bars_15m WHERE instrument_id = ?",
        [instrument_id(con, code)],
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def read_bars(
    con: duckdb.DuckDBPyConnection,
    code: str,
    timeframe: str = "15m",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pl.DataFrame:
    """Strateji/gösterge katmanının tek okuma kapısı.

    timeframe: '15m' | '1h' | '4h' | '1d'
    """
    table = "bars_15m" if timeframe == "15m" else "bars_{}".format(timeframe)
    if timeframe != "15m" and table not in TIMEFRAME_VIEWS:
        raise ValueError("desteklenmeyen zaman dilimi: {}".format(timeframe))

    sql = """
        SELECT ts, open, high, low, close, volume
        FROM {table}
        WHERE instrument_id = ?
    """.format(table=table)
    params: list = [instrument_id(con, code)]

    if start is not None:
        sql += " AND ts >= ?"
        params.append(start)
    if end is not None:
        sql += " AND ts < ?"
        params.append(end)
    sql += " ORDER BY ts"

    return con.execute(sql, params).pl()


BIST_TIMEFRAMES = ("1d", "1h")


def bist_var(con: duckdb.DuckDBPyConnection) -> bool:
    """BIST tablosu var mi.

    Sema yalnizca OKUMA-YAZMA baglantisinda kurulur (`connect`); arayuz
    salt-okunur baglanir. Bu yuzden BIST verisi hic indirilmemis bir
    veritabaninda tablo YOKTUR ve sorgu `CatalogException` verir. Ekranlar
    once bunu sorar; yoksa Veri Merkezi, indirme dugmesine basilmadan once
    cokerdi (23 Eylul 2026'da tam olarak bu oldu).
    """
    return bool(con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'bars_bist'"
    ).fetchone()[0])


_BIST_BOS = {"code": pl.Utf8, "timeframe": pl.Utf8,
             "first_ts": pl.Datetime(time_zone="UTC"),
             "last_ts": pl.Datetime(time_zone="UTC"), "bars": pl.Int64}
_BAR_BOS = {"ts": pl.Datetime(time_zone="UTC"), "open": pl.Float64,
            "high": pl.Float64, "low": pl.Float64, "close": pl.Float64,
            "volume": pl.Float64}


def read_bist_bars(
    con: duckdb.DuckDBPyConnection,
    code: str,
    timeframe: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pl.DataFrame:
    """BIST hissesinin barlari. `read_bars` ile ayni sutunlar, ayri tablo."""
    if not bist_var(con):
        return pl.DataFrame(schema=_BAR_BOS)
    if timeframe not in BIST_TIMEFRAMES:
        raise ValueError(
            "BIST'te desteklenmeyen zaman dilimi: {} (Yahoo gecmisi yetmiyor; "
            "gunluk 26 yil, saatlik ~3 yil, 15 dakika ~3 ay)".format(timeframe))
    sql = """
        SELECT ts, open, high, low, close, volume
        FROM bars_bist WHERE code = ? AND timeframe = ?
    """
    params: list = [code, timeframe]
    if start is not None:
        sql += " AND ts >= ?"
        params.append(start)
    if end is not None:
        sql += " AND ts < ?"
        params.append(end)
    sql += " ORDER BY ts"
    return con.execute(sql, params).pl()


def upsert_bist_bars(con: duckdb.DuckDBPyConnection, code: str,
                     timeframe: str, df: pl.DataFrame) -> int:
    """Idempotent yazma. Donen: tablodaki net artis (bkz. upsert_bars)."""
    if df.is_empty():
        return 0
    before = con.execute(
        "SELECT count(*) FROM bars_bist WHERE code = ? AND timeframe = ?",
        [code, timeframe]).fetchone()[0]
    rel = df.select("ts", "open", "high", "low", "close", "volume").to_arrow()
    con.register("_bist_yeni", rel)
    con.execute("""
        INSERT INTO bars_bist (code, timeframe, ts, open, high, low, close, volume)
        SELECT ?, ?, ts, open, high, low, close, volume FROM _bist_yeni
        ON CONFLICT (code, timeframe, ts) DO UPDATE SET
            open = excluded.open, high = excluded.high, low = excluded.low,
            close = excluded.close, volume = excluded.volume
    """, [code, timeframe])
    con.unregister("_bist_yeni")
    after = con.execute(
        "SELECT count(*) FROM bars_bist WHERE code = ? AND timeframe = ?",
        [code, timeframe]).fetchone()[0]
    return after - before


def bist_coverage(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Hisse basina ilk/son bar ve bar sayisi (Veri Merkezi ekrani icin)."""
    if not bist_var(con):
        return pl.DataFrame(schema=_BIST_BOS)
    return con.execute("""
        SELECT code, timeframe, min(ts) AS first_ts, max(ts) AS last_ts,
               count(*) AS bars
        FROM bars_bist GROUP BY code, timeframe ORDER BY code, timeframe
    """).pl()


def latest_snapshot(
    con: duckdb.DuckDBPyConnection, codes: list[str] | None = None
) -> pl.DataFrame:
    """Ana ekrandaki fiyat seridi icin: son fiyat + gunluk degisim.

    Degisim, son fiyatin BIR ONCEKI GUNUN kapanisina gore farkidir.
    `bars_1d` gorunumundeki en son kova bugunun (henuz kapanmamis) barisidir,
    o yuzden referans olarak sondan ikinci kova alinir (rn = 2).

    Donen sutunlar: code, ts, close, prev_close, change_pct
    """
    sql = """
        WITH son AS (
            SELECT instrument_id,
                   max(ts)             AS ts,
                   arg_max(close, ts)  AS close
            FROM bars_15m GROUP BY 1
        ),
        gunluk AS (
            SELECT instrument_id, close,
                   row_number() OVER (PARTITION BY instrument_id
                                      ORDER BY ts DESC) AS rn
            FROM bars_1d
        )
        SELECT i.code, s.ts, s.close,
               g.close AS prev_close,
               CASE WHEN g.close IS NULL OR g.close = 0 THEN NULL
                    ELSE 100.0 * (s.close - g.close) / g.close
               END AS change_pct
        FROM son s
        JOIN instruments i USING (instrument_id)
        LEFT JOIN gunluk g
               ON g.instrument_id = s.instrument_id AND g.rn = 2
    """
    df = con.execute(sql).pl()
    if codes:
        # Istenen sirayi koru -- ekranda sabit bir duzen olsun.
        order = {c: n for n, c in enumerate(codes)}
        df = (df.filter(pl.col("code").is_in(codes))
                .with_columns(pl.col("code").replace_strict(order, default=999)
                              .alias("_o"))
                .sort("_o").drop("_o"))
    return df


def describe(inst: Instrument) -> str:
    return "{} ({}, {})".format(inst.code, inst.category, inst.session)

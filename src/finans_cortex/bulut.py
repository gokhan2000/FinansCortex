"""Bulut (Streamlit Community Cloud) icin veritabani kurulumu.

Bulutta `data/market.duckdb` yok: 232 MB, GitHub'in 100 MB sinirina sigmaz.
Bunun yerine veri `bulut_veri/*.parquet` olarak (toplam ~55 MB, zstd) depoda
durur ve uygulama ilk acilista veritabanini bunlardan KURAR (~10 sn).
Evdeki bilgisayarda `data/market.duckdb` zaten vardir, bu modul hicbir sey
yapmaz. Parquet dosyalarini yazmak: scripts/bulut_veri_yaz.py

enstruman numaralari (instrument_id) kodla eslestirilir; bulutta kayit
defteri farkli sirada olsa bile barlar dogru enstrumana baglanir.
"""

from __future__ import annotations

from pathlib import Path

from . import storage

PARQUET_DIZINI = Path(__file__).resolve().parents[2] / "bulut_veri"
TABLOLAR = ("instruments", "bars_15m", "bars_bist")


def hazirla(db_yolu: Path | str | None = None,
            parquet_dizini: Path | str | None = None) -> bool:
    """Veritabani yoksa parquet'ten kurar. Kurduysa True doner."""
    db = Path(db_yolu) if db_yolu else storage.DEFAULT_DB_PATH
    pq = Path(parquet_dizini) if parquet_dizini else PARQUET_DIZINI
    if db.exists() or not (pq / "bars_15m.parquet").exists():
        return False

    tmp = db.with_suffix(".kuruluyor")
    tmp.unlink(missing_ok=True)
    con = storage.connect(tmp)  # sema + enstruman kaydi + gorunumler
    try:
        f = {t: (pq / f"{t}.parquet").as_posix() for t in TABLOLAR}
        con.execute(
            f"""
            INSERT INTO bars_15m
            SELECT i.instrument_id, b.ts, b.open, b.high, b.low, b.close, b.volume
            FROM read_parquet('{f['bars_15m']}') b
            JOIN read_parquet('{f['instruments']}') p USING (instrument_id)
            JOIN instruments i ON i.code = p.code
            """
        )
        con.execute(
            f"INSERT INTO bars_bist SELECT * FROM read_parquet('{f['bars_bist']}')"
        )
        con.execute("CHECKPOINT")
    finally:
        con.close()
    tmp.replace(db)
    return True

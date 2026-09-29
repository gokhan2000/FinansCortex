"""Bulut icin GUNLUK guncelleme (GitHub Actions calistirir, elle de calisir).

  1. Depodaki parquet'ten (ana + eski son.parquet) gecici veritabani kurar
  2. Dukascopy'den eksik barlari ceker (ingest.backfill_all, kaldigi yerden)
  3. Ana verinin USTUNDEKI barlari bulut_veri/son.parquet'e yazar
     (her enstruman icin ana verinin son barindan 1 gun oncesinden itibaren)

Sonuc kucuk bir dosyadir (gunde ~500 satir); 55 MB'lik ana veri her gun
git'e yazilmaz. Kullanici ana veriyi BULUT_VERI_YAZ.bat ile tazeleyince
son.parquet silinir ve tekrar sifirdan birikir.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402

from finans_cortex import bulut, ingest, storage  # noqa: E402


def main() -> None:
    pq = bulut.PARQUET_DIZINI
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "market.duckdb"
        bulut.hazirla(db, pq)

        con = storage.connect(db)
        try:
            eklenen = ingest.backfill_all(con, sure_sn=1500)
            print(f"\nToplam {eklenen} yeni bar")
            base = pq / "bars_15m.parquet"
            inst = pq / "instruments.parquet"
            son = pq / bulut.SON
            n = con.execute(
                f"""
                COPY (
                  SELECT i.code, b.ts, b.open, b.high, b.low, b.close, b.volume
                  FROM bars_15m b JOIN instruments i USING (instrument_id)
                  JOIN (
                    SELECT p.code, max(x.ts) AS son_ts
                    FROM read_parquet('{base.as_posix()}') x
                    JOIN read_parquet('{inst.as_posix()}') p USING (instrument_id)
                    GROUP BY p.code
                  ) t ON t.code = i.code
                  WHERE b.ts >= t.son_ts - INTERVAL 1 DAY
                  ORDER BY i.code, b.ts
                ) TO '{son.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
                """
            )
            satir = duckdb.connect(":memory:").execute(
                f"SELECT count(*), max(ts) FROM read_parquet('{son.as_posix()}')"
            ).fetchone()
            print(f"son.parquet: {satir[0]:,} satir, en yeni bar {satir[1]}")
        finally:
            con.close()


if __name__ == "__main__":
    main()

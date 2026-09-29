"""data/market.duckdb -> bulut_veri/*.parquet (bulut icin ~55 MB).

BULUT_VERI_YAZ.bat cift tiklaninca calisir. Uygulama kapaliyken calistirin.
Sonra bulut_veri/ klasoru GitHub'a gonderilir (Streamlit Cloud oradan okur).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402

from finans_cortex import bulut, storage  # noqa: E402


def main() -> None:
    hedef = bulut.PARQUET_DIZINI
    hedef.mkdir(exist_ok=True)
    con = duckdb.connect(str(storage.DEFAULT_DB_PATH), read_only=True)
    for t in bulut.TABLOLAR:
        f = hedef / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{f.as_posix()}' "
                    "(FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 19)")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n:,} satir, {f.stat().st_size // 1024:,} KB")
    # Ana veri tazelendi: eski "son gunler" dosyasi artik gereksiz.
    (hedef / bulut.SON).unlink(missing_ok=True)
    (hedef / bulut.SON_BIST).unlink(missing_ok=True)
    print("Tamam:", hedef)


if __name__ == "__main__":
    main()

"""Bulut (Streamlit Community Cloud) icin veritabani kurulumu.

Bulutta `data/market.duckdb` yok: 232 MB, GitHub'in 100 MB sinirina sigmaz.
Bunun yerine veri `bulut_veri/*.parquet` olarak (toplam ~55 MB, zstd) depoda
durur ve uygulama veritabanini bunlardan KURAR (~12 sn). Evdeki bilgisayarda
`data/market.duckdb` zaten vardir, bu modul hicbir sey yapmaz.

IKI KATMAN
  bars_15m.parquet, bars_bist.parquet, instruments.parquet
      ANA VERI. Kullanici evde BULUT_VERI_YAZ.bat ile tazeler
      (scripts/bulut_veri_yaz.py).
  son.parquet
      SON GUNLER (kucuk, kod sutunlu). GitHub Actions her gun
      scripts/bulut_guncelle.py ile Dukascopy'den ceker ve bunu yazar.
      Ana verinin ustune eklenir (ayni bar varsa ustune yazar).

enstruman numaralari (instrument_id) kodla eslestirilir; bulutta kayit
defteri farkli sirada olsa bile barlar dogru enstrumana baglanir.

YENIDEN KURMA: git'ten yeni son.parquet gelince kurulu veritabani eskir.
Kurulumda parquet dosyalarinin imzasi (boyut+zaman) `.imza` dosyasina
yazilir; imza degisince veritabani yeniden kurulur.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import storage

PARQUET_DIZINI = Path(__file__).resolve().parents[2] / "bulut_veri"
TABLOLAR = ("instruments", "bars_15m", "bars_bist")
SON = "son.parquet"


def _imza(pq: Path) -> str:
    parcalar = []
    for ad in [f"{t}.parquet" for t in TABLOLAR] + [SON]:
        f = pq / ad
        parcalar.append(f"{ad}:{f.stat().st_size}" if f.exists() else f"{ad}:-")
    return "|".join(parcalar)


def hazirla(db_yolu: Path | str | None = None,
            parquet_dizini: Path | str | None = None) -> bool:
    """Veritabani yoksa ya da parquet degistiyse kurar. Kurduysa True doner.

    Yerelde (parquet dizini yoksa ya da yerel veritabani bulut'tan degilse)
    hicbir sey yapmaz: `.imza` dosyasi yoksa veritabani bulutta kurulmamistir.
    """
    db = Path(db_yolu) if db_yolu else storage.DEFAULT_DB_PATH
    pq = Path(parquet_dizini) if parquet_dizini else PARQUET_DIZINI
    if not (pq / "bars_15m.parquet").exists():
        return False

    imza_dosyasi = db.with_suffix(".imza")
    yeni = _imza(pq)
    if db.exists():
        if not imza_dosyasi.exists():      # yerel (elle kurulmus) veritabani
            return False
        if imza_dosyasi.read_text() == yeni:
            return False

    tmp = db.with_suffix(f".kuruluyor{os.getpid()}")
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
        son = pq / SON
        if son.exists():
            con.execute(
                f"""
                INSERT OR REPLACE INTO bars_15m
                SELECT i.instrument_id, s.ts, s.open, s.high, s.low, s.close,
                       s.volume
                FROM read_parquet('{son.as_posix()}') s
                JOIN instruments i ON i.code = s.code
                """
            )
        con.execute("CHECKPOINT")
    finally:
        con.close()
    tmp.replace(db)
    imza_dosyasi.write_text(yeni)
    return True

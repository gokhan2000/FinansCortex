"""Strateji 1 (EMA 10 iki kapanis) -- tum enstrumanlarda rapor.

Iki giris turunu (kirilim / geri cekilme) yan yana calistirir.

Kullanim:
    python scripts/ema_report.py              # son 3 yil, 15dk
    python scripts/ema_report.py --tum        # tum gecmis
    python scripts/ema_report.py --1h         # 1 saatlik barlar
    python scripts/ema_report.py XAUUSD DAX
"""

import sys
import time
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import ema_two_close as ema, storage  # noqa: E402
from finans_cortex.instruments import INSTRUMENTS  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    days = None if "--tum" in args else 1095
    timeframe = "1h" if "--1h" in args else "15m"
    codes = [a for a in args if not a.startswith("--")] or [
        i.code for i in INSTRUMENTS
    ]

    print("donem: {} · zaman dilimi: {} · maliyet: DEFAULT_COSTS (TAHMIN)\n"
          .format("tum gecmis" if days is None else "son 3 yil", timeframe))

    con = storage.connect(read_only=True)
    rows = []
    for code in codes:
        for entry in ema.ENTRY_TYPES:
            t0 = time.perf_counter()
            r = ema.run(con, code, timeframe, ema.EmaConfig(entry=entry), days)
            m = dict(r.metrics)
            nedenler = m.pop("nedenler", {})
            m.update({"code": code, "giris": entry,
                      "nedenler": " ".join("{}:{}".format(k, v)
                                           for k, v in nedenler.items()),
                      "sn": round(time.perf_counter() - t0, 2)})
            rows.append(m)
    con.close()

    out = pl.DataFrame(rows).select(
        "code", "giris", "islem", "islem_ay", "kazanan_%", "kar_faktoru",
        "getiri_%", "al_tut_%", "MaxDD_%", "Sharpe", "long_%", "short_%",
        "ort_R", "ort_islem_bp", "sn", "nedenler",
    )
    with pl.Config(tbl_rows=100, tbl_cols=30, tbl_width_chars=260,
                   fmt_str_lengths=80):
        print(out)
        print("\n--- ortalama ---")
        print(out.group_by("giris").agg(
            pl.col("Sharpe", "getiri_%", "MaxDD_%", "kazanan_%",
                   "kar_faktoru", "long_%", "short_%").mean().round(2)
        ))


if __name__ == "__main__":
    main()

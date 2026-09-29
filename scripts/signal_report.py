"""Chandelier Exit sinyal frekans raporu.

Kullanicinin sordugu soruyu olcuyle cevaplar: "15 dk. cok gurultu olur gibi".
Her enstrumanda 15dk ve 4H icin Normal/Maverick profillerinin urettigi sinyal
sayisini ve sinyaller arasi ortalama mesafeyi karsilastirir.

Kullanim:
    python scripts/signal_report.py
    python scripts/signal_report.py XAUUSD
"""

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import indicators, storage  # noqa: E402
from finans_cortex.instruments import INSTRUMENTS  # noqa: E402

TIMEFRAMES = ("15m", "4h")
BAR_MINUTES = {"15m": 15, "4h": 240}


def analyse(con, code: str, timeframe: str, config) -> dict | None:
    df = storage.read_bars(con, code, timeframe)
    if df.height < config.atr_period * 3:
        return None

    out = indicators.chandelier_exit(df, config)
    n_sig = out.filter(pl.col("signal").is_not_null()).height

    span_days = (df["ts"][-1] - df["ts"][0]).total_seconds() / 86400
    months = span_days / 30.44

    return {
        "code": code,
        "tf": timeframe,
        "profil": config.name,
        "bar": df.height,
        "sinyal": n_sig,
        "sinyal_ay": round(n_sig / months, 1) if months else 0.0,
        # Sinyaller arasi ortalama sure -- pozisyonun ne kadar tutuldugunun olcusu
        "ort_saat": round(
            (df.height / n_sig) * BAR_MINUTES[timeframe] / 60, 1
        ) if n_sig else 0.0,
    }


def main() -> None:
    codes = sys.argv[1:] or [i.code for i in INSTRUMENTS]
    con = storage.connect()

    rows = []
    for code in codes:
        for tf in TIMEFRAMES:
            for cfg in (indicators.NORMAL, indicators.MAVERICK):
                r = analyse(con, code, tf, cfg)
                if r:
                    rows.append(r)

    if not rows:
        print("veri yok -- once scripts/backfill.py calistirin")
        return

    df = pl.DataFrame(rows)
    with pl.Config(tbl_rows=100, tbl_width_chars=140):
        print(df)

        print("\n--- 15dk vs 4H (Normal profil) ---")
        pivot = (
            df.filter(pl.col("profil") == "normal")
            .pivot(values="sinyal_ay", index="code", on="tf")
            .rename({"15m": "15dk_sinyal_ay", "4h": "4h_sinyal_ay"})
        )
        pivot = pivot.with_columns(
            (pl.col("15dk_sinyal_ay") / pl.col("4h_sinyal_ay"))
            .round(1).alias("gurultu_katsayisi")
        )
        print(pivot)

    con.close()


if __name__ == "__main__":
    main()

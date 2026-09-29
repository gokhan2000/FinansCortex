"""Backtest raporu: 'naif 4H girisi' ile '15dk zamanlamali giris' karsilastirmasi.

Bu betik, docs/CHANDELIER_BULGULARI.md bolum 8'deki acik soruyu cevaplar:
15dk beklemek 4-24 bp daha pahaliya girmeye deger mi?

Kullanim:
    python scripts/backtest_report.py
    python scripts/backtest_report.py XAUUSD
    python scripts/backtest_report.py --maverick
"""

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import backtest, indicators, storage, strategy  # noqa: E402
from finans_cortex.instruments import INSTRUMENTS  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    maverick = "--maverick" in args
    codes = [a for a in args if not a.startswith("--")] or [
        i.code for i in INSTRUMENTS
    ]
    cfg = indicators.MAVERICK if maverick else indicators.NORMAL

    print("profil: {} (ATR {} / carpan {})".format(
        cfg.name, cfg.atr_period, cfg.atr_multiplier))
    print("maliyet: DEFAULT_COSTS -- TAHMINDIR, dogrulanmali\n")

    con = storage.connect()
    rows = []

    for code in codes:
        df = strategy.combined_signals(con, code, entry_config=cfg, trend_config=cfg)
        if df.is_empty():
            continue
        cost = backtest.cost_for(code)
        for mode in ("naive", "timed"):
            r = backtest.run(df, cost, mode=mode)
            if r:
                r["code"] = code
                r["spread_bp"] = cost.spread_bp
                rows.append(r)

    if not rows:
        print("veri yok")
        con.close()
        return

    out = pl.DataFrame(rows).select(
        "code", "mod", "islem", "getiri_%", "CAGR_%", "Sharpe",
        "MaxDD_%", "kazanan_%", "kar_faktoru", "ort_islem_bp",
    )

    with pl.Config(tbl_rows=100, tbl_width_chars=160):
        print(out)

        print("\n--- MOD KARSILASTIRMASI (Sharpe) ---")
        piv = out.pivot(values="Sharpe", index="code", on="mod")
        piv = piv.with_columns(
            (pl.col("timed") - pl.col("naive")).round(2).alias("fark")
        )
        print(piv)

        print("\n--- ozet ---")
        for mode in ("naive", "timed"):
            s = out.filter(pl.col("mod") == mode)
            print("  {:<6} ort Sharpe {:>6.2f} | ort CAGR {:>6.2f}% | ort MaxDD {:>6.1f}%".format(
                mode,
                float(s["Sharpe"].mean()),
                float(s["CAGR_%"].mean()),
                float(s["MaxDD_%"].mean()),
            ))

    con.close()


if __name__ == "__main__":
    main()

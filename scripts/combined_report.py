"""4H yon + 15dk zamanlama stratejisinin sinyal raporu.

Kullanim:
    python scripts/combined_report.py
    python scripts/combined_report.py XAUUSD
"""

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import storage, strategy  # noqa: E402
from finans_cortex.instruments import INSTRUMENTS  # noqa: E402


def check_no_lookahead(con, code: str) -> None:
    """4H yonunun gelecekten sizmadigini dogrular.

    Her 15dk barinda kullanilan 4H barinin KAPANIS ani, o 15dk barinin
    zamanindan sonra olamaz.
    """
    df = strategy.combined_signals(con, code)
    df = df.filter(pl.col("valid_from").is_not_null())
    if df.is_empty():
        print("  {:<8} dogrulanamadi (veri yok)".format(code))
        return

    ihlal = df.filter(pl.col("valid_from") > pl.col("ts")).height
    gecikme = (df["ts"] - df["valid_from"]).dt.total_hours()
    print("  {:<8} lookahead ihlali: {:<5} | ort gecikme {:.2f} sa | max {:.1f} sa".format(
        code, ihlal, gecikme.mean(), gecikme.max()))


def main() -> None:
    codes = sys.argv[1:] or [i.code for i in INSTRUMENTS]
    con = storage.connect()

    print("LOOK-AHEAD DOGRULAMASI (ihlal 0 olmali)\n")
    for code in codes:
        check_no_lookahead(con, code)

    print("\n\n4H YON + 15dk ZAMANLAMA\n")
    rows = []
    timing = []
    for code in codes:
        df = strategy.combined_signals(con, code)
        s = strategy.summarise(df)
        if s:
            s["code"] = code
            rows.append(s)
        t = strategy.timing_benefit(df)
        if t:
            t["code"] = code
            timing.append(t)

    if not rows:
        print("veri yok")
        con.close()
        return

    out = pl.DataFrame(rows).select(
        "code", "bar", "ham_ay", "hizali_ay", "giris_ay",
        "giris", "long", "short",
    )
    with pl.Config(tbl_rows=50, tbl_width_chars=140):
        print(out)

        print("\n--- ayda kac sinyal? (huniyi asagi dogru okuyun) ---")
        print(out.select(
            "code",
            pl.col("ham_ay").alias("1_ham_15dk"),
            pl.col("hizali_ay").alias("2_4H_hizali"),
            pl.col("giris_ay").alias("3_bacak_basi_tek"),
        ).with_columns(
            (pl.col("1_ham_15dk") / pl.col("3_bacak_basi_tek"))
            .round(1).alias("toplam_azalma")
        ))

        if timing:
            print("\n--- 15dk zamanlamasi giris fiyatini iyilestirdi mi? ---")
            print("(pozitif bp = 4H kapanisindan girmeye gore daha iyi fiyat)")
            print(pl.DataFrame(timing).select(
                "code", "islem", "ort_bp", "medyan_bp", "kazandiran_%"))

    con.close()


if __name__ == "__main__":
    main()

"""Hayalet (donuk) bar temizligi.

Piyasa kapaliyken beslemenin son fiyati tekrar tekrar yayinlamasiyla olusan,
gun boyu fiyati hic degismeyen barlari tespit eder ve siler.

Neden onemli: bu barlarda True Range = 0. ATR yapay olarak coker, Chandelier
Exit stoplari asiri daralir ve piyasa acilinca sahte sinyal uretir.

Kullanim:
    python scripts/clean_ghost_bars.py            # sadece rapor (varsayilan)
    python scripts/clean_ghost_bars.py --apply    # gercekten sil
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import quality, storage  # noqa: E402
from finans_cortex.instruments import INSTRUMENTS  # noqa: E402


def main() -> None:
    apply = "--apply" in sys.argv
    con = storage.connect()

    print("HAYALET GUN TARAMASI (gun boyu fiyat hic degismemis)\n")
    total_days = 0
    total_bars = 0
    targets = []

    for inst in INSTRUMENTS:
        fd = quality.flat_days(con, inst.code)
        if fd.is_empty():
            print("  {:<8} temiz".format(inst.code))
            continue

        bars = int(fd["bars"].sum())
        days = fd.height
        total_days += days
        total_bars += bars
        targets.append(inst.code)

        yrs = sorted({d.year for d in fd["day"].to_list()})
        print("  {:<8} {:>4} gun / {:>6} bar   yillar: {}".format(
            inst.code, days, bars,
            "{}-{}".format(yrs[0], yrs[-1]) if len(yrs) > 1 else str(yrs[0])))

    print("\n  TOPLAM: {} gun / {} bar".format(total_days, total_bars))

    if not apply:
        print("\n  (rapor modu -- silmek icin: --apply)")
        con.close()
        return

    print("\nSILINIYOR...")
    removed = 0
    for code in targets:
        n = quality.remove_flat_days(con, code)
        removed += n
        print("  {:<8} {} bar silindi".format(code, n))

    print("\n  toplam {} bar silindi".format(removed))
    print("\nTEMIZLIK SONRASI KALITE")
    print(quality.report(con))
    con.close()


if __name__ == "__main__":
    main()

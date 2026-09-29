"""Veri dolum komutu.

Kullanim:
    python scripts/backfill.py              # hepsi, kaldigi yerden devam
    python scripts/backfill.py XAUUSD       # tek enstruman
    python scripts/backfill.py --full       # bastan tumunu tazele
    python scripts/backfill.py --sure 150   # en fazla 150 sn (BASLAT.bat boyle)

Istenildigi kadar tekrar calistirilabilir; veri bozulmaz, tekrar etmez.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finans_cortex import ingest, quality, storage  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:]]
    full = "--full" in args
    sure = None
    if "--sure" in args:
        i = args.index("--sure")
        sure = float(args[i + 1])
        del args[i:i + 2]
    codes = [a for a in args if not a.startswith("--")]

    con = storage.connect()
    t0 = time.time()

    if codes:
        total = sum(
            ingest.backfill_instrument(con, c, full=full) for c in codes
        )
    else:
        total = ingest.backfill_all(con, full=full, sure_sn=sure)

    print("\n{}".format("=" * 62))
    print("toplam {} yeni bar, {:.1f} sn".format(total, time.time() - t0))

    print("\nKAPSAM")
    print(storage.coverage(con))

    print("\nKALITE")
    print(quality.report(con))

    con.close()


if __name__ == "__main__":
    main()

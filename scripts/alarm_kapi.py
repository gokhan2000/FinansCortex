"""Alarm calismasi bu dakikada gerekli mi? (yalniz standart kutuphane)

GitHub Actions'ta ilk adimdir: gerek yoksa pahali adimlar (pip, veri, hesap)
atlanir ve GitHub dakikasi harcanmaz. cikis_izle.py de ayni kurali kullanir.

Kural (UTC): 15 dk secili ise yalniz ayardaki SAAT ARALIGINDA (TR saati,
varsayilan 10-22) her calisma -- gun boyu 15 dakikada bir calismak GitHub'in
ucretsiz aylik 2000 dakikasini asar; 4 saat yalniz 00/04/08/12/16/20
kapanislarinin ilk 50 dakikasinda; gunluk yalniz 00 UTC'de.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

YOL = Path(__file__).resolve().parents[1] / "config" / "alarm.json"


def zamanlar(ayar: dict) -> set[str]:
    return {tf for s in ayar.get("stratejiler", {}).values()
            for tfs in s.get("secim", {}).values() for tf in tfs}


def calismali(ayar: dict, simdi: datetime) -> bool:
    tf = zamanlar(ayar)
    if "15m" in tf:
        bas, bit = ayar.get("saat15", [10, 22])
        if bas <= (simdi.hour + 3) % 24 < bit:     # TR = UTC+3
            return True
    if "4h" in tf and simdi.hour % 4 == 0 and simdi.minute < 50:
        return True
    if "1d" in tf and simdi.hour == 0 and simdi.minute < 50:
        return True
    return False


def main() -> None:
    try:
        ayar = json.loads(YOL.read_text("utf-8"))
    except (OSError, ValueError):
        ayar = {"stratejiler": {}}
    devam = calismali(ayar, datetime.now(timezone.utc))
    print("devam =", devam)
    cikti = os.environ.get("GITHUB_OUTPUT")
    if cikti:
        with open(cikti, "a", encoding="utf-8") as f:
            f.write(f"devam={'true' if devam else 'false'}\n")


if __name__ == "__main__":
    main()

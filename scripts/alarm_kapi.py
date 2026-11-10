"""Alarm calismasi bu dakikada gerekli mi? (yalniz standart kutuphane)

GitHub Actions'ta ilk adimdir: gerek yoksa pahali adimlar (pip, veri, hesap)
atlanir ve GitHub dakikasi harcanmaz. cikis_izle.py de ayni kurali kullanir.

Kural (UTC): 15 dk secili ise yalniz ayardaki SAAT ARALIGINDA (TR saati,
varsayilan 10-22) her calisma -- gun boyu 15 dakikada bir calismak GitHub'in
ucretsiz aylik 2000 dakikasini asar; 4 saat yalniz 00/04/08/12/16/20
kapanislarinin ilk 50 dakikasinda; gunluk yalniz 00 UTC'de.

YAKALAMA (10.11.2026): GitHub zamanlayicisi "her 15 dakikada" demesine ragmen
pratikte cok seyrek tetikliyor (3 gunde ~6 calisma). Yalniz "tam su dakika"
kuralina guvenilirse alarm kapanis pencerelerini kacirir. Bu yuzden son tam
calismadan 3 saatten fazla gectiyse (ya da hic calisilmadiysa) kural ne olursa
olsun CALISILIR; olaylar son birkac barda aranir, ayni olay iki kez gitmez.
Son calisma zamani `.alarm/durum.json`'dadir (Actions onbellegi tasir).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

YOL = Path(__file__).resolve().parents[1] / "config" / "alarm.json"
DURUM = Path(__file__).resolve().parents[1] / ".alarm" / "durum.json"
YAKALAMA = timedelta(hours=3)


def durum_oku() -> tuple[set[str], datetime | None]:
    """(gonderilen olay anahtarlari, son tam calisma). Eski biçim: yalniz liste."""
    try:
        d = json.loads(DURUM.read_text("utf-8"))
    except (OSError, ValueError):
        return set(), None
    if isinstance(d, list):
        return set(d), None
    try:
        son = datetime.fromisoformat(d["son_calisma"])
    except (KeyError, ValueError, TypeError):
        son = None
    return set(d.get("gonderilen", [])), son


def durum_yaz(gonderilen: set[str], son: datetime) -> None:
    DURUM.parent.mkdir(exist_ok=True)
    # Yalniz son 500 anahtar: dosya buyumesin.
    DURUM.write_text(json.dumps({
        "gonderilen": sorted(gonderilen)[-500:],
        "son_calisma": son.isoformat()}), "utf-8")


def zamanlar(ayar: dict) -> set[str]:
    return {tf for s in ayar.get("stratejiler", {}).values()
            for tfs in s.get("secim", {}).values() for tf in tfs}


def calismali(ayar: dict, simdi: datetime,
              son_calisma: datetime | None = None) -> bool:
    tf = zamanlar(ayar)
    if not tf:
        return False
    if son_calisma is None or simdi - son_calisma > YAKALAMA:
        return True                               # yakalama: uzun suredir bakilmadi
    if simdi.hour == 7 and simdi.minute < 50:     # gunluk "calisiyor" ozeti
        return True
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
    _, son = durum_oku()
    devam = calismali(ayar, datetime.now(timezone.utc), son)
    print("devam =", devam)
    cikti = os.environ.get("GITHUB_OUTPUT")
    if cikti:
        with open(cikti, "a", encoding="utf-8") as f:
            f.write(f"devam={'true' if devam else 'false'}\n")


if __name__ == "__main__":
    main()

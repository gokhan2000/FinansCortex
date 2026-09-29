"""DeepCortex baslatici -- masaustu/Baslat ikonu ve Chrome yer imi bunu cagirir.

Kullanici (21.09.2026): "Chrome'a bir kisayol ikonu ekle, oraya basip
baslatayim." Chrome guvenlik geregi yerel bir programi kendiliginden
baslatamaz; bu yuzden ikon ve yer imi bu kucuk baslaticiyi calistirir.

NE YAPAR
  - Program zaten aciksa (8503 cevap veriyor): ikinci kopya ACMAZ, yalnizca
    Chrome'da uygulama penceresini acar. (Iki kopya ayni porta oturunca eski
    kod calisiyordu -- bkz. ui/CLAUDE.md, 21.09.2026.)
  - Kapaliysa: BASLAT.bat'i KUCULTULMUS pencerede baslatir (veri guncellenir,
    arayuz acilir; o pencere kapaninca program da kapanir) ve Chrome'u
    "aciliyor..." sayfasiyla acar. Sayfa program hazir olunca kendiliginden
    arayuze gecer (ui/assets/acilis.html).

Chrome "uygulama penceresi" (--app) ile acilir: sekme ve adres cubugu yok,
masaustu programi gibi durur.

pythonw ile calisir (siyah konsol penceresi acilmaz). Yer iminden gelince
ilk arguman "deepcortex://..." adresidir; su an kullanilmiyor.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADRES = "http://localhost:8503/"
ACILIS = ROOT / "ui" / "assets" / "acilis.html"

_GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def calisiyor() -> bool:
    try:
        with urllib.request.urlopen(ADRES + "_stcore/health", timeout=2) as r:
            return r.status == 200
    except Exception:       # noqa: BLE001 -- kapali / henuz acilmamis
        return False


def chrome_yolu() -> str | None:
    """Chrome'un yeri: once Windows'un kayitli uygulama yolu, sonra bilinen yerler."""
    try:
        import winreg
        for kok in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(kok, r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                                         r"\App Paths\chrome.exe") as k:
                    yol = winreg.QueryValue(k, None)
                    if yol and Path(yol).exists():
                        return yol
            except OSError:
                continue
    except ImportError:
        pass
    for aday in (Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                 Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                 Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"):
        if aday.exists():
            return str(aday)
    return None


def pencere_ac(adres: str) -> None:
    """Chrome uygulama penceresi; Chrome yoksa varsayilan tarayici."""
    chrome = chrome_yolu()
    if chrome:
        subprocess.Popen([chrome, "--app=" + adres], creationflags=_GIZLI)
    else:
        webbrowser.open(adres)


def main() -> int:
    if calisiyor():
        pencere_ac(ADRES)
        return 0

    # Kucultulmus konsolda BASLAT.bat: veri guncellemesi + arayuz. /uygulama
    # bayragi Streamlit'in ayrica bir tarayici sekmesi acmasini engeller.
    #
    # `start` KULLANILMAZ (21.09.2026 hatasi): start, tirnakli ilk argumani
    # pencere basligi sayar; subprocess "DeepCortex"i tirnaksiz gecirince
    # Windows onu calistirilacak program sandi -> "Windows cannot find
    # 'DeepCortex'", BASLAT hic baslamadi, acilis ekrani sonsuza kadar bekledi.
    # Onun yerine yeni konsol dogrudan kucultulmus acilir; basligi BASLAT.bat
    # kendisi koyar (title DeepCortex).
    bilgi = subprocess.STARTUPINFO()
    bilgi.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    bilgi.wShowWindow = 7          # SW_SHOWMINNOACTIVE: kucuk, odak calmaz
    subprocess.Popen(
        ["cmd", "/c", str(ROOT / "BASLAT.bat"), "/uygulama"],
        cwd=str(ROOT), startupinfo=bilgi,
        creationflags=subprocess.CREATE_NEW_CONSOLE)
    pencere_ac(ACILIS.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

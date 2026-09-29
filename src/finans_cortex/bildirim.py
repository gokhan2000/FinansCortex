"""E-posta bildirimi -- uzaktan erisim adresini kendinize yollar.

NE ICIN: ucretsiz tunelde adres her acilista degisir. Evden cikarken
UZAKTAN.bat calisir ve adresi buradan e-postayla gonderir; isteki
bilgisayardan ya da telefondan posta kutusunu acip adresi alirsiniz.
Hicbir yere kurulum gerekmez.

AYARLAR: config/eposta.json
    {"gonderen": "...@yahoo.com", "alici": "...", "sunucu": "smtp.mail.yahoo.com",
     "port": 465, "parola_dpapi": "<sifreli>"}

PAROLA NASIL SAKLANIR
    Yahoo/Gmail gibi saglayicilar programlara ana parolayi vermez;
    "uygulama parolasi" uretirsiniz (bkz. docs/UZAKTAN_ERISIM.md). O parola
    burada DUZ METIN saklanmaz: Windows'un DPAPI'siyle (CryptProtectData)
    sifrelenir. Sifreli metni yalnizca AYNI Windows kullanicisi AYNI
    bilgisayarda cozebilir; dosya kopyalansa bile baska yerde ise yaramaz.
    DPAPI bir sekilde yoksa program parolayi kaydetmez, her seferinde sorar
    -- korumasiz saklamaktansa sormak evladir.

Gonderim smtplib + SMTP_SSL ile yapilir; baglanti sifrelidir.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import smtplib
import tempfile
from ctypes import wintypes
from email.message import EmailMessage
from pathlib import Path

STORE_PATH = Path(__file__).resolve().parents[2] / "config" / "eposta.json"

# Yaygin saglayicilarin SMTP ayarlari (hepsi SSL / 465).
SUNUCULAR = {
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
    "yahoo.com.tr": ("smtp.mail.yahoo.com", 465),
    "ymail.com": ("smtp.mail.yahoo.com", 465),
    "gmail.com": ("smtp.gmail.com", 465),
    "googlemail.com": ("smtp.gmail.com", 465),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "live.com": ("smtp-mail.outlook.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
}


def sunucu_bul(adres: str) -> tuple[str, int] | None:
    """E-posta adresinden SMTP sunucusunu tahmin eder."""
    alan = adres.split("@")[-1].strip().lower()
    return SUNUCULAR.get(alan)


# --------------------------------------------------------------------------
# DPAPI (Windows kullanici anahtariyla sifreleme)
# --------------------------------------------------------------------------
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(veri: bytes):
    tampon = ctypes.create_string_buffer(veri, len(veri))
    return _BLOB(len(veri), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), tampon


def _cikar(blob: _BLOB) -> bytes:
    veri = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return veri


def dpapi_var() -> bool:
    try:
        return bool(ctypes.windll.crypt32)
    except Exception:       # noqa: BLE001 -- Windows disi
        return False


def sifrele(metin: str) -> str:
    """DPAPI ile sifreler, base64 metin doner."""
    giris, _tampon = _blob(metin.encode("utf-8"))
    cikis = _BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(giris), "finans-cortex", None, None, None, 0,
        ctypes.byref(cikis))
    if not ok:
        raise OSError("DPAPI sifreleme basarisiz")
    return base64.b64encode(_cikar(cikis)).decode("ascii")


def coz(sifreli: str) -> str:
    """DPAPI ile cozer. Baska kullanici/bilgisayar cozemez -> OSError."""
    giris, _tampon = _blob(base64.b64decode(sifreli))
    cikis = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(giris), None, None, None, None, 0, ctypes.byref(cikis))
    if not ok:
        raise OSError("DPAPI cozme basarisiz (parola baska bir kullanici ya da "
                      "bilgisayarda kaydedilmis olabilir)")
    return _cikar(cikis).decode("utf-8")


# --------------------------------------------------------------------------
# Ayarlar
# --------------------------------------------------------------------------
def ayar_oku(path: Path = STORE_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("{} okunamadi: {}".format(path.name, exc)) from exc


def ayar_yaz(ayar: dict, path: Path = STORE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(ayar, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def kurulu(path: Path = STORE_PATH) -> bool:
    ayar = ayar_oku(path)
    return bool(ayar and ayar.get("alici") and ayar.get("parola_dpapi"))


# --------------------------------------------------------------------------
# Gonderim
# --------------------------------------------------------------------------
def gonder(konu: str, metin: str, ayar: dict | None = None,
           parola: str | None = None, path: Path = STORE_PATH) -> None:
    """Tek bir e-posta gonderir. Hata olursa istisna firlatir."""
    ayar = ayar or ayar_oku(path)
    if not ayar:
        raise ValueError("E-posta ayari yok. EPOSTA_AYARLA.bat calistirin.")
    if parola is None:
        parola = coz(ayar["parola_dpapi"])

    ileti = EmailMessage()
    ileti["Subject"] = konu
    ileti["From"] = ayar["gonderen"]
    ileti["To"] = ayar["alici"]
    ileti.set_content(metin)

    port = int(ayar.get("port", 465))
    sunucu = ayar["sunucu"]
    if port == 465:
        with smtplib.SMTP_SSL(sunucu, port, timeout=30) as s:
            s.login(ayar["gonderen"], parola)
            s.send_message(ileti)
    else:
        with smtplib.SMTP(sunucu, port, timeout=30) as s:
            s.starttls()
            s.login(ayar["gonderen"], parola)
            s.send_message(ileti)


def adres_iletisi(adres: str, saat: str) -> tuple[str, str]:
    """Uzaktan erisim adresi icin konu ve govde."""
    konu = "DeepCortex Finans - erisim adresi ({})".format(saat)
    govde = (
        "DeepCortex Finans uzaktan erisim adresi:\n\n"
        "{}\n\n"
        "Acilis: {}\n\n"
        "- Adresi tarayicida acin, karsiniza parola ekrani gelir.\n"
        "- Bu adres yalnizca ev bilgisayarindaki pencere ACIK kaldigi surece\n"
        "  calisir; her acilista YENI bir adres uretilir.\n"
        "- Adres postayla gittigi icin tek basina gizli degildir; asil koruma\n"
        "  erisim parolanizdir. Parolayi kimseyle paylasmayin.\n"
    ).format(adres, saat)
    return konu, govde

"""Uzaktan erisim parolasi.

NE ICIN: program internete acildiginda (bkz. scripts/uzaktan.py) adresi
bilen herkes veriyi gorebilir. Bu dosya, arayuzun onune bir parola kapisi
koymak icin gereken en kucuk parcayi tasir.

NELER SAKLANIR
    config/erisim.json -> {"tuz": ..., "ozet": ...}
Parolanin KENDISI hicbir yerde saklanmaz. Saklanan, rastgele bir tuz ile
birlikte hesaplanmis SHA-256 ozetidir; dosyayi goren parolayi geri
uretemez. Arayuze de parola degil, "tuz:ozet" jetonu ortam degiskeniyle
gecer -- boylece calisan sureclerin ortaminda duz metin parola durmaz.

NEDEN config/ ALTINDA: "hafif tasima"da data/ kopyalanmaz ama config/
gider (docs/KURULUM_VE_TASIMA.md). Baska bir makineye tasindiginda parola da
gider; istenmezse dosya silinir, program ilk uzaktan aciliste yenisini
sorar.

KARSILASTIRMA hmac.compare_digest ile yapilir: erken donen bir karsilastirma
parolanin kac harfinin dogru oldugunu sure farkindan sizdirabilir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STORE_PATH = Path(__file__).resolve().parents[2] / "config" / "erisim.json"

# Arayuz bu ortam degiskenini gorurse parola kapisini acar.
ENV_JETON = "FINANS_ERISIM"

EN_AZ = 8
_TUR = 240_000   # PBKDF2 tur sayisi -- kaba kuvveti yavaslatir


def _ozet(parola: str, tuz: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", parola.encode("utf-8"), bytes.fromhex(tuz), _TUR
    ).hex()


def kaydet(parola: str, path: Path = STORE_PATH) -> dict:
    """Yeni parola belirler. Donen: kayit (ozet dahil, parola degil)."""
    if len(parola) < EN_AZ:
        raise ValueError("Parola en az {} karakter olmali.".format(EN_AZ))
    tuz = secrets.token_hex(16)
    kayit = {
        "surum": 1,
        "tuz": tuz,
        "ozet": _ozet(parola, tuz),
        "olusturma": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(kayit, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return kayit


def oku(path: Path = STORE_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            kayit = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("{} okunamadi: {}".format(path.name, exc)) from exc
    if not kayit.get("tuz") or not kayit.get("ozet"):
        raise ValueError("{} bozuk gorunuyor; dosyayi silip parolayi yeniden "
                         "belirleyin.".format(path.name))
    return kayit


def jeton(kayit: dict) -> str:
    """Arayuze ortam degiskeniyle gecen deger: 'tuz:ozet'."""
    return "{}:{}".format(kayit["tuz"], kayit["ozet"])


def dogrula(parola: str, jeton_metni: str) -> bool:
    """Girilen parola jetona uyuyor mu."""
    try:
        tuz, ozet = jeton_metni.split(":", 1)
    except ValueError:
        return False
    if not tuz or not ozet:
        return False
    return hmac.compare_digest(_ozet(parola, tuz), ozet)

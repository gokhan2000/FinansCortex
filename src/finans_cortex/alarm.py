"""Alarm ayarlari ve hesap yardimcilari (arayuz ve scripts/cikis_izle.py ortak).

Kullanici (9 Kasim 2026): *"neler gelecegini programdan belirleyelim; bazilari
icin 15 dakikalik sinyal de istiyorum."*

AYAR DOSYASI: config/alarm.json (depoda; gizli bilgi icermez -- ntfy konu adi
GitHub secret'indadir).

    {"surum": 1,
     "stratejiler": {
        "chandelier_zlsma": {
           "giris": true, "cikis": true,
           "secim": {"XAUUSD": ["4h", "15m"], "XAGUSD": ["4h"]}}}}

Yalniz Chandelier motorunu (heikin_range.py) kullanan stratejiler desteklenir:
Strateji 2, 3, 4 ve kayitli varyantlari. Strateji 1 (EMA, gun ici) desteklenmez.
Bu modul streamlit'e BAGLI DEGILDIR: GitHub Actions'ta kurulu degil.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import heikin_range as hr
from . import strategy_store

YOL = Path(__file__).resolve().parents[2] / "config" / "alarm.json"

# zaman dilimi -> (bar saati, simulasyon icin geriye bakilacak gun, ekran adi)
ZAMANLAR = {
    "15m": (0.25, 60, "15 dk"),
    "4h": (4.0, 900, "4 saat"),
    "1d": (24.0, 2500, "Gunluk"),
}

# Temel stratejiler (ui/strategies.py BASE ile AYNI ayarlar; iki yerde
# tutulur cunku Actions'ta streamlit/ui yok). Degisirse ikisi birlikte.
TEMEL = {
    "heikin_range": ("Strateji 2", hr.HeikinConfig()),
    "chandelier_ha": ("Strateji 3", hr.HeikinConfig(rf_kullan=False)),
    "chandelier_zlsma": ("Strateji 4", hr.HeikinConfig(
        rf_kullan=False, zlsma=32, zlsma_cikis=True)),
}
VARSAYILAN = {
    "saat15": [10, 22],       # 15 dk alarm saatleri (TR); bkz. scripts/alarm_kapi.py
    "stratejiler": {"chandelier_zlsma": {
        "giris": True, "cikis": True,
        "secim": {"XAUUSD": ["4h"], "XAGUSD": ["4h"]}}}}


def stratejiler() -> dict[str, tuple[str, object]]:
    """key -> (ekran adi, config). Temel stratejiler + kayitli varyantlar."""
    out = dict(TEMEL)
    try:
        for e in strategy_store.load():
            if e.get("temel") in TEMEL:
                out[e["key"]] = (e.get("ad", e["key"]),
                                 strategy_store.to_config(e))
    except ValueError:
        pass
    return out


def yukle(yol: Path = YOL) -> dict:
    try:
        with yol.open(encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("stratejiler"), dict):
            return d
    except (OSError, ValueError):
        pass
    return json.loads(json.dumps(VARSAYILAN))


def kaydet(ayar: dict, yol: Path = YOL) -> None:
    """Atomik yazma (yarim dosya kalmasin)."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=yol.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "saat15": ayar.get("saat15", [10, 22]),
                       "stratejiler": ayar["stratejiler"]}, f,
                      ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, yol)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def bar_suresi(tf: str) -> timedelta:
    return timedelta(hours=ZAMANLAR[tf][0])

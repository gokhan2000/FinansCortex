"""Kayitli strateji varyantlari -- "Farkli kaydet".

Bir varyant = temel strateji (orn. ema10) + farkli parametreler. Kod ayni
kalir; yalnizca parametre nesnesi (EmaConfig / HeikinConfig) degisir. Backtest > Canli parametre ayari ekraninda
olusturulur, Stratejiler listesinde temelin altinda "1.1, 1.2..." diye gorunur.

NEDEN JSON DOSYASI (DuckDB degil)
  - Birkac KB, elle okunabilir ve gerekirse elle duzeltilebilir.
  - "Hafif tasima"da data/ klasoru kopyalanmiyor (docs/KURULUM_VE_TASIMA.md).
    config/ ise kodla birlikte gider; kayitli stratejiler isyerine de tasinir.

Yazma atomik: gecici dosyaya yazilip os.replace ile degistirilir. Yarida
kalan bir yazma mevcut dosyayi bozmaz.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .ema_two_close import EmaConfig
from .heikin_range import HeikinConfig

STORE_PATH = Path(__file__).resolve().parents[2] / "config" / "stratejiler.json"

# Temel strateji anahtari -> parametre sinifi. Yeni bir temel strateji
# eklenince buraya da bir satir gerekir; varyantin hangi motorla acilacagini
# kayittaki "temel" alani belirler.
CONFIGS = {"ema10": EmaConfig, "heikin_range": HeikinConfig,
           "chandelier_ha": HeikinConfig}

# Temel strateji anahtarlari -- varyant bu anahtarlari alamaz.
RESERVED = set(CONFIGS)

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.translate(_TR).lower()).strip("-")
    return s or "strateji"


def load(path: Path = STORE_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f).get("stratejiler", [])
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("{} okunamadi: {}".format(path.name, exc)) from exc


def _write(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "stratejiler": items}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def to_config(entry: dict):
    """Kayittaki parametrelerden temeline uygun config nesnesi.

    Bilinmeyen alanlar yok sayilir -- ileride bir parametre kaldirilirsa eski
    kayit yine acilsin. Tanimsiz bir temel varsa (ornegin elle duzenlenmis
    dosya) ValueError.
    """
    cls = CONFIGS.get(entry.get("temel"))
    if cls is None:
        raise ValueError("bilinmeyen temel strateji: {}".format(entry.get("temel")))
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in entry["parametreler"].items() if k in known})


def _clean(meta: dict | None) -> dict:
    """NaN JSON standardinda yok; None'a cevrilir."""
    return {k: (None if isinstance(v, float) and v != v else v)
            for k, v in (meta or {}).items()}


def save_as(
    name: str,
    temel: str,
    cfg,
    timeframe: str,
    note: str = "",
    meta: dict | None = None,
    overwrite: bool = False,
    path: Path = STORE_PATH,
) -> dict:
    """Parametreleri yeni isimle kaydeder. Donen: kayit.

    Ayni isim (buyuk/kucuk harf farksiz) varsa `overwrite` olmadan ValueError.
    """
    name = name.strip()
    if not name:
        raise ValueError("Strateji adi bos olamaz.")
    if len(name) > 60:
        raise ValueError("Strateji adi en fazla 60 karakter olabilir.")

    items = load(path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    same = next((s for s in items if s["ad"].casefold() == name.casefold()), None)

    if same is not None:
        if not overwrite:
            raise ValueError("'{}' adinda bir strateji zaten var. Baska bir isim "
                             "verin ya da 'Uzerine yaz'i isaretleyin.".format(name))
        same.update({"parametreler": asdict(cfg), "zaman_dilimi": timeframe,
                     "not": note.strip(), "meta": _clean(meta),
                     "guncelleme": now})
        entry = same
    else:
        taken = {s["key"] for s in items} | RESERVED
        key = base = _slug(name)
        n = 2
        while key in taken:
            key = "{}-{}".format(base, n)
            n += 1
        # Numara silinenlerden sonra da tekrar etmesin diye en buyuk + 1.
        no = 1 + max((s.get("no", 0) for s in items if s["temel"] == temel),
                     default=0)
        entry = {"key": key, "ad": name, "temel": temel, "no": no,
                 "parametreler": asdict(cfg), "zaman_dilimi": timeframe,
                 "not": note.strip(), "meta": _clean(meta), "olusturma": now}
        items.append(entry)

    _write(items, path)
    return entry


def delete(key: str, path: Path = STORE_PATH) -> bool:
    items = load(path)
    kept = [s for s in items if s["key"] != key]
    if len(kept) == len(items):
        return False
    _write(kept, path)
    return True

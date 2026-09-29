"""
Dukascopy yoklama betigi (Faz 1 / adim 0b).

Yahoo elendi: spot ons altin/gumus yok, 15dk gecmisi 2.5 ay.
Kullanicinin sarti: ons altin + ons gumus ZORUNLU, 15dk gostergeler ZORUNLU.

Bu betik Dukascopy'nin bu iki sarti karsilayip karsilamadigini OLCER:
  1. 8 enstrumanin hepsi mevcut mu?
  2. 15dk verisi yil yil ne kadar geriye gidiyor?
  3. Saat dilimi ne? (ilk testte UTC goruldu, dogrulaniyor)
  4. Gun basina kac bar? (seans profili)

Her yoklama 1 gunluk pencere ile yapilir (hizli olsun diye).
Secilen tarihler Carsamba -- hafta sonu bosluguna denk gelmesin.
"""

import json
from datetime import datetime
from pathlib import Path

import dukascopy_python as dk
from dukascopy_python.instruments import (
    INSTRUMENT_CMD_ENERGY_E_BRENT,
    INSTRUMENT_CMD_ENERGY_E_LIGHT,
    INSTRUMENT_FX_MAJORS_EUR_USD,
    INSTRUMENT_FX_METALS_XAG_USD,
    INSTRUMENT_FX_METALS_XAU_USD,
    INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    INSTRUMENT_IDX_EUROPE_E_DAAX,
    INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
)

INSTRUMENTS = [
    ("EURUSD", INSTRUMENT_FX_MAJORS_EUR_USD),
    ("XAUUSD", INSTRUMENT_FX_METALS_XAU_USD),   # ons altin - SPOT
    ("XAGUSD", INSTRUMENT_FX_METALS_XAG_USD),   # ons gumus - SPOT
    ("BRENT", INSTRUMENT_CMD_ENERGY_E_BRENT),
    ("WTI", INSTRUMENT_CMD_ENERGY_E_LIGHT),
    ("DJ", INSTRUMENT_IDX_AMERICA_E_D_J_IND),
    ("DAX", INSTRUMENT_IDX_EUROPE_E_DAAX),
    ("FTSE", INSTRUMENT_IDX_EUROPE_E_FUTSEE_100),
]

# Hepsi Carsamba
PROBE_DATES = [
    datetime(2003, 6, 4),
    datetime(2007, 6, 6),
    datetime(2010, 6, 9),
    datetime(2015, 6, 10),
    datetime(2020, 6, 10),
    datetime(2026, 8, 5),
]

OUT_JSON = Path(
    r"C:\Users\gokha\AppData\Local\Temp\claude\c--gs-finans-cortex"
    r"\9caa4c67-8ff5-49b7-819d-a13d149eb508\scratchpad\dukascopy_probe.json"
)


def probe(instrument: str, day: datetime) -> dict:
    end = datetime(day.year, day.month, day.day, 23, 59)
    out = {"bars": 0, "tz": None, "error": None}
    try:
        df = dk.fetch(instrument, dk.INTERVAL_MIN_15, dk.OFFER_SIDE_BID, day, end)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:80]
        return out

    if df is None or df.empty:
        return out

    out["bars"] = int(len(df))
    out["tz"] = str(df.index.tz)
    return out


def main() -> None:
    results = {}
    header = "ENSTRUMAN   " + "".join(f"{d.year:>8}" for d in PROBE_DATES)
    print(header)
    print("-" * len(header))

    for name, instrument in INSTRUMENTS:
        row = {}
        cells = []
        for day in PROBE_DATES:
            r = probe(instrument, day)
            row[str(day.year)] = r
            cells.append(f"{r['bars']:>8}" if not r["error"] else f"{'HATA':>8}")
        results[name] = row
        print(f"{name:<12}" + "".join(cells))

    tzs = {
        r["tz"]
        for row in results.values()
        for r in row.values()
        if r["tz"]
    }
    print("\ngorulen saat dilimleri:", tzs)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("JSON:", OUT_JSON)
    print("\nNOT: rakamlar o gun donen 15dk bar sayisi. 0 = veri yok.")


if __name__ == "__main__":
    main()

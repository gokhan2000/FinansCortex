"""
Veri kaynagi yoklama betigi (Faz 1 / adim 0).

Amac: sema yazmadan once ASAGIDAKILERI VARSAYMAK YERINE OLCMEK.
  1. Enstrumanlarin Yahoo'daki gercek sembolleri neler?
  2. Her zaman dilimi (15dk / 1saat / 1gun) FIILEN ne kadar geriye gidiyor?
  3. Donen verinin saat dilimi ne? (UTC'de saklama karari icin)
  4. Gun basina kac bar geliyor? (seans uzunlugu / takvim farklari icin)

Limitleri olcmek icin bilerek dokumante limitin USTUNDE veri isteniyor:
15dk -> 90 gun, 1saat -> 800 gun. Yahoo ne kadarini kirparsa gercek limit odur.

Cikti: konsola tablo + scratchpad'e JSON.
"""

import json
import time
import warnings
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# (mantiksal ad, denenecek sembol adaylari)
PROBES = [
    ("EURUSD", ["EURUSD=X"]),
    ("XAUUSD", ["XAUUSD=X", "GC=F"]),   # spot altin var mi, yoksa COMEX vadeli mi?
    ("XAGUSD", ["XAGUSD=X", "SI=F"]),
    ("BRENT",  ["BZ=F"]),
    ("WTI",    ["CL=F"]),
    ("DJ",     ["^DJI"]),
    ("DAX",    ["^GDAXI"]),
    ("FTSE",   ["^FTSE"]),
]

# (interval, istenecek period)
#
# 1. tur (13 Agu 2026) limitin USTUNDE istedi (15m->90d, 1h->800d). Yahoo
#    kirpmak yerine istegi tamamen reddetti ve limitleri kendisi soyledi:
#      "15m data not available ... must be within the last 60 days"
#      "1h  data not available ... must be within the last 730 days"
#    Limitler boylece OLCULEREK dogrulandi. Asagidaki period'lar artik
#    limitin bir tik ALTINDA -- amac gercek intraday verisini gorup
#    bar/gun ve saat dilimi bilgisini cikarmak.
INTERVALS = [
    ("15m", "55d"),
    ("1h", "700d"),
    ("1d", "max"),
]

OUT_JSON = Path(
    r"C:\Users\gokha\AppData\Local\Temp\claude\c--gs-finans-cortex"
    r"\9caa4c67-8ff5-49b7-819d-a13d149eb508\scratchpad\probe_results.json"
)


def probe(symbol: str, interval: str, period: str) -> dict:
    row = {
        "symbol": symbol,
        "interval": interval,
        "period_requested": period,
        "ok": False,
        "rows": 0,
        "first": None,
        "last": None,
        "span_days": None,
        "tz": None,
        "bars_per_day_median": None,
        "error": None,
    }
    try:
        df = yf.Ticker(symbol).history(
            period=period, interval=interval, auto_adjust=False
        )
    except Exception as exc:  # noqa: BLE001 - yoklamada her hatayi yakalamak istiyoruz
        row["error"] = f"{type(exc).__name__}: {exc}"[:160]
        return row

    if df is None or df.empty:
        row["error"] = "bos veri dondu"
        return row

    idx = df.index
    row["ok"] = True
    row["rows"] = int(len(df))
    row["first"] = str(idx[0])
    row["last"] = str(idx[-1])
    row["span_days"] = round((idx[-1] - idx[0]).total_seconds() / 86400, 1)
    row["tz"] = str(idx.tz) if getattr(idx, "tz", None) is not None else "naive"

    if interval != "1d":
        per_day = pd.Series(idx.date).value_counts()
        row["bars_per_day_median"] = float(per_day.median())

    return row


def main() -> None:
    results = []
    resolved = {}

    for name, candidates in PROBES:
        print(f"\n=== {name} ===")
        for sym in candidates:
            for interval, period in INTERVALS:
                r = probe(sym, interval, period)
                r["asset"] = name
                results.append(r)

                if r["ok"]:
                    bpd = r["bars_per_day_median"]
                    bpd_s = f", {bpd:.0f} bar/gun" if bpd else ""
                    print(
                        f"  {sym:<10} {interval:<4} OK   "
                        f"{r['rows']:>6} bar, {r['span_days']:>7} gun geriye, "
                        f"tz={r['tz']}{bpd_s}"
                    )
                    resolved.setdefault(name, sym)
                else:
                    print(f"  {sym:<10} {interval:<4} FAIL {r['error']}")

                time.sleep(0.7)  # rate limit'e karsi nazik davran

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"results": results, "resolved": resolved}, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("COZULEN SEMBOLLER:", json.dumps(resolved))
    print("JSON:", OUT_JSON)


if __name__ == "__main__":
    main()

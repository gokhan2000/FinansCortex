"""Cikis (ve giris) sinyali bildirimi -- GitHub Actions calistirir (elle de olur).

Kullanici (8 Kasim 2026): *"anlik cikis mesaji atacak bir sey; ozellikle
Strateji 4."* Mesaj ntfy ile telefona bildirim olarak duser.

NE YAPAR
  1. Depodaki parquet'ten gecici veritabani kurar, Dukascopy'den eksik
     barlari ceker (bulut_guncelle.py ile ayni yol; yazma YOK, commit YOK).
  2. Her varlik x zaman dilimi icin stratejiyi KAPANMIS barlarla calistirir.
  3. Son birkac barda olusan yeni GIRIS / CIKIS olaylarini bulur.
  4. Daha once gonderilmemis olanlari ntfy'ye yollar, gonderilenleri
     `.alarm/durum.json`'a yazar (Actions onbellegi bu dosyayi calismalar
     arasinda tasir) -- ayni olay iki kez gitmesin.

NOT: Bu bir STRATEJI SIMULASYONUDUR. Gercek pozisyonunuzu bilmez; "su
varlikta stratejiye gore pozisyon kapanir" der. Karar sizindir.

Ortam degiskenleri
  NTFY_KONU   zorunlu (yoksa mesaj yazdirilir, gonderilmez)
  GIRIS=0     giris mesajlarini kapatir (varsayilan: acik)
  YEREL=1     data/market.duckdb'yi kullanir (indirme yok) -- deneme icin
  SIMDI       ISO UTC zaman; "simdi"yi bu ani say (deneme icin)
  KURU=1      mesaj gondermez, durum dosyasini degistirmez
  TEST=1      yalniz bir deneme mesaji yollar
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from finans_cortex import bulut, heikin_range as hr, ingest, storage  # noqa: E402
from finans_cortex.instruments import HESAP_KODLARI  # noqa: E402

DURUM = ROOT / ".alarm" / "durum.json"
TZ = ZoneInfo("Europe/Istanbul")

# (ad, ayar). Strateji 4 = ui/strategies.py'deki "chandelier_zlsma" kaydi;
# iki yerde AYNI olmali (buradaki UI'a bagli degil: Actions'ta streamlit yok).
STRATEJILER = {
    "Strateji 4": hr.HeikinConfig(rf_kullan=False, zlsma=32, zlsma_cikis=True),
}
# zaman dilimi -> (bar saati, simulasyon icin geriye bakilacak gun)
ZAMANLAR = {"4h": (4.0, 900), "1d": (24.0, 2500)}
ETIKET = {"4h": "4 saat", "1d": "gunluk"}
GERI_BAR = 3          # kacirilan calismayi yakalamak icin son N bar
NEDEN = {
    "zlsma": "fiyat ZLSMA'nin ters tarafina gecti",
    "ters_sinyal": "Chandelier ters yone dondu",
    "chandelier": "Chandelier ters yone dondu",
    "stop": "stop",
}


def fiyat(v: float) -> str:
    basamak = 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2
    return f"{v:,.{basamak}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def saat(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%d.%m %H:%M")


def olaylar(con, code: str, tf: str, ad: str, cfg, simdi: datetime) -> list[dict]:
    bar_saat, gun = ZAMANLAR[tf]
    bar = timedelta(hours=bar_saat)
    bars = storage.read_bars(con, code, tf)
    # Yalniz KAPANMIS barlar: son kova yarim kalmis olabilir.
    bars = bars.filter(pl.col("ts") + bar <= simdi)
    if bars.height < 400:
        return []
    res = hr.run_bars(bars, code, tf, cfg, days=gun)
    if res.trades.is_empty():
        return []
    son = bars["ts"][-1]
    # Olay hem "son N bar"da hem GERCEK ZAMANA yakin olmali: veri bayatsa
    # (indirme hatasi, tatil) eski olaylar yeni gibi gonderilmesin.
    sinir = max(son - bar * (GERI_BAR - 1), simdi - bar * GERI_BAR - bar)
    cikti = []
    for t in res.trades.tail(6).to_dicts():
        yon = "AL" if t["yon"] == 1 else "SAT"
        if t["neden"] != "veri_sonu" and t["cikis_ts"] >= sinir:
            cikti.append(dict(
                anahtar=f"{ad}|{code}|{tf}|cikis|{t['cikis_ts'].isoformat()}",
                tur="cikis", ts=t["cikis_ts"] + bar,
                baslik=f"CIKIS · {code} · {ad}",
                mesaj=(f"{code} {ETIKET[tf]}: {yon} pozisyonu KAPANIR\n"
                       f"Cikis ~{fiyat(t['cikis'])} · {NEDEN.get(t['neden'], t['neden'])}\n"
                       f"Giris {fiyat(t['giris'])} ({saat(t['giris_ts'])}) → "
                       f"{t['getiri'] * 100:+.2f}% (maliyet dahil)\n"
                       f"Mum kapanisi {saat(t['cikis_ts'] + bar)} TR")))
        if t["giris_ts"] >= sinir and os.environ.get("GIRIS", "1") != "0":
            cikti.append(dict(
                anahtar=f"{ad}|{code}|{tf}|giris|{t['giris_ts'].isoformat()}",
                tur="giris", ts=t["giris_ts"] + bar,
                baslik=f"GIRIS · {code} · {ad}",
                mesaj=(f"{code} {ETIKET[tf]}: yeni {yon} sinyali\n"
                       f"Giris ~{fiyat(t['giris'])}\n"
                       f"Mum kapanisi {saat(t['giris_ts'] + bar)} TR")))
    return cikti


def gonder(konu: str, o: dict) -> None:
    govde = json.dumps({
        "topic": konu, "title": o["baslik"], "message": o["mesaj"],
        "priority": 4 if o["tur"] == "cikis" else 3,
        "tags": ["red_circle" if o["tur"] == "cikis" else "green_circle"],
    }).encode("utf-8")
    istek = urllib.request.Request(
        "https://ntfy.sh/", data=govde,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=20) as r:
        r.read()


def main() -> None:
    if os.environ.get("TEST") == "1":      # telefona ulasiyor mu denemesi
        konu = os.environ.get("NTFY_KONU", "").strip()
        if not konu:
            sys.exit("NTFY_KONU tanimli degil (GitHub > Settings > Secrets).")
        gonder(konu, dict(tur="giris", baslik="DeepCortex · deneme",
                          mesaj="Bu bir deneme mesajidir. Cikis alarmlari "
                                "boyle gelecek."))
        print("deneme mesaji gonderildi")
        return
    kuru = os.environ.get("KURU") == "1"
    simdi = (datetime.fromisoformat(os.environ["SIMDI"]).astimezone(timezone.utc)
             if os.environ.get("SIMDI") else datetime.now(timezone.utc))
    konu = os.environ.get("NTFY_KONU", "").strip()
    gonderilen = (set(json.loads(DURUM.read_text("utf-8")))
                  if DURUM.exists() else set())

    with tempfile.TemporaryDirectory() as tmp:
        if os.environ.get("YEREL") == "1":
            con = storage.connect(read_only=True)
        else:
            db = Path(tmp) / "market.duckdb"
            bulut.hazirla(db, bulut.PARQUET_DIZINI, son_kullan=True)
            con = storage.connect(db)
            ingest.backfill_all(con, sure_sn=600)

        yeni = []
        for ad, cfg in STRATEJILER.items():
            for code in HESAP_KODLARI:
                for tf in ZAMANLAR:
                    try:
                        yeni += olaylar(con, code, tf, ad, cfg, simdi)
                    except Exception as exc:  # noqa: BLE001 -- biri digerini durdurmasin
                        print(f"HATA {code} {tf}: {exc}", flush=True)
        con.close()

    bekleyen = [o for o in yeni if o["anahtar"] not in gonderilen]
    print(f"{len(yeni)} olay, {len(bekleyen)} yeni (zaman {simdi:%Y-%m-%d %H:%M} UTC)")
    for o in sorted(bekleyen, key=lambda x: x["ts"]):
        print("-", o["baslik"], "|", o["mesaj"].replace("\n", " / "))
        if kuru:
            continue
        if konu:
            gonder(konu, o)
        else:
            print("  (NTFY_KONU yok: gonderilmedi)")
            continue
        gonderilen.add(o["anahtar"])
    if not kuru and konu:
        DURUM.parent.mkdir(exist_ok=True)
        # Yalniz son 500 anahtar: dosya buyumesin.
        DURUM.write_text(json.dumps(sorted(gonderilen)[-500:]), "utf-8")


if __name__ == "__main__":
    main()

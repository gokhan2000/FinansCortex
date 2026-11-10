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

AYAR: config/alarm.json (programdaki Alarmlar ekranindan yazilir): hangi
strateji x varlik x zaman dilimi, giris/cikis mesaji acik mi.

Ortam degiskenleri
  NTFY_KONU   zorunlu (yoksa mesaj yazdirilir, gonderilmez)
  ZORLA=1     zaman kapisini yok say (deneme icin)
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

from alarm_kapi import calismali  # noqa: E402  (scripts/ ayni klasor)
from finans_cortex import alarm, bulut, heikin_range as hr, ingest, storage  # noqa: E402

DURUM = ROOT / ".alarm" / "durum.json"
TZ = ZoneInfo("Europe/Istanbul")

ETIKET = {"15m": "15 dakika", "4h": "4 saat", "1d": "gunluk"}
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


SAGLIK: list[dict] = []     # her izlenen (strateji, varlik, dilim) icin son durum


def olaylar(con, code: str, tf: str, ad: str, cfg, simdi: datetime,
            giris: bool, cikis: bool) -> list[dict]:
    bar_saat, gun, _ = alarm.ZAMANLAR[tf]
    bar = timedelta(hours=bar_saat)
    # Gostergeler isinsin diye simulasyon gunune +60 gun eklenir.
    bars = storage.read_bars(con, code, tf,
                             start=simdi - timedelta(days=gun + 60))
    # Yalniz KAPANMIS barlar: son kova yarim kalmis olabilir.
    bars = bars.filter(pl.col("ts") + bar <= simdi)
    bilgi = dict(ad=ad, code=code, tf=tf, son_bar=None, son_islem="yok")
    SAGLIK.append(bilgi)
    if bars.height < 400:
        bilgi["son_islem"] = f"yetersiz veri ({bars.height} bar)"
        return []
    bilgi["son_bar"] = bars["ts"][-1] + bar          # son KAPANMIS barin kapanisi
    res = hr.run_bars(bars, code, tf, cfg, days=gun)
    if res.trades.is_empty():
        return []
    sn = res.trades.tail(1).to_dicts()[0]
    yon = "AL" if sn["yon"] == 1 else "SAT"
    bilgi["son_islem"] = (f"{yon} pozisyonu acik (giris {saat(sn['giris_ts'])})"
                          if sn["neden"] == "veri_sonu" else
                          f"son cikis {saat(sn['cikis_ts'])}")
    son = bars["ts"][-1]
    # Olay hem "son N bar"da hem GERCEK ZAMANA yakin olmali: veri bayatsa
    # (indirme hatasi, tatil) eski olaylar yeni gibi gonderilmesin.
    sinir = max(son - bar * (GERI_BAR - 1), simdi - bar * GERI_BAR - bar)
    cikti = []
    for t in res.trades.tail(6).to_dicts():
        yon = "AL" if t["yon"] == 1 else "SAT"
        if cikis and t["neden"] != "veri_sonu" and t["cikis_ts"] >= sinir:
            cikti.append(dict(
                anahtar=f"{ad}|{code}|{tf}|cikis|{t['cikis_ts'].isoformat()}",
                tur="cikis", ts=t["cikis_ts"] + bar,
                baslik=f"CIKIS · {code} · {ad}",
                mesaj=(f"{code} {ETIKET[tf]}: {yon} pozisyonu KAPANIR\n"
                       f"Cikis ~{fiyat(t['cikis'])} · {NEDEN.get(t['neden'], t['neden'])}\n"
                       f"Giris {fiyat(t['giris'])} ({saat(t['giris_ts'])}) → "
                       f"{t['getiri'] * 100:+.2f}% (maliyet dahil)\n"
                       f"Mum kapanisi {saat(t['cikis_ts'] + bar)} TR")))
        if giris and t["giris_ts"] >= sinir:
            cikti.append(dict(
                anahtar=f"{ad}|{code}|{tf}|giris|{t['giris_ts'].isoformat()}",
                tur="giris", ts=t["giris_ts"] + bar,
                baslik=f"GIRIS · {code} · {ad}",
                mesaj=(f"{code} {ETIKET[tf]}: yeni {yon} sinyali\n"
                       f"Giris ~{fiyat(t['giris'])}\n"
                       f"Mum kapanisi {saat(t['giris_ts'] + bar)} TR")))
    return cikti


# 24 saat islem goren varliklar: hafta ici veri bayatlarsa uyarilir (indeksler
# gece kapali oldugu icin bu kontrole girmez).
ISLEMDE_24S = {"EURUSD", "XAUUSD", "XAGUSD", "BRENT", "WTI"}


def piyasa_acik(t: datetime) -> bool:
    """Forex/metal/enerji icin kabaca acik saat (UTC): Pzt 03 - Cum 19."""
    g = t.weekday()
    return g in (1, 2, 3) or (g == 0 and t.hour >= 3) or (g == 4 and t.hour < 19)


def saglik_mesajlari(simdi: datetime) -> list[dict]:
    """Sessiz bozulma olmasin: (a) gunde bir kez 'alarm calisiyor' ozeti
    (07 UTC = 10 TR), (b) veri bayatsa gunde bir uyari.

    Alarm 'olay yok' ile 'calismiyor'u ayirt edemezdi (kullanici, 10.11.2026:
    'bir daha sinyal gondermedi')."""
    gun = f"{simdi:%Y-%m-%d}"
    cikti = []
    if simdi.hour == 7 and simdi.minute < 50 and SAGLIK:
        satir = [f"{b['code']} {ETIKET[b['tf']]}: son bar "
                 f"{saat(b['son_bar']) if b['son_bar'] else 'YOK'} · {b['son_islem']}"
                 for b in SAGLIK]
        cikti.append(dict(
            anahtar=f"saglik|{gun}", tur="saglik", ts=simdi,
            baslik="DeepCortex alarm · calisiyor",
            mesaj=("Alarm calisiyor; yeni olay olursa mesaj gelir.\n"
                   + "\n".join(satir[:12]))))
    if piyasa_acik(simdi):
        for b in SAGLIK:
            if b["code"] not in ISLEMDE_24S:
                continue
            bar = alarm.bar_suresi(b["tf"])
            if b["son_bar"] is None or simdi - b["son_bar"] > bar + timedelta(hours=2):
                cikti.append(dict(
                    anahtar=f"bayat|{gun}|{b['code']}|{b['tf']}", tur="uyari",
                    ts=simdi, baslik=f"UYARI · {b['code']} verisi bayat",
                    mesaj=(f"{b['code']} {ETIKET[b['tf']]}: son kapanmis bar "
                           f"{saat(b['son_bar']) if b['son_bar'] else 'YOK'} TR. "
                           "Veri kaynagindan veri gelmiyor olabilir; bu "
                           "durumda alarm sessiz kalir.")))
    return cikti


def gonder(konu: str, o: dict) -> None:
    govde = json.dumps({
        "topic": konu, "title": o["baslik"], "message": o["mesaj"],
        "priority": 4 if o["tur"] in ("cikis", "giris", "uyari") else
        (1 if o["tur"] == "saglik" else 3),
        "tags": {"cikis": ["red_circle"], "giris": ["green_circle"],
                 "uyari": ["warning"], "saglik": ["white_check_mark"]}.get(
                     o["tur"], []),
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
    ayar = alarm.yukle()
    simdi = (datetime.fromisoformat(os.environ["SIMDI"]).astimezone(timezone.utc)
             if os.environ.get("SIMDI") else datetime.now(timezone.utc))
    konu = os.environ.get("NTFY_KONU", "").strip()
    gonderilen = (set(json.loads(DURUM.read_text("utf-8")))
                  if DURUM.exists() else set())

    if not calismali(ayar, simdi) and os.environ.get("ZORLA") != "1":
        print("Bu dakikada izlenecek bar kapanisi yok; atlandi.")
        return
    with tempfile.TemporaryDirectory() as tmp:
        if os.environ.get("YEREL") == "1":
            con = storage.connect(read_only=True)
        else:
            db = Path(tmp) / "market.duckdb"
            bulut.hazirla(db, bulut.PARQUET_DIZINI, son_kullan=True)
            con = storage.connect(db)
            ingest.backfill_all(con, sure_sn=600)

        yeni = []
        tanim = alarm.stratejiler()
        for key, kural in ayar["stratejiler"].items():
            if key not in tanim:
                print(f"UYARI: bilinmeyen strateji {key} (silinmis varyant?)")
                continue
            ad, cfg = tanim[key]
            for code, tfler in kural.get("secim", {}).items():
                for tf in tfler:
                    if tf not in alarm.ZAMANLAR:
                        continue
                    try:
                        yeni += olaylar(con, code, tf, ad, cfg, simdi,
                                        kural.get("giris", True),
                                        kural.get("cikis", True))
                    except Exception as exc:  # noqa: BLE001 -- biri digerini durdurmasin
                        print(f"HATA {code} {tf}: {exc}", flush=True)
        con.close()

    yeni += saglik_mesajlari(simdi)
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

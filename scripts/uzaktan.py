"""Uzaktan erisim -- programi internetten acar, kod ve veri burada kalir.

NE YAPAR
    1. Erisim parolasini hazirlar (ilk seferde sorar, ozetini config/ altina yazar).
    2. Cloudflare'in tunel araci yoksa indirir (araclar/cloudflared.exe).
    3. Arayuzu YALNIZCA bu bilgisayarda dinleyecek sekilde baslatir (127.0.0.1).
    4. Tuneli acar ve ekrana "https://...trycloudflare.com" adresini yazar.
    5. Adresi kendinize E-POSTA ile yollar (kuruluysa) ve bulut
       klasorlerine (OneDrive / Google Drive) yazar -- evden cikarken adresi
       not almaniz gerekmesin.
    6. Program calistigi surece bilgisayarin uykuya gecmesini engeller
       (uyuyan bilgisayarda tunel de olur). Kapaninca eski haline doner.
    Pencere kapaninca hem tunel hem arayuz kapanir; adres olur.

NEDEN BOYLE
    - Kod ve veritabani HICBIR YERE gitmez; dosyalar bu bilgisayarda kalir.
      Disariya acilan sey yalnizca calisan arayuzun ekrani.
    - Adresi bilen herkes girebilecegi icin arayuzun onune parola kapisi
      konur (ui/auth.py). Parola olmadan tek bir veri sorgusu bile calismaz.
    - Arayuz 127.0.0.1'e baglanir: tunel disindan (ornegin ayni Wi-Fi'daki
      baska bir cihazdan) dogrudan erisilemez.
    - Bedava tunel her acilista BASKA bir adres verir. Sabit adres icin
      alan adi ya da Tailscale gerekir; bkz. docs/UZAKTAN_ERISIM.md.

GIZLILIK NOTU (durustce): trafik Cloudflare'in agindan gecer, sifreleme
orada cozulup yeniden kurulur. Dosyalariniz gitmez ama "hicbir ucuncu taraf
araya girmesin" istiyorsaniz Tailscale secenegine bakin (ayni belgede).

ADRESI ISTE NASIL OGRENIRSINIZ (is bilgisayarina hicbir sey kurulmadan)
    Ucretsiz tunelde adres her acilista degisir; adres su yollarla size gelir:
      1. E-POSTA (en saglami; is yerinde bulut depolama kapali olabilir).
         Kurulumu: EPOSTA_AYARLA.bat -- bir kez.
      2. Bulut klasorleri: OneDrive ve/veya Google Drive masaustu istemcisi
         kuruluysa "DeepCortex-ADRES.txt" oraya da yazilir.
      3. Proje klasorundeki ADRES.txt (ev bilgisayarinda).
    Program kapaninca ayni dosyalara "su an kapali" yazilir -- olu adrese
    ugrasmayasiniz diye.

Kullanim (normalde UZAKTAN.bat cift tiklanir):
    python scripts/uzaktan.py
"""

from __future__ import annotations

import getpass
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from queue import Empty, Queue

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finans_cortex import bildirim, erisim  # noqa: E402

# Port normalde 8503; FINANS_PORT ile degistirilebilir (deneme/kurtarma icin).
PORT = int(os.environ.get("FINANS_PORT", "8503"))
ARAC_DIZIN = ROOT / "araclar"
ARAC = ARAC_DIZIN / "cloudflared.exe"
ARAC_URL = ("https://github.com/cloudflare/cloudflared/releases/latest/"
            "download/cloudflared-windows-amd64.exe")
KAYIT = ARAC_DIZIN / "uzaktan.log"
ADRES_DOSYA = ROOT / "ADRES.txt"
ADRES_KALIBI = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# Windows'ta cocuk sureclere ayri konsol penceresi acilmasin.
_GIZLI = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# SetThreadExecutionState bayraklari (Windows): "calisiyorum, uyuma".
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def uyku_engelle(ac: bool) -> bool:
    """Program calistigi surece bilgisayar uykuya gecmesin.

    Sistem ayarini KALICI degistirmez: yalnizca bu surec yasadigi surece
    gecerli bir istek. Surec kapaninca (ya da ac=False ile) eski davranis
    doner. Ekranin kararmasina karismaz, yalnizca uykuyu engeller.
    """
    try:
        import ctypes
        bayrak = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if ac else 0)
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(bayrak))
    except Exception:       # noqa: BLE001 -- Windows disi ya da eski surum
        return False


def onedrive_dizini() -> Path | None:
    """Kullanicinin OneDrive klasoru (varsa)."""
    for ad in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        yol = os.environ.get(ad)
        if yol and Path(yol).is_dir():
            return Path(yol)
    varsayilan = Path.home() / "OneDrive"
    return varsayilan if varsayilan.is_dir() else None


def drive_dizini() -> Path | None:
    r"""Google Drive masaustu istemcisinin klasoru (varsa).

    Yeni istemci ("Google Drive for desktop") sanal bir surucu baglar:
    G:\My Drive ya da Turkce arayuzde G:\Drive'im. Eski istemci ev
    klasorune "Google Drive" diye kurardi. Hepsine bakilir.
    """
    adaylar = [Path.home() / "Google Drive", Path.home() / "My Drive"]
    for harf in "GHIJKLMNOPQRSTUVWXYZ":
        kok = Path("{}:\\".format(harf))
        adaylar += [kok / "My Drive", kok / "Drive'im", kok / "Drive'\u0131m"]
    for aday in adaylar:
        try:
            if aday.is_dir():
                return aday
        except OSError:      # baglanmamis surucu harfi
            continue
    return None


def bulut_dizinleri() -> list[tuple[str, Path]]:
    """Adresin yazilacagi bulut klasorleri: (ad, yol)."""
    bulunan = []
    od = onedrive_dizini()
    if od is not None:
        bulunan.append(("OneDrive", od))
    gd = drive_dizini()
    if gd is not None:
        bulunan.append(("Google Drive", gd))
    return bulunan


def adres_yaz(adres: str | None) -> list[Path]:
    """Adresi proje klasorune ve varsa OneDrive'a yazar. Donen: yazilan yollar.

    adres None ise "su an kapali" notu yazilir (dosya silinmez: isteki
    tarayicida acik duran eski dosya en azindan durumu soylesin).
    """
    saat = time.strftime("%d.%m.%Y %H:%M")
    if adres:
        metin = ("DeepCortex Finans -- uzaktan erisim adresi\n\n"
                 "{}\n\n"
                 "Acilis: {}\n"
                 "Bu adres her acilista DEGISIR.\n"
                 "Ev bilgisayarindaki pencere kapaninca calismaz.\n").format(
                     adres, saat)
    else:
        metin = ("DeepCortex Finans -- uzaktan erisim\n\n"
                 "SU AN KAPALI ({}).\n"
                 "Ev bilgisayarinda UZAKTAN.bat calistirildiginda buraya\n"
                 "yeni adres yazilir.\n").format(saat)

    yazilan = []
    hedefler = [ADRES_DOSYA]
    hedefler += [yol / "DeepCortex-ADRES.txt" for _, yol in bulut_dizinleri()]
    for hedef in hedefler:
        try:
            hedef.write_text(metin, encoding="utf-8")
            yazilan.append(hedef)
        except OSError:
            pass
    return yazilan


def yaz(*satirlar: str) -> None:
    for s in satirlar:
        print("  " + s if s else "")


def cerceve(baslik: str, satirlar: list[str]) -> None:
    en = max([len(baslik)] + [len(s) for s in satirlar]) + 4
    print()
    print("  +" + "-" * en + "+")
    print("  | " + baslik.ljust(en - 2) + " |")
    print("  |" + " " * en + "|")
    for s in satirlar:
        print("  | " + s.ljust(en - 2) + " |")
    print("  +" + "-" * en + "+")
    print()


def port_dolu(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def saglikli(port: int) -> bool:
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:{}/_stcore/health".format(port), timeout=2) as r:
            return r.status == 200
    except Exception:       # noqa: BLE001 -- henuz acilmamis olabilir
        return False


# --------------------------------------------------------------------------
# Parola
# --------------------------------------------------------------------------
def parola_hazirla() -> str:
    """Kayitli parolanin jetonunu doner; kayit yoksa yenisini sorar."""
    kayit = erisim.oku()
    if kayit is not None:
        return erisim.jeton(kayit)

    yaz("", "Ilk kurulum: uzaktan erisim icin bir PAROLA belirleyin.",
        "Bu parola yalnizca sizde kalir; dosyaya yalnizca ozeti yazilir.",
        "En az {} karakter olmali.".format(erisim.EN_AZ), "")
    while True:
        p1 = getpass.getpass("  Parola: ")
        if len(p1) < erisim.EN_AZ:
            yaz("Cok kisa, en az {} karakter.".format(erisim.EN_AZ))
            continue
        p2 = getpass.getpass("  Parola (tekrar): ")
        if p1 != p2:
            yaz("Iki parola ayni degil, tekrar deneyin.")
            continue
        kayit = erisim.kaydet(p1)
        yaz("", "Parola kaydedildi: config/erisim.json", "")
        return erisim.jeton(kayit)


# --------------------------------------------------------------------------
# Tunel araci
# --------------------------------------------------------------------------
def arac_hazirla() -> bool:
    if ARAC.exists() and ARAC.stat().st_size > 1_000_000:
        return True

    yaz("", "Tunel araci (cloudflared) bu bilgisayarda yok.",
        "Cloudflare'in resmi surumu indirilecek (~50 MB):",
        "  " + ARAC_URL,
        "Indirilen dosya: araclar/cloudflared.exe", "")
    try:
        cevap = input("  Indirilsin mi? [E/h]: ").strip().lower()
    except EOFError:
        cevap = "e"
    if cevap not in ("", "e", "evet", "y", "yes"):
        yaz("Indirme iptal edildi.")
        return False

    ARAC_DIZIN.mkdir(parents=True, exist_ok=True)
    gecici = ARAC.with_suffix(".indiriliyor")
    yaz("Indiriliyor...")
    try:
        with urllib.request.urlopen(ARAC_URL, timeout=60) as cevap_akis, \
                open(gecici, "wb") as f:
            toplam = int(cevap_akis.headers.get("Content-Length") or 0)
            inen = 0
            while True:
                parca = cevap_akis.read(262_144)
                if not parca:
                    break
                f.write(parca)
                inen += len(parca)
                if toplam:
                    print("\r  %{:.0f}".format(100 * inen / toplam), end="")
        print()
        gecici.replace(ARAC)
    except Exception as exc:        # noqa: BLE001 -- ag hatasi kullaniciya
        if gecici.exists():
            gecici.unlink()
        yaz("Indirilemedi: {}".format(exc),
            "Internet baglantinizi kontrol edip tekrar deneyin.")
        return False

    try:
        subprocess.run([str(ARAC), "--version"], capture_output=True,
                       timeout=30, creationflags=_GIZLI, check=True)
    except Exception as exc:        # noqa: BLE001
        yaz("Indirilen dosya calismadi: {}".format(exc))
        return False
    yaz("Tunel araci hazir.")
    return True


# --------------------------------------------------------------------------
# Arayuz ve tunel
# --------------------------------------------------------------------------
def arayuz_baslat(jeton: str) -> subprocess.Popen:
    """Streamlit'i yalnizca 127.0.0.1'de dinleyecek sekilde baslatir."""
    ortam = dict(os.environ)
    ortam[erisim.ENV_JETON] = jeton        # parola kapisini acar
    ARAC_DIZIN.mkdir(parents=True, exist_ok=True)
    kayit = open(KAYIT, "w", encoding="utf-8", errors="replace")
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(PORT),
         "--server.address", "127.0.0.1",
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), env=ortam, stdout=kayit, stderr=subprocess.STDOUT,
        creationflags=_GIZLI,
    )


def tunel_baslat() -> tuple[subprocess.Popen, str | None]:
    """Tuneli acar ve adresi cikartir. Donen: (surec, adres)."""
    surec = subprocess.Popen(
        [str(ARAC), "tunnel", "--no-autoupdate", "--url",
         "http://127.0.0.1:{}".format(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1, creationflags=_GIZLI,
    )

    kuyruk: Queue = Queue()

    def oku() -> None:
        for satir in surec.stdout:       # type: ignore[union-attr]
            kuyruk.put(satir)
    threading.Thread(target=oku, daemon=True).start()

    adres = None
    bitis = time.time() + 45
    with open(KAYIT.with_name("tunel.log"), "w", encoding="utf-8") as gunluk:
        while time.time() < bitis and adres is None:
            try:
                satir = kuyruk.get(timeout=1)
            except Empty:
                if surec.poll() is not None:
                    break
                continue
            gunluk.write(satir)
            gunluk.flush()
            bulunan = ADRES_KALIBI.search(satir)
            if bulunan:
                adres = bulunan.group(0)
    return surec, adres


def eposta_yolla(adres: str, saat: str) -> str:
    """Adresi e-postayla yollar. Donen: ekranda gosterilecek tek satir."""
    try:
        if not bildirim.kurulu():
            return ("E-posta kurulu degil (isterseniz EPOSTA_AYARLA.bat ile "
                    "bir kez kurun).")
        ayar = bildirim.ayar_oku()
        konu, govde = bildirim.adres_iletisi(adres, saat)
        bildirim.gonder(konu, govde, ayar=ayar)
        return "E-posta gonderildi: {}".format(ayar["alici"])
    except Exception as exc:        # noqa: BLE001 -- adres yine de ekranda
        return "E-posta GONDERILEMEDI: {}".format(exc)


def main() -> int:
    yaz("", "DeepCortex Finans -- uzaktan erisim")

    if port_dolu(PORT):
        cerceve("PROGRAM ZATEN ACIK", [
            "{} portu kullanimda. Buyuk ihtimalle program".format(PORT),
            "BASLAT.bat ile acik.",
            "",
            "Once o pencereyi kapatin, sonra UZAKTAN.bat'i",
            "yeniden calistirin. (Ayni anda ikisi calisamaz:",
            "acik olan kopyada parola kapisi YOKTUR.)",
        ])
        input("  Kapatmak icin Enter...")
        return 1

    jeton = parola_hazirla()
    if not arac_hazirla():
        input("  Kapatmak icin Enter...")
        return 1

    if uyku_engelle(True):
        yaz("Bilgisayar, bu pencere acik kaldigi surece uykuya gecmeyecek.")
    yaz("Arayuz baslatiliyor...")
    arayuz = arayuz_baslat(jeton)
    bitis = time.time() + 90
    while time.time() < bitis and not saglikli(PORT):
        if arayuz.poll() is not None:
            yaz("Arayuz baslatilamadi. Ayrinti: araclar/uzaktan.log")
            input("  Kapatmak icin Enter...")
            return 1
        time.sleep(1)

    yaz("Tunel aciliyor...")
    tunel, adres = tunel_baslat()
    if adres is None:
        yaz("Tunel adresi alinamadi. Ayrinti: araclar/tunel.log")
        tunel.terminate()
        arayuz.terminate()
        input("  Kapatmak icin Enter...")
        return 1

    saat = time.strftime("%d.%m.%Y %H:%M")
    adres_yaz(adres)
    posta_notu = eposta_yolla(adres, saat)
    bulutlar = bulut_dizinleri()

    satirlar = [
        adres,
        "",
        "Bu adresi is bilgisayarinizda ya da telefonunuzda acin.",
        "Karsiniza parola ekrani gelecek. Oraya hicbir sey KURULMAZ.",
        "",
        "Adres nereye gitti:",
        "  * " + posta_notu,
    ]
    for ad, _yol in bulutlar:
        satirlar.append("  * {} klasorune 'DeepCortex-ADRES.txt' yazildi"
                        .format(ad))
    if not bulutlar:
        satirlar.append("  * ADRES.txt (bu klasor) -- bulut klasoru bulunamadi")
    satirlar += [
        "",
        "Her acilista YENI bir adres uretilir.",
        "Program acik kaldigi surece bilgisayar uykuya GECMEZ.",
        "",
        "Kapatmak icin: bu pencereyi kapatin ya da Ctrl+C.",
        "Pencere kapaninca disaridan erisim de kapanir.",
    ]
    cerceve("ADRES HAZIR", satirlar)

    try:
        while True:
            time.sleep(2)
            if tunel.poll() is not None:
                yaz("Tunel kapandi.")
                break
            if arayuz.poll() is not None:
                yaz("Arayuz kapandi.")
                break
    except KeyboardInterrupt:
        yaz("", "Kapatiliyor...")
    finally:
        for surec in (tunel, arayuz):
            if surec.poll() is None:
                surec.terminate()
                try:
                    surec.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    surec.kill()
        adres_yaz(None)        # "su an kapali" notu
        uyku_engelle(False)
    yaz("Uzaktan erisim kapandi.", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

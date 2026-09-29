"""Kisayollari kurar / kaldirir -- KISAYOL_OLUSTUR.bat cagirir.

Kullanici (21.09.2026): "Chrome'a bir kisayol ikonu ekle, oraya basip
baslatayim" -> secimi: "ikisi de".

KURULANLAR (hepsi yalnizca bu Windows kullanicisi icin, geri alinabilir)
  1. ui/assets/deepcortex.ico   -- programin kendi ikonu (Pillow ile cizilir)
  2. Masaustu + Baslat menusu kisayolu "DeepCortex"
       -> pythonw scripts\\ac.py  (konsol penceresi acmaz)
     Gorev cubuguna sabitlemeyi Windows 11 programlara YAPTIRMIYOR; kullanici
     masaustundeki ikona sag tiklayip "Gorev cubuguna sabitle" der.
  3. "deepcortex:" baglanti turu (HKCU\\Software\\Classes\\deepcortex)
       -> Chrome'daki yer imi "deepcortex://baslat" bunu cagirir.
  4. Chrome'da yer imi sayfasi acilir (ui/assets/yer_imi.html): dugme
     yer imleri cubuguna suruklenir. Chrome'un yer imi dosyasina DOKUNULMAZ
     -- Chrome aciksa ustune yazar, ayrica kullanicinin tarayici verisi.

KALDIRMA: python scripts\\kisayol.py kaldir  (kisayollar + kayit defteri
anahtari silinir; ikon dosyasi kalir, zararsiz).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICO = ROOT / "ui" / "assets" / "deepcortex.ico"
YER_IMI = ROOT / "ui" / "assets" / "yer_imi.html"
AC = ROOT / "scripts" / "ac.py"
PROTOKOL = "deepcortex"
# Kayit defteri anahtari (HKEY_CURRENT_USER altinda)
KAYIT = r"Software\Classes\deepcortex"

sys.path.insert(0, str(ROOT / "scripts"))


def yaz(*satirlar: str) -> None:
    for s in satirlar:
        print("  " + s if s else "")


def pythonw() -> str:
    """Konsolsuz Python (pythonw.exe) -- yoksa normal python."""
    aday = Path(sys.executable).with_name("pythonw.exe")
    return str(aday if aday.exists() else Path(sys.executable))


# --------------------------------------------------------------------------
# Ikon
# --------------------------------------------------------------------------
def ikon_uret(yol: Path = ICO) -> Path:
    """Koyu zemin + yukselen uc mum. Kucuk boyutta (16 px) da okunsun diye
    kalin, sade sekiller; 1024'te cizilip kucultulur (yumusak kenar)."""
    from PIL import Image, ImageDraw, ImageFilter

    N = 1024
    zemin = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(zemin)
    kenar = 40
    d.rounded_rectangle([kenar, kenar, N - kenar, N - kenar], radius=210,
                        fill=(14, 16, 22, 255))

    # Mumlarin arkasinda hafif mavi parilti.
    parilti = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    pd = ImageDraw.Draw(parilti)
    pd.ellipse([230, 330, 800, 900], fill=(57, 135, 229, 70))
    parilti = parilti.filter(ImageFilter.GaussianBlur(90))
    zemin = Image.alpha_composite(zemin, parilti)
    d = ImageDraw.Draw(zemin)

    # (x merkez, fitil ust, govde ust, govde alt, fitil alt, renk)
    mumlar = [
        (330, 470, 540, 760, 820, (42, 94, 168, 255)),
        (512, 330, 400, 690, 760, (57, 135, 229, 255)),
        (694, 190, 250, 560, 640, (111, 176, 255, 255)),
    ]
    for x, fu, gu, ga, fa, renk in mumlar:
        d.rounded_rectangle([x - 16, fu, x + 16, fa], radius=16, fill=renk)
        d.rounded_rectangle([x - 72, gu, x + 72, ga], radius=26, fill=renk)

    # Ince mavi cerceve
    d.rounded_rectangle([kenar, kenar, N - kenar, N - kenar], radius=210,
                        outline=(57, 135, 229, 150), width=14)

    yol.parent.mkdir(parents=True, exist_ok=True)
    zemin.save(yol, format="ICO",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                      (128, 128), (256, 256)])
    # Onizleme icin PNG (belgelerde / kontrol icin)
    zemin.resize((256, 256), Image.LANCZOS).save(yol.with_suffix(".png"))
    return yol


# --------------------------------------------------------------------------
# Kisayollar (.lnk) -- Windows'un kendi WScript.Shell nesnesiyle
# --------------------------------------------------------------------------
_PS_LNK = r"""
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$klasorler = @([Environment]::GetFolderPath('Desktop'),
               [Environment]::GetFolderPath('Programs'))
foreach ($k in $klasorler) {
    $yol = Join-Path $k 'DeepCortex.lnk'
    if ($env:DC_KALDIR -eq '1') {
        if (Test-Path -LiteralPath $yol) { Remove-Item -LiteralPath $yol -Force }
        Write-Output ("silindi: " + $yol)
        continue
    }
    $s = $ws.CreateShortcut($yol)
    $s.TargetPath = $env:DC_HEDEF
    $s.Arguments = '"' + $env:DC_AC + '"'
    $s.WorkingDirectory = $env:DC_KOK
    $s.IconLocation = $env:DC_ICO + ',0'
    $s.Description = 'DeepCortex Finans - baslat ya da pencereyi getir'
    $s.Save()
    Write-Output ("olusturuldu: " + $yol)
}
"""


def kisayollar(kaldir: bool = False) -> list[str]:
    ortam = dict(os.environ, DC_HEDEF=pythonw(), DC_AC=str(AC), DC_KOK=str(ROOT),
                 DC_ICO=str(ICO), DC_KALDIR="1" if kaldir else "0")
    sonuc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         _PS_LNK], env=ortam, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if sonuc.returncode != 0:
        raise RuntimeError(sonuc.stderr.strip() or "kisayol olusturulamadi")
    return [s for s in sonuc.stdout.splitlines() if s.strip()]


# --------------------------------------------------------------------------
# "deepcortex:" baglanti turu (yalniz bu kullanici -- HKCU)
# --------------------------------------------------------------------------
def protokol_kaydet() -> None:
    import winreg
    kok = KAYIT
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, kok) as k:
        winreg.SetValue(k, "", winreg.REG_SZ, "URL:DeepCortex")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, kok + r"\DefaultIcon") as k:
        winreg.SetValue(k, "", winreg.REG_SZ, '"{}",0'.format(ICO))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          kok + r"\shell\open\command") as k:
        winreg.SetValue(k, "", winreg.REG_SZ,
                        '"{}" "{}" "%1"'.format(pythonw(), AC))


def protokol_sil() -> None:
    import winreg
    kok = KAYIT
    for alt in (r"\shell\open\command", r"\shell\open", r"\shell",
                r"\DefaultIcon", ""):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, kok + alt)
        except OSError:
            pass


# --------------------------------------------------------------------------
def kur() -> int:
    yaz("", "DeepCortex kisayollari kuruluyor...", "")
    ikon_uret()
    yaz("ikon: " + str(ICO))
    for satir in kisayollar():
        yaz(satir)
    protokol_kaydet()
    yaz("Chrome yer imi icin 'deepcortex:' baglanti turu kaydedildi.")

    import ac
    chrome = ac.chrome_yolu()
    if chrome:
        subprocess.Popen([chrome, YER_IMI.as_uri()])
        yaz("", "Chrome'da acilan sayfadaki DeepCortex dugmesini yer imleri",
            "cubuguna surukleyin.")
    else:
        yaz("", "Chrome bulunamadi; yer imi icin adres: deepcortex://baslat")
    yaz("", "Gorev cubuguna sabitlemek icin: masaustundeki DeepCortex ikonuna",
        "sag tiklayin -> 'Gorev cubuguna sabitle'. (Windows 11'de once",
        "'Daha fazla secenek goster'.)", "")
    return 0


def kaldir() -> int:
    for satir in kisayollar(kaldir=True):
        yaz(satir)
    protokol_sil()
    yaz("'deepcortex:' baglanti turu silindi. (Chrome'daki yer imini elle silin.)")
    return 0


if __name__ == "__main__":
    komut = sys.argv[1] if len(sys.argv) > 1 else "kur"
    raise SystemExit(kaldir() if komut == "kaldir" else kur())

"""E-posta bildirimini kurar (bir kez) -- EPOSTA_AYARLA.bat bunu cagirir.

Sorar: gonderen adres, uygulama parolasi, alici adres. Sonra DENEME POSTASI
gonderir; gelmezse ayar kaydedilmez -- yanlis ayarla "gonderdim" demeyelim.

UYGULAMA PAROLASI NEDIR
    Yahoo/Gmail gibi saglayicilar ana parolanizi programlara vermez. Hesap
    ayarlarindan "uygulama parolasi" (app password) uretirsiniz: yalnizca
    o program icin gecerli, istediginiz an iptal edebileceginiz bir parola.
    Yahoo:  Hesap Bilgileri > Hesap Guvenligi > Uygulama parolasi olustur
    Gmail:  Google Hesabi > Guvenlik > 2 adimli dogrulama > Uygulama sifreleri

Parola bu bilgisayarda Windows DPAPI ile sifrelenerek saklanir; duz metin
hicbir yere yazilmaz ve ekranda gorunmez.
"""

from __future__ import annotations

import getpass
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finans_cortex import bildirim  # noqa: E402


def yaz(*satirlar: str) -> None:
    for s in satirlar:
        print("  " + s if s else "")


def main() -> int:
    yaz("", "DeepCortex Finans -- e-posta bildirimi kurulumu", "")

    if not bildirim.dpapi_var():
        yaz("Bu bilgisayarda Windows sifreleme (DPAPI) yok; parola guvenli",
            "sekilde saklanamaz. Kurulum iptal edildi.")
        return 1

    mevcut = bildirim.ayar_oku()
    if mevcut:
        yaz("Kayitli ayar var: {} -> {}".format(
            mevcut.get("gonderen", "?"), mevcut.get("alici", "?")))
        if input("  Degistirilsin mi? [e/H]: ").strip().lower() not in ("e", "evet"):
            yaz("Degisiklik yapilmadi.")
            return 0
        yaz("")

    yaz("Adresi HANGI hesaptan gonderelim? (postayi bu hesap yollayacak)")
    gonderen = input("  Gonderen e-posta: ").strip()
    if "@" not in gonderen:
        yaz("Gecerli bir e-posta adresi degil.")
        return 1

    sunucu = bildirim.sunucu_bul(gonderen)
    if sunucu is None:
        yaz("", "Bu saglayicinin ayarlarini bilmiyorum; elle girin.")
        ad = input("  SMTP sunucusu (orn. smtp.mail.yahoo.com): ").strip()
        port = input("  Port [465]: ").strip() or "465"
        sunucu = (ad, int(port))
    yaz("SMTP: {}:{}".format(*sunucu))

    yaz("", "Simdi UYGULAMA PAROLASI gerekli (ana parolaniz DEGIL).",
        "Yahoo: Hesap Guvenligi > Uygulama parolasi olustur",
        "Gmail: Guvenlik > 2 adimli dogrulama > Uygulama sifreleri",
        "Yazarken ekranda gorunmez.", "")
    parola = getpass.getpass("  Uygulama parolasi: ").replace(" ", "")
    if not parola:
        yaz("Parola bos, iptal edildi.")
        return 1

    varsayilan_alici = gonderen
    alici = input("  Adres hangi posta kutusuna gelsin? [{}]: ".format(
        varsayilan_alici)).strip() or varsayilan_alici

    ayar = {"gonderen": gonderen, "alici": alici,
            "sunucu": sunucu[0], "port": sunucu[1]}

    yaz("", "Deneme postasi gonderiliyor...")
    try:
        bildirim.gonder(
            "DeepCortex Finans - deneme",
            "Bu bir deneme postasidir.\n\nBunu gorduyseniz uzaktan erisim "
            "adresi de buraya gelecek demektir.\n\nSaat: {}\n".format(
                time.strftime("%d.%m.%Y %H:%M")),
            ayar=ayar, parola=parola)
    except Exception as exc:        # noqa: BLE001 -- kullaniciya gosterilir
        yaz("Gonderilemedi: {}".format(exc), "",
            "Sik sebepler:",
            "  - Ana parola girildi (uygulama parolasi gerekiyor)",
            "  - Uygulama parolasi yanlis kopyalandi",
            "  - Saglayici SMTP erisimini kapatmis",
            "Ayar KAYDEDILMEDI.")
        return 1

    ayar["parola_dpapi"] = bildirim.sifrele(parola)
    bildirim.ayar_yaz(ayar)
    yaz("Gonderildi. Posta kutunuza bakin: {}".format(alici), "",
        "Ayar kaydedildi: config/eposta.json",
        "(Parola bu bilgisayarin Windows kullanicisina bagli sifrelenmistir.)",
        "Bundan sonra UZAKTAN.bat her acilista adresi buraya yollayacak.", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

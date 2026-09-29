"""Kural akisi -- stratejinin kurallarini akis semasi olarak tarif eder.

AMAC (kullanici istegi, 20.09.2026): "Alim satim kurallarini akis semasi
halinde goster; sectigim gercek bir sinyalde kurallarin nasil isledigini
adim adim animasyonla anlat."

TASARIM: TEK MOTOR, HER STRATEJI
    Bu dosya yalnizca ORTAK dili tanimlar (Dugum / Adim). Her strateji
    motoru (ema_two_close, heikin_range, ...) iki fonksiyon verir:

        sema(cfg)                 -> list[Dugum]   kurallarin semasi
        izle(bars, islem, cfg, timeframe) -> list[Adim]
                                     secilen sinyalde her dugumun sonucu
                                     (+ mum grafigindeki Isaret'leri)

    Arayuz (ui/akis.py) stratejiyi TANIMAZ: semayi cizer, adimlari
    sirayla oynatir. Yeni bir strateji eklenince bu iki fonksiyonu yazmak
    yeter; cizim, animasyon, sinyal listesi kendiliginden calisir.

SEMANIN SEKLI
    Dugumler yukaridan asagiya tek bir omurga olusturur. Kosul dugumlerinin
    "hayir" tarafi saga dogru kucuk bir cikis kutusuna gider (ornegin
    "sinyal yok, bekle"). Bu, iki stratejinin de kurallarini anlatmaya
    yetiyor ve cizimi basit/saglam tutuyor.

DURUMLAR
    gecti    kosul saglandi / islem yapildi   (yesil)
    kaldi    kosul saglanmadi, akis buradan cikti (kirmizi)
    atlandi  bu sinyalde sirasi gelmedi ya da kapali bir secenek (soluk)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

GECTI = "gecti"
KALDI = "kaldi"
ATLANDI = "atlandi"

TIPLER = ("baslangic", "kosul", "islem", "bitis")


@dataclass(frozen=True)
class Dugum:
    """Semadaki bir kutu.

    kod     benzersiz kimlik; Adim bu kodla dugume baglanir
    tip     baslangic | kosul | islem | bitis  (cizim sekli bundan)
    baslik  kutudaki ana metin -- KURAL, sinyale gore degismez
    alt     kucuk punto ikinci satir (parametre: "EMA 10", "tolerans 3 bar")
    hayir   kosulda "hayir" dalinin gidecegi kutunun metni; bos ise dal yok
    """

    kod: str
    tip: str
    baslik: str
    alt: str = ""
    hayir: str = ""

    def __post_init__(self) -> None:
        if self.tip not in TIPLER:
            raise ValueError("bilinmeyen dugum tipi: {}".format(self.tip))


ISARET_TURLERI = ("nokta", "ok", "cizgi", "bolge")


@dataclass(frozen=True)
class Isaret:
    """Adimin mum grafigindeki karsiligi (21.09.2026, kullanici: sema "havada
    duruyordu" -- "Chandelier 15:00'te yandi" yaziyor ama bar gorunmuyordu).

    tur     nokta  fiyat seviyesinde daire (giris, cikis)
            ok     mumun altinda (yon=+1) / ustunde (yon=-1) ucgen (gosterge
                   yandi, onay kapanisi)
            cizgi  `zaman`dan `bitis`e yatay cizgi `fiyat`ta (stop, hedef)
            bolge  `zaman`-`bitis` arasi golge (islemin acik oldugu sure)
    renk    "" = adimin durum rengi; "stop" / "hedef" / "notr" sabit renk
    neden   yalniz nokta icin: doluysa nokta BUYUK etiketli bir ana olay olur
            (GIRIS / CIKIS) -- dikey cizgi + kutu: etiket, fiyat ve bu cumle.
            Kullanici (21.09.2026): "nerede girdik nerede ciktik anlamiyorum,
            neden girdik neden ciktik belli olsun".
    """

    tur: str
    zaman: datetime
    fiyat: float | None = None
    bitis: datetime | None = None
    etiket: str = ""
    yon: int = 1
    renk: str = ""
    neden: str = ""

    def __post_init__(self) -> None:
        if self.tur not in ISARET_TURLERI:
            raise ValueError("bilinmeyen isaret turu: {}".format(self.tur))


@dataclass(frozen=True)
class Adim:
    """Secilen sinyalde bir dugumun sonucu.

    metin GERCEK degerleri tasir: "kapanis 4.315,20 > EMA 4.312,50".
    zaman varsa kutunun yaninda saat olarak gorunur.
    isaretler  bu adim mum grafiginde nereyi gosterir; animasyonda kutuyla
               AYNI anda belirir. Bos olabilir (ornegin "SAT izni").
    """

    kod: str
    durum: str
    metin: str
    zaman: datetime | None = None
    isaretler: tuple[Isaret, ...] = ()


def bos_adim(dugumler: list[Dugum]) -> list[Adim]:
    """Hicbir sinyal secilmemisken: tum dugumler soluk."""
    return [Adim(d.kod, ATLANDI, "") for d in dugumler]


def destekli(motor) -> bool:
    """Motor akis semasi veriyor mu (eski/yeni strateji karisik olabilir)."""
    return callable(getattr(motor, "sema", None)) and callable(
        getattr(motor, "izle", None))

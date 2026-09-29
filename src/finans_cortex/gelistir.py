"""Gelistirme motoru -- stratejinin zayif noktalarini bulur, parametre onerir.

AMAC (kullanici, 22.09.2026): *"Strateji 2.1'in kazandirma orani yeterli
degil. Bunu inceleyip orani artirmaya yonelik fikirler veren bir motor gerek.
Parametre tuning yapabilir, backtest'leri inceleyip zayif noktalari bulabilir.
Programin en guclu yani burasi olmali."*

BU DOSYA STRATEJIDEN BAGIMSIZDIR. Motorlardan yalnizca sunlari ister:
    motor.prepare(bars, cfg[, ek])           gosterge sutunlari (ek =
                                             baska zaman diliminin cercevesi)
    motor.hazir_simule(hazir, cfg, tf, bp)   islem listesi
    motor.ARAMA_UZAYI                        {parametre: [denenecek degerler]}
    motor.GOSTERGE_PARAMLARI                 prepare'i etkileyen parametreler
    dataclasses.replace(cfg, **degisiklik)   parametre degistirme

ASIRI UYUM (bu dosyanin varlik sebebi kadar onemli)
    Gecmise en iyi uyan parametreyi bulmak kolaydir ve GELECEKTE CALISMAZ.
    Bu yuzden her tarama satiri uc sayiyla gelir:
      - AYAR bolumu (ilk %70): parametrenin secildigi yer
      - KONTROL bolumu (son %30): parametrenin hic gormedigi yer
      - KOMSU ortalamasi: bir parametre adim saga/sola kaydirilinca sonuc ne
        oluyor. Tek basina parlayip komsulari kotu olan nokta TESADUFTUR;
        genis bir "yayla" aranir.
    Sirala: once kontrol bolumu, sonra komsu ortalamasi. Yalniz ayar bolumune
    bakarak strateji secilmez.

OLCU HAVUZU
    Birden cok varlik tek portfoy gibi degerlendirilir: her islem ayni
    buyuklukte (bilesik degil, backtest paneliyle ayni varsayim), gunluk
    getiri varliklarin ortalamasidir (esit agirlik).
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field, replace
from datetime import datetime

import polars as pl

from . import perf

# Amac -> (olcu anahtari, buyuk olan iyi mi, ekranda birim)
AMACLAR: dict[str, tuple[str, bool, str]] = {
    # ILK SIRADA yillik getiri (24 Eylul 2026). "Net kar %" islem
    # getirilerinin toplamidir; farkli uzunluktaki gecmisler toplaninca
    # kiyaslanamaz hale gelir ve taramayi yanlis yere goturur. Eski secenek
    # duruyor ama varsayilan artik bu degil.
    "Yillik getiri %": ("yillik_%", True, "%"),
    "Net kar % (toplam)": ("getiri_%", True, "%"),
    "Kar faktoru": ("kar_faktoru", True, ""),
    "Islem basina (bp)": ("ort_islem_bp", True, " bp"),
    "Kazanan islem %": ("kazanan_%", True, "%"),
    "Sharpe": ("Sharpe", True, ""),
}

AYAR_ORANI = 0.7          # ilk %70 ayar, son %30 kontrol (backtest paneliyle ayni)
EN_AZ_ISLEM = 20          # bir bulgunun kurulabilmesi icin en az islem sayisi
ONEMLI_FARK_BP = 5.0      # iki grubu "farkli" saymak icin en az fark (bp)


# ==========================================================================
# CALISTIRMA
# ==========================================================================
def hazirla(motor, bars: dict[str, pl.DataFrame], cfg,
            yardimci: dict[str, pl.DataFrame] | None = None) -> dict[str, pl.DataFrame]:
    """Varlik basina gosterge sutunlari. Pahali kisim budur; tarama sirasinda
    gosterge parametreleri degismedigi surece TEKRAR HESAPLANMAZ.

    `yardimci`: bazi kurallar BASKA bir zaman diliminin verisini ister
    (Strateji 2'nin 15 dakikalik Chandelier teyidi gibi). Varsa varlik basina
    ikinci cerceve olarak motora gecer; motor istemiyorsa yok sayilir."""
    out = {}
    for kod, df in bars.items():
        if not df.height:
            continue
        ek = (yardimci or {}).get(kod)
        out[kod] = (motor.prepare(df, cfg, ek) if ek is not None
                    else motor.prepare(df, cfg))
    return out


def kos(motor, hazir: dict[str, pl.DataFrame], cfg, timeframe: str,
        maliyet: dict[str, float], baslangic: datetime | None = None,
        bitis: datetime | None = None) -> dict:
    """Tum varliklarda calistirir, sonuclari tek havuzda toplar.

    Doner: {"islemler": havuz (kod sutunlu), "gunluk": portfoy gunluk getiri,
            "varlik": {kod: (islemler, barlar)}}
    """
    parcalar, gunlukler, varlik = [], [], {}
    for kod, df in hazir.items():
        if baslangic is not None:
            df = df.filter(pl.col("ts") >= baslangic)
        if bitis is not None:
            df = df.filter(pl.col("ts") < bitis)
        if df.height < 2:
            continue
        islemler = motor.hazir_simule(df, cfg, timeframe, maliyet.get(kod, 0.0))
        varlik[kod] = (islemler, df)
        if islemler.height:
            parcalar.append(islemler.with_columns(pl.lit(kod).alias("kod")))
        g = motor.daily_equity(islemler, df)
        gunlukler.append(g.select("tday", "ret"))

    havuz = (pl.concat(parcalar).sort("giris_ts") if parcalar else
             pl.DataFrame(schema=dict(perf.TRADE_SCHEMA, kod=pl.Utf8)))
    gunluk = _portfoy_gunluk(gunlukler)
    varlik_gun = 0.0
    for _, (_, df) in varlik.items():
        if df.height >= 2:
            varlik_gun += (df["ts"][-1] - df["ts"][0]).total_seconds() / 86400.0
    # Havuzun TAM oldugu (secilen her varligin verisinin basladigi) gun.
    # Oncesinde para daha az varliga bolunur -- ekranda soylenir.
    tam = max((df["ts"][0] for _, df in varlik.values()), default=None)
    return {"islemler": havuz, "gunluk": gunluk, "varlik": varlik,
            "al_tut": _al_tut(varlik),
            "havuz": {"varlik_gun": varlik_gun, "n_varlik": len(varlik),
                      "tam_baslangic": tam}}


def _al_tut(varlik: dict) -> dict:
    """Ayni havuzun AL-TUT karsiligi: yillik getiri ve en buyuk dusus.

    Stratejinin egrisiyle BIREBIR ayni yontemle kurulur (esit agirlik, gunluk
    ortalama, bilesik) ki yan yana konabilsin. Bu olmadan "strateji %8,6
    kazandirdi" cumlesi tek basina bir sey ifade etmiyor -- al-tut %11,5 ise
    strateji ise yaramamis demektir (24 Eylul 2026 dersi).
    """
    nan = float("nan")
    out = {"yillik_%": nan, "MaxDD_%": nan}
    parcalar = []
    for _, (_, df) in varlik.items():
        if df.height < 2 or "tday" not in df.columns:
            continue
        g = (df.select("tday", "close").group_by("tday")
             .agg(pl.col("close").last()).sort("tday")
             .with_columns(pl.col("close").pct_change().alias("ret"))
             .drop_nulls("ret").select("tday", "ret"))
        if g.height:
            parcalar.append(g)
    if not parcalar:
        return out
    e = _portfoy_gunluk(parcalar)
    if e.height < 2:
        return out
    yil = (e["tday"][-1] - e["tday"][0]).days / 365.0
    son = float(e["equity"][-1])
    if yil > 0 and son > 0:
        out["yillik_%"] = round(100 * (son ** (1 / yil) - 1), 1)
    tepe = e["equity"].cum_max()
    out["MaxDD_%"] = round(100 * float(((e["equity"] - tepe) / tepe).min()), 1)
    return out


def _portfoy_gunluk(gunlukler: list[pl.DataFrame]) -> pl.DataFrame:
    """Esit para: gunun getirisi, VERISI BASLAMIS varliklarin ortalamasi.

    Listenin her elemani bir varliktir. Bir varlik ilk ve son gunu arasinda
    havuzdadir; o gun piyasasi kapaliysa (hafta sonu, tatil) payini korur ve
    getirisi 0 sayilir. Yeni varligin verisi baslayinca para yeniden esit
    bolunur.

    24 Eylul 2026 duzeltmesi: eskiden "o gun verisi olanlarin ortalamasi"
    aliniyordu. Hafta sonu yalniz BTC acik oldugu icin 402 gunde portfoyun
    %100'u BTC sayiliyordu; 9 varligin al-tut'u %16,0 goruyordu, dogrusu
    %13,1 (olculdu).
    """
    bos = pl.DataFrame(schema={"tday": pl.Date, "ret": pl.Float64,
                               "equity": pl.Float64})
    parcalar = [g.select("tday", "ret").with_columns(pl.lit(j).alias("_v"))
                for j, g in enumerate(gunlukler) if not g.is_empty()]
    if not parcalar:
        return bos
    tum = pl.concat(parcalar)
    aralik = tum.group_by("_v").agg(pl.col("tday").min().alias("_a"),
                                    pl.col("tday").max().alias("_b"))
    g = (tum.select("tday").unique()
         .join(aralik, how="cross")
         .filter(pl.col("tday").is_between(pl.col("_a"), pl.col("_b")))
         .join(tum, on=["tday", "_v"], how="left")
         .group_by("tday").agg(pl.col("ret").fill_null(0.0).mean())
         .sort("tday"))
    return g.with_columns((1 + pl.col("ret")).cum_prod().alias("equity"))


def olcu(islemler: pl.DataFrame, gunluk: pl.DataFrame,
         havuz: dict | None = None) -> dict:
    """Havuzun olculeri. perf.metrics tek varlik icindir; portfoyde gunluk
    egri varliklarin ortalamasi oldugu icin burada ayrica hesaplanir."""
    nan = float("nan")
    out = {"islem": islemler.height, "kazanan_%": nan, "kar_faktoru": nan,
           "getiri_%": nan, "ort_islem_bp": nan, "ort_R": nan, "Sharpe": nan,
           "MaxDD_%": nan, "ort_kazanc_%": nan, "ort_kayip_%": nan,
           "odul_kayip": nan, "basabas_kazanan_%": nan,
           # 24 Eylul 2026, kullanici: "senede 2-3 sinyal vermisler, onda da
           # dogru durust kazanc yok". Hakliydi ve GOREMEDIGIMIZ icin
           # yanilmistik: ekranda yalnizca `getiri_%` vardi, o da islem
           # getirilerinin TOPLAMI. 23 yillik bir varligin toplami ile 9
           # yillik bir varligin toplami yan yana konunca anlamsiz buyuk bir
           # sayi cikiyor ("+%1.245"), oysa yillik karsiligi %8,6'ydi ve
           # al-tut'un (%11,5) altindaydi. Asagidaki uc olcu bunu gorunur
           # kilar; hangi ayarin iyi oldugunu ancak bunlarla ayirt edebiliriz.
           "yillik_%": nan,        # bilesik yillik getiri (portfoy egrisinden)
           "piyasada_%": nan,      # sermayenin pozisyonda gectigi sure orani
           "islem_yil": nan,       # varlik basina yilda kac islem
           "yil": nan}
    if islemler.is_empty():
        return out

    r = islemler["getiri"]
    kazanan = r.filter(r > 0)
    kaybeden = r.filter(r < 0)
    brut_kar = float(kazanan.sum()) if kazanan.len() else 0.0
    brut_zarar = abs(float(kaybeden.sum())) if kaybeden.len() else 0.0
    ok = float(kazanan.mean()) if kazanan.len() else nan
    oz = abs(float(kaybeden.mean())) if kaybeden.len() else nan
    odul = ok / oz if oz and oz == oz and oz > 0 else nan

    out.update({
        "kazanan_%": round(100.0 * kazanan.len() / r.len(), 1),
        "kar_faktoru": (round(brut_kar / brut_zarar, 2) if brut_zarar > 0
                        else float("inf")),
        # Her islem ayni buyuklukte: toplam getiri islemlerin toplamidir.
        "getiri_%": round(100.0 * float(r.sum()), 1),
        "ort_islem_bp": round(float(r.mean()) * 10000, 1),
        "ort_R": (round(float(islemler["R"].mean()), 2)
                  if islemler["R"].drop_nulls().len() else nan),
        "ort_kazanc_%": round(100 * ok, 2) if ok == ok else nan,
        "ort_kayip_%": round(100 * oz, 2) if oz == oz else nan,
        "odul_kayip": round(odul, 2) if odul == odul else nan,
        # Basabas icin gereken kazanma orani: 1 / (1 + odul/kayip)
        "basabas_kazanan_%": (round(100.0 / (1.0 + odul), 1)
                              if odul == odul and odul > 0 else nan),
    })

    if gunluk.height >= 2:
        d = gunluk["ret"]
        sd = float(d.std() or 0.0)
        eq = gunluk["equity"]
        tepe = eq.cum_max()
        out["Sharpe"] = (round(float(d.mean()) / sd * math.sqrt(252), 2)
                         if sd > 0 else nan)
        out["MaxDD_%"] = round(100 * float(((eq - tepe) / tepe).min()), 1)

        gun = (gunluk["tday"][-1] - gunluk["tday"][0]).days
        yil = gun / 365.0
        out["yil"] = round(yil, 1)
        if yil > 0:
            son = float(eq[-1])
            if son > 0:
                out["yillik_%"] = round(100 * (son ** (1 / yil) - 1), 1)
            # Sermaye kullanimi: acik pozisyonda gecen varlik-gunu / toplam
            # varlik-gunu. Her islem ayni buyuklukte oldugu icin bu, paranin
            # ne kadarinin ne kadar sure calistigini dogrudan verir.
            #
            # TUZAK: varliklarin gecmisi ayni uzunlukta DEGIL (XAUUSD 23 yil,
            # BTCUSD 9 yil). "n_varlik x havuz suresi" ile bolmek yanlis olur
            # -- islem/yil 2,5 yerine 1,4 cikiyordu. Dogrusu her varligin
            # KENDI suresinin toplami; `kos` bunu `havuz` icinde verir.
            varlik_gun = (havuz or {}).get("varlik_gun")
            n_varlik = (havuz or {}).get("n_varlik")
            if not varlik_gun:
                n_varlik = (islemler["kod"].n_unique()
                            if "kod" in islemler.columns else 1)
                varlik_gun = n_varlik * gun
            if varlik_gun:
                sure = float((islemler["cikis_ts"] - islemler["giris_ts"])
                             .dt.total_seconds().sum()) / 86400.0
                out["piyasada_%"] = round(100 * sure / varlik_gun, 1)
                out["islem_yil"] = round(
                    islemler.height / (varlik_gun / 365.0), 1)
    return out


def bol(sonuc: dict, oran: float = AYAR_ORANI) -> tuple[dict, dict, datetime]:
    """Ayar (ilk %70) ve kontrol (son %30) bolumlerinin olculeri.

    Yeniden simulasyon YOK: tek kosunun islemleri giris zamanina gore
    bolunur (backtest panelindeki asiri uyum kontrolu ile ayni yontem).
    """
    g = sonuc["gunluk"]
    islemler = sonuc["islemler"]
    if islemler.is_empty() or g.height < 4:
        return olcu(islemler, g), olcu(islemler.head(0), g.head(0)), None
    t0, t1 = islemler["giris_ts"].min(), islemler["giris_ts"].max()
    kesim = t0 + (t1 - t0) * oran
    kesim_gun = (kesim + perf.DAY_ROLL).date()
    ayar = olcu(islemler.filter(pl.col("giris_ts") < kesim),
                g.filter(pl.col("tday") < kesim_gun))
    kontrol = olcu(islemler.filter(pl.col("giris_ts") >= kesim),
                   g.filter(pl.col("tday") >= kesim_gun))
    return ayar, kontrol, kesim


# ==========================================================================
# PARAMETRE TARAMASI
# ==========================================================================
def kombinasyonlar(uzay: dict[str, list], en_fazla: int,
                   tohum: int = 7) -> list[dict]:
    """Izgara; cok buyukse rastgele ornek (tohum sabit -> tekrar edilebilir)."""
    adlar = list(uzay)
    hepsi = [dict(zip(adlar, v)) for v in itertools.product(*(uzay[a] for a in adlar))]
    if len(hepsi) <= en_fazla:
        return hepsi
    return random.Random(tohum).sample(hepsi, en_fazla)


def tarama(motor, cfg, bars: dict[str, pl.DataFrame], timeframe: str,
           maliyet: dict[str, float], uzay: dict[str, list], amac: str,
           en_fazla: int = 120, baslangic: datetime | None = None,
           bitis: datetime | None = None, ilerleme=None,
           yardimci: dict[str, pl.DataFrame] | None = None) -> pl.DataFrame:
    """Parametre taramasi. Her satir: parametreler + ayar/kontrol olculeri.

    Hiz: kombinasyonlar GOSTERGE parametrelerine gore gruplanir, her grup
    icin `prepare` bir kez calisir (olculdu: prepare ~1,3 sn / simulate
    ~0,3 sn, 9 varlik 4 saatlik, 11 yil).
    """
    anahtar, buyuk_iyi, _ = AMACLAR[amac]
    combos = kombinasyonlar(uzay, en_fazla)
    gosterge = set(getattr(motor, "GOSTERGE_PARAMLARI", frozenset()))

    def imza(k: dict):
        return tuple(sorted((a, v) for a, v in k.items() if a in gosterge))

    combos.sort(key=lambda k: str(imza(k)))
    satirlar = []
    onceki_imza = object()
    hazir = None
    for n, k in enumerate(combos):
        yeni = replace(cfg, **k)
        if imza(k) != onceki_imza:
            hazir = hazirla(motor, bars, yeni, yardimci)
            onceki_imza = imza(k)
        sonuc = kos(motor, hazir, yeni, timeframe, maliyet, baslangic, bitis)
        ayar, kontrol, _ = bol(sonuc)
        tum = olcu(sonuc["islemler"], sonuc["gunluk"], sonuc.get("havuz"))
        satirlar.append(dict(
            k,
            islem=tum["islem"],
            ayar=_sayi(ayar[anahtar]), kontrol=_sayi(kontrol[anahtar]),
            tum=_sayi(tum[anahtar]),
            kontrol_islem=kontrol["islem"],
            kazanan=tum["kazanan_%"], kar_faktoru=_sayi(tum["kar_faktoru"]),
            yillik=tum["yillik_%"], piyasada=tum["piyasada_%"],
            yilda_islem=tum["islem_yil"],
            getiri=tum["getiri_%"], ort_bp=tum["ort_islem_bp"],
            maxdd=tum["MaxDD_%"]))
        if ilerleme is not None:
            ilerleme((n + 1) / len(combos), k)

    if not satirlar:
        return pl.DataFrame()
    df = pl.DataFrame(satirlar)
    df = df.with_columns(pl.Series("komsu", _komsu_ortalamasi(
        satirlar, list(uzay), uzay)))
    yon = not buyuk_iyi
    df = df.sort(["kontrol", "komsu"], descending=[not yon, not yon],
                 nulls_last=True)
    # Sutun sirasi: once parametreler, sonra KARAR sutunlari (kontrol ve
    # komsu yan yana dursun -- ekranda saga kacinca kimse bakmiyor).
    sira = list(uzay) + ["kontrol", "komsu", "ayar", "tum", "kontrol_islem",
                         "islem", "kazanan", "kar_faktoru", "getiri",
                         "ort_bp", "maxdd"]
    return df.select([s for s in sira if s in df.columns])


def _sayi(v) -> float:
    """inf / NaN tabloyu ve siralamayi bozar; None'a cevrilir."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isinf(f) or f != f else round(f, 3)


def _komsu_ortalamasi(satirlar: list[dict], adlar: list[str],
                      uzay: dict[str, list]) -> list:
    """Bir parametre bir adim saga/sola kaydirilinca AYAR sonucu ne oluyor.

    Yalniz tarananlar arasindan bakilir; komsusu bulunmayan satir icin None.
    Amaci: tek basina parlayan tesadufi noktayi ayiklamak.
    """
    indeks = {tuple(s[a] for a in adlar): s for s in satirlar}
    sirali = {a: list(uzay[a]) for a in adlar}
    out = []
    for s in satirlar:
        degerler = []
        for a in adlar:
            try:
                i = sirali[a].index(s[a])
            except ValueError:
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(sirali[a]):
                    anahtar = tuple(sirali[a][j] if b == a else s[b]
                                    for b in adlar)
                    komsu = indeks.get(anahtar)
                    if komsu is not None and komsu["ayar"] is not None:
                        degerler.append(komsu["ayar"])
        out.append(round(sum(degerler) / len(degerler), 3) if degerler else None)
    return out


# ==========================================================================
# TESHIS -- "zayif nokta nerede"
# ==========================================================================
@dataclass
class Bulgu:
    """Bir zayif nokta ve (varsa) denenecek somut parametre degisikligi."""

    baslik: str
    olcum: str
    oneri: str = ""
    degisiklik: dict = field(default_factory=dict)
    siddet: str = "bilgi"      # "yuksek" | "orta" | "bilgi"


def teshis(motor, cfg, sonuc: dict, timeframe: str) -> list[Bulgu]:
    """Havuzdaki islemlerden zayif noktalari cikarir.

    Her bulgu RAKAMLIDIR ve mumkunse denenecek bir parametre onerir.
    Sirasiz bir "ipucu listesi" degil: siddete gore siralanir.
    """
    islemler = sonuc["islemler"]
    if islemler.height < EN_AZ_ISLEM:
        return [Bulgu("Yeterli islem yok",
                      "{} islem -- guvenilir bir teshis icin en az {} gerekir."
                      .format(islemler.height, EN_AZ_ISLEM),
                      "Donemi uzatin ya da daha fazla varlik secin.")]

    alanlar = {f for f in cfg.__dataclass_fields__}
    bulgular = [_b_kazanma(olcu(islemler, sonuc["gunluk"], sonuc.get("havuz")))]
    bulgular += _b_yon(islemler, alanlar)
    bulgular += _b_nedenler(islemler, cfg, alanlar)
    bulgular += _b_varlik(islemler)
    bulgular += _b_rejim(sonuc, alanlar)
    bulgular += _b_donem(islemler)
    sira = {"yuksek": 0, "orta": 1, "bilgi": 2}
    return sorted([b for b in bulgular if b], key=lambda b: sira[b.siddet])


def _yuzde(v: float, basamak: int = 1) -> str:
    return "%{:.{}f}".format(v, basamak).replace(".", ",")


def _b_kazanma(m: dict) -> Bulgu:
    """Kullanicinin asil sorusu: kazandirma orani neden yetmiyor?"""
    kaz, basabas = m["kazanan_%"], m["basabas_kazanan_%"]
    odul = m["odul_kayip"]
    if basabas != basabas:
        return Bulgu("Kazanma orani", "{} kazanan islem.".format(_yuzde(kaz)))
    fark = kaz - basabas
    olcum = (
        "Kazanan {} · ortalama kazanc {} / ortalama kayip {} "
        "(odul/kayip {:.2f}). Bu odulle BASABAS icin {} kazanma orani "
        "gerekiyor; aradaki fark {}{}.".format(
            _yuzde(kaz), _yuzde(m["ort_kazanc_%"], 2),
            _yuzde(m["ort_kayip_%"], 2), odul, _yuzde(basabas),
            "+" if fark >= 0 else "", _yuzde(fark)))
    if fark >= 0:
        return Bulgu("Kazanma orani basabasin ustunde", olcum,
                     "Kenar burada; asil sorun baska yerde olabilir.",
                     siddet="bilgi")
    return Bulgu(
        "Kazanma orani basabasin ALTINDA", olcum,
        "Iki yol var: (1) kazanma oranini yukseltmek -- daha secici giris, "
        "zayif rejimleri elemek; (2) odulu buyutmek -- kar hedefini "
        "genisletmek ya da zarar kesi daraltmak. Asagidaki bulgular "
        "hangisinin daha ucuz oldugunu gosterir.", siddet="yuksek")


def _b_yon(islemler: pl.DataFrame, alanlar: set) -> list[Bulgu]:
    out = []
    for yon, ad, kapat in ((1, "AL (uzun)", None), (-1, "SAT (kisa)", "allow_short")):
        s = islemler.filter(pl.col("yon") == yon)
        if s.height < EN_AZ_ISLEM:
            continue
        toplam = 100 * float(s["getiri"].sum())
        ort = float(s["getiri"].mean()) * 10000
        if ort >= 0:
            continue
        olcum = "{} islem, toplam {}, islem basina {:.1f} bp.".format(
            s.height, _yuzde(toplam), ort)
        if kapat and kapat in alanlar:
            out.append(Bulgu("{} tarafi zarar ediyor".format(ad), olcum,
                             "Yalniz AL yonunde islem yapmayi deneyin.",
                             {kapat: False}, "yuksek"))
        else:
            out.append(Bulgu("{} tarafi zarar ediyor".format(ad), olcum,
                             "Bu yonu eleyecek bir filtre gerekir.", {}, "orta"))
    return out


def _b_nedenler(islemler: pl.DataFrame, cfg, alanlar: set) -> list[Bulgu]:
    """Hangi cikis kapisi zarar ettiriyor."""
    g = (islemler.group_by("neden").agg(
        pl.len().alias("n"), (pl.col("getiri").mean() * 10000).alias("bp"),
        (pl.col("getiri").sum() * 100).alias("toplam"))
        .sort("toplam"))
    toplam_islem = islemler.height
    out = []
    for satir in g.iter_rows(named=True):
        pay = 100.0 * satir["n"] / toplam_islem
        olcum = "{} islem (islemlerin {}), islem basina {:.1f} bp, toplam {}.".format(
            satir["n"], _yuzde(pay), satir["bp"], _yuzde(satir["toplam"]))
        neden = satir["neden"]
        if satir["toplam"] >= 0 or satir["n"] < EN_AZ_ISLEM:
            continue
        oneri, degisiklik = "", {}
        if neden == "zarar_kes" and "zarar_kes" in alanlar:
            oneri = ("Zarar kes cok sik tetikleniyor olabilir; biraz "
                     "genisletmeyi deneyin (asagidaki tarama bunu olcer).")
            degisiklik = {"zarar_kes": round(cfg.zarar_kes * 1.5, 2)}
        elif neden == "tek_ters" and "tek_ters" in alanlar:
            oneri = ("Tek ters sinyal cikisi erken olabilir; kapatip ikili "
                     "sinyali beklemeyi deneyin.")
            degisiklik = {"tek_ters": False}
        elif neden == "ters_sinyal":
            oneri = "Ters sinyal cikisi gec kaliyor olabilir."
        elif neden == "kar_al" and "kar_al" in alanlar:
            oneri = "Kar hedefi maliyeti karsilamiyor; buyutmeyi deneyin."
            degisiklik = {"kar_al": round(cfg.kar_al * 1.5, 2)}
        out.append(Bulgu("'{}' cikisi zarar yaziyor".format(neden), olcum,
                         oneri, degisiklik, "orta"))
    return out


def _b_varlik(islemler: pl.DataFrame) -> list[Bulgu]:
    if "kod" not in islemler.columns:
        return []
    g = (islemler.group_by("kod").agg(
        pl.len().alias("n"), (pl.col("getiri").sum() * 100).alias("toplam"))
        .filter(pl.col("n") >= EN_AZ_ISLEM).sort("toplam"))
    if g.height < 3:
        return []
    kotu = g.filter(pl.col("toplam") < 0)
    if kotu.is_empty():
        return []
    ad = ", ".join("{} ({})".format(r["kod"], _yuzde(r["toplam"]))
                   for r in kotu.head(3).iter_rows(named=True))
    iyi = g.tail(1).row(0, named=True)
    return [Bulgu(
        "Varliklarin {}'i zarar ediyor".format(
            _yuzde(100 * kotu.height / g.height, 0)),
        "En kotuler: {}. En iyi: {} ({}).".format(
            ad, iyi["kod"], _yuzde(iyi["toplam"])),
        "Strateji her varlikta ayni davranmiyor. Zarar edenleri listeden "
        "cikarip kalanla calismayi deneyin -- ama bu da bir tur gecmise uyum, "
        "kontrol bolumunde de zarar ediyorlar mi bakin.", {}, "orta")]


def _b_rejim(sonuc: dict, alanlar: set) -> list[Bulgu]:
    """Piyasa rejimi: trend yonunde mi, yatayda mi kaybediyor.

    Olcut barlardan turetilir (strateji bilmez): 200 barlik ustel ortalamaya
    uzaklik (trend gucu) ve 50 barlik oynaklik.
    """
    parcalar = []
    for kod, (islemler, bars) in sonuc["varlik"].items():
        if islemler.is_empty() or bars.height < 220:
            continue
        b = bars.with_columns(
            pl.col("close").ewm_mean(span=200, adjust=False).alias("_ema200"),
            pl.col("close").pct_change().rolling_std(50).alias("_oyn"))
        b = b.with_columns(
            ((pl.col("close") / pl.col("_ema200") - 1) * 100).alias("_uzaklik"))
        parcalar.append(islemler.join(
            b.select("ts", "_uzaklik", "_oyn"),
            left_on="giris_ts", right_on="ts", how="left"))
    if not parcalar:
        return []
    d = pl.concat(parcalar, how="vertical_relaxed").drop_nulls(["_uzaklik"])
    if d.height < 4 * EN_AZ_ISLEM:
        return []

    # Trend yonunde mi girildi: uzun islem ortalamanin ustunde acildiysa "uyumlu"
    d = d.with_columns(
        ((pl.col("_uzaklik") * pl.col("yon")) > 0).alias("_uyumlu"))
    g = d.group_by("_uyumlu").agg(pl.len().alias("n"),
                                  (pl.col("getiri").mean() * 10000).alias("bp"))
    out = []
    satirlar = {r["_uyumlu"]: r for r in g.iter_rows(named=True)}
    uyumlu, karsi = satirlar.get(True), satirlar.get(False)
    # Fark ONEMLI olmali: ekranda -6,0 bp ile -6,0 bp'yi "zayif nokta" diye
    # yazmak gurultudur (22.09.2026 denemesinde tam bunu yapti).
    if (uyumlu and karsi and uyumlu["n"] >= EN_AZ_ISLEM
            and karsi["n"] >= EN_AZ_ISLEM
            and uyumlu["bp"] - karsi["bp"] >= ONEMLI_FARK_BP):
        olcum = ("200 barlik ortalamanin trend yonunde acilan {} islem "
                 "{:.1f} bp; tersine acilan {} islem {:.1f} bp.".format(
                     uyumlu["n"], uyumlu["bp"], karsi["n"], karsi["bp"]))
        # Motorda trend filtresi varsa bulgu UYGULANABILIR; yoksa eskisi gibi
        # "eklenmesi gereken yeni bir kural" der (Strateji 1'de durum bu).
        if "trend_filter" in alanlar:
            out.append(Bulgu(
                "Trendin tersine acilan islemler daha kotu", olcum,
                "Trend filtresi bu islemleri eler: yalniz fiyatin 200 barlik "
                "ortalamaya gore bulundugu yonde islem acilir. Elenen "
                "islemlerin bir kismi kazanan olacagi icin islem sayisi "
                "belirgin duser -- kontrol bolumune bakin.",
                {"trend_filter": 200}, "orta"))
        else:
            out.append(Bulgu(
                "Trendin tersine acilan islemler daha kotu", olcum,
                "Bir trend filtresi (islem yonu 200 barlik ortalamayla ayni "
                "olsun) bu islemleri eler. Motorda boyle bir parametre YOK -- "
                "eklenmesi gereken yeni bir kural.", {}, "orta"))

    # Oynaklik dortte birlikleri
    d = d.drop_nulls(["_oyn"]).with_columns(
        pl.col("_oyn").qcut(4, labels=["1 (sakin)", "2", "3", "4 (calkantili)"])
        .alias("_dilim"))
    if d.height >= 4 * EN_AZ_ISLEM:
        q = (d.group_by("_dilim").agg(
            pl.len().alias("n"), (pl.col("getiri").mean() * 10000).alias("bp"))
            .sort("_dilim"))
        en_kotu = q.sort("bp").row(0, named=True)
        en_iyi = q.sort("bp").row(-1, named=True)
        if (en_kotu["bp"] < 0 < en_iyi["bp"]
                and en_iyi["bp"] - en_kotu["bp"] >= ONEMLI_FARK_BP):
            out.append(Bulgu(
                "Oynakliga gore ikiye ayriliyor",
                "En kotu dilim {}: {} islem, {:.1f} bp. En iyi dilim {}: "
                "{} islem, {:.1f} bp.".format(
                    en_kotu["_dilim"], en_kotu["n"], en_kotu["bp"],
                    en_iyi["_dilim"], en_iyi["n"], en_iyi["bp"]),
                "Oynaklik filtresi (50 barlik oynaklik esigi) denenebilir; "
                "bu da motorda olmayan yeni bir kural.", {}, "orta"))
    return out


def _b_donem(islemler: pl.DataFrame) -> list[Bulgu]:
    """Son donem eskisinden kotuyse bu, parametreden cok yapisal bir uyaridir."""
    if islemler.height < 4 * EN_AZ_ISLEM:
        return []
    d = islemler.sort("giris_ts")
    yari = d.height // 2
    ilk = float(d.head(yari)["getiri"].mean()) * 10000
    son = float(d.tail(d.height - yari)["getiri"].mean()) * 10000
    if son >= ilk:
        return []
    return [Bulgu(
        "Son donem eskisinden kotu",
        "Ilk yari {} islem {:.1f} bp; ikinci yari {} islem {:.1f} bp.".format(
            yari, ilk, d.height - yari, son),
        "Parametre aramadan once buna bakin: kenar zamanla kayboluyorsa "
        "gecmise uydurulan ayar da gecmiste kalir.", {}, "orta")]


# ==========================================================================
# KARSILASTIRMA -- "bunu dene"
# ==========================================================================
def karsilastir(motor, cfg, degisiklik: dict, bars: dict[str, pl.DataFrame],
                timeframe: str, maliyet: dict[str, float],
                baslangic: datetime | None = None,
                bitis: datetime | None = None,
                yardimci: dict[str, pl.DataFrame] | None = None) -> dict:
    """Simdiki ayar ile onerilen ayari ayni donemde yan yana kor."""
    yeni = replace(cfg, **degisiklik)
    out = {}
    for ad, c in (("simdiki", cfg), ("onerilen", yeni)):
        hazir = hazirla(motor, bars, c, yardimci)
        sonuc = kos(motor, hazir, c, timeframe, maliyet, baslangic, bitis)
        ayar, kontrol, _ = bol(sonuc)
        out[ad] = {"tum": olcu(sonuc["islemler"], sonuc["gunluk"],
                               sonuc.get("havuz")),
                   "al_tut": sonuc.get("al_tut", {}),
                   "ayar": ayar, "kontrol": kontrol}
    out["cfg"] = yeni
    return out

"""Stratejiler ekrani -- strateji listesi, kayitli varyantlar, canli sinyaller.

DUZEN (kullanici: "ekran cok karisik")
  1. ?ekran=stratejiler                  aciklamali strateji listesi
                                         (temel stratejiler + kayitli varyantlar)
  2. ?ekran=stratejiler&strateji=<key>   secilen stratejinin OZETI
  3. ustteki menu                        Sinyaller, BIST 30, Backtest, Kurallar

BACKTEST bolumu ui/backtest.panel()'i gomer; ana ekrandaki Backtest menusu
de AYNI paneli acar. Kullanici once "backtest'i Backtest menusune koy" dedi,
sonra "Stratejilerde de kalsin / ikisini birlestirelim".

KAYITLI VARYANTLAR: Backtest > Canli parametre ayari > "Farkli kaydet" ile
olusur (finans_cortex/strategy_store.py -> config/stratejiler.json). Varyant
= temel strateji + farkli parametreler; listede temelin altinda "1.1, 1.2"
diye gorunur ve Sinyaller / BIST 30 / Backtest kendi parametreleriyle calisir.

HER STRATEJI KENDI MOTORUYLA GELIR. BASE sozlugundeki her kayit bir
"motor" modulu (finans_cortex/...) ve o motora ait parametre denetimleri,
kurallar, zaman dilimleri ve gorunecek bolumleri tasir. Arayuzde strateji
adi gecen tek yer burasi; backtest paneli de bu kayittan okur. Yeni strateji
eklemek = motor modulu + BASE'e bir kayit + strategy_store.CONFIGS'e bir
satir.

Liste kartlari <a> baglantisidir (ana ekrandaki kutucuklarla ayni gerekce).
Strateji ICINDEKI menu ise st.segmented_control: baglanti sayfayi yeniden
yukler ve kenar cubugundaki ayarlar sifirlanirdi. Secili bolum adres
cubuguna da yazilir (&bolum=) ki yer imi calissin.

Anayasa 2.4: bu dosya SQL yazmaz; hesap tamamen finans_cortex altinda.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from finans_cortex import (bist, ema_two_close as ema,
                          heikin_range as heikin, strategy_store)
from finans_cortex.instruments import INSTRUMENTS

from . import charts, home, theme

TZ = "Europe/Istanbul"

# ekrandaki ad -> adres cubugundaki anahtar. Her strateji bunlarin
# hangilerini gosterecegini kendi kaydinda "bolumler" ile secer.
SECTIONS = {
    "Ozet": "ozet",
    "Sinyaller": "sinyaller",
    "BIST 30": "bist30",
    "Backtest": "backtest",
    "Kurallar": "kurallar",
    "Kural akisi": "akis",
    "Gelistir": "gelistir",
}

TF_15M_1H = {"15 dakika": "15m", "1 saat": "1h"}
TF_SWING = {"4 saat": "4h", "1 gun": "1d", "1 saat": "1h",
            "15 dakika": "15m"}
# Eski cagrilar icin ad: tek strateji varken TIMEFRAMES diye geciyordu.
TIMEFRAMES = TF_15M_1H

RULES_EMA = """
**Videodaki kurallar**
1. Ustel hareketli ortalama: **EMA 10**.
2. EMA'nin **ustunde art arda 2 kapanis -> AL**, **altinda 2 kapanis -> SAT**.
3. Giris: **kirilim** (ikinci kapanista hemen) ya da **geri cekilme**
   (ikinci kapanistan sonra fiyat EMA'ya geri dokununca).
4. Stop: AL'da son dip, SAT'ta son tepe.
5. Hedef: risk/odul 1:2,5 - 1:3.
6. Hedefe gelmeden fiyat EMA'nin ters tarafinda kapatirsa cik.
7. 1R kara gelince stop giris fiyatina cekilir (break even).
8. Gun ici sistem: aksam pozisyon tasinmaz, acilistan sonra ilk 30 dakika
   islem yapilmaz.

**Bizim veriye uyarlama**
- Video BIST30 VIOP'ta 5dk sinyal + 1dk giris kullaniyor. Bizde en kucuk bar
  **15dk**; sinyal ve islem ayni barlarda.
- Takip listesindeki varliklar ~23 saat isleyen CFD'ler. Islem gunu **01:00 TR
  (22:00 UTC)** kesiminde biter. BIST 30'da gun **18:00 TR**'de biter.
- "Son dip/tepe" = son N bardaki en dusuk / en yuksek fiyat.
- Ayni bar icinde hem stop hem hedef gorulurse **stop** sayilir (kotumser).
"""

RULES_CE_ONLY = """
**Kurallar**
1. Grafik **Heikin Ashi** mumuna cevrilir; gosterge bu mumlar uzerinde calisir.
2. **Tek gosterge: Chandelier Exit** -- periyot **1**, carpan **1,8**,
   "Use Close Price for Extremums" acik (Strateji 2 ile ayni varsayilanlar).
3. **Giris:** Chandelier yon degistirdigi barin kapanisinda, donen yonde.
   Onaylayacak ikinci gosterge YOKTUR.
4. **Cikis:** Chandelier ters yone dondugunde. Yani sistem surekli
   piyasadadir ve her donuste yon degistirir (al-sat / sat-al).

**Strateji 2'den farki**
Strateji 2 iki gosterge (Chandelier + Range Filter) ayni yonde ve yakin
barlarda yanmasini sart kosar; Range Filter bir **filtre** gorevi gorur ve
sinyallerin bir kismini eler. Burada o filtre **hic yoktur** -- kullanicinin
sorusu buydu: *"Range Filter'i kaldirsak ne olur?"* Beklenen: cok daha fazla
islem, daha fazla yanlis sinyal; karsiliginda hicbir donus kacmaz.
Tolerans, bekleyen sinyal ve "tek gosterge sayilmaz" kurali burada anlamsizdir.

**Bizim veriye uyarlama** (Strateji 2 ile ayni)
- **Sinyal Heikin Ashi'den, islem GERCEK fiyattan.** Heikin Ashi kapanisi bir
  ortalamadir, o fiyattan islem yapilamaz.
- Karar barin **kapanisinda** verilir, islem ayni kapanistan yapilir.
- Kar al / zarar kes / trend filtresi / 15 dakikalik teyit burada da
  **secenektir**, varsayilanlari kapali.
"""


RULES_HEIKIN = """
**Videodaki kurallar**
1. Grafik **Heikin Ashi** mumuna cevrilir; iki gosterge de bu mumlar
   uzerinde calisir. Video **4 saatlik** ve gunluk grafigi oneriyor.
2. Gosterge 1: **Chandelier Exit** -- videoda periyot **1**, carpan **1,8**,
   "Use Close Price for Extremums" acik.
3. Gosterge 2: **Range Filter Buy and Sell** -- ayarlari degistirilmiyor:
   ornekleme **100**, carpan **3,0**.
4. **Giris:** iki gosterge **ayni yonde** ve **birbirine yakin** barlarda
   sinyal verirse. Video: ayni anda ya da 1-2 bar sonra cok iyi, **3 bara
   kadar** kabul; 4-5 bar arayla yananlar sayilmaz. Tek basina sinyal veren
   gosterge dikkate ALINMAZ.
5. **Cikis:** ters yonde ayni ikili sinyal. Video ayrica iki sey soyluyor:
   uzun fitilli / ince govdeli mum trend donusu uyarisidir ("ilk gelen
   fitilli mumda cikilabilir") ve "stop yukseltilerek ilerlenebilir".
   Ikisi de burada **secenek**, varsayilani kapali.

**Bizim veriye uyarlama**
- **Sinyal Heikin Ashi'den, islem GERCEK fiyattan.** Heikin Ashi fiyati bir
  ortalamadir, o fiyattan alim satim yapilamaz; giris/cikis her zaman barin
  gercek kapanisidir. TradingView'de Heikin Ashi grafiginde alinan
  backtestlerin sisirilmis cikmasinin sebebi tam olarak budur.
- Karar barin **kapanisinda** verilir, islem ayni kapanistan yapilir.
- 4 saatlik kovalar **00/04/08/12/16/20 UTC** hizalidir. Broker'in 4H bari
  baska hizalanmissa sinyaller de farkli cikar.
- "Uzun fitilli mum" goz karariyla tarif ediliyordu; burada olculur hale
  getirildi: **govde / (yuksek-dusuk)** orani esigin altindaysa fitilli mum.
- Pozisyon gece de tasinir (gun ici degil). Bu yuzden **BIST 30** bolumu
  yok: Yahoo'nun saatlik BIST gecmisi ~1 ay, Range Filter'in 100'luk
  ornekleme penceresi icin yetersiz.
"""

# ==========================================================================
# TEMEL STRATEJILER
# ==========================================================================
# Her kayit kendi MOTORUNU (finans_cortex modulu) ve o motorun arayuz
# parcalarini tasir:
#   motor        run / run_bars / signal_state / recent_state / metrics ...
#   cfg          varsayilan parametreler (videodaki degerler)
#   zamanlar     bu strateji icin anlamli zaman dilimleri
#   bolumler     ust menude gorunecek bolumler
#   egriler      backtest grafigine cizilecek (sutun, ad, renk) cizgileri
#   isaretler    grafikte mumun altina/ustune konacak GOSTERGE sinyalleri
#                (sutun +1/-1 tasir); "hangi gosterge ne zaman yandi"
# Parametre denetimleri ve etiketleri asagida, motor bazinda tanimli.
# Kayitli varyantlar strategy_store'dan eklenir; motorlari temelinkidir.
BASE = {
    "ema10": dict(
        no="1", ad="EMA 10 iki kapanis",
        kaynak="Kaynak: Sidar Demirgil · YouTube · VIOP scalping sistemi",
        video="https://www.youtube.com/watch?v=iNuqAD5ngro",
        video_ad="En Cok Kazandiran VIOP Scalping Sistemim",
        aciklama=("Fiyat 10'luk ustel ortalamanin ustunde art arda 2 kez "
                  "kapatirsa AL, altinda 2 kez kapatirsa SAT. Stop son "
                  "dip/tepeye, hedef 1:3 risk/odul, 1R karda stop girise "
                  "cekilir. Gun ici: aksam pozisyon tasinmaz."),
        etiketler=("Gun ici", "Trend takip", "15dk / 1 saat"),
        renk="violet", motor=ema, cfg=ema.EmaConfig(), timeframe="15m",
        zamanlar=TF_15M_1H,
        bolumler=("Ozet", "Sinyaller", "BIST 30", "Backtest", "Kurallar",
                  "Kural akisi", "Gelistir"),
        kurallar=RULES_EMA,
        egriler=(("ema", "EMA", "yellow"),),
        isaretler=(("kurulum", "EMA kurulumu", "magenta"),),
        gun_notu="Takip listesinde gun **01:00 TR**'de (22:00 UTC) biter.",
        efsane=("△ / ▽ bekliyor = geri cekilme girisinde fiyatin "
                "EMA'ya donmesi bekleniyor. (BE) = stop giris fiyatina "
                "cekildi. Son kurulum = en son AL/SAT kosulunun olustugu an."),
    ),
    "heikin_range": dict(
        no="2", ad="Heikin Ashi ikili sinyal",
        kaynak=("Kaynak: Kripton Gezegeni · YouTube · "
                "Chandelier Exit + Range Filter"),
        video="https://www.youtube.com/watch?v=dkX7PkoBzok",
        video_ad="Ihtiyaciniz olan TEK Heikin Ashi Al-Sat Stratejisi",
        aciklama=("Heikin Ashi mumlarinda iki gosterge -- Chandelier Exit ve "
                  "Range Filter -- ayni yonde ve birbirine yakin barlarda "
                  "sinyal verirse girilir; tek basina sinyal veren gosterge "
                  "sayilmaz. Cikis ters yondeki ikili sinyalde. 4 saatlik ve "
                  "gunluk barlar icin; pozisyon gece de tasinir."),
        etiketler=("Swing", "Trend donusu", "4 saat / gunluk"),
        renk="aqua", motor=heikin, cfg=heikin.HeikinConfig(), timeframe="4h",
        zamanlar=TF_SWING,
        bolumler=("Ozet", "Sinyaller", "Backtest", "Kurallar", "Kural akisi",
                  "Gelistir"),
        kurallar=RULES_HEIKIN,
        egriler=(("filt", "Range filtresi", "yellow"),
                 ("ha_close", "Heikin Ashi kapanis", "blue")),
        isaretler=(("ce_sig", "Chandelier", "orange"),
                   ("rf_sig", "Range Filter", "magenta")),
        gun_notu=("Pozisyon gun sonunda kapanmaz; cikis ters ikili sinyalde "
                  "(ya da acik birakilan cikis seceneklerinde)."),
        efsane=("△ / ▽ bekliyor = bir gosterge sinyal verdi, "
                "digerinin tolerans penceresi icinde onaylamasi bekleniyor. "
                "Son kurulum = en son ikili sinyalin olustugu an."),
    ),
    # Kullanici (23.09.2026): *"Strateji 2'yi kopyalayip Strateji 3 yapalim,
    # icinde Range Filter hic olmasin."* Ayni motor, `rf_kullan=False`.
    "chandelier_ha": dict(
        no="3", ad="Chandelier Exit tek basina",
        kaynak="Strateji 2'nin Range Filter'siz hali · kullanici denemesi",
        aciklama=("Heikin Ashi mumlarinda YALNIZ Chandelier Exit. Gosterge yon "
                  "degistirdiginde girilir, ters yone dondugunde cikilir; "
                  "onaylayacak ikinci gosterge yoktur. Strateji 2'deki Range "
                  "Filter filtresinin ne kadar ise yaradigini olcmek icin."),
        etiketler=("Tek gosterge", "Surekli piyasada", "4 saat / gunluk"),
        renk="orange", motor=heikin,
        cfg=heikin.HeikinConfig(rf_kullan=False), timeframe="4h",
        zamanlar=TF_SWING,
        bolumler=("Ozet", "Sinyaller", "Backtest", "Kurallar", "Kural akisi",
                  "Gelistir"),
        kurallar=RULES_CE_ONLY,
        egriler=(("ha_close", "Heikin Ashi kapanis", "blue"),),
        isaretler=(("ce_sig", "Chandelier", "orange"),),
        gun_notu=("Pozisyon gun sonunda kapanmaz; cikis ters yondeki "
                  "Chandelier sinyalidir."),
        efsane=("Bu stratejide 'bekleyen sinyal' yoktur: onaylanacak ikinci "
                "gosterge olmadigi icin sinyal olustugu anda islem acilir."),
    ),
}

# Parametre etiketleri (fark metni ve parametre tablosu) ve widget anahtar
# ekleri (sifirlama dugmesi bunlari siler), motor bazinda.
PARAM_LABELS_EMA = (
    ("entry", "Giris"), ("ema_period", "EMA"), ("confirm_bars", "Onay kapanisi"),
    ("rr_target", "Hedef"), ("swing_lookback", "Stop penceresi"),
    ("breakeven_r", "Break even"), ("exit_on_ema", "EMA cikisi"),
    ("intraday", "Gun ici"),
)
PARAM_KEYS_EMA = ("_giris", "_ema", "_onay", "_rr", "_pencere", "_be",
                  "_emacikis", "_gunici")

PARAM_LABELS_HEIKIN = (
    ("heikin", "Heikin Ashi"), ("ce_period", "Chandelier periyot"),
    ("ce_mult", "Chandelier carpan"), ("ce_use_close", "Kapanistan tepe/dip"),
    ("rf_period", "Range ornekleme"), ("rf_mult", "Range carpan"),
    ("tolerance", "Tolerans"), ("allow_short", "SAT islemleri"),
    ("exit_chandelier", "Chandelier cikisi"), ("doji_exit", "Fitilli mum cikisi"),
    ("doji_body", "Fitil esigi"), ("tek_ters", "Tek ters sinyalde cik"),
    ("kar_al", "Kar al %"), ("zarar_kes", "Zarar kes %"),
    ("trend_filter", "Trend filtresi"),
    ("onay_15m", "15dk Chandelier teyidi"),
)
PARAM_KEYS_HEIKIN = ("_ha", "_ceper", "_cemult", "_ceclose", "_rfper",
                     "_rfmult", "_tol", "_short", "_cecikis", "_doji",
                     "_dojiesik", "_tekters", "_karal", "_zararkes", "_trend", "_onay15")

# Eski cagrilar icin adlar.
PARAM_LABELS = PARAM_LABELS_EMA
PARAM_KEYS = PARAM_KEYS_EMA
RULES_MD = RULES_EMA


def param_labels(temel: str) -> tuple:
    return (PARAM_LABELS_HEIKIN if temel in ("heikin_range", "chandelier_ha")
            else PARAM_LABELS_EMA)


def param_keys(temel: str) -> tuple:
    return PARAM_KEYS_HEIKIN if temel == "heikin_range" else PARAM_KEYS_EMA


def motor(temel: str):
    """Temel stratejinin hesap modulu. Varyantlar temelininkini kullanir."""
    return BASE[temel]["motor"]


_LIST_CSS = """
<style>
 .dc-back {{font-size:13px; color:{dim} !important; text-decoration:none !important;}}
 .dc-back:hover {{color:{ink} !important;}}
 .dc-h2 {{font-size:26px; font-weight:250; letter-spacing:.14em; color:{ink};
          text-transform:uppercase; margin:16px 0 4px 0;}}
 .dc-lead {{font-size:13px; color:{dim}; margin:0 0 22px 0; line-height:1.6;}}
 .dc-strat {{
    display:flex; gap:20px; align-items:flex-start;
    background:{panel}; border:1px solid var(--c-dim); border-radius:14px;
    padding:22px 24px; margin-bottom:14px;
    transition: transform .16s ease, box-shadow .16s ease,
                border-color .16s ease, background .16s ease;
 }}
 .dc-strat.sub {{margin-left:44px; padding:16px 22px;}}
 .dc-strat, .dc-strat:hover, .dc-strat * {{text-decoration:none !important;}}
 .dc-strat:hover {{
    transform:translateY(-2px); border-color:var(--c); background:{panel_hi};
    box-shadow:0 0 24px var(--c-glow);
 }}
 .dc-strat .no {{
    flex:0 0 44px; height:44px; border-radius:50%; border:1px solid var(--c);
    color:var(--c) !important; display:flex; align-items:center;
    justify-content:center; font-size:16px; box-shadow:0 0 12px var(--c-glow);
 }}
 .dc-strat .body {{flex:1; display:flex; flex-direction:column; gap:7px; min-width:0;}}
 .dc-strat .ttl {{font-size:18px; color:{ink} !important; font-weight:500;}}
 .dc-strat.sub .ttl {{font-size:16px;}}
 .dc-strat .src {{font-size:11.5px; color:{dim} !important; letter-spacing:.03em;}}
 .dc-strat .dsc {{font-size:13.5px; color:#cfcfd4 !important; line-height:1.6;}}
 .dc-strat .tags {{display:flex; flex-wrap:wrap; gap:6px; margin-top:2px;}}
 .dc-strat .tags span {{
    font-size:10.5px; letter-spacing:.08em; text-transform:uppercase;
    color:var(--c) !important; border:1px solid var(--c-dim);
    border-radius:20px; padding:2px 9px;
 }}
 .dc-strat .alt {{font-size:12px; color:{dim} !important; margin-top:2px;}}
 .dc-strat .go {{flex:0 0 auto; align-self:center; font-size:13px; color:var(--c) !important;}}
 @media (max-width: 640px) {{
    .dc-strat {{flex-wrap:wrap;}}
    .dc-strat.sub {{margin-left:16px;}}
    .dc-strat .go {{display:none;}}
 }}
</style>
"""


# ==========================================================================
# STRATEJI KAYIT DEFTERI (temel + kayitli varyantlar)
# ==========================================================================
def param_text(field: str, value) -> str:
    """Bir parametrenin ekranda gorunen hali. Alan adlari motorlar arasinda
    cakismadigi icin tek fonksiyon yetiyor."""
    if field == "entry":
        return "kirilim" if value == "kirilim" else "geri cekilme"
    if field == "rr_target":
        return "1:{:g}".format(value).replace(".", ",") if value > 0 else "yok"
    if field == "breakeven_r":
        return "1R" if value > 0 else "kapali"
    if isinstance(value, bool):
        return "acik" if value else "kapali"
    if field == "tolerance":
        return "{} bar".format(value)
    if field == "trend_filter":
        return "{} bar".format(value) if value else "kapali"
    if isinstance(value, float):
        return "{:g}".format(value).replace(".", ",")
    return str(value)


def diff_text(cfg, base, temel: str = "ema10") -> str:
    """Temelden farkli parametreler, orn. 'EMA 14 · Hedef 1:2'."""
    return " · ".join(
        "{} {}".format(label, param_text(f, getattr(cfg, f)))
        for f, label in param_labels(temel) if getattr(cfg, f) != getattr(base, f))


def all_strategies() -> list[dict]:
    """Temel stratejiler + kayitli varyantlar, listede gorunecek sirayla.

    Dosya her cagrida okunur: birkac KB, onbellege gerek yok -- baska bir
    sekmede kaydedilen varyant da hemen gorunsun.
    """
    try:
        saved = strategy_store.load()
    except ValueError as exc:
        st.error("Kayitli stratejiler okunamadi: {}".format(exc))
        saved = []

    out = []
    for key, b in BASE.items():
        out.append(dict(b, key=key, temel=key, kayitli=False, fark="", meta={}))
        for v in sorted((s for s in saved if s.get("temel") == key),
                        key=lambda s: s.get("no", 0)):
            cfg = strategy_store.to_config(v)
            out.append(dict(
                b, key=v["key"], temel=key, kayitli=True,
                no="{}.{}".format(b["no"], v.get("no", 0)), ad=v["ad"],
                kaynak="{} tabanli · kayit {}".format(
                    b["ad"], _date_tr(v.get("olusturma", ""))),
                aciklama=v.get("not") or b["aciklama"],
                etiketler=b["etiketler"], renk="aqua", cfg=cfg,
                timeframe=v.get("zaman_dilimi", b["timeframe"]),
                fark=diff_text(cfg, b["cfg"], key), meta=v.get("meta") or {},
            ))
    return out


def get_strategy(key: str) -> dict | None:
    return next((s for s in all_strategies() if s["key"] == key), None)


def label(strat: dict) -> str:
    return "{} · {}".format(strat["no"], strat["ad"])


def timeframes(strat: dict) -> dict:
    """Stratejinin anlamli zaman dilimleri (ekrandaki ad -> kod)."""
    return strat.get("zamanlar") or TF_15M_1H


def tf_index(strat: dict) -> int:
    values = list(timeframes(strat).values())
    return values.index(strat["timeframe"]) if strat["timeframe"] in values else 0


def sections(strat: dict) -> list[str]:
    """Ust menude gorunecek bolumler."""
    return [s for s in SECTIONS if s in (strat.get("bolumler") or tuple(SECTIONS))]


def _date_tr(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(ZoneInfo(TZ)).strftime("%d.%m.%Y")
    except ValueError:
        return iso[:10]


# ==========================================================================
# YONLENDIRME
# ==========================================================================
def render() -> None:
    strat = get_strategy(st.query_params.get("strateji", ""))
    if strat is None:
        _list_view()
    else:
        _strategy_page(strat)


def _card(s: dict) -> str:
    c = theme.ACCENTS[s["renk"]]
    esc = html.escape
    if s["kayitli"]:
        alt = "Degisen: " + (s["fark"] or "parametreler temel ile ayni")
        m = s["meta"]
        if m.get("aralik"):
            alt += " · kayit aninda {} {} {}: getiri {}, {} islem".format(
                m.get("enstruman", ""), m.get("zaman_dilimi", ""), m["aralik"],
                pct(m["getiri_%"] if m.get("getiri_%") is not None else float("nan")),
                m.get("islem", "-"))
    else:
        alt = ("Canli sinyal: takip listesi (9 varlik){} · Backtest ve "
               "canli parametre ayari".format(
                   " + BIST 30" if "BIST 30" in (s.get("bolumler") or ()) else ""))
    return (
        '<a class="dc-strat{sub}" href="?ekran=stratejiler&strateji={key}" '
        'target="_self" style="--c:{c};--c-dim:{cdim};--c-glow:{cglow}">'
        '<span class="no">{no}</span>'
        '<span class="body">'
        '<span class="ttl">{ad}</span>'
        '<span class="src">{kaynak}</span>'
        '<span class="dsc">{aciklama}</span>'
        '{tags}'
        '<span class="alt">{alt}</span>'
        '</span>'
        '<span class="go">Ac →</span>'
        '</a>'.format(
            sub=" sub" if s["kayitli"] else "", key=esc(s["key"]), c=c,
            cdim=theme.rgba(c, 0.30), cglow=theme.rgba(c, 0.30),
            no=esc(s["no"]), ad=esc(s["ad"]), kaynak=esc(s["kaynak"]),
            aciklama=esc(s["aciklama"]), alt=esc(alt),
            tags="" if s["kayitli"] else '<span class="tags">{}</span>'.format(
                "".join("<span>{}</span>".format(esc(t)) for t in s["etiketler"])),
        )
    )


def _list_view() -> None:
    st.markdown(theme.css() + _LIST_CSS.format(
        dim=theme.INK_DIM, ink=theme.INK, panel=theme.PANEL,
        panel_hi=theme.PANEL_HI), unsafe_allow_html=True)
    st.markdown(
        '<a class="dc-back" href="?ekran=home" target="_self">← Ana ekran</a>'
        '<div class="dc-h2">Stratejiler</div>'
        '<p class="dc-lead">Bir stratejiye tiklayin: once ozeti gelir. '
        "Guncel sinyaller, BIST 30, backtest ve kurallar ustteki menuden "
        "acilir. Kayitli stratejiler temelin altinda listelenir; yenisini "
        "<b>Backtest &gt; Canli parametre ayari &gt; Farkli kaydet</b> ile "
        "olusturun.</p>" + "".join(_card(s) for s in all_strategies()),
        unsafe_allow_html=True,
    )


# ==========================================================================
# STRATEJI SAYFASI
# ==========================================================================
# Onbellek anahtari icin motor DEGIL temel anahtari (str) geciyor: modul
# nesnesi hash'lenemez, config nesnesi (frozen dataclass) hash'lenebilir.
@st.cache_data(ttl=120, show_spinner=False)
def _signals(temel: str, timeframe: str, cfg) -> list[dict]:
    now = datetime.now(timezone.utc)
    con = charts.get_connection()
    m = motor(temel)
    return _sorted([
        _state_row(i.code, m.recent_state(con, i.code, timeframe, cfg, now))
        for i in INSTRUMENTS if i.hesapta
    ])


@st.cache_data(ttl=300, show_spinner=False)
def _bist_signals(temel: str, timeframe: str, cfg):
    now = datetime.now(timezone.utc)
    m = motor(temel)
    data, failed = bist.fetch(timeframe, now=now)
    rows = []
    for code in bist.BIST30:
        df = data.get(code)
        state = None
        if df is not None:
            state = m.signal_state(df, cfg, timeframe,
                                   bist.day_over(df["ts"][-1], now))
        rows.append(_state_row(code, state))
    return _sorted(rows), failed, now


def keep_section(key: str, fallback: str) -> None:
    """Secili menu ogesine tekrar tiklanirsa Streamlit secimi bosaltir; geri al."""
    if st.session_state.get(key) is None:
        st.session_state[key] = st.session_state.get("_son_" + key, fallback)


def param_widgets(
    strat_or_cfg=None,
    defaults=None,
    key: str = "p",
    caption: str = "Varsayilanlar videodaki degerler",
    sliders: bool = False,
):
    """Strateji parametre denetimleri. Cagiran taraf bir kap icine koyar.

    Stratejiler, Backtest ve Canli ayar ekranlari ayni denetimleri kullanir --
    ayni strateji her yerde ayni sekilde tanimlansin diye tek yerde.
    Ilk deger strateji kaydi (dict) ya da dogrudan bir config nesnesi
    olabilir; denetimler stratejinin motoruna gore secilir.
    `key` her strateji/ekran icin farkli olmali (widget durumu karismasin).
    `sliders=True`: tamsayi parametreler kaydirici (canli ayar icin).
    """
    if isinstance(strat_or_cfg, dict):
        temel = strat_or_cfg["temel"]
        defaults = defaults if defaults is not None else strat_or_cfg["cfg"]
    else:
        defaults = defaults if defaults is not None else strat_or_cfg
        temel = ("heikin_range" if isinstance(defaults, heikin.HeikinConfig)
                 else "ema10")
    if defaults is None:
        defaults = BASE[temel]["cfg"]
    if caption:
        st.caption(caption)
    if temel in ("heikin_range", "chandelier_ha"):
        return _heikin_widgets(defaults, key, sliders)
    return _ema_widgets(defaults, key, sliders)


def _ema_widgets(
    defaults: ema.EmaConfig, key: str, sliders: bool
) -> ema.EmaConfig:
    """Strateji 1 denetimleri. Varsayilanlar videodaki degerler."""
    entry_label = st.radio(
        "Giris turu", ["Kirilim", "Geri cekilme"],
        index=0 if defaults.entry == "kirilim" else 1, horizontal=True,
        key=key + "_giris",
        help="Kirilim: ikinci kapanista hemen gir. Geri cekilme: ikinci "
             "kapanistan sonra fiyat EMA'ya geri dokununca gir.")
    num = st.slider if sliders else st.number_input
    ema_period = num("EMA periyodu", 3, 50, defaults.ema_period, step=1,
                     key=key + "_ema")
    confirm = num("Onay kapanisi (bar)", 1, 5, defaults.confirm_bars, step=1,
                  key=key + "_onay")
    rr = st.slider("Risk/odul hedefi (1:x)", 0.0, 5.0, float(defaults.rr_target),
                   0.5, key=key + "_rr",
                   help="0 = sabit hedef yok; cikis EMA kapanisina kalir.")
    lookback = num("Son dip/tepe penceresi (bar)", 3, 40, defaults.swing_lookback,
                   step=1, key=key + "_pencere",
                   help="Stop, son bu kadar bardaki en dusuk (AL) / en yuksek "
                        "(SAT) fiyata konur.")
    breakeven = st.checkbox("1R karda stopu girise cek", defaults.breakeven_r > 0,
                            key=key + "_be")
    exit_ema = st.checkbox("EMA'nin ters tarafinda kapanista cik",
                           defaults.exit_on_ema, key=key + "_emacikis")
    intraday = st.checkbox("Gun ici: aksam pozisyon tasima", defaults.intraday,
                           key=key + "_gunici")
    return ema.EmaConfig(
        ema_period=int(ema_period), confirm_bars=int(confirm),
        entry="kirilim" if entry_label == "Kirilim" else "geri_cekilme",
        rr_target=float(rr), swing_lookback=int(lookback),
        breakeven_r=1.0 if breakeven else 0.0,
        exit_on_ema=exit_ema, intraday=intraday,
    )


def _heikin_widgets(
    defaults: heikin.HeikinConfig, key: str, sliders: bool
) -> heikin.HeikinConfig:
    """Strateji 2 denetimleri. Videodaki degerler varsayilan."""
    num = st.slider if sliders else st.number_input
    ha = st.checkbox("Heikin Ashi barlari", defaults.heikin, key=key + "_ha",
                     help="Kapali: gostergeler gercek mumlardan hesaplanir. "
                          "Islem fiyati her iki durumda da gercek kapanistir.")
    st.markdown("**Chandelier Exit**")
    ce_period = num("ATR periyodu", 1, 50, defaults.ce_period, step=1,
                    key=key + "_ceper")
    ce_mult = st.slider("ATR carpani", 0.5, 5.0, float(defaults.ce_mult), 0.1,
                        key=key + "_cemult")
    ce_close = st.checkbox("Tepe/dip kapanistan (fitiller sayilmaz)",
                           defaults.ce_use_close, key=key + "_ceclose",
                           help="TradingView'deki 'Use Close Price for "
                                "Extremums' secenegi; videoda acik.")
    # Strateji 3'te Range Filter HIC yok: denetimleri de cizilmez, yoksa
    # "kapattim ama bir sey degismedi" yanilgisi olur. Degerler kayitta
    # varsayilan olarak durur, giriste kullanilmaz.
    if defaults.rf_kullan:
        st.markdown("**Range Filter**")
        rf_period = num("Ornekleme periyodu", 5, 300, defaults.rf_period, step=5,
                        key=key + "_rfper")
        rf_mult = st.slider("Menzil carpani", 0.5, 8.0, float(defaults.rf_mult),
                            0.1, key=key + "_rfmult")
        st.markdown("**Birlestirme ve cikis**")
        tol = num("Tolerans (bar)", 0, 8, defaults.tolerance, step=1,
                  key=key + "_tol",
                  help="Iki gostergenin sinyali arasinda en fazla kac bar "
                       "olabilir. 0 = ayni bar. Videoda 3'e kadar kabul.")
    else:
        rf_period, rf_mult, tol = (defaults.rf_period, defaults.rf_mult,
                                   defaults.tolerance)
        st.caption("Range Filter bu stratejide yok; giris yalniz Chandelier.")
        st.markdown("**Cikis**")
    short = st.checkbox("SAT (short) islemleri", defaults.allow_short,
                        key=key + "_short",
                        help="Kapali: yalnizca AL yonunde islem acilir, ters "
                             "sinyal cikis olur.")
    ce_exit = st.checkbox("Chandelier yonu donunce cik", defaults.exit_chandelier,
                          key=key + "_cecikis",
                          help="Takip eden stop gibi calisir: ikinci gosterge "
                               "onaylamasa da pozisyondan cikar.")
    doji = st.checkbox("Fitilli mumda cik", defaults.doji_exit,
                       key=key + "_doji",
                       help="Uzun fitilli / ince govdeli Heikin Ashi mumu "
                            "trend donusu uyarisidir (videodaki 'doji').")
    body = st.slider("Fitil esigi (govde / menzil)", 0.05, 0.60,
                     float(defaults.doji_body), 0.05, key=key + "_dojiesik",
                     help="Govde, barin tamamina bu orandan kucukse fitilli "
                          "mum sayilir.")
    onay15 = st.checkbox("15 dakikalik Chandelier teyidi", defaults.onay_15m,
                         key=key + "_onay15",
                         help="Acikken ikili sinyal olustugu anda 15 dakikalik "
                              "grafikteki Chandelier yonu de ayni olmali; "
                              "degilse islem acilmaz. Barin kapandigi anda "
                              "kapanmis son 15 dakikalik bar kullanilir.")
    st.markdown("**Trend filtresi**")
    trend = num("Trend ortalamasi (bar)", 0, 400, int(defaults.trend_filter),
                step=50, key=key + "_trend",
                help="0 = kapali. Acikken yalniz fiyatin ortalamaya gore "
                     "bulundugu yonde islem acilir: fiyat ortalamanin "
                     "ustundeyse AL, altindaysa SAT. Trende ters sinyaller "
                     "elenir -- islem sayisi belirgin duser.")
    st.markdown("**Kar al / zarar kes** (Strateji 2.1)")
    tek = st.checkbox("TEK ters sinyalde cik", defaults.tek_ters,
                      key=key + "_tekters",
                      help="CE ya da RF'den biri ters yonde yanarsa bar "
                           "kapanisinda cikar; ikincisinin onayi beklenmez.")
    kar = st.number_input("Kar al (%)", 0.0, 20.0, float(defaults.kar_al),
                          0.5, key=key + "_karal",
                          help="0 = kapali. Fiyat girisin bu kadar otesine "
                               "degerse o seviyeden satar.")
    zarar = st.number_input("Zarar kes (%)", 0.0, 20.0,
                            float(defaults.zarar_kes), 0.5,
                            key=key + "_zararkes",
                            help="0 = kapali (stop Chandelier cizgisi olur, "
                                 "yalniz bilgi amacli). Ayni barda hem kar "
                                 "hem zarar gorulurse ZARAR sayilir.")
    return heikin.HeikinConfig(
        heikin=ha, ce_period=int(ce_period), ce_mult=float(ce_mult),
        ce_use_close=ce_close, rf_period=int(rf_period), rf_mult=float(rf_mult),
        tolerance=int(tol), allow_short=short, exit_chandelier=ce_exit,
        doji_exit=doji, doji_body=float(body), kar_al=float(kar),
        zarar_kes=float(zarar), tek_ters=tek, trend_filter=int(trend), onay_15m=onay15,
        rf_kullan=defaults.rf_kullan)


def _strategy_page(strat: dict) -> None:
    key = strat["key"]
    st.sidebar.markdown("[← Strateji listesi](?ekran=stratejiler)  \n"
                        "[← Ana ekran](?ekran=home)")
    st.sidebar.title(strat["ad"])
    tfs = timeframes(strat)
    tf_label = st.sidebar.selectbox(
        "Zaman dilimi", list(tfs), index=tf_index(strat), key="tf_" + key,
        help="Sinyaller ve backtest bu bar boyutunda hesaplanir.")
    timeframe = tfs[tf_label]
    with st.sidebar.expander("Strateji parametreleri"):
        cfg = param_widgets(strat, key="p_" + key,
                            caption=("Kayitli degerler" if strat["kayitli"]
                                     else "Varsayilanlar videodaki degerler"))
    if strat["kayitli"]:
        with st.sidebar.expander("Stratejiyi yonet"):
            _manage(strat)

    base = BASE[strat["temel"]]
    # Kaynak / varyant satiri artik yalnizca Ozet ve Kurallar'da (kullanici
    # 21.09.2026: "ekranin ustu cok kalabalik").
    if strat["kayitli"]:
        kaynak = "{} tabanli · Degisen: {}".format(
            base["ad"], strat["fark"] or "yok")
    elif base.get("video"):
        kaynak = "{} -- [{}]({})".format(
            base["kaynak"].split(" · ")[0],
            base.get("video_ad") or "video", base["video"])
    else:
        # Kaynak videosu olmayan strateji (orn. Strateji 3, kullanici
        # denemesi). Baglanti satiri yerine yalniz kaynak yazisi.
        kaynak = base["kaynak"]

    names = sections(strat)
    # Bolum secimi oturumda tutulur; baska bir stratejide olmayan bir bolum
    # secili kalmissa (orn. BIST 30 -> Strateji 2) Ozet'e duser.
    if "bolum" not in st.session_state or st.session_state["bolum"] not in names:
        wanted = st.query_params.get("bolum", "ozet")
        st.session_state["bolum"] = next(
            (name for name, k in SECTIONS.items() if k == wanted and name in names),
            "Ozet")
    # Baslik ve bolum menusu AYNI satirda: sayfanin ustu tek satir.
    bas, menu = st.columns([1, 1.9], vertical_alignment="center")
    bas.markdown('<div class="dc-sbaslik"><span class="no">{}</span>{}</div>'
                 .format(html.escape(strat["no"]), html.escape(strat["ad"])),
                 unsafe_allow_html=True)
    sel = menu.segmented_control("Bolum", names, key="bolum",
                                 on_change=keep_section, args=("bolum", "Ozet"),
                                 label_visibility="collapsed")
    sel = sel or st.session_state.get("_son_bolum", "Ozet")
    st.session_state["_son_bolum"] = sel
    st.query_params["bolum"] = SECTIONS[sel]

    if sel == "Ozet":
        st.caption(kaynak)
        _section_summary(strat, timeframe, tf_label, cfg)
    elif sel == "Sinyaller":
        _section_signals(strat, timeframe, tf_label, cfg)
    elif sel == "BIST 30":
        _section_bist(strat, timeframe, tf_label, cfg)
    elif sel == "Backtest":
        # Gec import: backtest.py bu modulden param_widgets vb. aliyor;
        # dosya basinda import etmek dongusel import olurdu.
        from . import backtest
        backtest.panel(strat, cfg, timeframe, tf_label)
    elif sel == "Kurallar":
        st.caption(kaynak)
        st.markdown(base["kurallar"])
        _params_table(strat)
    elif sel == "Kural akisi":
        # Gec import: akis modulu buradan motor() aliyor (dongusel import).
        from . import akis as akis_ekrani
        akis_ekrani.render(strat, cfg, timeframe, tf_label)
    elif sel == "Gelistir":
        from . import gelistir as gelistir_ekrani     # gec import (ayni sebep)
        gelistir_ekrani.render(strat, cfg, timeframe, tf_label)


def _manage(strat: dict) -> None:
    st.caption("Kayit yeri: config/stratejiler.json")
    sure = st.checkbox("Silmek istedigimden eminim", key="sil_onay_" + strat["key"])
    if st.button("Stratejiyi sil", disabled=not sure, key="sil_" + strat["key"]):
        strategy_store.delete(strat["key"])
        st.query_params.clear()
        st.query_params["ekran"] = "stratejiler"
        st.rerun()


def _params_table(strat: dict) -> None:
    base = BASE[strat["temel"]]["cfg"]
    rows = [{"Parametre": lbl,
             "Bu strateji": param_text(f, getattr(strat["cfg"], f)),
             "Temel (video)": param_text(f, getattr(base, f))}
            for f, lbl in param_labels(strat["temel"])]
    st.markdown("**{} -- parametreler**".format(strat["ad"]))
    st.dataframe(pd.DataFrame(rows), hide_index=True)


# --------------------------------------------------------------------------
# Bolumler
# --------------------------------------------------------------------------
def _section_summary(strat, timeframe, tf_label, cfg) -> None:
    st.markdown(strat["aciklama"])
    m = strat["meta"]
    if strat["kayitli"] and m.get("aralik"):
        st.caption("Kayit aninda: {} · {} · {} -- getiri {}, {} islem".format(
            m.get("enstruman", ""), m.get("zaman_dilimi", ""), m["aralik"],
            pct(m["getiri_%"] if m.get("getiri_%") is not None else float("nan")),
            m.get("islem", "-")))

    rows = _signals(strat["temel"], timeframe, cfg)
    st.markdown("**Guncel durum** · takip listesi (9 varlik) · {} bar"
                .format(tf_label))
    _counts_line(rows)
    active = [r for r in rows if r["_sira"] < 2]
    if active:
        st.markdown("\n".join(_signal_line(r) for r in active))
    else:
        st.caption("Su an takip listesinde acik sinyal yok.")
    st.caption("Tum liste **Sinyaller**, {}gecmis performans ve canli "
               "parametre ayari **Backtest** bolumunde.".format(
                   "BIST 30 hisseleri **BIST 30**, "
                   if "BIST 30" in sections(strat) else ""))
    st.caption(_DISCLAIMER)


def _section_signals(strat, timeframe, tf_label, cfg) -> None:
    st.markdown("**Takip listesi -- guncel sinyaller** · {} bar".format(tf_label))

    c = st.columns([1, 3])
    if c[0].button("Verileri guncelle", type="primary"):
        with st.spinner("Dukascopy'den yeni barlar cekiliyor..."):
            added = charts.refresh_data()
        _signals.clear()
        st.session_state["sinyal_mesaj"] = (
            "{} yeni bar eklendi.".format(added) if added
            else "Veri zaten guncel.")
        st.rerun()
    if "sinyal_mesaj" in st.session_state:
        c[1].success(st.session_state.pop("sinyal_mesaj"))

    rows = _signals(strat["temel"], timeframe, cfg)
    _counts_line(rows)
    _signal_table(rows)

    newest = max((r["_son_ts"] for r in rows if r["_son_ts"]), default=None)
    if newest and datetime.now(timezone.utc) - newest > timedelta(days=3):
        st.warning("En yeni bar {} gun once. Sinyaller guncel DEGIL; "
                   "**Verileri guncelle** dugmesine basin."
                   .format((datetime.now(timezone.utc) - newest).days))
    st.caption("{} {} Veri yalnizca **Verileri guncelle** ile ya da "
               "/baslat'ta yenilenir.".format(_legend(strat),
                                              BASE[strat["temel"]]["gun_notu"]))
    st.caption(_DISCLAIMER)


def _section_bist(strat, timeframe, tf_label, cfg) -> None:
    st.markdown("**BIST 30 -- guncel sinyaller** · {} bar".format(tf_label))

    c = st.columns([1, 3])
    if c[0].button("Yenile", type="primary"):
        _bist_signals.clear()
        st.rerun()
    try:
        with st.spinner("Yahoo Finance'ten BIST 30 verisi cekiliyor..."):
            rows, failed, fetched = _bist_signals(strat["temel"], timeframe, cfg)
    except Exception as exc:  # noqa: BLE001 - ag hatasi kullaniciya gosterilir
        st.error("BIST verisi alinamadi ({}). Internet baglantisini kontrol "
                 "edip **Yenile**'ye basin.".format(exc))
        return
    tz = ZoneInfo(TZ)
    c[1].caption("Cekilme: {} (TR) · 5 dk onbellek".format(
        fetched.astimezone(tz).strftime("%d.%m.%Y %H:%M")))

    _counts_line(rows)
    newest = max((r["_son_ts"] for r in rows if r["_son_ts"]), default=None)
    if newest and bist.day_over(newest, datetime.now(timezone.utc)):
        st.info("Seans kapali. Gun ici kural geregi pozisyonlar 18:00'de "
                "kapanir; bu yuzden simdi acik sinyal gorunmez. Bugun kimin "
                "sinyal verdigini **Bugun sinyal verenler** gosterir. Yeni "
                "sinyaller acilistan 30 dk sonra (10:30) baslar.")

    filt = st.radio("Goster", ["Tumu", "Acik sinyaller", "Bugun sinyal verenler"],
                    horizontal=True, key="bist_filtre")
    if filt == "Acik sinyaller":
        shown = [r for r in rows if r["_sira"] < 2]
    elif filt == "Bugun sinyal verenler":
        today = newest.astimezone(tz).date() if newest else None
        shown = sorted(
            (r for r in rows if r["_kurulum_ts"]
             and r["_kurulum_ts"].astimezone(tz).date() == today),
            key=lambda r: r["_kurulum_ts"], reverse=True)
    else:
        shown = rows
    if shown:
        _signal_table(shown)
    else:
        st.info("Bu filtrede hisse yok.")
    if failed:
        st.warning("Veri alinamayan: " + ", ".join(failed))

    st.caption(_legend(strat) + " BIST'te seans **18:00**'de biter; "
               "acilistan sonraki ilk 30 dk islem yok.")
    st.caption("BIST 30 listesi: {} donemi. Veri: Yahoo Finance, ~15 dk "
               "gecikmeli olabilir; kapanmamis bar kullanilmaz."
               .format(bist.BIST30_DONEM))
    st.caption(_DISCLAIMER)


# --------------------------------------------------------------------------
# Sinyal tablosu yardimcilari
# --------------------------------------------------------------------------
_LEGEND_ORTAK = ("▲ AL / ▼ SAT = strateji su an o yonde pozisyonda. "
                 "● yeni = sinyal son kapanan barda olustu.")


def _legend(strat: dict) -> str:
    """Tablo aciklamasi: ortak isaretler + stratejiye ozgu kisim."""
    return "{} {}".format(_LEGEND_ORTAK, BASE[strat["temel"]]["efsane"])


# Eski ad (tek strateji varken).
_LEGEND = "{} {}".format(_LEGEND_ORTAK, BASE["ema10"]["efsane"])
_DISCLAIMER = ("Sinyaller stratejinin kurallarinin otomatik uygulamasidir; "
               "yatirim tavsiyesi degildir.")


def _tr_time(ts: datetime | None) -> str:
    return ts.astimezone(ZoneInfo(TZ)).strftime("%d.%m %H:%M") if ts else ""


def _px(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2)


def _state_row(code: str, s: dict | None) -> dict:
    row = {"Varlik": code, "Sinyal": "Veri yok", "Yeni": "",
           "Sinyal zamani (TR)": "", "Giris": None, "Stop": None,
           "Hedef": None, "Son fiyat": None, "Anlik %": None,
           "Son bar (TR)": "", "Son kurulum": "",
           "_sira": 3, "_yon": 0, "_ts": None, "_son_ts": None,
           "_kurulum_ts": None}
    if s is None:
        return row

    pos, pend = s["pos"], s["bekleyen"]
    row.update({"Son fiyat": _px(s["son_fiyat"]),
                "Son bar (TR)": _tr_time(s["son_ts"]),
                "_son_ts": s["son_ts"]})
    if s["son_kurulum"]:
        d, t = s["son_kurulum"]
        row["Son kurulum"] = "{} · {}".format("AL" if d == 1 else "SAT",
                                             _tr_time(t))
        row["_kurulum_ts"] = t
    if pos:
        row.update({
            "Sinyal": ("▲ AL" if pos == 1 else "▼ SAT")
                      + (" (BE)" if s["break_even"] else ""),
            "Sinyal zamani (TR)": _tr_time(s["giris_ts"]),
            "Giris": _px(s["giris"]), "Stop": _px(s["stop"]),
            "Hedef": _px(s["hedef"]),
            "Anlik %": round((s["son_fiyat"] - s["giris"]) / s["giris"]
                             * pos * 100, 2),
            "_sira": 0, "_yon": pos, "_ts": s["giris_ts"],
        })
    elif pend:
        row.update({
            "Sinyal": "△ AL bekliyor" if pend == 1 else "▽ SAT bekliyor",
            "Sinyal zamani (TR)": _tr_time(s["bekleyen_ts"]),
            "Giris": _px(s["bekleyen_seviye"]), "Stop": _px(s["bekleyen_stop"]),
            "_sira": 1, "_yon": pend, "_ts": s["bekleyen_ts"],
        })
    else:
        row.update({"Sinyal": "— Yok", "_sira": 2})
    if s["yeni"]:
        row["Yeni"] = "● yeni"
    return row


def _sorted(rows: list[dict]) -> list[dict]:
    """Acik pozisyonlar, sonra bekleyenler, sonra bos; her grupta en yeni ustte."""
    return sorted(rows, key=lambda r: (
        r["_sira"], -(r["_ts"].timestamp() if r["_ts"] else 0)))


def _counts_line(rows: list[dict]) -> None:
    c = st.columns(4)
    c[0].metric("Acik AL", sum(1 for r in rows if r["_sira"] == 0 and r["_yon"] == 1))
    c[1].metric("Acik SAT", sum(1 for r in rows if r["_sira"] == 0 and r["_yon"] == -1))
    c[2].metric("Bekleyen emir", sum(1 for r in rows if r["_sira"] == 1))
    c[3].metric("Sinyal yok", sum(1 for r in rows if r["_sira"] >= 2))


def _signal_table(rows: list[dict]) -> None:
    pdf = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                        for r in rows])
    st.dataframe(pdf, width="stretch", hide_index=True,
                 height=min(38 + 35 * len(pdf), 1120))


def _signal_line(r: dict) -> str:
    fiyat = home._fmt_price(r["Giris"]) if r["Giris"] is not None else "-"
    anlik = "" if r["Anlik %"] is None else " · anlik {}".format(pct(r["Anlik %"]))
    return "- {} · **{}** · {} · giris {}{} {}".format(
        r["Sinyal"], r["Varlik"], r["Sinyal zamani (TR)"], fiyat, anlik,
        r["Yeni"]).rstrip()


def pct(v: float) -> str:
    """+1,2% bicimi. Backtest ekrani da kullanir."""
    if v != v:  # nan
        return "-"
    return "{:+.1f}%".format(v).replace(".", ",")

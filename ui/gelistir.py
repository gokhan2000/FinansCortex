"""Gelistir ekrani -- zayif nokta teshisi + parametre taramasi.

Kullanici (22.09.2026): *"Kazandirma orani yeterli degil. Inceleyip orani
artirmaya yonelik fikirler veren bir motor gerek... programin en guclu yani
burasi olmali."*

BU EKRAN HESAP YAPMAZ; hepsi `finans_cortex/gelistir.py`'de. Burasi yalnizca
sorar, gosterir ve "bunu dene" der. Strateji tanimaz: parametre listesini
motorun `ARAMA_UZAYI`'ndan alir, yeni strateji eklenince kendiliginden calisir.

ISLEYIS (kullanicinin istedigi sira)
    1. TESHIS   Su anki ayarla tum varliklarda kos, zayif noktalari rakamla
                yaz. Her bulgunun yaninda -- varsa -- denenecek somut bir
                parametre ve "Bunu dene" dugmesi.
    2. TARAMA   Secilen parametreleri tara. Siralama KONTROL bolumune gore
                (ayar bolumune gore siralamak gecmisi ezberlemektir).
    3. KAYDET   Begenilen satir "Farkli kaydet" ile yeni varyant olur (2.2...).

Hicbir sey kendiliginden calismaz (dugme), cunku tarama dakikalar surebilir.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pandas as pd
import polars as pl
import streamlit as st

from finans_cortex import backtest as bt_cost
from finans_cortex import gelistir, strategy_store

from . import charts, theme
from .backtest import BIST_TF, PIYASALAR

DONEMLER = {"Son 3 yil": 3 * 365, "Son 5 yil": 5 * 365, "Son 10 yil": 10 * 365,
            "Tumu": None}

SIDDET_RENK = {"yuksek": theme.DOWN, "orta": theme.ACCENTS["yellow"],
               "bilgi": theme.ACCENTS["aqua"]}

# Taramada ONCE denenecek parametreler: cikis kurallari. Gosterge
# parametreleri (ce_period, rf_period...) prepare'i her seferinde yeniden
# hesaplatir; varsayilan disinda tutuldu.
ONCELIKLI = ("kar_al", "zarar_kes", "tek_ters", "tolerance", "allow_short",
             "rr_target", "swing_lookback", "breakeven_r", "exit_on_ema")

_CSS = """
<style>
 .dc-bulgu {{border:1px solid {hair}; border-left:4px solid; border-radius:9px;
             padding:9px 13px; margin:0 0 9px 0; background:{panel};}}
 .dc-bulgu .b {{font-weight:700; font-size:13px; color:{ink};}}
 .dc-bulgu .o {{font-size:12px; color:{ink}; margin-top:3px;}}
 .dc-bulgu .n {{font-size:11.5px; color:{dim}; margin-top:4px;}}
 .dc-ozet {{display:flex; gap:18px; flex-wrap:wrap; background:{panel};
            border:1px solid {hair}; border-radius:9px; padding:8px 14px;
            margin-bottom:10px;}}
 .dc-ozet div {{font-size:11px; color:{dim};}}
 .dc-ozet b {{display:block; font-size:16px; color:{ink}; font-weight:650;}}
</style>
"""


# ==========================================================================
# VERI
# ==========================================================================
@st.cache_resource(ttl=1800, max_entries=10, show_spinner=False)
def _bars(kodlar: tuple[str, ...], timeframe: str, piyasa: str = "kuresel"):
    """Ham barlar. cache_resource: cerceve buyuk, her okumada kopyalanmasin
    (backtest ve kural akisi ekraniyla ayni gerekce)."""
    from finans_cortex import storage
    con = charts.get_connection()
    if piyasa == "bist":
        return {k: storage.read_bist_bars(con, k, timeframe) for k in kodlar}
    return {k: storage.read_bars(con, k, timeframe) for k in kodlar}


def _yardimci(bars, cfg, istek, hazir_yardimci):
    """15 dakikalik teyit cerceveleri -- YALNIZ gerekiyorsa.

    Gerekli olmasinin iki yolu var: ya su anki ayarda acik (`cfg.onay_15m`),
    ya da kullanici onu denemek istiyor (Sonuclar'da secmis ya da taramaya
    koymus). Gereksiz yere yuklenmemeli: 9 varlikta 15 dakikalik veri 2,5
    milyon satirdir. `_bars` onbellekli, ikinci cagri bedava."""
    if hazir_yardimci is not None:
        return hazir_yardimci
    ister = bool(getattr(cfg, "onay_15m", False))
    if not ister and istek:
        # istek: {parametre: deger} ya da {parametre: [degerler]}
        d = istek.get("onay_15m")
        ister = bool(d) if not isinstance(d, (list, tuple)) else any(d)
    return _bars(tuple(bars), "15m") if ister else None


def _maliyet(kodlar, piyasa: str = "kuresel") -> dict[str, float]:
    # BIST hisseleri daha pahali: spread + araci kurum komisyonu (bkz.
    # backtest.BIST_COST). Ayni fonksiyona koymak yanlis olurdu -- kod
    # cakismasi da olabilir (bir BIST kodu kuresel bir kodla ayni olabilir).
    if piyasa == "bist":
        return {k: bt_cost.bist_cost_for(k).roundtrip_bp for k in kodlar}
    return {k: bt_cost.cost_for(k).roundtrip_bp for k in kodlar}


def _olcu_serit(m: dict, al_tut: dict | None = None) -> str:
    """Ozet serit. SIRA ONEMLI (24 Eylul 2026): en basta YILLIK getiri ve
    al-tut farki durur.

    Eskiden ilk sirada "Net %" vardi -- islem getirilerinin toplami. Farkli
    uzunluktaki gecmisler toplaninca devasa ve anlamsiz bir sayi cikiyordu
    (+%1.245), yillik karsiligi ise %8,3'tu ve al-tut'un (%16,0) yarisiydi.
    Kullanici hakli olarak "kazanan strateji cikmiyor" dedi; goremedigimiz
    icin yanilmistik. Toplam hala var ama en sona alindi.
    """
    at = (al_tut or {}).get("yillik_%")
    fark = (m["yillik_%"] - at if at == at and at is not None
            and m["yillik_%"] == m["yillik_%"] else float("nan"))
    alanlar = (("YILLIK", m["yillik_%"], "%"),
               ("Al-tut yillik", at if at is not None else float("nan"), "%"),
               ("Fark", fark, "%"),
               ("Piyasada", m["piyasada_%"], "%"),
               ("Yilda islem", m["islem_yil"], ""),
               ("Kar faktoru", m["kar_faktoru"], ""),
               ("Maks. dusus", m["MaxDD_%"], "%"),
               ("Kazanan", m["kazanan_%"], "%"),
               ("Toplam", m["getiri_%"], "%"))
    parcalar = []
    for ad, deger, birim in alanlar:
        metin = "-" if deger != deger else "{}{}".format(
            str(deger).replace(".", ","), birim)
        parcalar.append("<div>{}<b>{}</b></div>".format(ad, metin))
    return '<div class="dc-ozet">{}</div>'.format("".join(parcalar))


def _tablo(kars: dict) -> pd.DataFrame:
    """Simdiki / onerilen ayari bolum bolum yan yana."""
    satirlar = []
    for ad in ("simdiki", "onerilen"):
        for bolum, etiket in (("tum", "tum donem"), ("ayar", "ayar %70"),
                              ("kontrol", "kontrol %30")):
            m = kars[ad][bolum]
            satirlar.append({
                "Ayar": "Simdiki" if ad == "simdiki" else "Onerilen",
                "Bolum": etiket, "Islem": m["islem"],
                "Yillik %": m["yillik_%"], "Piyasada %": m["piyasada_%"],
                "Yilda islem": m["islem_yil"],
                "Kazanan %": m["kazanan_%"], "Kar faktoru": m["kar_faktoru"],
                "Islem basina bp": m["ort_islem_bp"], "Toplam %": m["getiri_%"]})
    return pd.DataFrame(satirlar)


# ==========================================================================
# EKRAN
# ==========================================================================
def render(strat: dict, cfg, timeframe: str, tf_label: str) -> None:
    """Stratejiler > <strateji> > Gelistir bolumu."""
    from finans_cortex.instruments import HESAP_KODLARI

    from .strategies import motor

    m = motor(strat["temel"])
    if not hasattr(m, "ARAMA_UZAYI"):
        st.info("Bu strateji icin gelistirme motoru henuz tanimlanmadi.")
        return
    st.markdown(_CSS.format(panel=theme.PANEL, hair=theme.HAIRLINE,
                            ink=theme.INK, dim=theme.INK_DIM),
                unsafe_allow_html=True)

    ust = st.columns([0.9, 2.2, 1, 1.2], gap="medium", vertical_alignment="bottom")
    piyasa = PIYASALAR[ust[0].selectbox("Piyasa", list(PIYASALAR), key="gel_piyasa")]
    if piyasa == "bist":
        cov = charts.load_bist_coverage()
        if cov.is_empty():
            st.info("BIST gecmisi henuz indirilmedi. **Veri Merkezi > BIST "
                    "gecmisini guncelle**'ye bir kez basin (~15 saniye).")
            return
        # Backtest paneliyle ayni kural: STRATEJININ destekledigi dilimlerle
        # BIST'te var olanlarin kesisimi. Strateji 1 gunluk barla calismaz.
        from .strategies import timeframes as _tfs
        uygun = {lbl: kod for lbl, kod in _tfs(strat).items()
                 if kod in BIST_TF}
        if not uygun:
            st.warning("**{}** BIST'te calistirilamiyor: bu strateji {} "
                       "diliminde calisiyor, BIST'te yalniz gunluk ve 1 saat "
                       "var.".format(strat["ad"], " / ".join(_tfs(strat))))
            return
        if timeframe not in BIST_TF:
            secim = st.radio("BIST zaman dilimi", list(uygun), horizontal=True,
                             key="gel_bist_tf_" + strat["key"])
            timeframe, tf_label = uygun[secim], secim
            st.caption("Kenar cubugundaki dilim BIST'te yok; **{}** barla "
                       "olculuyor.".format(secim))
        havuz = sorted(cov.filter(pl.col("timeframe") == timeframe)["code"]
                       .unique().to_list())
    else:
        havuz = list(HESAP_KODLARI)
    kodlar = ust[1].multiselect(
        "Varliklar", havuz, default=havuz, key="gel_varlik_" + piyasa,
        help="Hepsi secili: strateji tek tek varlikta degil, portfoy olarak "
             "olculur (her islem ayni buyuklukte).")
    donem_ad = ust[2].selectbox("Donem", list(DONEMLER), index=1,
                                key="gel_donem")
    amac = ust[3].selectbox(
        "Amac", list(gelistir.AMACLAR), index=0, key="gel_amac",
        help="Tarama bu olcuye gore siralanir. Yalniz 'kazanan islem %' "
             "secmek yaniltir: %2 hedef / %1 zararla kazanma orani "
             "dusuk ama kazanclar buyuk olabilir.")
    if not kodlar:
        st.info("En az bir varlik secin.")
        return

    gun = DONEMLER[donem_ad]
    baslangic = (datetime.now(timezone.utc) - timedelta(days=gun)) if gun else None
    bars = _bars(tuple(kodlar), timeframe, piyasa)
    maliyet = _maliyet(kodlar, piyasa)
    # Bazi kurallar baska bir zaman dilimini ister (Strateji 2'nin 15 dakikalik
    # Chandelier teyidi). YALNIZ gerekiyorsa okunur: 15 dakikalik veri 9
    # varlikta 2,5 milyon satir, bosuna yuklenmemeli.
    # BIST'te 15 dakikalik gecmis yok (Yahoo ~3 ay) -- teyit orada calismaz.
    yardimci = (_bars(tuple(kodlar), "15m")
                if piyasa == "kuresel" and getattr(cfg, "onay_15m", False)
                else None)
    ortak = (m, cfg, bars, timeframe, maliyet, baslangic, yardimci)

    teshis_sekme, tarama_sekme = st.tabs(
        ["Teshis -- zayif noktalar", "Parametre taramasi"])
    with teshis_sekme:
        _teshis(strat, ortak, tf_label, donem_ad)
    with tarama_sekme:
        _tarama(strat, ortak, amac, tf_label)


def _anahtar(strat: dict, ek: str) -> str:
    return "gel_{}_{}".format(strat["key"], ek)


# --------------------------------------------------------------------------
# 1. TESHIS
# --------------------------------------------------------------------------
def _teshis(strat: dict, ortak: tuple, tf_label: str, donem_ad: str) -> None:
    m, cfg, bars, timeframe, maliyet, baslangic, yardimci = ortak
    st.caption("Su anki ayar {} varlikta, {} donemde, {} barla calistirilir; "
               "islemler tek havuzda incelenir.".format(
                   len(bars), donem_ad.lower(), tf_label.lower()))
    if st.button("Teshis et", type="primary", key=_anahtar(strat, "teshis")):
        with st.spinner("Calistiriliyor..."):
            hazir = gelistir.hazirla(m, bars, cfg, yardimci)
            sonuc = gelistir.kos(m, hazir, cfg, timeframe, maliyet, baslangic)
            st.session_state[_anahtar(strat, "sonuc")] = {
                "olcu": gelistir.olcu(sonuc["islemler"], sonuc["gunluk"],
                                      sonuc.get("havuz")),
                "al_tut": sonuc.get("al_tut", {}),
                "tam": (sonuc.get("havuz") or {}).get("tam_baslangic"),
                "bulgular": gelistir.teshis(m, cfg, sonuc, timeframe),
                "cfg": cfg, "donem": donem_ad}

    kayit = st.session_state.get(_anahtar(strat, "sonuc"))
    if not kayit:
        return
    if kayit["cfg"] != cfg or kayit["donem"] != donem_ad:
        st.warning("Asagidaki teshis ONCEKI ayarlara/doneme ait. Yeniden "
                   "'Teshis et'e basin.")

    st.markdown(_olcu_serit(kayit["olcu"], kayit.get("al_tut")),
                unsafe_allow_html=True)
    tam = kayit.get("tam")
    if tam is not None and len(bars) > 1:
        st.caption("Her varliga esit para. Havuz **{}** tarihinden itibaren "
                   "tam; oncesinde verisi baslamis varliklar arasinda "
                   "bolunur.".format(tam.strftime("%d.%m.%Y")))
    for b in kayit["bulgular"]:
        st.markdown(
            '<div class="dc-bulgu" style="border-left-color:{r}">'
            '<div class="b">{b}</div><div class="o">{o}</div>'
            '{n}</div>'.format(
                r=SIDDET_RENK.get(b.siddet, theme.INK_DIM),
                b=_kacis(b.baslik), o=_kacis(b.olcum),
                n='<div class="n">{}</div>'.format(_kacis(b.oneri))
                if b.oneri else ""),
            unsafe_allow_html=True)

    _sonuclar(strat, kayit, ortak)


def _degisiklik_metni(temel: str, degisiklik: dict) -> str:
    """Ham alan adi degil, ekrandaki adiyla: "SAT islemleri: kapali"."""
    from .strategies import param_labels, param_text
    adlar = dict(param_labels(temel))
    return " · ".join(
        "{}: {}".format(adlar.get(k, k), param_text(k, v))
        for k, v in degisiklik.items())


# --------------------------------------------------------------------------
# 2. SONUCLAR -- bulgulari secip BIRLIKTE uygula, sonra kaydet/guncelle
# --------------------------------------------------------------------------
def _sonuclar(strat: dict, kayit: dict, ortak: tuple) -> None:
    """Kullanici (22.09.2026): *"bu rapordan cikarilacak sonuclar olmali,
    kullanici sonuclardan stratejiyi guncelleyebilmeli"*.

    Teshis bulgularindan parametre onerisi TASIYANLAR burada secilebilir
    kutular olur; birkaci birden isaretlenip TEK seferde denenir (tek tek
    denemek "ikisi birlikte ne yapar" sorusunu cevaplamiyordu). Begenilirse
    ya yeni varyant olur ya da uzerinde calisilan varyant guncellenir.
    """
    m, cfg, bars, timeframe, maliyet, baslangic, yardimci = ortak
    onerililer = [b for b in kayit["bulgular"] if b.degisiklik]

    st.markdown("### Sonuclar")
    if not onerililer:
        st.info("Yukaridaki bulgularin hicbirinin motorda dogrudan bir "
                "parametre karsiligi yok -- uygulanabilmeleri icin yeni bir "
                "kural yazilmasi gerekir. Parametre taramasi sekmesinden "
                "mevcut parametreleri yine de deneyebilirsiniz.")
        return

    st.caption("Uygulamak istediklerinizi isaretleyin, sonra birlikte "
               "deneyin. Hicbir sey kendiliginden kaydedilmez.")
    secilen: dict = {}
    catisma = []
    for n, b in enumerate(onerililer):
        etiket = "{} → {}".format(
            b.baslik, _degisiklik_metni(strat["temel"], b.degisiklik))
        if st.checkbox(etiket, key=_anahtar(strat, "sec{}".format(n))):
            for k, v in b.degisiklik.items():
                if k in secilen and secilen[k] != v:
                    catisma.append(k)
                secilen[k] = v

    if catisma:
        st.warning("Ayni parametreye iki farkli deger onerildi ({}); "
                   "sonuncusu kullanilir.".format(", ".join(sorted(set(catisma)))))

    etkisiz = {k: v for k, v in secilen.items() if getattr(cfg, k, None) == v}
    if etkisiz:
        st.caption("Zaten boyle ayarli, bir sey degistirmez: {}".format(
            _degisiklik_metni(strat["temel"], etkisiz)))

    c = st.columns([1.6, 3])
    if c[0].button("Secilenleri dene", type="primary",
                   disabled=not secilen,
                   key=_anahtar(strat, "uygula")):
        with st.spinner("Iki ayar yan yana kosuluyor..."):
            st.session_state[_anahtar(strat, "kars")] = (
                gelistir.karsilastir(
                    m, cfg, secilen, bars, timeframe, maliyet, baslangic,
                    yardimci=_yardimci(bars, cfg, secilen, yardimci)),
                dict(secilen))
    if not secilen:
        c[1].caption("En az bir sonuc isaretleyin.")

    kars = st.session_state.get(_anahtar(strat, "kars"))
    if not kars:
        return
    sonuc, degisiklik = kars
    if degisiklik != secilen:
        st.warning("Asagidaki karsilastirma ONCEKI secime ait "
                   "({}). Yeniden 'Secilenleri dene'ye basin.".format(
                       _degisiklik_metni(strat["temel"], degisiklik)))
    st.markdown("**Karsilastirma** -- {}".format(
        _degisiklik_metni(strat["temel"], degisiklik)))
    st.dataframe(_tablo(sonuc), width="stretch", hide_index=True)
    st.caption("Onerilen ayar KONTROL bolumunde de iyiyse anlamlidir; "
               "yalniz ayar bolumunde iyiyse tesaduf olabilir.")
    _kaydet(strat, sonuc["cfg"], ortak, "dene")


def _kacis(metin: str) -> str:
    return (metin.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# --------------------------------------------------------------------------
# 2. TARAMA
# --------------------------------------------------------------------------
def _tarama(strat: dict, ortak: tuple, amac: str, tf_label: str) -> None:
    m, cfg, bars, timeframe, maliyet, baslangic, yardimci = ortak
    uzay_hepsi = m.ARAMA_UZAYI
    gosterge = set(getattr(m, "GOSTERGE_PARAMLARI", frozenset()))
    varsayilan = [a for a in ONCELIKLI if a in uzay_hepsi][:3]

    secim = st.multiselect(
        "Taranacak parametreler", list(uzay_hepsi), default=varsayilan,
        key=_anahtar(strat, "param"),
        help="Gosterge parametreleri (yildizli) gostergeleri yeniden "
             "hesaplatir, tarama yavaslar.",
        format_func=lambda a: a + (" *" if a in gosterge else ""))
    c = st.columns([1, 1, 1.4], gap="medium", vertical_alignment="bottom")
    en_fazla = c[0].slider("En fazla kombinasyon", 10, 300, 60, 10,
                           key=_anahtar(strat, "adet"),
                           help="Izgara buyukse rastgele ornek alinir "
                                "(tohum sabit, ayni sonuc tekrar eder).")
    if secim:
        toplam = 1
        for a in secim:
            toplam *= len(uzay_hepsi[a])
        c[1].metric("Izgara", "{} kombinasyon".format(toplam))
    basla = c[2].button("Taramayi baslat", type="primary",
                        disabled=not secim, key=_anahtar(strat, "tara"))

    if basla:
        uzay = {a: uzay_hepsi[a] for a in secim}
        cubuk = st.progress(0.0, text="Hazirlaniyor...")

        def ilerleme(oran: float, k: dict) -> None:
            cubuk.progress(oran, text="{} / {} -- {}".format(
                int(oran * min(en_fazla, _izgara(uzay))),
                min(en_fazla, _izgara(uzay)),
                ", ".join("{}={}".format(a, v) for a, v in k.items())))

        tablo = gelistir.tarama(m, cfg, bars, timeframe, maliyet, uzay, amac,
                                en_fazla=en_fazla, baslangic=baslangic,
                                ilerleme=ilerleme,
                                yardimci=_yardimci(bars, cfg, uzay, yardimci))
        cubuk.empty()
        st.session_state[_anahtar(strat, "tablo")] = (tablo, secim, amac)

    kayit = st.session_state.get(_anahtar(strat, "tablo"))
    if not kayit:
        st.caption("Parametreleri secip taramayi baslatin. Sonuc KONTROL "
                   "bolumune gore siralanir.")
        return
    tablo, secim, tarama_amac = kayit
    if tablo.is_empty():
        st.info("Sonuc yok.")
        return

    _, _, birim = gelistir.AMACLAR[tarama_amac]
    pdf = tablo.to_pandas().rename(columns={
        "ayar": "Ayar %70" + birim, "kontrol": "Kontrol %30" + birim,
        "tum": "Tum donem" + birim, "komsu": "Komsu ort.",
        "islem": "Islem", "kontrol_islem": "Kontrol islem",
        "kazanan": "Kazanan %", "kar_faktoru": "Kar faktoru",
        "yillik": "Yillik %", "piyasada": "Piyasada %",
        "yilda_islem": "Yilda islem",
        "getiri": "Toplam %", "ort_bp": "Islem basina bp",
        "maxdd": "Maks. dusus %"})
    st.dataframe(pdf, width="stretch", hide_index=True, height=340)
    st.caption(
        "Siralama **kontrol bolumune** gore ({}). 'Komsu ort.' bir parametre "
        "bir adim saga/sola kaydiginda ayar bolumunun ne oldugudur: komsusu "
        "kotu olan tek basina parlak satir buyuk ihtimalle tesaduftur.".format(
            tarama_amac))

    en_iyi = tablo.row(0, named=True)
    degisiklik = {a: en_iyi[a] for a in secim}
    st.markdown("**En iyi satir:** " + ", ".join(
        "{} = {}".format(a, degisiklik[a]) for a in secim))
    if st.button("Bu satiri simdiki ayarla karsilastir",
                 key=_anahtar(strat, "tara_dene")):
        with st.spinner("Iki ayar yan yana kosuluyor..."):
            st.session_state[_anahtar(strat, "tara_kars")] = (
                gelistir.karsilastir(
                    m, cfg, degisiklik, bars, timeframe, maliyet, baslangic,
                    yardimci=_yardimci(bars, cfg, degisiklik, yardimci)))
    kars = st.session_state.get(_anahtar(strat, "tara_kars"))
    if kars:
        st.dataframe(_tablo(kars), width="stretch", hide_index=True)
        _kaydet(strat, kars["cfg"], ortak, "tara")


def _izgara(uzay: dict) -> int:
    toplam = 1
    for v in uzay.values():
        toplam *= len(v)
    return toplam


# --------------------------------------------------------------------------
# 3. KAYDET
# --------------------------------------------------------------------------
def _kaydet(strat: dict, yeni_cfg, ortak: tuple, ek: str) -> None:
    """Begenilen ayari sakla (Backtest panelindekiyle ayni yer:
    config/stratejiler.json).

    Iki kapi: uzerinde calisilan KAYITLI varyanti guncelle, ya da yeni bir
    varyant olarak kaydet. Temel stratejiler (Strateji 1 / 2) guncellenemez --
    onlar koddaki varsayilanlardir, kaynak videonun kurallari; degistirilirse
    "video boyle diyordu" dayanagi kaybolur. Onlardan tureyen her sey varyant
    olarak kaydedilir.
    """
    _, cfg, _, timeframe, _, _, _ = ortak
    if yeni_cfg == cfg:
        return
    mesaj = st.session_state.pop(_anahtar(strat, ek + "_mesaj"), None)
    if mesaj:
        st.success(mesaj)

    if strat.get("kayitli"):
        st.markdown("**Bu stratejiyi guncelle** -- '{}' onerilen ayarla "
                    "degisir, yeni bir kayit olusmaz".format(strat["ad"]))
        g = st.columns([1.8, 3])
        if g[0].button("'{}' stratejisini guncelle".format(strat["ad"]),
                       type="primary", key=_anahtar(strat, ek + "_guncelle")):
            try:
                strategy_store.save_as(
                    strat["ad"], strat["temel"], yeni_cfg, timeframe,
                    note=strat.get("aciklama", ""), overwrite=True)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[_anahtar(strat, ek + "_mesaj")] = (
                    "'{}' guncellendi.".format(strat["ad"]))
                st.rerun()
        g[1].caption("Eski ayar saklanmaz. Karsilastirmayi kaybetmek "
                     "istemiyorsaniz asagidan farkli kaydedin.")
    else:
        st.caption("'{}' bir TEMEL strateji; uzerine yazilmaz. Onerilen ayar "
                   "yeni bir varyant olarak kaydedilir.".format(strat["ad"]))

    with st.form(_anahtar(strat, ek + "_form")):
        st.markdown("**Farkli kaydet** -- onerilen ayari yeni strateji yap")
        c = st.columns([2, 3, 1.2])
        ad = c[0].text_input("Strateji adi", placeholder="orn. Strateji 2.2",
                             max_chars=60)
        not_ = c[1].text_input("Not (istege bagli)", max_chars=200,
                               placeholder="orn. gelistirme motoru onerisi")
        uzerine = c[2].checkbox("Uzerine yaz")
        if st.form_submit_button("Farkli kaydet", type="primary"):
            try:
                kayit = strategy_store.save_as(
                    ad, strat["temel"], yeni_cfg, timeframe, note=not_,
                    overwrite=uzerine)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[_anahtar(strat, ek + "_mesaj")] = (
                    "'{}' kaydedildi. Strateji listesinde gorunur.".format(
                        kayit["ad"]))
                st.rerun()


def uygula(cfg, degisiklik: dict):
    """Disaridan cagrilabilsin diye (test)."""
    return replace(cfg, **degisiklik)

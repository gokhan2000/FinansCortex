"""Kural akisi ekrani -- kurallar akis semasi + secilen sinyalin animasyonu.

STRATEJIDEN BAGIMSIZ. Bu dosya hicbir stratejinin kuralini bilmez; motorun
iki fonksiyonunu cagirir (bkz. finans_cortex/akis.py):

    motor.sema(cfg)                       -> semadaki kutular
    motor.izle(bars, islem, cfg, tf)      -> secilen sinyalde her kutunun sonucu

Yeni bir strateji eklenince bu ekran kendiliginden calisir; burada
degisiklik gerekmez.

DUZEN (kullanici, 21.09.2026: "kutular cok buyuk, ekranin ustu kalabalik,
yan taraf iyi kullanilmamis, semanin buyuk kismini ekranda gorebileyim")
  ust satir   varlik + sinyal + hiz + Oynat + secilen islemin karti
  alt         solda akis semasi, sagda islemin mum grafigi; adim listesi
              katlanir kutuda. Sema kucuk kutular (iki satir), ~470 px
              genislik; 6-7 kutuluk sema tek ekrana sigar.
  Uzun aciklamalar ekrandan kalkti; kutunun parametre satiri, deger yokken
  gorunur, fare ustune gelince (tooltip) hep gorunur.

CIZIM: elle uretilen SVG + CSS animasyonu. Neden kutuphane degil?
  - Streamlit'te calisan hazir akis kutuphaneleri (graphviz, mermaid) ya
    stil denetimi vermiyor ya da her adimi tek tek boyamaya izin vermiyor.
  - Animasyon CSS `animation-delay` ile: adimlar sirayla beliriyor. JavaScript
    yok, yeniden calistirma yok -- uzaktan baglantida da akici.
  - "Oynat"a her basista animasyon ADI degisir (t0/t1); yalniz sinif
    degisince tarayici animasyonu baslatmiyordu (Streamlit ayni SVG ogesini
    yeniden kullaniyor). Ad degisince bastan oynar.

RENKLER: gecti = yesil, kaldi (kural saglanmadi / zarar) = turuncu,
atlandi (bu sinyalde sirasi gelmedi) = soluk.

MUM GRAFIGI (21.09.2026): sema "havada duruyordu" -- "Chandelier 15:00'te
yandi" yaziyor ama o bar gorunmuyordu. Semanin yaninda islemin cevresindeki
mumlar durur; her kutu yandiginda motorun verdigi `Isaret`ler (hangi mumda
gosterge yandi, giris, stop, cikis) grafikte AYNI anda belirir. Giristen
cikisa kadarki mumlar "Giris" ile "Cikis" kutularinin arasindaki surede
soldan saga akar, stop cizgisi de onlarla birlikte uzar. Yine yalniz CSS.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from finans_cortex import akis

from . import charts, theme

TZ = "Europe/Istanbul"

# Sinyal listesi icin kac gun geriye bakilacagi (bar boyutuna gore).
# Amac: en az birkac on sinyal cikaracak kadar gecmis, ama gereksiz hesap yok.
GUN = {"15m": 45, "1h": 180, "4h": 900, "1d": 2500}
EN_FAZLA = 20

HIZLAR = {"Yavas": 1.0, "Normal": 0.6, "Hizli": 0.35}
ADIM_ADIM = "Adim adim"

# --- cizim olculeri (SVG birimi = piksel; ekranda en fazla ~1:1 cizilir) ---
# Kullanici %125 Windows olceginde "kutular dev gibi, fontlar kocaman" dedi
# (21.09.2026): kutu 320x38, baslik 11,5 px, deger 10 px. SVG sabit piksel
# genislikte cizilir, kolona gore BUYUMEZ (dar ekranda kuculur).
KUTU_G, KUTU_Y, ARALIK = 320, 38, 14
SOL, DAL_ARA, DAL_G, DAL_Y = 6, 22, 112, 20
GENISLIK = SOL + KUTU_G + DAL_ARA + DAL_G + 8

RENK = {
    akis.GECTI: theme.ACCENTS["aqua"],
    akis.KALDI: theme.ACCENTS["orange"],
    akis.ATLANDI: theme.INK_DIM,
}

_CSS = """
<style>
 .dc-akis {{width:100%;}}
 .dc-akis svg {{width:{maks}px; max-width:100%; height:auto; display:block;}}
 .dc-akis .nd {{opacity:0; animation:dcin .45s cubic-bezier(.2,.7,.3,1) forwards;}}
 .dc-akis .ln {{opacity:0; animation:dcin .25s ease-out forwards;}}
 @keyframes dcin {{from {{opacity:0; transform:translateY(8px);}}
                   to   {{opacity:1; transform:translateY(0);}}}}
 .dc-akis .son rect {{animation:dcnabiz 1.6s ease-in-out .2s infinite;}}
 @keyframes dcnabiz {{0%,100% {{filter:drop-shadow(0 0 0 rgba(0,0,0,0));}}
                      50% {{filter:drop-shadow(0 0 8px {vurgu});}}}}
 .dc-akis text {{font-family:system-ui,"Segoe UI",sans-serif;}}

 .dc-mum svg {{width:100%; max-width:{mum_maks}px; height:auto; display:block;}}
 .dc-mum text {{font-family:system-ui,"Segoe UI",sans-serif;}}
 .dc-mum .mm {{opacity:0; animation:dcgor .18s ease-out forwards;}}
 .dc-mum .nd {{opacity:0; animation:dcin .45s cubic-bezier(.2,.7,.3,1) forwards;}}
 .dc-mum .uz {{stroke-dasharray:1; stroke-dashoffset:1;
               animation-name:dcuz; animation-timing-function:linear;
               animation-fill-mode:forwards;}}
 @keyframes dcgor {{from {{opacity:0;}} to {{opacity:1;}}}}
 @keyframes dcuz {{from {{stroke-dashoffset:1;}} to {{stroke-dashoffset:0;}}}}
 .dc-mum-not {{font-size:10px; color:{dim}; margin:4px 0 0 0;}}

 /* Yeniden oynatma: Streamlit ikinci basista AYNI SVG ogesini yeniden
    kullaniyor; yalnizca sinif/gecikme degisince tarayici bitmis animasyonu
    bastan BASLATMAZ (olculdu, 21.09.2026). Her basista animasyon ADI
    degisir (t0/t1 sirayla) -- ad degisince animasyon bastan oynar. */
 .t1 .nd {{animation-name:dcin_ !important;}}
 .t1 .ln {{animation-name:dcin_ !important;}}
 .t1 .mm {{animation-name:dcgor_ !important;}}
 .t1 .uz {{animation-name:dcuz_ !important;}}
 @keyframes dcin_ {{from {{opacity:0; transform:translateY(8px);}}
                    to   {{opacity:1; transform:translateY(0);}}}}
 @keyframes dcgor_ {{from {{opacity:0;}} to {{opacity:1;}}}}
 @keyframes dcuz_ {{from {{stroke-dashoffset:1;}} to {{stroke-dashoffset:0;}}}}

 .dc-kart {{background:{panel}; border:1px solid {hair}; border-radius:9px;
            padding:5px 11px; margin:0; font-size:11px;
            color:{ink}; line-height:1.45;}}
 .dc-kart .ust {{display:flex; align-items:center; gap:10px; margin-bottom:4px;}}
 .dc-kart .yon {{font-weight:700; font-size:10.5px; letter-spacing:.08em;
                 padding:1px 8px; border-radius:20px; border:1px solid;}}
 .dc-kart .sonuc {{margin-left:auto; font-size:15px; font-weight:600;}}
 .dc-kart .dim {{color:{dim};}}

 .dc-adimlar {{list-style:none; padding:0; margin:0; font-size:11px;
               line-height:1.45;}}
 /* Streamlit markdown li'ye kendi punto'sunu dayatiyor; !important sart. */
 .dc-adimlar li, .dc-adimlar li span {{font-size:11px !important;
                                      line-height:1.4 !important;}}
 .dc-adimlar li .m {{font-size:10px !important;}}
 .dc-adimlar li {{margin:0 !important;}}
 .dc-adimlar li {{display:flex; gap:7px; padding:3px 0;
                  border-bottom:1px solid {hair};}}
 .dc-adimlar li:last-child {{border-bottom:none;}}
 .dc-adimlar .no {{flex:0 0 16px; color:{dim};}}
 .dc-adimlar .nokta {{flex:0 0 8px; height:8px; border-radius:50%;
                      margin-top:6px;}}
 .dc-adimlar .b {{color:{ink};}}
 .dc-adimlar .m {{color:{dim}; font-size:10.5px;}}

 .dc-anlik {{display:flex; align-items:center; gap:10px; flex-wrap:wrap;
             border:1px solid; border-radius:9px; padding:6px 12px;
             margin:2px 0 10px 0; background:{panel}; font-size:12.5px;}}
 .dc-anlik .no {{color:#0b0b0d; font-weight:750; border-radius:12px;
                 padding:1px 9px; font-size:11.5px;}}
 .dc-anlik .b {{color:{ink}; font-weight:650;}}
 .dc-anlik .m {{font-weight:600;}}
 .dc-anlik .ipucu {{margin-left:auto; color:{dim}; font-size:10.5px;}}

 .dc-efsane {{display:flex; gap:12px; flex-wrap:wrap; font-size:10px;
              color:{dim}; margin:10px 0 0 0;}}
 .dc-efsane i {{font-style:normal; margin-right:4px;}}
</style>
"""


# ==========================================================================
# VERI
# ==========================================================================
@st.cache_resource(ttl=600, max_entries=16, show_spinner=False)
def _sonuc(temel: str, code: str, timeframe: str, cfg):
    """Sinyal listesi icin gecmis calistirma. cache_resource: Result icindeki
    bar cercevesi buyuk, her okumada kopyalanmasin (backtest ekraniyla ayni
    gerekce)."""
    from .strategies import motor
    return motor(temel).run(charts.get_connection(), code, timeframe, cfg,
                            days=GUN.get(timeframe, 180))


def _yuzde(islem: dict) -> str:
    g = islem["getiri"] * 100
    return "{}%{:.2f}".format("+" if g > 0 else "-", abs(g)).replace(".", ",")


def _etiket(islem: dict) -> str:
    t = islem["giris_ts"].astimezone(ZoneInfo(TZ))
    acik = islem["neden"] == "veri_sonu"
    return "{} · {} · {}".format(
        t.strftime("%d.%m %H:%M"), "AL" if islem["yon"] == 1 else "SAT",
        "ACIK" if acik else _yuzde(islem))


def _para(v: float) -> str:
    """Turk bicimi fiyat: 4.493,62 / 1,14693"""
    basamak = 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2
    return "{:,.{}f}".format(v, basamak).replace(
        ",", " ").replace(".", ",").replace(" ", ".")


def _sure(delta: timedelta) -> str:
    dakika = delta.total_seconds() / 60
    if dakika < 120:
        return "{:.0f} dk".format(dakika)
    if dakika < 2880:
        return "{:.0f} saat".format(dakika / 60)
    return "{:.1f} gun".format(dakika / 1440).replace(".", ",")


# ==========================================================================
# CIZIM
# ==========================================================================
def _kirp(metin: str, sinir: int) -> str:
    return metin if len(metin) <= sinir else metin[:sinir - 1] + "…"


def _kacis(metin: str) -> str:
    return (metin.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _kutu(d: akis.Dugum, adim: akis.Adim | None, y: int, gecikme: float,
          son: bool, ink: str) -> str:
    """Iki satirlik kompakt kutu: baslik + (gercek deger ya da parametre)."""
    durum = adim.durum if adim else akis.ATLANDI
    renk = RENK[durum]
    aktif = durum != akis.ATLANDI
    yuvarlak = KUTU_Y / 2 if d.tip in ("baslangic", "bitis") else 8
    ipucu = " — ".join(x for x in (d.baslik, d.alt,
                                   adim.metin if adim else "") if x)

    p = ['<g class="nd{}" style="animation-delay:{:.2f}s"><title>{}</title>'
         .format(" son" if son else "", gecikme, _kacis(ipucu))]
    p.append('<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
             'fill="{f}" stroke="{s}" stroke-width="{k}"/>'.format(
                 x=SOL, y=y, w=KUTU_G, h=KUTU_Y, r=yuvarlak,
                 f=theme.rgba(renk, 0.10 if aktif else 0.03), s=renk,
                 k=1.5 if aktif else 0.9))
    if d.tip == "kosul":
        p.append('<path d="M{x} {y} l5 5 l-5 5 l-5 -5 z" fill="{r}"/>'.format(
            x=SOL + 11, y=y + KUTU_Y / 2 - 5, r=renk))
    mx = SOL + (21 if d.tip == "kosul" else 11)

    p.append('<text x="{x}" y="{y}" fill="{c}" font-size="11.5" '
             'font-weight="{w}">{t}</text>'.format(
                 x=mx, y=y + 15, c=ink if aktif else theme.INK_DIM,
                 w=650 if d.tip in ("islem", "bitis") else 500,
                 t=_kacis(_kirp(d.baslik, 50))))
    if adim and adim.metin:
        p.append('<text x="{x}" y="{y}" fill="{c}" font-size="10" '
                 'font-weight="500">{t}</text>'.format(
                     x=mx, y=y + 29, c=renk, t=_kacis(_kirp(adim.metin, 60))))
    elif d.alt:
        p.append('<text x="{x}" y="{y}" fill="{c}" font-size="9.5">{t}</text>'
                 .format(x=mx, y=y + 29, c=theme.INK_DIM,
                         t=_kacis(_kirp(d.alt, 62))))
    p.append("</g>")
    return "".join(p)


def _dal(d: akis.Dugum, adim: akis.Adim | None, y: int, gecikme: float) -> str:
    """Kosulun 'hayir' tarafi: saga kisa ok + kucuk cikis kutusu."""
    if not d.hayir:
        return ""
    secildi = adim is not None and adim.durum == akis.KALDI
    renk = RENK[akis.KALDI] if secildi else theme.INK_DIM
    op = 1.0 if secildi else 0.5
    orta = y + KUTU_Y / 2
    x0 = SOL + KUTU_G
    x1 = x0 + DAL_ARA
    return (
        '<g class="ln" style="animation-delay:{g:.2f}s" opacity="{op}">'
        '<line x1="{x0}" y1="{o}" x2="{x1}" y2="{o}" stroke="{r}" '
        'stroke-width="1.1" marker-end="url(#ok{m})"/>'
        '<rect x="{x1}" y="{ry}" width="{w}" height="{h}" rx="{rx}" '
        'fill="none" stroke="{r}" stroke-width="1"/>'
        '<text x="{mx}" y="{my}" fill="{r}" font-size="9.5" '
        'text-anchor="middle">{t}</text></g>'.format(
            g=gecikme, op=op, x0=x0, x1=x1 - 1, o=orta, r=renk,
            m="k" if secildi else "s", ry=orta - DAL_Y / 2, w=DAL_G, h=DAL_Y,
            rx=DAL_Y / 2, mx=x1 + DAL_G / 2, my=orta + 3.2,
            t=_kacis(_kirp(d.hayir, 22))))


def _ok(y: int, gecikme: float, renk: str, evet: bool) -> str:
    """Iki kutu arasindaki kisa dikey ok."""
    x = SOL + 32
    return (
        '<g class="ln" style="animation-delay:{g:.2f}s">'
        '<line x1="{x}" y1="{y0}" x2="{x}" y2="{y1}" stroke="{r}" '
        'stroke-width="1.2" marker-end="url(#ok{m})"/>{e}</g>'.format(
            g=gecikme, x=x, y0=y + 1, y1=y + ARALIK - 4, r=renk,
            m="g" if renk == RENK[akis.GECTI] else "s",
            e='<text x="{}" y="{}" fill="{}" font-size="8.5">evet</text>'
              .format(x + 6, y + ARALIK / 2 + 3, renk) if evet else ""))


def cizim(dugumler: list[akis.Dugum], adimlar: list[akis.Adim],
          hiz: float, anahtar: str, gec: dict[str, float] | None = None,
          sinir: float | None = None) -> str:
    """Semayi SVG olarak uretir. `adimlar` bossa yalnizca kurallar gorunur.
    `gec` verilirse kutularin saniyesi oradan (mum grafigiyle es zaman).
    `sinir` (adim adim modu): saniyesi bundan sonra olan kutular henuz
    oynanmamistir -- soluk iskelet olarak hemen gorunur, sonuc yazmaz."""
    ink = charts.BASE["dark"]["ink"]
    durumlar = {a.kod: a for a in adimlar}
    yukseklik = 6 + len(dugumler) * (KUTU_Y + ARALIK) - ARALIK + 6

    p = ['<div class="dc-akis {a}"><svg viewBox="0 0 {w} {h}" '
         'xmlns="http://www.w3.org/2000/svg" role="img">'.format(
             a=anahtar, w=GENISLIK, h=yukseklik), "<defs>"]
    for ad, renk in (("g", RENK[akis.GECTI]), ("k", RENK[akis.KALDI]),
                     ("s", theme.INK_DIM)):
        p.append('<marker id="ok{}" markerWidth="6" markerHeight="6" refX="5" '
                 'refY="2.5" orient="auto"><path d="M0,0 L0,5 L5,2.5 z" '
                 'fill="{}"/></marker>'.format(ad, renk))
    p.append("</defs>")

    aktif = None
    if sinir is not None and gec:
        oynanan = [d.kod for d in dugumler if gec.get(d.kod, 0) <= sinir]
        aktif = oynanan[-1] if oynanan else None

    for n, d in enumerate(dugumler):
        y = 6 + n * (KUTU_Y + ARALIK)
        adim = durumlar.get(d.kod)
        g = gec.get(d.kod, n * hiz) if gec else n * hiz
        gelecek = sinir is not None and g > sinir
        if gelecek:                     # henuz oynanmadi: iskelet, animasyonsuz
            adim, g = None, -60.0
        # nabiz: normalde son kutu; adim adim modunda SIRADAKI (su anki) kutu
        son = (d.kod == aktif) if aktif else n == len(dugumler) - 1
        p.append(_kutu(d, adim, y, g, son, ink))
        p.append(_dal(d, adim, y, g + hiz * 0.3))
        if n < len(dugumler) - 1:
            sonraki = durumlar.get(dugumler[n + 1].kod)
            if sinir is not None and gec and gec.get(
                    dugumler[n + 1].kod, 0) > sinir:
                sonraki = None
            gecer = bool(adim and adim.durum == akis.GECTI and sonraki
                         and sonraki.durum != akis.ATLANDI)
            p.append(_ok(y + KUTU_Y, g + hiz * 0.6,
                         RENK[akis.GECTI] if gecer else theme.INK_DIM,
                         d.tip == "kosul" and bool(d.hayir)))
    p.append("</svg></div>")
    return "".join(p)


# --- mum grafigi olculeri ---
# Ustte iki satirlik bant: GIRIS ve CIKIS etiket kutulari burada durur,
# dikey kesikli cizgiyle mumlarin arasindaki noktaya baglanir.
MUM_G, MUM_Y = 640, 390
M_SOL, M_SAG, M_UST, M_ALT = 4, 60, 76, 22
BANT_Y, BANT_H = 4, 32
ONCE, SONRA, MUM_EN_FAZLA = 20, 8, 600
ISARET_RENK = {"stop": theme.DOWN, "hedef": theme.ACCENTS["aqua"],
               "notr": theme.INK}


AKIS_CARPAN, AKIS_BAR = 5.0, 20


def _son_zaman(i: akis.Isaret):
    """Isaretin grafikte ulastigi en gec an (bolge bitisiyle birlikte)."""
    return i.bitis if i.tur == "bolge" and i.bitis is not None else i.zaman


def zamanlama(dugumler: list[akis.Dugum], adimlar: list[akis.Adim],
              hiz: float, bars) -> dict[str, float]:
    """Her kutunun belirdigi saniye. Sema ve mum grafigi AYNI tabloyu kullanir.

    Temel: kutu basina `hiz` saniye. Ek: bir kutunun isareti grafikte
    oncekilerden ileride bir bara dusuyorsa (giris -> cikis gibi), aradaki
    mumlarin akabilmesi icin o kutudan once ek sure verilir -- en fazla
    `AKIS_CARPAN * hiz` (Normal'de 3 sn), AKIS_BAR bardan kisa araliklarda
    orantili olarak daha az. Strateji bilgisi yok; yalnizca isaretlerin
    zamanina bakar.
    """
    ts = bars["ts"] if bars is not None and not bars.is_empty() else None
    adim = {a.kod: a for a in adimlar}
    sonuc: dict[str, float] = {}
    an, onceki = 0.0, None
    for d in dugumler:
        a = adim.get(d.kod)
        if a is not None and a.isaretler and ts is not None and hiz > 0:
            j = max(int((ts <= _son_zaman(i)).sum()) for i in a.isaretler)
            if onceki is not None and j > onceki:
                an += hiz * AKIS_CARPAN * min(1.0, (j - onceki) / AKIS_BAR)
            onceki = j if onceki is None else max(onceki, j)
        sonuc[d.kod] = an
        an += hiz
    return sonuc


def adim_kesiti(gec: dict[str, float], dugumler: list[akis.Dugum], k: int,
                hiz: float) -> tuple[dict[str, float], float]:
    """Adim adim modu: ilk `k` kutu oynanmis sayilir.

    Gercek zaman tablosu (`zamanlama`) kaydirilir: (k-1). kutuya kadarki her
    sey eksi saniyeye duser (zaten bitmis, hemen gorunur), k. kutu ve onun
    getirdigi mum akisi 0'dan baslayip oynar. Doner: (kaydirilmis tablo,
    sinir) -- siniri asan her sey henuz yok sayilir.
    """
    kodlar = [d.kod for d in dugumler]
    k = max(1, min(k, len(kodlar)))
    pay = hiz * 0.6 + 0.05          # kutunun kendi oku/dali bu surede cizilir
    kay = gec[kodlar[k - 2]] + pay if k >= 2 else 0.0
    return ({kod: v - kay for kod, v in gec.items()},
            gec[kodlar[k - 1]] + pay - kay)


def _metin_g(metin: str, punto: float) -> float:
    """SVG metninin yaklasik genisligi (system-ui; olculdu: ortalama ~0,47 em)."""
    return len(metin) * punto * 0.49


def grafik(bars, adimlar: list[akis.Adim], dugumler: list[akis.Dugum],
           gec: dict[str, float], anahtar: str, egriler=(),
           timeframe: str = "4h", sinir: float | None = None,
           akis_bas: float = 0.0) -> tuple[str, str]:
    """Islemin cevresindeki mumlar + adimlarin isaretleri, SVG olarak.

    Zamanlama: isaretler kendi kutusuyla ayni anda belirir. Mumlar icin
    "capa" = (adimin en gec isaret zamani, kutunun saniyesi); iki capa
    arasindaki mumlar o iki saniye arasinda sirayla belirir. Boylece giris
    ile cikis arasindaki mumlar Giris -> Cikis kutulari arasinda akar
    (`akis_bas`: onceki kutunun oku cizildikten sonra baslasin diye gecikme).
    `sinir` (adim adim): saniyesi bundan sonra olan mum ve isaret CIZILMEZ --
    gelecek gorunmez, tipki gercek zamanda oldugu gibi.
    `neden` tasiyan nokta = ana olay (GIRIS / CIKIS): ustteki bantta etiket
    kutusu + dikey kesikli cizgi + buyuk nokta.
    Doner: (svg html, alt not).
    """
    isaretli = [(a, i) for a in adimlar for i in a.isaretler]
    if not isaretli or bars is None or bars.is_empty():
        return "", ""

    def gorunur(g: float) -> bool:
        return sinir is None or g <= sinir + 1e-6

    ts_hepsi = bars["ts"]
    zamanlar = [i.zaman for _, i in isaretli] + [
        i.bitis for _, i in isaretli if i.bitis is not None]
    ilk = int((ts_hepsi < min(zamanlar)).sum())
    son = int((ts_hepsi <= max(zamanlar)).sum()) - 1
    i0 = max(0, ilk - ONCE)
    i1 = min(bars.height - 1, son + SONRA)
    kirpildi = i1 - i0 + 1 > MUM_EN_FAZLA
    if kirpildi:
        i1 = i0 + MUM_EN_FAZLA - 1
    pen = bars.slice(i0, i1 - i0 + 1)
    ts = pen["ts"].to_list()
    o, h, l, c = (pen[k].to_list() for k in ("open", "high", "low", "close"))
    n = len(ts)

    def idx(t) -> int | None:
        """Zamanin penceredeki bar sirasi (tam eslesme yoksa oncesindeki)."""
        k = bisect_right(ts, t) - 1
        return k if 0 <= k < n else (n - 1 if k >= n else None)

    # --- olcek (tum pencere; adim adim ilerlerken eksen oynamasin) ---
    fiyatlar = [v for v in h + l if v is not None]
    fiyatlar += [i.fiyat for _, i in isaretli
                 if i.fiyat is not None and idx(i.zaman) is not None]
    alt, ust = min(fiyatlar), max(fiyatlar)
    pay = (ust - alt) * 0.06 or abs(ust) * 0.001 or 1.0
    alt, ust = alt - pay, ust + pay
    pw = MUM_G - M_SOL - M_SAG
    ph = MUM_Y - M_UST - M_ALT
    aralik = pw / n
    govde = max(1.0, min(9.0, aralik * 0.62))

    def x(j: float) -> float:
        return M_SOL + (j + 0.5) * aralik

    def y(v: float) -> float:
        return M_UST + (ust - v) / (ust - alt) * ph

    # --- capalar: mumlarin belirme saniyesi ---
    # Capa = (bar sirasi, ilk saniye, son saniye). Ayni bara birden cok kutu
    # dusebilir (Bar kapandi + Giris; Cikis + Sonuc): akis onceki capanin SON
    # saniyesinde baslar, sonrakinin ILK saniyesinde biter. Bolge'nin bitisi
    # de sayilir -- acik islemde Cikis kutusu isaret vermez, Sonuc bolgesi
    # verinin sonuna kadar uzanir ve akisi o tasir.
    capalar: list[list] = []
    for d in dugumler:
        a = next((a for a in adimlar if a.kod == d.kod and a.isaretler), None)
        if a is None:
            continue
        j = max((b for b in (idx(_son_zaman(i)) for i in a.isaretler)
                 if b is not None), default=None)
        if j is None:
            continue
        g = gec[a.kod]
        if capalar and j <= capalar[-1][0]:
            capalar[-1][2] = max(capalar[-1][2], g)
        else:
            capalar.append([j, g, g])

    def mum_gecikme(j: int) -> float:
        if not capalar or j <= capalar[0][0]:
            return capalar[0][1] if capalar else 0.0
        for (ja, _, ga), (jb, gb, _) in zip(capalar, capalar[1:]):
            if j <= jb:
                bas = min(gb, ga + akis_bas)
                return bas + (gb - bas) * (j - ja) / (jb - ja)
        return capalar[-1][1]

    gecik = [mum_gecikme(j) for j in range(n)]
    son_gorunen = max((j for j in range(n) if gorunur(gecik[j])), default=-1)

    ink = charts.BASE["dark"]["ink"]
    p = ['<div class="dc-mum {a}"><svg viewBox="0 0 {w} {h}" '
         'xmlns="http://www.w3.org/2000/svg" role="img">'.format(
             a=anahtar, w=MUM_G, h=MUM_Y)]

    # izgara + fiyat etiketleri (sagda)
    for k in range(5):
        v = alt + (ust - alt) * (k + 0.5) / 5
        p.append('<line x1="{a}" x2="{b}" y1="{y:.1f}" y2="{y:.1f}" '
                 'stroke="{r}" stroke-width="0.6"/>'
                 '<text x="{t}" y="{ty:.1f}" fill="{d}" font-size="9.5">{v}'
                 '</text>'.format(a=M_SOL, b=M_SOL + pw, y=y(v), r=theme.HAIRLINE,
                                  t=M_SOL + pw + 6, ty=y(v) + 3,
                                  d=theme.INK_DIM, v=_para(v)))
    # zaman etiketleri (altta, TR)
    bicim = "%d.%m" if timeframe in ("4h", "1d") else "%d.%m %H:%M"
    for k in range(5):
        j = round((n - 1) * (k + 0.5) / 5)
        p.append('<text x="{x:.1f}" y="{y}" fill="{d}" font-size="9.5" '
                 'text-anchor="middle">{t}</text>'.format(
                     x=x(j), y=MUM_Y - 6, d=theme.INK_DIM,
                     t=ts[j].astimezone(ZoneInfo(TZ)).strftime(bicim)))

    # bolgeler (en altta kalsin)
    for a, i in isaretli:
        g0 = gec.get(a.kod, 0)
        if i.tur != "bolge" or not gorunur(g0):
            continue
        ja, jb = idx(i.zaman), idx(i.bitis or i.zaman)
        if ja is None or jb is None:
            continue
        renk = ISARET_RENK.get(i.renk) or RENK[a.durum]
        p.append('<rect class="nd" style="animation-delay:{g:.2f}s" '
                 'x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" '
                 'fill="{f}"/>'.format(
                     g=g0, x=x(ja) - aralik / 2, y=M_UST,
                     w=(jb - ja + 1) * aralik, h=ph,
                     f=theme.rgba(renk, 0.07 if i.renk == "notr" else 0.10)))

    # gosterge egrileri: mumla birlikte parca parca belirir
    for sutun, _ad, renk_ad in egriler:
        if sutun not in pen.columns:
            continue
        seri = pen[sutun].to_list()
        renk = theme.ACCENTS.get(renk_ad, theme.INK_DIM)
        for j in range(1, son_gorunen + 1):
            if seri[j - 1] is None or seri[j] is None:
                continue
            p.append('<line class="mm" style="animation-delay:{g:.2f}s" '
                     'x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{d:.1f}" '
                     'stroke="{r}" stroke-width="1.1" opacity=".8"/>'.format(
                         g=gecik[j], a=x(j - 1), b=y(seri[j - 1]),
                         c=x(j), d=y(seri[j]), r=renk))

    # mumlar
    for j in range(son_gorunen + 1):
        if None in (o[j], h[j], l[j], c[j]):
            continue
        renk = theme.UP if c[j] >= o[j] else theme.DOWN
        ust_g, alt_g = y(max(o[j], c[j])), y(min(o[j], c[j]))
        p.append('<g class="mm" style="animation-delay:{g:.2f}s">'
                 '<line x1="{x:.1f}" x2="{x:.1f}" y1="{h:.1f}" y2="{l:.1f}" '
                 'stroke="{r}" stroke-width="0.9"/>'
                 '<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" '
                 'height="{bh:.1f}" fill="{r}"/></g>'.format(
                     g=gecik[j], x=x(j), h=y(h[j]), l=y(l[j]), r=renk,
                     bx=x(j) - govde / 2, by=ust_g, bw=govde,
                     bh=max(0.8, alt_g - ust_g)))

    # cizgiler (stop / hedef): giris kutusunda baslar, mumlarla uzar.
    # Adim adim: yalniz gorunen mumlara kadar (en az 3 bar, seviye okunsun).
    for a, i in isaretli:
        g0 = gec.get(a.kod, 0)
        if i.tur != "cizgi" or i.fiyat is None or not gorunur(g0):
            continue
        ja, jb = idx(i.zaman), idx(i.bitis or i.zaman)
        if ja is None or jb is None:
            continue
        if sinir is not None:
            jb = min(jb, max(son_gorunen, ja + 3))
        renk = ISARET_RENK.get(i.renk) or RENK[a.durum]
        sure = max(0.0, gecik[jb] - g0)
        p.append('<line class="uz" pathLength="1" style="animation-delay:'
                 '{g:.2f}s;animation-duration:{s:.2f}s" x1="{a:.1f}" '
                 'x2="{b:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{r}" '
                 'stroke-width="1.3" opacity=".9"/>'
                 '<text class="nd" style="animation-delay:{g:.2f}s" '
                 'x="{a:.1f}" y="{ty:.1f}" fill="{r}" font-size="10" '
                 'font-weight="600">{t} {v}</text>'.format(
                     g=g0, s=sure, a=x(ja), b=x(jb), y=y(i.fiyat), r=renk,
                     ty=y(i.fiyat) + 13, t=_kacis(i.etiket),
                     v=_para(i.fiyat)))

    # oklar ve sade noktalar
    olaylar = []
    for a, i in isaretli:
        j = idx(i.zaman)
        g0 = gec.get(a.kod, 0)
        if j is None or i.tur not in ("ok", "nokta") or not gorunur(g0):
            continue
        if i.tur == "nokta" and i.neden and i.fiyat is not None:
            olaylar.append((a, i, j, g0))
            continue
        renk = ISARET_RENK.get(i.renk) or RENK[a.durum]
        if i.tur == "ok":
            if i.yon == 1:     # AL: mumun altinda, yukari bakan
                ty = y(l[j]) + 5
                sekil = "M{x:.1f} {y:.1f} l5 8 l-10 0 z"
                ey = ty + 19
            else:              # SAT: mumun ustunde, asagi bakan
                ty = y(h[j]) - 5
                sekil = "M{x:.1f} {y:.1f} l5 -8 l-10 0 z"
                ey = ty - 11
            p.append('<g class="nd" style="animation-delay:{g:.2f}s">'
                     '<path d="{d}" fill="{r}"/><text x="{x:.1f}" y="{ey:.1f}" '
                     'fill="{r}" font-size="9.5" font-weight="700" '
                     'text-anchor="middle">{t}</text></g>'.format(
                         g=g0, d=sekil.format(x=x(j), y=ty), r=renk, x=x(j),
                         ey=ey, t=_kacis(i.etiket)))
        elif i.fiyat is not None:
            ey = y(i.fiyat) + (16 if i.yon == 1 else -9)
            p.append('<g class="nd" style="animation-delay:{g:.2f}s">'
                     '<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{r}" '
                     'stroke="{bg}" stroke-width="1.5"/>'
                     '<text x="{x:.1f}" y="{ey:.1f}" fill="{ink}" '
                     'font-size="9.5" font-weight="650" text-anchor="middle">'
                     '{t}</text></g>'.format(
                         g=g0, x=x(j), y=y(i.fiyat), r=renk, bg=theme.PANEL,
                         ey=ey, ink=ink, t=_kacis(i.etiket)))

    # ANA OLAYLAR: GIRIS / CIKIS -- ustte etiket kutusu, dikey cizgi, buyuk
    # nokta. Ilk olay ust satirda, ikincisi alt satirda (ust uste binmesin).
    # Giris rengi yon (AL yesil / SAT kirmizi), cikis rengi islemin sonucu.
    sonuc_renk = RENK[adimlar[-1].durum] if adimlar else theme.INK
    for sira, (a, i, j, g0) in enumerate(olaylar):
        giris = sira == 0
        renk = ((theme.UP if i.yon == 1 else theme.DOWN) if giris
                else sonuc_renk)
        satir1 = "{} · {} · {}".format(
            i.etiket, _para(i.fiyat),
            ts[j].astimezone(ZoneInfo(TZ)).strftime("%d.%m %H:%M"))
        satir2 = "neden: " + i.neden
        kg = max(_metin_g(satir1, 10.5), _metin_g(satir2, 9.5)) + 18
        ky = BANT_Y + (sira % 2) * (BANT_H + 3)
        kx = min(max(M_SOL, x(j) - kg / 2), M_SOL + pw - kg)
        p.append(
            '<g class="nd" style="animation-delay:{g:.2f}s">'
            '<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0:.1f}" y2="{y1:.1f}" '
            'stroke="{r}" stroke-width="1.2" stroke-dasharray="3 3" '
            'opacity=".8"/>'
            '<rect x="{kx:.1f}" y="{ky}" width="{kg:.1f}" height="{kh}" rx="6" '
            'fill="{bg}" stroke="{r}" stroke-width="1.4"/>'
            '<text x="{tx:.1f}" y="{t1:.1f}" fill="{r}" font-size="10.5" '
            'font-weight="750">{s1}</text>'
            '<text x="{tx:.1f}" y="{t2:.1f}" fill="{ink}" font-size="9.5">'
            '{s2}</text>'
            '<circle cx="{x:.1f}" cy="{py:.1f}" r="9.5" fill="{halka}"/>'
            '<circle cx="{x:.1f}" cy="{py:.1f}" r="5.5" fill="{r}" '
            'stroke="{bg}" stroke-width="1.8"/></g>'.format(
                g=g0, x=x(j), y0=ky + BANT_H, y1=M_UST + ph, r=renk,
                kx=kx, ky=ky, kg=kg, kh=BANT_H, bg=theme.PANEL,
                tx=kx + 9, t1=ky + 13, t2=ky + 26, s1=_kacis(satir1),
                s2=_kacis(satir2), ink=ink, py=y(i.fiyat),
                halka=theme.rgba(renk, 0.32)))
    p.append("</svg></div>")

    not_ = "{} mum{} · TR saati · isaretler semadaki kutuyla ayni anda belirir".format(
        n, " (ilk {} mum gosteriliyor, islem daha uzun)".format(MUM_EN_FAZLA)
        if kirpildi else "")
    return "".join(p), not_


def _efsane() -> str:
    return (
        '<div class="dc-efsane">'
        '<span><i style="color:{g}">●</i>saglandi</span>'
        '<span><i style="color:{k}">●</i>saglanmadi / zarar</span>'
        '<span><i style="color:{s}">●</i>sirasi gelmedi</span>'
        '<span>◆ karar kutusu</span></div>'.format(
            g=RENK[akis.GECTI], k=RENK[akis.KALDI], s=theme.INK_DIM))


def _kart(islem: dict) -> str:
    """Secilen islemin kucuk ozet karti (sol sutun)."""
    tz = ZoneInfo(TZ)
    al = islem["yon"] == 1
    acik = islem["neden"] == "veri_sonu"
    getiri = islem["getiri"]
    renk_yon = RENK[akis.GECTI] if al else RENK[akis.KALDI]
    renk_sonuc = (theme.INK_DIM if acik and getiri == 0 else
                  RENK[akis.GECTI] if getiri > 0 else RENK[akis.KALDI])
    return (
        '<div class="dc-kart"><div class="ust">'
        '<span class="yon" style="color:{ry};border-color:{ry}">{yon}</span>'
        '<span class="dim">{sure}</span>'
        '<span class="sonuc" style="color:{rs}">{sonuc}</span></div>'
        '<div><span class="dim">Giris</span> {gt} @ <b>{gp}</b></div>'
        '<div><span class="dim">Cikis</span> {cikis}</div></div>'.format(
            ry=renk_yon, yon="AL" if al else "SAT",
            sure=_sure(islem["cikis_ts"] - islem["giris_ts"]),
            rs=renk_sonuc, sonuc=_yuzde(islem) + (" acik" if acik else ""),
            gt=islem["giris_ts"].astimezone(tz).strftime("%d.%m %H:%M"),
            gp=_para(islem["giris"]),
            cikis="islem hala acik" if acik else "{} @ <b>{}</b>".format(
                islem["cikis_ts"].astimezone(tz).strftime("%d.%m %H:%M"),
                _para(islem["cikis"]))))


# Adim adim modunun klavyesi. Streamlit'in dugme kisayolu (shortcut="Space")
# denendi, iki sorunu vardi (21.09.2026): "Adim adim" secilince imlec secim
# kutusunda kaliyor ve Streamlit yazi alani odaktayken kisayolu yok sayiyor
# -- kullanici bosluga basinca liste aciliyordu. Bu dinleyici YAKALAMA
# asamasinda calisir: bosluk / → "Ileri"ye, ← "◀"e basar; imlec kapali bir
# secim kutusundaysa onu da birakir. Adim modu kapaliyken dugmeler yok,
# dinleyici hicbir sey yapmaz. Sayfaya bir kez eklenir.
_TUS_DINLEYICI = """
<script>
(function () {
  if (window.__dcAdimTus) return;
  window.__dcAdimTus = true;
  function dugme(bas) {
    return Array.from(document.querySelectorAll('button')).find(
      function (b) { return b.innerText.trim().indexOf(bas) === 0; });
  }
  document.addEventListener('keydown', function (e) {
    var hedef = (e.key === ' ' || e.code === 'Space' || e.key === 'ArrowRight')
      ? 'Ileri' : (e.key === 'ArrowLeft' ? '◀' : null);
    if (!hedef || e.ctrlKey || e.altKey || e.metaKey) return;
    var b = dugme(hedef);
    if (!b) return;
    var t = e.target;
    if (t && t.tagName === 'TEXTAREA') return;
    if (t && t.tagName === 'INPUT' && t.getAttribute('role') !== 'combobox') return;
    if (t && t.getAttribute && t.getAttribute('aria-expanded') === 'true') return;
    e.preventDefault();
    e.stopPropagation();
    if (e.repeat) return;
    if (t && t.blur) t.blur();
    b.click();
  }, true);
})();
</script>
"""


def _anlik(dugumler: list[akis.Dugum], adimlar: list[akis.Adim],
           k: int) -> str:
    """Adim adim modunda su anki kutunun seridi: numara, kural, sonuc."""
    d = dugumler[max(1, min(k, len(dugumler))) - 1]
    a = next((a for a in adimlar if a.kod == d.kod), None)
    renk = RENK[a.durum] if a else theme.INK_DIM
    return (
        '<div class="dc-anlik" style="border-color:{r}">'
        '<span class="no" style="background:{r}">{k}/{n}</span>'
        '<span class="b">{b}</span><span class="m" style="color:{r}">{m}</span>'
        '<span class="ipucu">BOSLUK / → = ileri · ← = geri</span></div>'.format(
            r=renk, k=k, n=len(dugumler), b=_kacis(d.baslik),
            m=_kacis(a.metin if a and a.metin else "bu sinyalde sirasi gelmedi")))


def _adim_listesi(dugumler: list[akis.Dugum], adimlar: list[akis.Adim]) -> str:
    satirlar = []
    basliklar = {d.kod: d.baslik for d in dugumler}
    for n, a in enumerate((a for a in adimlar if a.kod in basliklar), 1):
        satirlar.append(
            '<li><span class="no">{n}</span><span class="nokta" '
            'style="background:{r}"></span><span><span class="b">{b}</span>'
            '<br><span class="m">{m}</span></span></li>'.format(
                n=n, r=RENK[a.durum], b=_kacis(basliklar[a.kod]),
                m=_kacis(a.metin or "—")))
    return '<ul class="dc-adimlar">{}</ul>'.format("".join(satirlar))


# ==========================================================================
# EKRAN
# ==========================================================================
def render(strat: dict, cfg, timeframe: str, tf_label: str) -> None:
    """Stratejiler > <strateji> > Kural akisi bolumu."""
    from finans_cortex.instruments import INSTRUMENTS

    from .strategies import motor      # gec import: dongusel bagimlilik

    m = motor(strat["temel"])
    if not akis.destekli(m):
        st.info("Bu strateji icin akis semasi henuz tanimlanmadi.")
        return

    dugumler = m.sema(cfg)
    st.markdown(_CSS.format(
        maks=GENISLIK + 40, mum_maks=MUM_G + 80,
        vurgu=theme.rgba(RENK[akis.GECTI], 0.85),
        panel=theme.PANEL, hair=theme.HAIRLINE, ink=theme.INK,
        dim=theme.INK_DIM), unsafe_allow_html=True)

    # DUZEN (21.09.2026, mum grafigi eklenince): uc sutunda sema ~300 px'e
    # dusup okunmaz oluyordu. Denetimler ustte TEK ince satir; altinda sema
    # (kendi boyunda) ile mum grafigi yan yana; adim listesi katlanir kutuda.
    ust = st.columns([0.8, 1.3, 0.62, 0.75, 1.55], gap="small",
                     vertical_alignment="bottom")
    code = ust[0].selectbox(
        "Varlik", [i.code for i in INSTRUMENTS], index=1, key="akis_varlik",
        help="Sema kenar cubugundaki zaman dilimi ve parametrelerle "
             "hesaplanir; parametre degisince kutular da degisir.")
    try:
        res = _sonuc(strat["temel"], code, timeframe, cfg)
    except Exception as exc:      # noqa: BLE001 -- kullaniciya gosterilir
        st.error("Sinyaller hesaplanamadi: {}".format(exc))
        return
    islemler = ([] if res.trades.is_empty() else
                list(reversed(res.trades.tail(EN_FAZLA).to_dicts())))

    islem = None
    adimlar: list[akis.Adim] = []
    hiz = 0.0
    sayac = 0
    adim_modu = False
    k = 0
    if islemler:
        secim = ust[1].selectbox(
            "Sinyal (son {})".format(len(islemler)), range(len(islemler)),
            format_func=lambda k: _etiket(islemler[k]),
            key="akis_sinyal_" + code,
            help="En yenisi ustte. Saat = girisin olustugu bar (TR).")
        hiz_ad = ust[2].selectbox(
            "Hiz", list(HIZLAR) + [ADIM_ADIM], index=1, key="akis_hiz",
            help="Adim adim: her BOSLUK tusunda bir kutu ilerler "
                 "(◀ ile geri).")
        islem = islemler[secim]
        adimlar = m.izle(res.bars, islem, cfg, timeframe)
        ust[4].markdown(_kart(islem), unsafe_allow_html=True)

        adim_modu = hiz_ad == ADIM_ADIM
        if adim_modu:
            # Adim adim (kullanici, 21.09.2026: "space tusuna bastikca
            # ilerlesin"). Streamlit 1.59 dugmesi klavye kisayolu alir.
            # Sinyal / varlik / ayar degisince bastan (1. kutu) baslar.
            imza = (strat["key"], code, secim, timeframe, len(dugumler))
            if st.session_state.get("akis_adim_imza") != imza:
                st.session_state["akis_adim_imza"] = imza
                st.session_state["akis_adim"] = 1
            geri_c, ileri_c = ust[3].columns([1, 2.2], gap="small")
            geri = geri_c.button("◀", key="akis_geri", width="stretch",
                                 help="Bir adim geri (← tusu)")
            ileri = ileri_c.button("Ileri ▶", key="akis_ileri",
                                   type="primary", width="stretch",
                                   help="Bir adim ileri (BOSLUK ya da → tusu)")
            st.html(_TUS_DINLEYICI, unsafe_allow_javascript=True)
            k = st.session_state["akis_adim"]
            if ileri:
                k = min(len(dugumler), k + 1)
            if geri:
                k = max(1, k - 1)
            st.session_state["akis_adim"] = k
            hiz = HIZLAR["Normal"]
            sayac = k
        else:
            oynat = ust[3].button("▶ Oynat", type="primary", width="stretch")
            sayac = st.session_state.get("akis_sayac", 0) + (1 if oynat else 0)
            st.session_state["akis_sayac"] = sayac
            if sayac:
                hiz = HIZLAR[hiz_ad]
    else:
        st.info("{} icin son {} gunde bu ayarlarla sinyal yok.".format(
            code, GUN.get(timeframe, 180)))

    gec = zamanlama(dugumler, adimlar, hiz, res.bars)
    sinir = None
    if adim_modu:
        gec, sinir = adim_kesiti(gec, dugumler, k, hiz)
        st.markdown(_anlik(dugumler, adimlar, k), unsafe_allow_html=True)
    anahtar = "r{} t{}".format(sayac, sayac % 2)
    sol, sag = st.columns([1, 1.3], gap="medium")
    with sol:
        st.markdown(cizim(dugumler, adimlar, hiz, anahtar, gec, sinir),
                    unsafe_allow_html=True)
        st.markdown(_efsane(), unsafe_allow_html=True)
    with sag:
        if islem is None:
            return
        from .strategies import BASE
        svg, not_ = grafik(res.bars, adimlar, dugumler, gec, anahtar,
                           BASE[strat["temel"]].get("egriler", ()), timeframe,
                           sinir=sinir, akis_bas=hiz * 0.65)
        if svg:
            st.markdown(svg, unsafe_allow_html=True)
            st.markdown('<div class="dc-mum-not">{}</div>'.format(not_),
                        unsafe_allow_html=True)
        else:
            st.caption("Bu strateji grafik isareti vermiyor.")
        with st.expander("Adimlar (yazili)"):
            st.markdown(_adim_listesi(dugumler, adimlar),
                        unsafe_allow_html=True)

"""Ana ekran: baslik, canli fiyat seridi, ikon menu.

Menu kutucuklari Streamlit dugmesi DEGIL, bagimsiz <a> baglantisidir.
Sebep: Streamlit dugmesinin ic duzenine (ikon + baslik + aciklama, kare
oran, neon cerceve) mudahale edilemiyor. Baglanti ile tam gorsel denetim
bizde kaliyor ve yonlendirme adres cubugundaki ?ekran= parametresiyle
yapiliyor -- yer imine eklenebilir olmasi da bonus.
"""

from __future__ import annotations

import html

import polars as pl
import streamlit as st

from . import theme

# Serit icin enstrumanlar. Kod -> ekranda gorunecek ad.
TICKERS = {
    "XAUUSD": "Altin (ons)",
    "XAGUSD": "Gumus (ons)",
    "EURUSD": "EUR / USD",
    "BRENT": "Brent",
    "BTCUSD": "Bitcoin",
    "DJ": "Dow Jones",
}

# Serit rengi: her kutuya kategorik paletten sabit bir renk.
TICK_COLORS = ["yellow", "blue", "aqua", "orange", "violet", "magenta"]

ICONS = {
    "piyasalar": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><path d="M3 20.5h18"/>
        <rect x="4.5" y="12" width="3.6" height="6"/>
        <rect x="10.2" y="8" width="3.6" height="10"/>
        <rect x="15.9" y="4" width="3.6" height="14"/></svg>""",
    "grafikler": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><path d="M7 2.5v3.2M7 16v5.5"/>
        <rect x="4.5" y="5.7" width="5" height="10.3" rx="1"/>
        <path d="M17 4v4.6M17 18.4v2.4"/>
        <rect x="14.5" y="8.6" width="5" height="9.8" rx="1"/></svg>""",
    "stratejiler": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><rect x="3.5" y="4" width="17" height="4.2" rx="1.4"/>
        <rect x="3.5" y="9.9" width="17" height="4.2" rx="1.4"/>
        <rect x="3.5" y="15.8" width="17" height="4.2" rx="1.4"/></svg>""",
    "yaratma": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><path d="M3.5 20.5 13 11"/>
        <path d="M16.6 2.8l1.35 3.15L21.1 7.3l-3.15 1.35L16.6 11.8l-1.35-3.15
        L12.1 7.3l3.15-1.35z"/><path d="M6.4 4.2l.7 1.6 1.6.7-1.6.7-.7 1.6
        -.7-1.6-1.6-.7 1.6-.7z"/></svg>""",
    "backtest": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><path d="M3.4 12a8.6 8.6 0 1 0 2.7-6.3"/>
        <path d="M3 3.8v4.4h4.4"/><path d="M12 7.6V12l3.3 2"/></svg>""",
    "veri": """<svg viewBox="0 0 24 24" width="42" height="42" fill="none"
        stroke="currentColor" stroke-width="1.4" stroke-linecap="round"
        stroke-linejoin="round"><ellipse cx="12" cy="5.7" rx="7.6" ry="3.1"/>
        <path d="M4.4 5.7v12.6c0 1.7 3.4 3.1 7.6 3.1s7.6-1.4 7.6-3.1V5.7"/>
        <path d="M4.4 12c0 1.7 3.4 3.1 7.6 3.1s7.6-1.4 7.6-3.1"/></svg>""",
}

# (anahtar, baslik, aciklama, renk, hazir mi)
MENU = [
    ("piyasalar", "Piyasalar", "Tum enstrumanlarin anlik durumu, "
     "gunluk degisim ve siralama", "blue", False),
    ("grafikler", "Grafikler", "Mum grafigi, Chandelier Exit ve MACD "
     "sinyalleri, coklu zaman dilimi", "aqua", True),
    ("stratejiler", "Stratejiler", "Strateji listesi, guncel AL/SAT "
     "sinyalleri (takip listesi + BIST 30) ve backtest", "violet", True),
    ("yaratma", "Strateji Yaratma", "Gosterge ve kurallari birlestirerek "
     "yeni strateji tanimla", "orange", False),
    ("backtest", "Backtest", "Strateji, varlik ve tarih araligi sec; "
     "islemler, kar/zarar, grafik ve sermaye egrisi", "magenta", True),
    ("veri", "Veri Merkezi", "Veri tazeligi, tek tikla guncelleme, "
     "varlik kapsami ve kalite denetimi", "yellow", True),
]


def _fresh_html(tazelik: tuple[str, bool] | None) -> str:
    """Basligin sagindaki veri tazeligi rozeti (Veri Merkezi'ne baglanti)."""
    if tazelik is None:
        return ""
    metin, bayat = tazelik
    return (
        '<a class="dc-fresh{sinif}" href="?ekran=veri" target="_self" '
        'title="Veri Merkezi: guncelle, kapsam, kalite">'
        '<span class="dot">●</span> Veri: {metin}{ek}</a>'.format(
            sinif=" stale" if bayat else "", metin=html.escape(metin),
            ek=" · guncelleyin" if bayat else "")
    )


def _fmt_price(value: float) -> str:
    """Turk sayi bicimi: binlik nokta, ondalik virgul.

    Ondalik basamak buyuklukten turetilir -- EURUSD'de 5 hane gerekir,
    Bitcoin'de 5 hane sacma olur.
    """
    if value is None:
        return "-"
    if value >= 1000:
        s = "{:,.2f}".format(value)
    elif value >= 10:
        s = "{:,.3f}".format(value)
    else:
        s = "{:,.5f}".format(value)
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


def _fmt_change(pct: float | None) -> tuple[str, str]:
    """(metin, renk). Yon renge EK OLARAK ok ve isaretle de veriliyor."""
    if pct is None:
        return "—", theme.INK_DIM
    ok = "▲" if pct >= 0 else "▼"
    return "{} {:+.2f}%".format(ok, pct).replace(".", ","), (
        theme.UP if pct >= 0 else theme.DOWN)


def _ticker_html(snap: pl.DataFrame) -> str:
    if snap.is_empty():
        return ""
    rows = []
    for i, r in enumerate(snap.iter_rows(named=True)):
        color = theme.ACCENTS[TICK_COLORS[i % len(TICK_COLORS)]]
        txt, col = _fmt_change(r["change_pct"])
        rows.append(
            '<div class="dc-tick" style="--c:{c}">'
            '<span class="n">{ad}</span>'
            '<span class="p">{fiyat}</span>'
            '<span class="d" style="color:{dc}">{deg}</span>'
            "</div>".format(
                c=color, ad=TICKERS.get(r["code"], r["code"]),
                fiyat=_fmt_price(r["close"]), dc=col, deg=txt,
            )
        )
    return '<div class="dc-ticker">{}</div>'.format("".join(rows))


def _menu_html() -> str:
    tiles = []
    for key, baslik, aciklama, renk, hazir in MENU:
        c = theme.ACCENTS[renk]
        tiles.append(
            '<a class="dc-tile{ready}" href="?ekran={key}" target="_self" '
            'style="--c:{c};--c-dim:{cdim};--c-glow:{cglow}">'
            '<span class="soon">{rozet}</span>'
            '<span class="ico">{ico}</span>'
            '<span><span class="lbl">{baslik}</span>'
            '<div class="desc">{aciklama}</div></span>'
            "</a>".format(
                ready=" ready" if hazir else "", key=key, c=c,
                cdim=theme.rgba(c, 0.30), cglow=theme.rgba(c, 0.34),
                rozet="hazir" if hazir else "yakinda",
                ico=ICONS[key], baslik=baslik, aciklama=aciklama,
            )
        )
    return '<div class="dc-grid">{}</div>'.format("".join(tiles))


def render(snap: pl.DataFrame, son_guncelleme: str,
           tazelik: tuple[str, bool] | None = None) -> None:
    """Ana ekran. `tazelik` = (metin, bayat mi) -- basligin sagindaki rozet.

    Rozet Veri Merkezi'ne baglanti: "veri eski" gorulen anda tek tikla
    guncelleme ekrani acilsin diye (kullanici istegi, 20.09.2026).
    """
    st.markdown(theme.css(), unsafe_allow_html=True)
    st.markdown(
        '<div class="dc-head">'
        '<h1 class="dc-title">Deep<b>Cortex</b></h1>'
        '<p class="dc-sub">Finansal Analiz Platformu</p>'
        '{}</div>'
        '<div class="dc-rule"></div>'.format(_fresh_html(tazelik)),
        unsafe_allow_html=True,
    )
    st.markdown(_ticker_html(snap), unsafe_allow_html=True)
    st.markdown(_menu_html(), unsafe_allow_html=True)
    st.markdown(
        '<div class="dc-foot">Veri: Dukascopy · '
        "Son bar: {} · Gunluk degisim bir onceki gun kapanisina gore"
        "</div>".format(son_guncelleme),
        unsafe_allow_html=True,
    )

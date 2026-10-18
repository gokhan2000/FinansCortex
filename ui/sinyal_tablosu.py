"""Sinyal tablosu: secilen varlikta son N AL/SAT sinyalinin kisa raporu.

Kural akisi ekraniyla ayni sinyal kaynagi (`akis._sonuc`), ama ekranin tamami
tablo: baslangic fiyati, son fiyat, islem boyunca en dusuk/en yuksek fiyat,
kar/zarar yuzdesi ve tutari. Hesap burada degil motorun islem listesinde;
min/max yalniz o islemin baslangic-bitis aralindaki barlardan okunur.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import streamlit as st

from . import akis, theme

TZ = akis.TZ
ADETLER = (10, 20, 30, 50)


def _tl(v: float) -> str:
    s = "{:,.2f}".format(abs(v)).replace(",", " ").replace(".", ",").replace(
        " ", ".")
    return "{}${}".format("-" if v < 0 else "+" if v > 0 else "", s)


def _yz(v: float) -> str:
    return "{}%{:.2f}".format("+" if v > 0 else "-" if v < 0 else "",
                              abs(v)).replace(".", ",")


def _satirlar(res, adet: int, kapital: float, kaldirac: float) -> list[dict]:
    bars = res.bars
    ts = bars["ts"]
    son_kapanis = float(bars["close"][-1])
    tz = ZoneInfo(TZ)
    satirlar = []
    for t in reversed(res.trades.tail(adet).to_dicts()):
        d = t["yon"]
        g = t["giris"]
        acik = t["neden"] == "veri_sonu"
        i0 = int((ts < t["giris_ts"]).sum())
        i1 = int((ts <= t["cikis_ts"]).sum()) - 1
        icinde = bars.slice(i0, max(1, i1 - i0 + 1))
        alt = float(icinde["low"].min())
        ust = float(icinde["high"].max())
        # Yone gore en iyi / en kotu ara durum (giristen, % olarak)
        if d == 1:
            mfe, mae = (ust - g) / g * 100, (alt - g) / g * 100
        else:
            mfe, mae = (g - alt) / g * 100, (g - ust) / g * 100
        getiri = t["getiri"]
        satirlar.append(dict(
            yon=d, acik=acik, getiri=getiri,
            tutar=getiri * kapital * kaldirac,
            sure=t["cikis_ts"] - t["giris_ts"], neden=t["neden"],
            giris=g, son=son_kapanis if acik else t["cikis"],
            alt=alt, ust=ust, mfe=mfe, mae=mae,
            giris_s=t["giris_ts"].astimezone(tz)))
    return satirlar


def _ozet(satirlar: list[dict]) -> None:
    kapali = [s for s in satirlar if not s["acik"]] or satirlar
    kaz = [s for s in kapali if s["getiri"] > 0]
    kay = [s for s in kapali if s["getiri"] <= 0]
    toplam = sum(s["tutar"] for s in satirlar)
    kar = sum(s["tutar"] for s in kaz)
    zarar = -sum(s["tutar"] for s in kay)
    seri = en_uzun = 0                       # ust uste kayip (kronolojik)
    for s in reversed(satirlar):
        seri = seri + 1 if s["getiri"] <= 0 else 0
        en_uzun = max(en_uzun, seri)
    ort_k = _yz(sum(s["getiri"] for s in kaz) * 100 / len(kaz)) if kaz else "-"
    ort_z = _yz(sum(s["getiri"] for s in kay) * 100 / len(kay)) if kay else "-"
    c = st.columns(6)
    c[0].metric("Net", _tl(toplam))
    c[1].metric("Kazanma orani", "%{:.0f}".format(100 * len(kaz) / len(kapali)))
    c[2].metric("Ort. kazanc / kayip", "{} / {}".format(ort_k, ort_z))
    c[3].metric("Kar faktoru", "{:.2f}".format(kar / zarar).replace(".", ",")
                if zarar > 0 else "-")
    c[4].metric("Ust uste kayip", str(en_uzun))
    c[5].metric("En iyi / en kotu",
                "{} / {}".format(_yz(max(s["getiri"] for s in satirlar) * 100),
                                 _yz(min(s["getiri"] for s in satirlar) * 100)))


def _tablo(satirlar: list[dict]) -> str:
    yesil, kirmizi = theme.UP, theme.DOWN
    baslik = ("Giris (TR)", "Yon", "Baslangic", "Son fiyat",
              "En dusuk", "En yuksek", "En iyi ara", "En kotu ara",
              "Sure", "Cikis nedeni", "Kar/Zarar %", "Kar/Zarar $")
    h = "".join("<th>{}</th>".format(b) for b in baslik)
    govde = []
    for s in satirlar:
        renk = yesil if s["getiri"] > 0 else kirmizi if s["getiri"] < 0 else \
            theme.INK_DIM
        govde.append(
            "<tr><td>{t}</td><td style='color:{yr};font-weight:700'>{yon}"
            "</td><td>{g}</td><td>{son}{acik}</td><td>{alt}</td><td>{ust}"
            "</td><td style='color:{yesil}'>{mfe}</td>"
            "<td style='color:{kirmizi}'>{mae}</td><td>{sure}</td><td>{nd}"
            "</td><td style='color:{r};font-weight:700'>{y}</td>"
            "<td style='color:{r};font-weight:700'>{p}</td></tr>".format(
                t=s["giris_s"].strftime("%d.%m %H:%M"),
                yr=yesil if s["yon"] == 1 else kirmizi,
                yon="AL" if s["yon"] == 1 else "SAT",
                g=akis._para(s["giris"]), son=akis._para(s["son"]),
                acik=" <i>(acik)</i>" if s["acik"] else "",
                alt=akis._para(s["alt"]), ust=akis._para(s["ust"]),
                mfe=_yz(s["mfe"]), mae=_yz(s["mae"]),
                sure=akis._sure(s["sure"]),
                nd="acik" if s["acik"] else s["neden"], r=renk,
                yesil=yesil, kirmizi=kirmizi,
                y=_yz(s["getiri"] * 100), p=_tl(s["tutar"])))
    return (
        "<style>.dc-st{{width:100%;border-collapse:collapse;font-size:12.5px}}"
        ".dc-st th{{text-align:right;color:{dim};font-weight:600;padding:5px "
        "8px;border-bottom:1px solid {hair};white-space:nowrap}}"
        ".dc-st td{{text-align:right;padding:5px 8px;border-bottom:1px solid "
        "{hair};white-space:nowrap}}"
        ".dc-st th:first-child,.dc-st td:first-child{{text-align:left}}"
        ".dc-st tr:hover td{{background:{panel}}}</style>"
        "<div style='overflow-x:auto'><table class='dc-st'><thead><tr>{h}"
        "</tr></thead><tbody>{b}</tbody></table></div>".format(
            dim=theme.INK_DIM, hair=theme.HAIRLINE, panel=theme.PANEL,
            h=h, b="".join(govde)))


def render(strat: dict, cfg, timeframe: str, tf_label: str) -> None:
    """Stratejiler > <strateji> > Sinyal tablosu bolumu."""
    from finans_cortex.instruments import INSTRUMENTS

    ust = st.columns([1, 0.8, 0.8, 0.8, 2], gap="small",
                     vertical_alignment="bottom")
    code = ust[0].selectbox("Varlik", [i.code for i in INSTRUMENTS], index=1,
                            key="st_varlik")
    adet = ust[1].selectbox("Son kac sinyal", ADETLER, index=1, key="st_adet")
    kapital = ust[2].number_input("Kapital ($)", min_value=10.0, value=1000.0,
                                  step=100.0, key="st_kapital")
    kaldirac = ust[3].number_input("Kaldirac (x)", min_value=1.0, value=1.0,
                                   step=1.0, key="st_kaldirac")
    try:
        res = akis._sonuc(strat["temel"], code, timeframe, cfg)
    except Exception as exc:      # noqa: BLE001 -- kullaniciya gosterilir
        st.error("Sinyaller hesaplanamadi: {}".format(exc))
        return
    if res.trades.is_empty():
        st.info("{} icin son {} gunde bu ayarlarla sinyal yok.".format(
            code, akis.GUN.get(timeframe, 180)))
        return
    satirlar = _satirlar(res, adet, kapital, kaldirac)
    ust[4].caption(
        "Son {} sinyal · {} · maliyet dahil · her islemde ayni kapital. "
        "En dusuk/en yuksek = islem suresince goren fiyat; en iyi/en kotu "
        "ara = girisinize gore.".format(len(satirlar), tf_label))
    _ozet(satirlar)
    st.markdown(_tablo(satirlar), unsafe_allow_html=True)

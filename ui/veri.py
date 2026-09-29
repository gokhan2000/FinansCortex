"""Veri Merkezi ekrani -- tazelik, guncelleme, kapsam, kalite denetimi.

NEDEN AYRI BIR EKRAN
"Verileri guncelle" dugmesi Grafikler'in kenar cubugunda ve Stratejiler >
Sinyaller bolumunde vardi; uzaktan baglanildiginda "veriyi nereden
guncelleyecegim" diye aranmasi gerekiyordu (kullanicinin sorusu, 20.09.2026).
Artik ana menuden tek tik: veri ile ilgili her sey burada.

UZAKTAN BAGLIYKEN DE CALISIR: dugmeye isteki tarayicidan basilir ama
indirme EV BILGISAYARINDA olur (program orada calisiyor). Internet de
oradan kullanilir.

Anayasa 2.4: bu dosya SQL yazmaz; kapsam/kalite sorgulari finans_cortex
altinda (storage.coverage, quality.report).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import polars as pl
import streamlit as st

from finans_cortex import quality, storage

from . import charts, theme

TZ = "Europe/Istanbul"

# Hafta sonu piyasa kapali: Cuma kapanisindan sonra 2 gun gecikme normaldir.
ESKI_GUN = 3


def _tr(ts: datetime | None) -> str:
    return ts.astimezone(ZoneInfo(TZ)).strftime("%d.%m.%Y %H:%M") if ts else "-"


def _yas(delta: timedelta | None) -> str:
    """Ortak bicim (charts.age_text): ana ekran ve Grafikler ile ayni dil."""
    return charts.age_text(delta)


def _boyut() -> str:
    try:
        mb = storage.DEFAULT_DB_PATH.stat().st_size / 1e6
    except OSError:
        return "-"
    return "{:.0f} MB".format(mb)


def _sayi(v: int) -> str:
    return "{:,}".format(v).replace(",", ".")


def render() -> None:
    st.sidebar.markdown("[← Ana ekran](?ekran=home)")
    st.sidebar.title("Veri Merkezi")
    st.sidebar.caption("Veri yalnizca siz istediginizde guncellenir; "
                       "arayuz kendiliginden indirmez.")

    st.markdown(theme.css(), unsafe_allow_html=True)
    st.subheader("Veri Merkezi", anchor=False)

    cov = charts.load_coverage()
    son, yas = charts.data_age()

    # ---------------- tazelik + guncelleme ----------------
    if "veri_sonuc" in st.session_state:
        eklenen = st.session_state.pop("veri_sonuc")
        if isinstance(eklenen, str):
            st.error("Guncelleme basarisiz: {}".format(eklenen))
        elif eklenen:
            st.success("{} yeni bar eklendi.".format(_sayi(eklenen)))
        else:
            st.success("Veri zaten guncel; yeni bar yok.")

    # Uc olcu yeter: dar ekranda (telefon, is dizustu) bes sutun rakamlari
    # kirpiyordu. Varlik sayisi ve dosya boyutu alt satirda yaziyla.
    c = st.columns(3)
    c[0].metric("Son bar (TR)", _tr(son))
    c[1].metric("Yas", _yas(yas),
                help="En yeni barin uzerinden gecen sure.")
    c[2].metric("Toplam bar",
                _sayi(int(cov["bars"].sum())) if not cov.is_empty() else "-")
    st.caption("{} varlik · {} veritabani · kaynak: Dukascopy".format(
        cov.height, _boyut()))

    if yas is not None and yas > timedelta(days=ESKI_GUN):
        st.warning("En yeni bar **{}** once. Ekrandaki fiyatlar ve sinyaller "
                   "guncel DEGIL. Asagidaki dugmeye basin.".format(_yas(yas)))
    elif yas is not None:
        st.info("Veri guncel gorunuyor. (Hafta sonu piyasa kapali oldugu icin "
                "Cuma kapanisindan sonra 2 gune kadar gecikme normaldir.)")

    c = st.columns([1.3, 3])
    if c[0].button("Verileri guncelle", type="primary", width="stretch"):
        with st.spinner("Dukascopy'den eksik barlar cekiliyor... (~15-60 sn)"):
            try:
                st.session_state["veri_sonuc"] = charts.refresh_data()
            except Exception as exc:      # noqa: BLE001 -- ag/dosya hatasi
                st.session_state["veri_sonuc"] = str(exc)
        st.rerun()
    c[1].caption("Eksik barlar Dukascopy'den cekilir, kaldigi yerden devam "
                 "eder. Gunluk artimli guncelleme ~15 saniye surer. **Uzaktan "
                 "bagliyken de calisir** -- indirme ev bilgisayarinda yapilir.")

    # ---------------- BIST 30 gecmisi ----------------
    st.divider()
    st.markdown("**BIST 30 -- backtest gecmisi**")
    if "bist_sonuc" in st.session_state:
        r = st.session_state.pop("bist_sonuc")
        if isinstance(r, str):
            st.error("BIST guncellemesi basarisiz: {}".format(r))
        else:
            mesaj = "{} yeni bar, {} hisse.".format(_sayi(r["eklenen"]), r["hisse"])
            if r["alinamayan"]:
                mesaj += " Alinamayan: {}".format(", ".join(r["alinamayan"][:5]))
            if r["atlanan"]:
                mesaj += " Verisi yetersiz: {}".format(", ".join(r["atlanan"][:5]))
            (st.warning if (r["alinamayan"] or r["atlanan"]) else st.success)(mesaj)

    bcov = charts.load_bist_coverage()
    if bcov.is_empty():
        st.info("BIST gecmisi henuz indirilmedi. Backtest ve Gelistir "
                "ekranlarinda BIST 30'u secebilmek icin bir kez indirin.")
    else:
        gun = bcov.filter(pl.col("timeframe") == "1d")
        sa = bcov.filter(pl.col("timeframe") == "1h")
        c = st.columns(3)
        c[0].metric("Hisse", int(bcov["code"].n_unique()))
        c[1].metric("Gunluk bar", _sayi(int(gun["bars"].sum())) if not gun.is_empty() else "-")
        c[2].metric("Saatlik bar", _sayi(int(sa["bars"].sum())) if not sa.is_empty() else "-")
        if not gun.is_empty():
            st.caption("Gunluk: {} -> {} · kaynak: Yahoo (duzeltilmis fiyat)".format(
                _tr(gun["first_ts"].min()), _tr(gun["last_ts"].max())))

    c = st.columns([1.3, 3])
    if c[0].button("BIST gecmisini guncelle", width="stretch"):
        with st.spinner("Yahoo'dan 30 hissenin gecmisi cekiliyor... (~15 sn)"):
            try:
                st.session_state["bist_sonuc"] = charts.refresh_bist()
            except Exception as exc:      # noqa: BLE001 -- ag/dosya hatasi
                st.session_state["bist_sonuc"] = str(exc)
        st.rerun()
    c[1].caption("Gunluk ~21 yil, saatlik ~3 yil (Yahoo'nun siniri). Fiyatlar "
                 "**bedelsiz ve temettuye gore duzeltilmis**; duzeltilmemis "
                 "seride sahte trend donusu sinyali cikiyordu. 2005 para "
                 "reformu oncesi veri bozuk oldugu icin alinmaz.")

    # ---------------- kapsam ----------------
    st.markdown("**Varlik bazinda kapsam**")
    simdi = datetime.now(timezone.utc)
    tablo = cov.sort("code").select(
        pl.col("code").alias("Varlik"),
        pl.col("first_ts").dt.convert_time_zone(TZ)
        .dt.strftime("%d.%m.%Y").alias("Ilk bar (TR)"),
        pl.col("last_ts").dt.convert_time_zone(TZ)
        .dt.strftime("%d.%m.%Y %H:%M").alias("Son bar (TR)"),
        pl.col("bars").alias("Bar sayisi"),
    ).to_pandas()
    tablo["Yas"] = [
        _yas(simdi - ts) if ts is not None else "-"
        for ts in cov.sort("code")["last_ts"].to_list()
    ]
    st.dataframe(tablo, width="stretch", hide_index=True)
    st.caption("Barlar 15 dakikalik; 1 saat / 4 saat / gunluk gorunumler "
               "bunlardan turetilir. Saatler Turkiye (UTC+3).")

    # ---------------- kalite ----------------
    with st.expander("Kalite denetimi"):
        st.caption("Eksik gun, hayalet (donuk) bar ve tutarsiz fiyat araniyor. "
                   "Okuma yapar, hicbir sey silmez.")
        if st.button("Denetimi calistir"):
            with st.spinner("Denetleniyor..."):
                st.session_state["veri_kalite"] = quality.report(
                    charts.get_connection())
        rapor = st.session_state.get("veri_kalite")
        if rapor is not None:
            st.dataframe(pd.DataFrame(rapor.to_pandas()), width="stretch",
                         hide_index=True)
            st.caption(
                "**eksik_gun/eksik_oran:** hafta ici gunlerde beklenenden az "
                "bar. Yuzde 0-1,5 normaldir (tatiller). · **hayalet_gun:** "
                "piyasa kapaliyken beslemenin ayni fiyati tekrarladigi gun -- "
                "bunlar temizlendi, yeniden cikarsa `clean_ghost_bars.py` ile "
                "silinir. · **sorunlu_bar:** high < low gibi tutarsizliklar; "
                "0 olmali.")

    st.caption("Veri kaynagi: Dukascopy · Guncelleme yalnizca bu dugmeyle, "
               "BASLAT.bat / UZAKTAN.bat acilisinda ya da Grafikler ekraninin "
               "kenar cubugundan yapilir.")

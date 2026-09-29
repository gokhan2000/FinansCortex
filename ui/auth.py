"""Parola kapisi -- yalnizca uzaktan eriside devrede.

`UZAKTAN.bat` arayuzu baslatirken `FINANS_ERISIM` ortam degiskenine parola
jetonunu koyar (bkz. finans_cortex/erisim.py). Degisken yoksa -- yani program
normal sekilde `BASLAT.bat` ile acildiysa -- bu dosya HICBIR SEY yapmaz:
kendi bilgisayarinda her acilista parola sormak gereksiz surtunmedir.

Kapi `app.py`'de, ekran yonlendiricisinden ONCE cagrilir; parola dogru
degilse `st.stop()` ile sayfanin geri kalani hic calismaz -- veri katmanina
tek bir sorgu bile gitmez.

KABA KUVVET: her yanlis denemede 1 saniye beklenir, 5 yanlisten sonra o
oturum 60 saniye kilitlenir. Saldirgan yeni oturum acarak kilidi asabilir;
asil koruma parolanin kendisidir, bu yalnizca deneme hizini kirar.
"""

from __future__ import annotations

import os
import time

import streamlit as st

from finans_cortex import erisim

from . import theme

_ANAHTAR = "_erisim_ok"
_SAYAC = "_erisim_yanlis"
_KILIT = "_erisim_kilit"
EN_FAZLA = 5
KILIT_SN = 60

_CSS = """
<style>
 .dc-kapi {{
    max-width:460px; margin:8vh auto 0 auto; text-align:center;
 }}
 .dc-kapi .mark {{
    font-size:30px; letter-spacing:.22em; color:{ink}; font-weight:250;
 }}
 .dc-kapi .alt {{
    font-size:13px; color:{dim}; line-height:1.7; margin-top:10px;
 }}
</style>
"""


def gerekli() -> bool:
    """Bu calistirmada parola sorulacak mi."""
    return bool(os.environ.get(erisim.ENV_JETON))


def kapi() -> None:
    """Parola dogrulanana kadar sayfayi durdurur."""
    if not gerekli() or st.session_state.get(_ANAHTAR):
        return

    jeton = os.environ[erisim.ENV_JETON]
    st.markdown(theme.css() + _CSS.format(ink=theme.INK, dim=theme.INK_DIM),
                unsafe_allow_html=True)
    st.markdown(
        '<div class="dc-kapi"><div class="mark">DEEPCORTEX</div>'
        '<div class="alt">Bu baglanti internete acik. Devam etmek icin '
        'erisim parolasini girin.</div></div>',
        unsafe_allow_html=True,
    )

    orta = st.columns([1, 2, 1])[1]
    with orta:
        kalan = st.session_state.get(_KILIT, 0) - time.time()
        if kalan > 0:
            st.error("Cok fazla yanlis deneme. {} saniye sonra tekrar "
                     "deneyin.".format(int(kalan) + 1))
            st.stop()

        # clear_on_submit: yanlis denemeden sonra kutu bosalsin, kullanici
        # eski metnin ustune yazmaya calismasin.
        with st.form("erisim_formu", clear_on_submit=True):
            parola = st.text_input("Parola", type="password",
                                   label_visibility="collapsed",
                                   placeholder="Erisim parolasi")
            gonder = st.form_submit_button("Gir", type="primary",
                                           width="stretch")
        if gonder:
            if erisim.dogrula(parola, jeton):
                st.session_state[_ANAHTAR] = True
                st.session_state[_SAYAC] = 0
                st.rerun()
            time.sleep(1)      # deneme hizini kir
            yanlis = st.session_state.get(_SAYAC, 0) + 1
            st.session_state[_SAYAC] = yanlis
            if yanlis >= EN_FAZLA:
                st.session_state[_KILIT] = time.time() + KILIT_SN
                st.session_state[_SAYAC] = 0
                st.error("Cok fazla yanlis deneme. {} saniye "
                         "bekleyin.".format(KILIT_SN))
            else:
                st.error("Parola yanlis. ({}/{})".format(yanlis, EN_FAZLA))
        st.caption("Parolayi unuttuysaniz: bilgisayarinizda `config/erisim.json` "
                   "dosyasini silin, `UZAKTAN.bat` bir sonraki aciliste yenisini "
                   "sorar.")
    st.stop()


def rozet() -> None:
    """Kenar cubugunda 'uzaktan erisim acik' hatirlaticisi."""
    if gerekli():
        st.sidebar.caption("🔓 Uzaktan erisim acik - adresi kimseyle paylasmayin.")

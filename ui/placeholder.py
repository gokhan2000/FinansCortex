"""Henuz yapilmamis ekranlar icin gecici sayfa.

Kullanici "ikonlardan baglanacagimiz ekranlar ile hic ilgilenme, onlari tek
tek yapacagiz" dedi. Bos beyaz sayfa yerine, ekranin ne is yapacagini
soyleyen ve geri donus veren bir sayfa gosteriyoruz -- tiklayinca hicbir sey
olmamasi bozuk gibi hissettirir.
"""

from __future__ import annotations

import streamlit as st

from . import theme
from .home import ICONS, MENU

_BY_KEY = {k: (baslik, aciklama, renk) for k, baslik, aciklama, renk, _ in MENU}


def render(key: str) -> None:
    baslik, aciklama, renk = _BY_KEY.get(
        key, ("Bilinmeyen ekran", "Bu adres tanimli degil.", "blue")
    )
    c = theme.ACCENTS[renk]

    st.markdown(theme.css(), unsafe_allow_html=True)
    st.markdown(
        """
<style>
 .dc-ph {{
    max-width:560px; margin:8vh auto 0 auto; text-align:center;
    background:{panel}; border:1px solid {cdim}; border-radius:16px;
    padding:44px 34px 38px 34px;
 }}
 .dc-ph .ico {{color:{c}; filter:drop-shadow(0 0 10px {cglow});}}
 .dc-ph h2 {{
    font-size:22px; font-weight:500; letter-spacing:.05em; color:{ink};
    margin:16px 0 8px 0;
 }}
 .dc-ph p {{font-size:13px; color:{dim}; line-height:1.6; margin:0 0 26px 0;}}
 .dc-ph .rozet {{
    display:inline-block; font-size:10px; letter-spacing:.14em;
    text-transform:uppercase; color:{c}; border:1px solid {cdim};
    border-radius:20px; padding:4px 12px; margin-bottom:6px;
 }}
 .dc-back {{
    display:inline-block; margin-top:6px; font-size:13px; color:{c};
    text-decoration:none; border-bottom:1px solid {cdim}; padding-bottom:2px;
 }}
 .dc-back:hover {{border-color:{c};}}
</style>
<div class="dc-ph">
  <span class="rozet">yakinda</span>
  <div class="ico">{ico}</div>
  <h2>{baslik}</h2>
  <p>{aciklama}</p>
  <a class="dc-back" href="?ekran=home" target="_self">← Ana ekrana don</a>
</div>
""".format(
            panel=theme.PANEL, ink=theme.INK, dim=theme.INK_DIM, c=c,
            cdim=theme.rgba(c, 0.30), cglow=theme.rgba(c, 0.34),
            ico=ICONS.get(key, ICONS["veri"]), baslik=baslik,
            aciklama=aciklama,
        ),
        unsafe_allow_html=True,
    )

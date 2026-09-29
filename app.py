"""DeepCortex Finans -- giris noktasi ve ekran yonlendirici.

Calistirma:  BASLAT.bat  (ya da terminalde: streamlit run app.py)

YAPI
  app.py          bu dosya: hangi ekranin cizilecegine karar verir
  ui/theme.py     renk paleti + neon stil
  ui/home.py      ana ekran (baslik, fiyat seridi, ikon menu)
  ui/charts.py    Grafikler ekrani
  ui/placeholder.py  henuz yapilmamis ekranlar
  src/finans_cortex/  veri ve hesap katmani (arayuzden tamamen bagimsiz)

UZAKTAN ERISIM
Program internete acildiginda (UZAKTAN.bat) arayuzun onune bir parola
kapisi konur: ui/auth.py. Normal aciliste (BASLAT.bat) kapi yoktur.

YONLENDIRME
Ekran secimi adres cubugundaki ?ekran= parametresiyle yapilir. Menu
kutucuklari normal <a> baglantisi oldugu icin tarayicinin ileri/geri
tuslari ve yer imleri kendiliginden calisir.

KENAR CUBUGU
Ana ekranda kenar cubuguna hicbir sey yazilmaz; Streamlit de bos kenar
cubugunu hic cizmez. Boylece giris ekrani tertemiz kalir. Ic ekranlar
kendi denetimlerini yazar ve cubuk kendiliginden belirir (Streamlit'in
kendi ac/kapa dugmesiyle birlikte).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

st.set_page_config(
    page_title="DeepCortex Finans",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="auto",
)

from finans_cortex import bulut, storage  # noqa: E402
from ui import (auth, backtest, charts, home, placeholder,  # noqa: E402
                strategies, theme, veri)

# Bulutta veritabani yoksa bulut_veri/*.parquet'ten kurulur (yerelde: hicbir sey).
if bulut.hazirla():  # yeni veri kuruldu: eski baglanti/onbellekler atilsin
    st.cache_resource.clear()
    st.cache_data.clear()

HAZIR = {
    "grafikler": charts.render,
    "stratejiler": strategies.render,
    "backtest": backtest.render,
    "veri": veri.render,
}


@st.cache_data(ttl=120, show_spinner=False)
def _snapshot():
    """Ana ekrandaki fiyat seridi. Grafik ekraniyla AYNI baglantiyi kullanir --
    DuckDB tek yaziciya izin verdigi icin ikinci bir baglanti acmiyoruz."""
    return storage.latest_snapshot(
        charts.get_connection(), list(home.TICKERS)
    )


def main() -> None:
    # Ortak sayfa kurallari (ust bosluk yok) -- her ekrandan once.
    st.markdown(theme.global_css(), unsafe_allow_html=True)

    # Parola kapisi: yalnizca UZAKTAN.bat ile acildiginda devrede. Dogru
    # parola girilene kadar asagisi hic calismaz (veriye sorgu bile gitmez).
    auth.kapi()

    ekran = st.query_params.get("ekran", "home")

    if ekran in HAZIR:
        HAZIR[ekran]()
        # Uzaktan erisim rozeti yalnizca kenar cubugu ZATEN kullanilan
        # ekranlarda: strateji listesinde cubuk bos durur, tek bir satir
        # icin acilmasi ekrani bozardi (ana ekrandaki gerekcenin aynisi).
        if ekran != "stratejiler" or st.query_params.get("strateji"):
            auth.rozet()
        return

    if ekran == "home":
        snap = _snapshot()
        son = "-"
        if not snap.is_empty():
            son = snap["ts"].max().strftime("%d.%m.%Y %H:%M UTC")
        # Tazelik rozeti Grafikler ve Veri Merkezi ile AYNI kaynaktan
        # (charts.data_age -> kapsam tablosu) gelir ki uc ekran ayni seyi
        # soylesin.
        home.render(snap, son, charts.freshness())
        return

    placeholder.render(ekran)


if __name__ == "__main__":
    main()

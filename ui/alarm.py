"""Alarmlar ekrani: hangi varlik / zaman dilimi / strateji icin telefona mesaj.

Kullanici (9 Kasim 2026): *"neler gelecegini programdan belirleyelim; bazilari
icin 15 dakikalik sinyal de istiyorum."*

Ayar config/alarm.json'a yazilir. Alarmi GitHub Actions calistirir
(.github/workflows/cikis_alarm.yml -> scripts/cikis_izle.py), yani ayarin
GitHub'a GITMESI gerekir: "GitHub'a gonder" dugmesi yalnizca bu tek dosyayi
commit + push eder. Evdeki programda calisir; bulut kopyasinda yalniz gosterir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st

from finans_cortex import alarm, storage
from finans_cortex.instruments import HESAP_KODLARI

from . import theme

ROOT = Path(__file__).resolve().parents[1]
TF_AD = {tf: ad for tf, (_, _, ad) in alarm.ZAMANLAR.items()}


def _bulutta_mi() -> bool:
    """bulut.hazirla bulutta veritabaninin yanina .imza yazar."""
    return storage.DEFAULT_DB_PATH.with_suffix(".imza").exists()


def _git(*args: str) -> tuple[bool, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                       text=True, timeout=120)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def _gonder() -> tuple[bool, str]:
    """config/alarm.json'u GitHub'a yollar (baska dosyaya dokunmaz)."""
    kimlik = ["-c", "user.name=DeepCortex", "-c",
              "user.email=deepcortex@users.noreply.github.com"]
    ok, cikti = _git("add", "config/alarm.json")
    if not ok:
        return False, cikti
    ok, cikti = _git(*kimlik, "commit", "-m", "Alarm ayari guncellendi",
                     "--", "config/alarm.json")
    if not ok and "nothing to commit" not in cikti \
            and "no changes added" not in cikti:
        return False, cikti
    ok, cikti = _git(*kimlik, "pull", "--rebase", "origin", "main")
    if not ok:
        return False, cikti
    ok, cikti = _git("push", "origin", "main")
    return ok, cikti


def _tablo(key: str, secim: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Varlik": kod,
          **{TF_AD[tf]: tf in secim.get(kod, []) for tf in alarm.ZAMANLAR}}
         for kod in HESAP_KODLARI])


def _secimden(df: pd.DataFrame) -> dict:
    out = {}
    for _, r in df.iterrows():
        tfler = [tf for tf in alarm.ZAMANLAR if bool(r[TF_AD[tf]])]
        if tfler:
            out[r["Varlik"]] = tfler
    return out


def _tahmin(saat15: list[int], var15: bool) -> str:
    if not var15:
        return ("Yalniz 4 saatlik / gunluk kapanislarda calisir; GitHub "
                "dakikasi neredeyse hic harcanmaz.")
    bas, bit = saat15
    calisma = max(0, bit - bas) * 4
    dk = calisma * 1.7 * 22
    uyari = " **Ucretsiz 2000 dakikayi asabilir.**" if dk > 1500 else ""
    return ("15 dk alarm {} saat boyunca 15 dakikada bir calisir (gunde ~{} "
            "calisma, her biri ~1-2 dk). Tahmini ay: ~{:.0f} GitHub dakikasi "
            "(ucretsiz sinir 2000; gercegini GitHub > Settings > Billing'de "
            "gorursun).{}".format(bit - bas, calisma, dk, uyari))


def render() -> None:
    st.markdown(theme.css(), unsafe_allow_html=True)
    st.markdown('<a class="dc-back" href="?ekran=home" target="_self">'
                '← Ana ekran</a>', unsafe_allow_html=True)
    st.subheader("Alarmlar", anchor=False)
    st.caption(
        "Secili stratejide yeni bir **giris / cikis** olunca telefonuna "
        "(ntfy) mesaj gelir. Kontrolu GitHub yapar, bilgisayarin kapali "
        "olabilir. Mesaj bir strateji SIMULASYONUDUR: gercek pozisyonunu "
        "bilmez, \"stratejiye gore su varlikta pozisyon kapanir\" der.")

    ayar = alarm.yukle()
    tanim = alarm.stratejiler()
    secili_vars = [k for k in ayar["stratejiler"] if k in tanim]
    keys = st.multiselect(
        "Izlenecek stratejiler", list(tanim), default=secili_vars,
        format_func=lambda k: tanim[k][0],
        help="Strateji 2, 3, 4 ve kayitli varyantlari. Strateji 1 (EMA, gun "
             "ici) alarmda desteklenmez.")

    yeni: dict = {}
    for key in keys:
        eski = ayar["stratejiler"].get(key, {})
        with st.container(border=True):
            st.markdown("**{}**".format(tanim[key][0]))
            c = st.columns(2)
            giris = c[0].checkbox("Giris mesaji", eski.get("giris", True),
                                  key="al_g_" + key)
            cikis = c[1].checkbox("Cikis mesaji", eski.get("cikis", True),
                                  key="al_c_" + key)
            df = st.data_editor(
                _tablo(key, eski.get("secim", {})), hide_index=True,
                key="al_t_" + key, width="stretch", disabled=["Varlik"],
                column_config={TF_AD[tf]: st.column_config.CheckboxColumn(
                    TF_AD[tf]) for tf in alarm.ZAMANLAR})
            yeni[key] = {"giris": giris, "cikis": cikis,
                         "secim": _secimden(df)}

    var15 = any("15m" in tfs for k in yeni.values()
                for tfs in k["secim"].values())
    saat15 = list(ayar.get("saat15", [10, 22]))
    if var15:
        s = st.slider("15 dk alarm saatleri (Turkiye saati)", 0, 24,
                      tuple(saat15), key="al_saat15",
                      help="15 dakikada bir calisma GitHub'in ucretsiz "
                           "dakikasini yer; yalniz bu saatlerde calisir.")
        saat15 = list(s)
        st.info("15 dakikalik periyotta strateji kenari zayiftir (daha onceki "
                "olcumde 15 dk'da brut bile eksiydi); alarm bunu degistirmez.")
    st.caption(_tahmin(saat15, var15))

    hedef = {"saat15": saat15, "stratejiler": yeni}
    degisti = hedef != {"saat15": ayar.get("saat15", [10, 22]),
                        "stratejiler": ayar["stratejiler"]}
    bulut = _bulutta_mi()
    c = st.columns([1, 1.3, 2.7])
    if c[0].button("Kaydet", type="primary", disabled=bulut or not degisti):
        alarm.kaydet(hedef)
        st.session_state["al_kayit"] = True
        st.rerun()
    if bulut:
        st.warning("Bu bulut kopyasi. Ayar yalniz evdeki programdan "
                   "degistirilir.")
    elif st.session_state.pop("al_kayit", False):
        st.success("Kaydedildi. Alarmin calismasi icin **GitHub'a gonder**.")
    if c[1].button("GitHub'a gonder (alarm calissin)", disabled=bulut):
        with st.spinner("GitHub'a gonderiliyor..."):
            ok, cikti = _gonder()
        (st.success if ok else st.error)(
            "GitHub'a gonderildi. Alarm bir sonraki kontrolde yeni ayari "
            "kullanir." if ok else "Gonderilemedi:\n\n" + cikti)
    n = sum(len(v["secim"]) for v in yeni.values())
    st.caption("{} strateji · {} varlik secimi. Ilk kurulum: telefona ntfy "
               "uygulamasi + GitHub'da NTFY_KONU gizli anahtari "
               "(docs/KURULUM_VE_TASIMA.md).".format(len(yeni), n))

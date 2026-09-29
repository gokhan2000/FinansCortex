"""Backtest paneli -- kullanici stratejiyi kendisi calistirir.

IKI GIRIS KAPISI, TEK PANEL
  - Ana ekrandaki Backtest menusu (?ekran=backtest)  -> render()
  - Stratejiler > strateji > Backtest bolumu          -> panel()
Kullanici once "backtest'i Backtest menusune koy, ben kontrol ederim" dedi,
sonra "Stratejilerde de kalsin / ikisini birlestirelim". Panel tek yerde.

IKI MOD
  Tek backtest            ayarlari sec, dugmeye bas, sonuc sekmelerde.
                          Hicbir sey kendiliginden calismaz.
  Canli parametre ayari   kaydiricilari oynat, kar/zarar ANINDA degissin;
                          begenilen ayar "Farkli kaydet" ile yeni strateji
                          olur (finans_cortex/strategy_store.py).

CANLI AYAR NEDEN HIZLI
  - st.fragment: kaydirici degisince yalniz bu bolum yeniden calisir.
  - Ham barlar st.cache_resource'ta KOPYALANMADAN tutulur (cache_data her
    okumada pickle kopyasi cikarirdi). Her harekette yalniz EMA + simulasyon
    dongusu calisir.
  - Baslangic degerleriyle karsilastirma sonucu da onbellekte.

ISLEM INCELEMESI (kullanici: "ne zaman al vermis ne zaman sat vermis,
nasil kazanmis nasil kaybetmis -- hem tablo hem grafik")
  Islemler sekmesinde tablodan bir satira tiklayinca ALTINDA o islemin
  grafigi acilir: giris/cikis, stop, hedef, islemin yolu ve -- strateji
  veriyorsa -- her gostergenin o civarda verdigi sinyaller. Boylece "bu
  islem neden kaybetti" ve "bu sinyal neden alinmadi" ayni ekranda gorulur.
  Grafik sekmesi ayni seyin donem gezintisi: pencere boyu + bitis tarihi
  kaydiricisi ile tum aralikta gezilir.

ASIRI UYUM (curve fitting) KONTROLU
  Ayni veride parametreyi uzun uzun oynatmak gecmisi "ezberleyen" bir ayar
  bulur. Aralik %70 ayar / %30 kontrol diye bolunup yan yana gosterilir.
  Yeniden simulasyon yok: tek sonucun islemleri giris zamanina gore bolunur.

Donem her iki modda iki TARIHLE secilir (baslangic / bitis TR gunu, dahil).

PANEL STRATEJIDEN BAGIMSIZ. Hangi motorun calisacagini, hangi zaman
dilimlerinin secilebilecegini ve grafige hangi egrilerin cizilecegini
ui/strategies.py'deki strateji kaydi soyler. Onbellekli fonksiyonlara motor
modulu degil temel strateji ANAHTARI (str) geciyor -- modul nesnesi
hash'lenemez.

Anayasa 2.4: bu dosya SQL yazmaz; hesap finans_cortex altindaki motorlarda.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from finans_cortex import backtest as bt_cost, storage, strategy_store
from finans_cortex.instruments import HESAP_KODLARI, get as get_instrument

from . import charts, theme
from .strategies import (BASE, TZ, all_strategies, diff_text, label, motor,
                         param_keys, param_widgets, pct, tf_index, timeframes)

LAST_N = 10
MAX_BARS = 4000     # tek grafikte cizilecek en fazla mum (plotly yavaslamasin)
MAX_MARK_BARS = 600  # gosterge sinyali isaretleri bu barin altinda cizilir
PRESETS = {"1 ay": 30, "3 ay": 91, "1 yil": 365, "3 yil": 1095, "Tumu": None}
MODES = ["Tek backtest", "Canli parametre ayari"]
SPLIT = 0.7   # asiri uyum kontrolu: ilk %70 ayar, son %30 kontrol


def _utc_range(start: date, end: date) -> tuple[datetime, datetime]:
    """TR gunlerini [baslangic 00:00, bitis+1 00:00) UTC araligina cevirir."""
    tz = ZoneInfo(TZ)
    return (datetime.combine(start, time(0, 0), tzinfo=tz).astimezone(timezone.utc),
            datetime.combine(end + timedelta(days=1), time(0, 0),
                             tzinfo=tz).astimezone(timezone.utc))


# Iki piyasa, tek panel (23 Eylul 2026, kullanici: "BIST 30 hisseleri icinde
# ayri bir backtest yapma olanagimiz olsun"). BIST verisi AYRI tabloda
# (bars_bist), kaynagi Yahoo, maliyeti daha yuksek; bu yuzden her veri
# yardimcisi hangi piyasada oldugunu bilmek zorunda.
PIYASALAR = {"Kuresel {}".format(len(HESAP_KODLARI)): "kuresel", "BIST 30": "bist"}
BIST_TF = ("1d", "1h")            # Yahoo gecmisi: gunluk ~21 yil, saatlik ~3 yil


def _seans(code: str, piyasa: str = "kuresel") -> str:
    """Grafikte hafta sonunun gizlenip gizlenmeyecegi (`rangebreaks`).

    BIST hisseleri `instruments` kayit defterinde YOK (bilerek -- 9 kuresel
    varligin listelerine karismasinlar). Kayit defterine sorulursa
    `KeyError: bilinmeyen enstruman: AKBNK` verir; BIST hafta ici calistigi
    icin kuresel varliklarla ayni "24h" davranisi dogru.
    """
    if piyasa == "bist":
        return "24h"
    return get_instrument(code).session


def _kodlar(piyasa: str) -> list[str]:
    if piyasa == "bist":
        cov = charts.load_bist_coverage()
        return sorted(cov["code"].unique().to_list()) if not cov.is_empty() else []
    return list(HESAP_KODLARI)


@st.cache_data(ttl=600, show_spinner=False)
def _run(temel: str, code: str, timeframe: str, start: date, end: date, cfg,
         piyasa: str = "kuresel"):
    s, e = _utc_range(start, end)
    if piyasa == "bist":
        return motor(temel).run_bars(
            _raw_bars(code, timeframe, "bist"), code, timeframe, cfg,
            start=s, end=e, cost_bp=bt_cost.bist_cost_for(code).roundtrip_bp)
    return motor(temel).run(charts.get_connection(), code, timeframe, cfg,
                            start=s, end=e)


@st.cache_resource(ttl=600, max_entries=8, show_spinner=False)
def _raw_bars(code: str, timeframe: str, piyasa: str = "kuresel") -> pl.DataFrame:
    con = charts.get_connection()
    if piyasa == "bist":
        return storage.read_bist_bars(con, code, timeframe)
    return storage.read_bars(con, code, timeframe)


@st.cache_resource(ttl=600, max_entries=64, show_spinner=False)
def _lab_run(temel: str, code: str, timeframe: str, start: date, end: date, cfg,
             piyasa: str = "kuresel"):
    s, e = _utc_range(start, end)
    # 15 dakikalik teyit acikken (Strateji 2 onay_15m) ikinci cerceve gerekir.
    # Kapaliyken okunmaz -- panel eskisi kadar hizli kalir. BIST'te 15 dakikalik
    # gecmis yok (Yahoo ~3 ay), o yuzden teyit orada devre disi kalir.
    ek = (_raw_bars(code, "15m") if piyasa == "kuresel"
          and getattr(cfg, "onay_15m", False) else None)
    maliyet = (bt_cost.bist_cost_for(code).roundtrip_bp if piyasa == "bist"
               else None)
    return motor(temel).run_bars(_raw_bars(code, timeframe, piyasa), code,
                                 timeframe, cfg, start=s, end=e, bars_15m=ek,
                                 cost_bp=maliyet)


def _bounds(code: str, piyasa: str = "kuresel",
            timeframe: str = "1d") -> tuple[date, date]:
    """Varligin verisinin ilk ve son gunu (TR)."""
    tz = ZoneInfo(TZ)
    if piyasa == "bist":
        row = charts.load_bist_coverage().filter(
            (pl.col("code") == code) & (pl.col("timeframe") == timeframe))
    else:
        row = charts.load_coverage().filter(pl.col("code") == code)
    if row.is_empty():
        bugun = datetime.now(ZoneInfo(TZ)).date()
        return bugun - timedelta(days=365), bugun
    return (row["first_ts"][0].astimezone(tz).date(),
            row["last_ts"][0].astimezone(tz).date())


def _apply_preset(first: date, last: date) -> None:
    choice = st.session_state.get("bt_hizli")
    if choice:
        days = PRESETS[choice]
        st.session_state["bt_d1"] = first if days is None else max(
            first, last - timedelta(days=days))
        st.session_state["bt_d2"] = last
    st.session_state["bt_hizli"] = None


def render() -> None:
    """Ana ekrandaki Backtest menusu: kenar cubugu + ortak panel."""
    st.sidebar.markdown("[← Ana ekran](?ekran=home)")
    st.sidebar.title("Backtest")
    strategies = {s["key"]: s for s in all_strategies()}
    key = st.sidebar.selectbox("Strateji", list(strategies),
                               format_func=lambda k: label(strategies[k]),
                               key="bt_strateji")
    strat = strategies[key]
    tfs = timeframes(strat)
    tf_label = st.sidebar.selectbox("Zaman dilimi", list(tfs),
                                    index=tf_index(strat), key="bt_tf_" + key)
    with st.sidebar.expander("Strateji parametreleri"):
        cfg = param_widgets(strat, key="p_" + key,
                            caption=("Kayitli degerler" if strat["kayitli"]
                                     else "Varsayilanlar videodaki degerler"))

    st.subheader("Backtest", anchor=False)
    st.caption("Ayni panel Stratejiler ekraninda da var: strateji > Backtest.")
    panel(strat, cfg, tfs[tf_label], tf_label)


def panel(strat: dict, cfg, timeframe: str, tf_label: str) -> None:
    """Ortak backtest paneli. Zaman dilimi ve parametreler cagirandan gelir."""
    mode = st.radio("Mod", MODES, horizontal=True, key="bt_mod",
                    help="Canli parametre ayari: kaydiricilari oynattikca kar/"
                         "zarar aninda degisir; begendiginiz ayari yeni isimle "
                         "kaydedebilirsiniz.")

    _ilk_tf_label = tf_label
    c = st.columns([0.9, 1.1, 1, 1, 1.9])
    piyasa = PIYASALAR[c[0].selectbox("Piyasa", list(PIYASALAR), key="bt_piyasa")]
    kodlar = _kodlar(piyasa)
    if not kodlar:
        st.info("BIST gecmisi henuz indirilmedi. **Veri Merkezi > BIST "
                "gecmisini guncelle**'ye bir kez basin (~15 saniye).")
        return
    if piyasa == "bist" and timeframe not in BIST_TF:
        # Kullanici (24.09.2026): "mevcut veriler backtest yapmiyor". Sebep:
        # Strateji 2'nin varsayilan dilimi 4 saat, BIST'te ise yalniz gunluk
        # ve saatlik var -- panel uyari verip duruyordu ve kullanicinin kenar
        # cubugundan dilim degistirmesi gerektigini BILMESI gerekiyordu.
        # Artik panel kendi diliminIi secer; kenar cubugu degismez.
        # STRATEJININ destekledigi dilimlerle BIST'te VAR OLANLARIN kesisimi.
        # Strateji 1 gun ici bir stratejidir, gunluk barla calismaz (motor
        # `KeyError: '1d'` verir) -- listeye koymak yanlisti.
        uygun = {lbl: kod for lbl, kod in timeframes(strat).items()
                 if kod in BIST_TF}
        if not uygun:
            st.warning("**{}** BIST'te calistirilamiyor: bu strateji {} "
                       "diliminde calisiyor, BIST'te ise yalniz gunluk ve "
                       "1 saat var (Yahoo siniri).".format(
                           strat["ad"], " / ".join(timeframes(strat))))
            return
        secim = c[4].radio("BIST zaman dilimi", list(uygun), horizontal=True,
                           key="bt_bist_tf_" + strat["key"],
                           help="BIST'te Yahoo gunluk ~21 yil, saatlik ~3 yil "
                                "veriyor; 4 saat ve 15 dakika yok.")
        timeframe = uygun[secim]
        tf_label = secim
        st.caption("Kenar cubugunda **{}** secili ama BIST'te o dilim yok; "
                   "backtest **{}** barla calisiyor.".format(
                       _ilk_tf_label, secim))
    code = c[1].selectbox("Enstruman" if piyasa == "kuresel" else "Hisse",
                          kodlar, index=min(1, len(kodlar) - 1), key="bt_code")
    first, last = _bounds(code, piyasa, timeframe)
    # Enstruman degisince onceki tarihler yeni sinirlarin disinda kalabilir;
    # denetim olusturulmadan ONCE sinira cekilir (yoksa Streamlit hata verir).
    for key, default in (("bt_d1", max(first, last - timedelta(days=365))),
                         ("bt_d2", last)):
        v = st.session_state.get(key, default)
        st.session_state[key] = min(max(v, first), last)
    d1 = c[2].date_input("Baslangic", min_value=first, max_value=last,
                         format="DD.MM.YYYY", key="bt_d1")
    d2 = c[3].date_input("Bitis", min_value=first, max_value=last,
                         format="DD.MM.YYYY", key="bt_d2")
    c[3].pills("Hizli secim", list(PRESETS), key="bt_hizli",
               on_change=_apply_preset, args=(first, last))
    if d1 > d2:
        st.warning("Baslangic tarihi, bitis tarihinden sonra olamaz.")
        return

    if mode == MODES[1]:
        st.caption("{} verisi: {} - {} · zaman dilimi kenar cubugunda".format(
            code, first.strftime("%d.%m.%Y"), last.strftime("%d.%m.%Y")))
        _lab(strat, timeframe, tf_label, code, d1, d2, piyasa)
        return

    c = st.columns([1, 3])
    clicked = c[0].button("Backtest'i calistir", type="primary", width="stretch")
    c[1].caption("{} verisi: {} - {} · zaman dilimi ve strateji parametreleri "
                 "kenar cubugunda".format(code, first.strftime("%d.%m.%Y"),
                                          last.strftime("%d.%m.%Y")))

    request = (strat["temel"], code, timeframe, d1, d2, cfg, piyasa)
    if clicked:
        with st.spinner("Backtest calisiyor..."):
            _run(*request)
        st.session_state["bt_istek"] = (request, label(strat), tf_label)

    done = st.session_state.get("bt_istek")
    if done is None:
        st.info("Enstruman ve **tarih araligini** secip **Backtest'i "
                "calistir**'a basin.")
        st.markdown(
            "Sonucta:\n"
            "- **Sonuc** -- islem sayisi, kazanan orani, getiri, dusus, Sharpe\n"
            "- **Islemler** -- son 10 islem ya da iki tarih arasi; kapitale "
            "gore kar/zarar\n"
            "- **Grafik** -- mum grafiginde giris ve cikislar\n"
            "- **Sermaye egrisi** -- stratejiye karsi al-tut\n"
            "- **Karsilastirma** -- ayni ayarlarla tum varliklar\n\n"
            "Parametreleri oynatip sonucu aninda gormek icin ustten "
            "**Canli parametre ayari**'ni secin.")
        return

    (r_temel, r_code, r_tf, r_d1, r_d2, r_cfg, r_piyasa), r_strat, r_tf_label = done
    if done[0] != request:
        st.warning("Ayarlar degisti; asagidaki sonuc **onceki ayarlara** ait. "
                   "Guncellemek icin **Backtest'i calistir**.")

    span = _span(r_d1, r_d2)
    st.markdown("**{}** · {} · {} · {}".format(r_code, r_tf_label, span, r_strat))

    res = _run(*done[0])
    if res.bars.is_empty():
        st.warning("Bu tarih araliginda veri yok.")
        return

    tabs = st.tabs(["Sonuc", "Islemler", "Grafik", "Sermaye egrisi",
                    "Karsilastirma"])
    with tabs[0]:
        _section_summary(res, span)
    katmanlar = (BASE[r_temel]["egriler"], BASE[r_temel].get("isaretler", ()))
    with tabs[1]:
        _section_trades(res, span, "{}_{}_{}_{}".format(r_code, r_tf, r_d1, r_d2),
                        r_code, katmanlar, r_piyasa)
    with tabs[2]:
        _section_chart(res, r_code, katmanlar, r_piyasa)
    with tabs[3]:
        st.plotly_chart(_equity_chart(res.daily, _colors()), width="stretch",
                        config={"displaylogo": False})
        st.caption("Maliyet dahil, bilesik. Al-tut: araligin basinda alip "
                   "hic satmamak.")
        _pnl_bars(res)
    with tabs[4]:
        _section_compare(r_temel, r_tf, r_d1, r_d2, r_cfg, span, r_piyasa)


# ==========================================================================
# CANLI PARAMETRE AYARI
# ==========================================================================
def _reset_widgets(prefix: str, temel: str) -> None:
    for suffix in param_keys(temel):
        st.session_state.pop(prefix + suffix, None)


@st.fragment
def _lab(strat: dict, timeframe: str, tf_label: str, code: str,
         d1: date, d2: date, piyasa: str = "kuresel") -> None:
    prefix = "lab_" + strat["key"]
    left, right = st.columns([1, 2.6], gap="large")
    with left:
        st.markdown("**Parametreler**")
        cfg = param_widgets(strat, key=prefix, sliders=True,
                            caption="Baslangic = stratejinin kayitli degerleri")
        st.button("Baslangic degerlerine don", on_click=_reset_widgets,
                  args=(prefix, strat["temel"]), width="stretch")
        capital = st.number_input("Kapital ($)", min_value=100.0,
                                  max_value=1_000_000.0, value=1000.0,
                                  step=100.0, key="lab_kapital")
        split = st.checkbox("Asiri uyum kontrolu", True, key="lab_kontrol",
                            help="Araligi ilk %70 ayar / son %30 kontrol diye "
                                 "bolup iki bolumu yan yana gosterir.")

    temel = strat["temel"]
    t0 = perf_counter()
    cur = _lab_run(temel, code, timeframe, d1, d2, cfg, piyasa)
    ref = _lab_run(temel, code, timeframe, d1, d2, strat["cfg"], piyasa)
    secs = perf_counter() - t0

    with right:
        if cur.bars.is_empty():
            st.warning("Bu tarih araliginda veri yok.")
            return
        same = cfg == strat["cfg"]
        span = _span(d1, d2)
        st.markdown("**{}** · {} · {} · {}".format(code, tf_label, span, label(strat)))
        st.caption("Degisen: {} · hesap {} sn".format(
            diff_text(cfg, strat["cfg"], temel) or "yok (baslangic degerleri)",
            "{:.2f}".format(secs).replace(".", ",")))

        _lab_metrics(cur, ref, capital, same)
        _verdict(cur.metrics, span)
        st.plotly_chart(_lab_equity(cur, ref, same), width="stretch",
                        config={"displaylogo": False})
        if split:
            _overfit(cur, capital, temel)
        _save_form(strat, cfg, timeframe, tf_label, code, span, cur)


def _net(res, capital: float) -> float:
    """Her islemde ayni kapital (bilesik degil), maliyet dahil."""
    return float(res.trades["getiri"].sum()) * capital if res.trades.height else 0.0


def _lab_metrics(cur, ref, capital: float, same: bool) -> None:
    mc, mr = cur.metrics, ref.metrics

    def delta(a, b, fmt):
        if same or a is None or b is None or not (
                math.isfinite(a) and math.isfinite(b)):
            return None
        return fmt(a - b)

    pts = lambda x: "{:+.1f} puan".format(x).replace(".", ",")  # noqa: E731
    net_c, net_r = _net(cur, capital), _net(ref, capital)

    c = st.columns(3)
    c[0].metric("Net kar/zarar", _money(net_c), delta=delta(net_c, net_r, _money),
                help="Kapital {} ile; her islemde ayni kapital (bilesik "
                     "degil), maliyet dahil.".format(_money(capital).lstrip("+")))
    c[1].metric("Getiri", pct(mc["getiri_%"]),
                delta=delta(mc["getiri_%"], mr["getiri_%"], pts),
                help="Bilesik, maliyet dahil.")
    c[2].metric("Islem", _int(mc["islem"]),
                delta=delta(mc["islem"], mr["islem"],
                            lambda x: "{:+d}".format(int(x))),
                delta_color="off")
    c = st.columns(3)
    c[0].metric("Kazanan", _share(mc["kazanan_%"]),
                delta=delta(mc["kazanan_%"], mr["kazanan_%"], pts))
    c[1].metric("Kar faktoru", _num(mc["kar_faktoru"]),
                delta=delta(mc["kar_faktoru"], mr["kar_faktoru"],
                            lambda x: "{:+.2f}".format(x).replace(".", ",")))
    c[2].metric("Maks. dusus", pct(mc["MaxDD_%"]),
                delta=delta(mc["MaxDD_%"], mr["MaxDD_%"], pts))
    if not same:
        st.caption("Kucuk renkli degerler: baslangic degerlerine gore fark.")


def _lab_equity(cur, ref, same: bool) -> go.Figure:
    colors = _colors()
    fig = go.Figure()
    x = cur.daily["tday"].to_list()
    fig.add_trace(go.Scatter(
        x=x, y=((cur.daily["al_tut"] - 1) * 100).to_list(), name="Al-tut",
        line=dict(color=colors["ink_muted"], width=1.2, dash="dot"),
        hovertemplate="al-tut: %{y:.1f}%<extra></extra>"))
    if not same:
        fig.add_trace(go.Scatter(
            x=ref.daily["tday"].to_list(),
            y=((ref.daily["equity"] - 1) * 100).to_list(),
            name="Baslangic degerleri",
            line=dict(color=theme.ACCENTS["blue"], width=1.5, dash="dash"),
            hovertemplate="baslangic: %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=((cur.daily["equity"] - 1) * 100).to_list(), name="Simdiki ayar",
        line=dict(color=theme.ACCENTS["violet"], width=2.2),
        hovertemplate="simdiki: %{y:.1f}%<extra></extra>"))
    _layout(fig, colors, 320)
    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=colors["axis"])
    return fig


def _overfit(res, capital: float, temel: str) -> None:
    b = res.bars
    t0, t1 = b["ts"][0], b["ts"][-1]
    cut = t0 + (t1 - t0) * SPLIT
    tz = ZoneInfo(TZ)
    rows = []
    for name, keep_bar, keep_trade in (
        ("Ayar bolumu (ilk %70)", pl.col("ts") < cut, pl.col("giris_ts") < cut),
        ("Kontrol bolumu (son %30)", pl.col("ts") >= cut, pl.col("giris_ts") >= cut),
    ):
        bb = b.filter(keep_bar)
        tt = res.trades.filter(keep_trade)
        if bb.height < 2:
            continue
        m = motor(temel).metrics(tt, motor(temel).daily_equity(tt, bb), bb)
        rows.append({
            "Bolum": name,
            "Tarih": "{} - {}".format(bb["ts"][0].astimezone(tz).strftime("%d.%m.%Y"),
                                      bb["ts"][-1].astimezone(tz).strftime("%d.%m.%Y")),
            "Islem": m["islem"], "Kazanan %": m["kazanan_%"],
            "Kar faktoru": m["kar_faktoru"], "Getiri %": m["getiri_%"],
            "Net $": round(float(tt["getiri"].sum()) * capital, 2) if tt.height else 0.0,
        })
    st.markdown("**Asiri uyum kontrolu**")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption("Ayni veride parametreyi uzun uzun oynatmak gecmisi ezberleyen "
               "bir ayar bulur. Ayar bolumunde iyi ama kontrol bolumunde "
               "kotuyse bu ayar buyuk ihtimalle tesaduf.")


def _save_form(strat: dict, cfg, timeframe: str, tf_label: str,
               code: str, span: str, res) -> None:
    msg = st.session_state.pop("lab_kayit_mesaj", None)
    if msg:
        st.success(msg)

    with st.form("lab_kaydet"):
        st.markdown("**Farkli kaydet** -- su anki parametreler yeni bir "
                    "strateji olarak saklanir")
        c = st.columns([2, 3, 1.3])
        name = c[0].text_input("Strateji adi", placeholder="orn. Strateji 1.1",
                               max_chars=60)
        note = c[1].text_input("Not (istege bagli)", max_chars=200,
                               placeholder="orn. EMA 14, hedef 1:2 -- daha az islem")
        overwrite = c[2].checkbox("Uzerine yaz",
                                  help="Ayni isimde kayit varsa parametrelerini "
                                       "bu ayarla degistirir.")
        submitted = st.form_submit_button("Farkli kaydet", type="primary")
    if not submitted:
        return

    m = res.metrics
    try:
        saved = strategy_store.save_as(
            name, temel=strat["temel"], cfg=cfg, timeframe=timeframe,
            note=note, overwrite=overwrite,
            meta={"enstruman": code, "zaman_dilimi": tf_label, "aralik": span,
                  "getiri_%": m.get("getiri_%"), "islem": m.get("islem"),
                  "kazanan_%": m.get("kazanan_%")})
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state["lab_kayit_mesaj"] = (
        "**{}** kaydedildi. Stratejiler listesinde {} altinda gorunur: "
        "[ac →](?ekran=stratejiler&strateji={})".format(
            saved["ad"], BASE[strat["temel"]]["ad"], saved["key"]))
    # Tum uygulama yeniden calissin: kenar cubugundaki strateji listesi de
    # yeni kaydi gostersin.
    st.rerun()


# ==========================================================================
# TEK BACKTEST SEKMELERI
# ==========================================================================
def _span(d1: date, d2: date) -> str:
    return "{} - {}".format(d1.strftime("%d.%m.%Y"), d2.strftime("%d.%m.%Y"))


def _section_summary(res, span: str) -> None:
    m = res.metrics
    c = st.columns(6)
    c[0].metric("Islem", _int(m["islem"]),
                help="ayda {} islem".format(_num(m["islem_ay"])))
    c[1].metric("Kazanan", _share(m["kazanan_%"]))
    c[2].metric("Kar faktoru", _num(m["kar_faktoru"]),
                help="Kazanan islemlerin toplami / kaybedenlerin toplami. "
                     "1'in altinda = zarar.")
    c[3].metric("Toplam getiri", pct(m["getiri_%"]),
                help="Maliyet dahil, bilesik.")
    c[4].metric("Maks. dusus", pct(m["MaxDD_%"]))
    c[5].metric("Sharpe", _num(m["Sharpe"]))

    c = st.columns(6)
    c[0].metric("AL getiri", pct(m["long_%"]))
    c[1].metric("SAT getiri", pct(m["short_%"]))
    c[2].metric("Ort. R", _num(m["ort_R"]),
                help="Islem basina ortalama kazanc, riskin kati cinsinden.")
    c[3].metric("Ort. islem", "-" if m["ort_islem_bp"] != m["ort_islem_bp"]
                else "{:+.1f} bp".format(m["ort_islem_bp"]).replace(".", ","))
    c[4].metric("Al-tut", pct(m["al_tut_%"]),
                help="Ayni aralikta alip hic satmasaydiniz.")
    c[5].metric("Maliyet", "{} bp".format(_num(res.cost_bp)),
                help="Islem basina gidis-donus spread. TAHMINDIR.")

    _verdict(m, span)
    if m["nedenler"]:
        st.caption("Cikis nedenleri: " + " · ".join(
            "{} {}".format(k, v) for k, v in m["nedenler"].items()))


def _section_trades(res, span: str, key: str, code: str = "",
                    katmanlar=((), ()), piyasa: str = "kuresel") -> None:
    st.markdown("**Islem listesi** · toplam {} islem".format(
        _int(res.trades.height)))
    if res.trades.is_empty():
        st.caption("Islem yok.")
        return
    _trade_list(res, key, span, code, katmanlar, piyasa)


def _section_chart(res, code: str, katmanlar=((), ()), piyasa: str = "kuresel") -> None:
    """Donem gezintisi: pencere boyu + pencerenin bitisi ile tum aralikta gez.

    Eskiden yalnizca "son N islem gunu" gosteriliyordu; bir yillik backtest'in
    ortasindaki islemler gorulemiyordu.
    """
    tz = ZoneInfo(TZ)
    first = res.bars["ts"][0].astimezone(tz).date()
    last = res.bars["ts"][-1].astimezone(tz).date()

    c = st.columns([1, 3])
    gun = c[0].selectbox("Pencere (gun)", [3, 7, 15, 30, 90, 180, 365],
                         index=2, key="gr_pencere",
                         help="Grafikte kac gunluk bolum gorunsun.")
    if first == last:
        end = last
        c[1].caption("Veri tek gune sigiyor.")
    else:
        end = c[1].slider("Pencerenin bitisi", min_value=first, max_value=last,
                          value=last, format="DD.MM.YYYY", key="gr_bitis",
                          help="Kaydirici ile donem boyunca ileri geri gezin.")
    start = max(first, end - timedelta(days=gun))

    s_utc = datetime.combine(start, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    e_utc = datetime.combine(end + timedelta(days=1), time(0, 0),
                             tzinfo=tz).astimezone(timezone.utc)
    view = res.bars.filter(pl.col("ts").is_between(s_utc, e_utc, closed="left"))
    if view.is_empty():
        st.info("Bu pencerede bar yok (piyasa kapali olabilir); kaydiriciyi "
                "oynatin.")
        return
    kirpik = ""
    if view.height > MAX_BARS:
        view = view.tail(MAX_BARS)
        kirpik = " · pencere cok genis, son {} bar cizildi".format(
            _int(MAX_BARS))

    # Pencereye degen her islem: girisi ya da cikisi icerideyse gosterilir.
    tr = res.trades.filter(
        (pl.col("cikis_ts") >= view["ts"][0]) & (pl.col("giris_ts") <= view["ts"][-1]))
    st.plotly_chart(
        _trade_chart(_to_tr(view), _to_tr_trades(tr), _colors(),
                     _seans(code, piyasa), katmanlar),
        width="stretch", config={"scrollZoom": True, "displaylogo": False})
    st.caption("{} - {} · {} bar · {} islem{} · saatler Turkiye "
               "(UTC+3) · ucgen = giris, carpi = cikis, noktali cizgi = "
               "islemin yolu".format(start.strftime("%d.%m.%Y"),
                                     end.strftime("%d.%m.%Y"),
                                     _int(view.height), tr.height, kirpik))


def _section_compare(temel: str, timeframe: str, d1: date, d2: date,
                     cfg, span: str, piyasa: str = "kuresel") -> None:
    kodlar = _kodlar(piyasa)
    st.markdown("**Ayni ayarlarla tum varliklar** · {}".format(span))
    if not st.button("Tum varliklarda calistir"):
        st.caption("{} varligin her biri icin ayri backtest calisir; birkac "
                   "saniye surebilir.".format(len(kodlar)))
        return
    rows = []
    bar = st.progress(0.0, text="Varliklar hesaplaniyor...")
    for n, kod in enumerate(kodlar):
        r = _run(temel, kod, timeframe, d1, d2, cfg, piyasa).metrics
        if r:
            rows.append({
                "Varlik": kod, "Islem": r["islem"],
                "Ayda": r["islem_ay"], "Kazanan %": r["kazanan_%"],
                "Kar faktoru": r["kar_faktoru"], "Getiri %": r["getiri_%"],
                "Al-tut %": r["al_tut_%"], "Maks dusus %": r["MaxDD_%"],
                "Sharpe": r["Sharpe"], "AL %": r["long_%"],
                "SAT %": r["short_%"], "Ort. R": r["ort_R"],
            })
        bar.progress((n + 1) / len(kodlar))
    bar.empty()
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Getiri maliyet dahil ve bilesiktir.")


# --------------------------------------------------------------------------
# Islem listesi
# --------------------------------------------------------------------------
def _trade_list(res, key: str, span_all: str, code: str = "",
                katmanlar=((), ()), piyasa: str = "kuresel") -> None:
    """Islem tablosu + secilen islemin grafigi.

    Kapital her islemde AYNI kullanilir (bilesik degil). Kucuk hesapta "bu
    islemler bana kac dolar kazandirdi / kaybettirdi" sorusunun en anlasilir
    cevabi bu. Maliyet (spread) getiriye zaten dahil.

    Tablodan bir satira tiklaninca ALTINDA o islemin grafigi acilir. Secim
    yoksa en yeni islem gosterilir.

    Tarih secicilerin anahtari calistirilan backtest'e bagli: yeni backtest
    baska bir aralikta ise eski tarih sinirlarin disinda kalip hata vermesin.
    """
    c = st.columns([1.8, 1, 1])
    mode = c[0].radio("Gosterim", ["Son {} islem".format(LAST_N),
                                   "Tum islemler", "Iki tarih arasi"],
                      horizontal=True, key="gosterim")
    capital = c[1].number_input("Kapital ($)", min_value=100.0,
                                max_value=1_000_000.0, value=1000.0,
                                step=100.0, key="kapital")
    lev = c[2].selectbox("Kaldirac", [1, 2, 5, 10], format_func="{}x".format,
                         key="kaldirac",
                         help="1x = kapital kadar pozisyon. VIOP gibi "
                              "kaldiracli piyasada kar da zarar da katlanir.")

    # Islem numarasi TUM listeye gore (filtre ne olursa olsun ayni kalsin).
    trades = res.trades.with_row_index("no", offset=1)

    if mode.startswith("Son"):
        sel = trades.tail(LAST_N)
        span = "son {} islem".format(sel.height)
    elif mode.startswith("Tum"):
        sel = trades
        span = "{} (tum islemler)".format(span_all)
    else:
        tz = ZoneInfo(TZ)
        first = res.bars["ts"][0].astimezone(tz).date()
        last = res.bars["ts"][-1].astimezone(tz).date()
        c = st.columns(4)
        d1 = c[0].date_input("Baslangic tarihi",
                             value=max(first, last - timedelta(days=7)),
                             min_value=first, max_value=last,
                             format="DD.MM.YYYY", key="d1_" + key)
        t1 = c[1].time_input("Baslangic saati", value=time(0, 0), step=900,
                             key="t1_" + key)
        d2 = c[2].date_input("Bitis tarihi", value=last, min_value=first,
                             max_value=last, format="DD.MM.YYYY",
                             key="d2_" + key)
        t2 = c[3].time_input("Bitis saati", value=time(23, 45), step=900,
                             key="t2_" + key)
        start = datetime.combine(d1, t1, tzinfo=tz)
        end = datetime.combine(d2, t2, tzinfo=tz)
        if start > end:
            st.warning("Baslangic, bitisten sonra olamaz.")
            return
        # Filtre giris zamanina gore; saklama UTC oldugu icin UTC'ye cevrilir.
        sel = trades.filter(pl.col("giris_ts").is_between(
            start.astimezone(timezone.utc), end.astimezone(timezone.utc)))
        span = "{} - {} (TR)".format(start.strftime("%d.%m.%Y %H:%M"),
                                     end.strftime("%d.%m.%Y %H:%M"))

    f = st.columns([1.5, 1.7, 2.5])
    yon = f[0].radio("Yon", ["Tumu", "AL", "SAT"], horizontal=True, key="f_yon")
    sonuc = f[1].radio("Sonuc", ["Tumu", "Kazanan", "Kaybeden"],
                       horizontal=True, key="f_sonuc")
    if yon != "Tumu":
        sel = sel.filter(pl.col("yon") == (1 if yon == "AL" else -1))
    if sonuc != "Tumu":
        sel = sel.filter(pl.col("getiri") > 0 if sonuc == "Kazanan"
                         else pl.col("getiri") <= 0)
    if yon != "Tumu" or sonuc != "Tumu":
        span += " \u00b7 {} / {}".format(yon.lower(), sonuc.lower())

    n = sel.height
    if n == 0:
        st.info("Bu filtrede islem yok.")
        return

    notional = capital * lev
    pnl = sel["getiri"] * notional
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    gross_win = float(pnl.filter(pnl > 0).sum())
    gross_loss = float(pnl.filter(pnl < 0).sum())
    net = gross_win + gross_loss

    m = st.columns(6)
    m[0].metric("Islem", n, help=span)
    m[1].metric("Karda", "%{:.0f}".format(100 * wins / n),
                help="{} islem kar etti".format(wins))
    m[2].metric("Zararda", "%{:.0f}".format(100 * losses / n),
                help="{} islem zarar etti".format(losses))
    m[3].metric("Toplam kar", _money(gross_win))
    m[4].metric("Toplam zarar", _money(gross_loss))
    m[5].metric("Net sonuc", _money(net), delta=pct(100 * net / capital),
                help="Kapitale gore net degisim")
    st.caption(
        "{} \u00b7 her islemde {} x {} = {} pozisyon (bilesik degil) \u00b7 maliyet "
        "(spread) dahil".format(span, _money(capital).lstrip("+"),
                                "{}x".format(lev),
                                _money(notional).lstrip("+")))

    # Kisa bir secim tum araliktan cok farkli gorunebilir -- yan yana koy.
    full = res.trades["getiri"] * notional
    if n < full.len():
        f_net = float(full.sum())
        msg = ("**{} tamami** ({} islem): karda %{:.0f}, ayni kapitalle net "
               "**{}**{}.".format(
                   span_all, _int(full.len()),
                   100 * int((full > 0).sum()) / full.len(), _money(f_net),
                   " (kapital tamamen erirdi)" if f_net <= -capital else ""))
        if net > 0 >= f_net:
            st.warning("Secilen islemler karda gorunuyor, ama " + msg +
                       " Kisa donem sonucu yaniltici olabilir.")
        else:
            st.caption("Karsilastirma -- " + msg)

    # Kumulatif toplam kronolojik sirada birikir, tablo ters sirada gosterir.
    sel = sel.with_columns(
        (pl.col("getiri") * notional).cum_sum().alias("kumulatif"))
    sirali = sel.reverse()
    olay = st.dataframe(
        _trade_table(sirali, notional).to_pandas(), width="stretch",
        height=min(460, 38 + 35 * n), hide_index=True,
        on_select="rerun", selection_mode="single-row",
        # Anahtar filtreyi de tasiyor: filtre degisince secim sifirlanir,
        # yoksa satir numarasi baska bir isleme denk gelirdi.
        key="islem_sec_{}_{}_{}_{}".format(key, mode, yon, sonuc))

    secim = []
    try:
        secim = list(olay.selection.rows)
    except AttributeError:      # eski Streamlit: secim yoksa tablo dondurur
        secim = []
    sira = secim[0] if secim and secim[0] < sirali.height else 0
    islem = sirali.row(sira, named=True)

    st.markdown("---")
    st.markdown("**Islem #{} \u2014 grafik**".format(islem["no"]))
    if not secim:
        st.caption("Tabloda bir satira tiklayin: o islemin grafigi burada "
                   "acilir. (Secim yokken en yeni islem gosterilir.)")
    _trade_zoom(res, islem, code, katmanlar, notional, piyasa)


def _trade_zoom(res, islem: dict, code: str, katmanlar, notional: float,
                piyasa: str = "kuresel") -> None:
    """Tek islemin grafigi: giris, cikis, stop, hedef ve islemin yolu.

    Bar ici en iyi/en kotu durum (MFE/MAE) da hesaplanir -- "stop biraz genis
    olsa kurtulur muydu" sorusunun cevabi burada.
    """
    bars = res.bars
    pad = st.slider("Islemin cevresinde kac bar gorunsun", 5, 200, 30, 5,
                    key="zoom_pad")

    ts = bars["ts"]
    i0 = int((ts < islem["giris_ts"]).sum())
    i1 = int((ts <= islem["cikis_ts"]).sum()) - 1
    a = max(0, i0 - pad)
    b = min(bars.height, i1 + 1 + pad)
    view = bars.slice(a, b - a)
    icinde = bars.slice(i0, max(1, i1 - i0 + 1))

    tek = res.trades.filter((pl.col("giris_ts") == islem["giris_ts"])
                            & (pl.col("cikis_ts") == islem["cikis_ts"]))
    fig = _trade_chart(_to_tr(view), _to_tr_trades(tek), _colors(),
                       _seans(code, piyasa), katmanlar)

    colors = _colors()
    tz = ZoneInfo(TZ)
    x0 = islem["giris_ts"].astimezone(tz)
    x1 = islem["cikis_ts"].astimezone(tz)
    # Islem suresi golgeli, stop ve hedef yatay cizgi.
    fig.add_vrect(x0=x0, x1=x1, fillcolor=theme.rgba(
        colors["up"] if islem["getiri"] > 0 else colors["down"], 0.07),
        line_width=0, layer="below")
    for alan, ad, renk, kesik in (("stop", "Stop", colors["down"], "dash"),
                                  ("hedef", "Hedef", colors["up"], "dot")):
        v = islem.get(alan)
        if v is None or v != v:
            continue
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[v, v], mode="lines", name=ad,
            line=dict(color=renk, width=1.2, dash=kesik),
            hovertemplate=ad.lower() + ": %{y}<extra></extra>"))
    st.plotly_chart(fig, width="stretch",
                    config={"scrollZoom": True, "displaylogo": False})

    d = islem["yon"]
    giris = islem["giris"]
    if icinde.height:
        mfe = (float(icinde["high"].max()) - giris) / giris * 100 * d if d == 1 \
            else (giris - float(icinde["low"].min())) / giris * 100
        mae = (float(icinde["low"].min()) - giris) / giris * 100 * d if d == 1 \
            else (giris - float(icinde["high"].max())) / giris * 100
    else:
        mfe = mae = float("nan")

    sure = islem["cikis_ts"] - islem["giris_ts"]
    saat = sure.total_seconds() / 3600
    kar = islem["getiri"] * notional
    st.markdown(
        "**{yon}** \u00b7 giris {gt} @ {gp} \u00b7 cikis {ct} @ {cp} \u00b7 "
        "sure {sure} \u00b7 cikis nedeni **{neden}**".format(
            yon="AL" if d == 1 else "SAT",
            gt=x0.strftime("%d.%m.%Y %H:%M"), gp=_px(giris),
            ct=x1.strftime("%d.%m.%Y %H:%M"), cp=_px(islem["cikis"]),
            sure=("{:.0f} saat".format(saat) if saat < 48
                  else "{:.1f} gun".format(saat / 24).replace(".", ",")),
            neden=islem["neden"]))
    c = st.columns(4)
    c[0].metric("Sonuc", pct(islem["getiri"] * 100), delta=_money(kar),
                delta_color="off")
    c[1].metric("R", _num(islem["R"]),
                help="Kazanc, baslangictaki riskin kati cinsinden.")
    c[2].metric("En iyi ara durum", pct(mfe),
                help="Islem acikken fiyat lehinize en fazla bu kadar gitti "
                     "(bar ici en uc deger).")
    c[3].metric("En kotu ara durum", pct(mae),
                help="Islem acikken fiyat aleyhinize en fazla bu kadar gitti. "
                     "Stop bu degerin otesindeyse islem stop yemeden hayatta "
                     "kalmis demektir.")
    st.caption("Ucgen = giris, carpi = cikis, noktali cizgi = islemin yolu, "
               "golgeli alan = pozisyonun acik oldugu sure. Kar/zarar "
               "{} pozisyon icin.".format(_money(notional).lstrip("+")))


def _pnl_bars(res) -> None:
    """Islem basina kar/zarar cubuklari -- "nasil kazanmis nasil kaybetmis"."""
    t = res.trades
    if t.is_empty():
        return
    colors = _colors()
    y = (t["getiri"] * 100).to_list()
    x = t["cikis_ts"].dt.convert_time_zone(TZ).to_list()
    fig = go.Figure(go.Bar(
        x=x, y=y, name="Islem",
        marker_color=[colors["up"] if v > 0 else colors["down"] for v in y],
        customdata=[["AL" if d == 1 else "SAT", n]
                    for d, n in zip(t["yon"].to_list(), t["neden"].to_list())],
        hovertemplate="%{x|%d.%m.%Y %H:%M}<br>%{customdata[0]} \u00b7 "
                      "%{y:.2f}%<br>cikis: %{customdata[1]}<extra></extra>"))
    _layout(fig, colors, 240)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=colors["axis"])
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    st.caption("Her cubuk bir islem (cikis zamaninda). Yesil kar, kirmizi "
               "zarar; maliyet dahil. Ust uste binen kirmizi kumeler "
               "stratejinin hangi donemde zorlandigini gosterir.")


def _to_tr(bars: pl.DataFrame) -> pl.DataFrame:
    """Bar zamanlarini Turkiye saatine cevirir (yalniz gosterim icin)."""
    return bars.with_columns(pl.col("ts").dt.convert_time_zone(TZ))


def _to_tr_trades(trades: pl.DataFrame) -> pl.DataFrame:
    return trades.with_columns(
        pl.col("giris_ts").dt.convert_time_zone(TZ),
        pl.col("cikis_ts").dt.convert_time_zone(TZ),
    )


def _px(v) -> str:
    """Fiyati okunur bicimde yazar (buyuklugune gore ondalik)."""
    if v is None or v != v:
        return "-"
    basamak = 5 if abs(v) < 10 else 3 if abs(v) < 1000 else 2
    return "{:,.{}f}".format(v, basamak).replace(",", " ").replace(
        ".", ",").replace(" ", ".")


def _trade_table(trades: pl.DataFrame, notional: float) -> pl.DataFrame:
    """Ekranda gorunen islem tablosu. Girdi GOSTERIM sirasindadir (yeniden
    siralanmaz) -- tablodaki satir numarasi ile islem birebir eslesmeli."""
    sure = (pl.col("cikis_ts") - pl.col("giris_ts")).dt.total_minutes()
    return trades.select(
        pl.col("no").alias("No"),
        pl.col("giris_ts").dt.convert_time_zone(TZ)
        .dt.strftime("%d.%m.%Y %H:%M").alias("Giris (TR)"),
        pl.col("cikis_ts").dt.convert_time_zone(TZ)
        .dt.strftime("%d.%m.%Y %H:%M").alias("Cikis (TR)"),
        pl.when(pl.col("yon") == 1).then(pl.lit("AL"))
        .otherwise(pl.lit("SAT")).alias("Yon"),
        pl.col("giris").alias("Giris fiyati"),
        pl.col("cikis").alias("Cikis fiyati"),
        pl.col("stop").alias("Stop"),
        pl.col("hedef").alias("Hedef"),
        pl.col("neden").alias("Cikis nedeni"),
        (pl.col("getiri") * 100).round(3).alias("Getiri %"),
        (pl.col("getiri") * notional).round(2).alias("Kar/Zarar $"),
        pl.col("kumulatif").round(2).alias("Kumulatif $"),
        pl.col("R").round(2),
        pl.when(sure < 120).then(sure.cast(pl.Utf8) + pl.lit(" dk"))
        .when(sure < 2880).then((sure // 60).cast(pl.Utf8) + pl.lit(" saat"))
        .otherwise((sure // 1440).cast(pl.Utf8) + pl.lit(" gun")).alias("Sure"),
    )


# --------------------------------------------------------------------------
# Bicim ve grafik yardimcilari
# --------------------------------------------------------------------------
def _verdict(m: dict, span: str) -> None:
    """Hukum HER ZAMAN secilen araligin tamami icindir -- metinde acikca yazar."""
    n = m.get("islem", 0)
    if n == 0:
        st.info("Bu ayarlarla hic islem olusmadi.")
        return
    donem = "{} araliginda ({} islem)".format(span, _int(n))
    total = m["getiri_%"]
    if total <= 0:
        st.error("{} bu ayarlarla strateji **para kaybettiriyor** (maliyet "
                 "dahil {}). Daha kisa araliklar karli gorunebilir."
                 .format(donem, pct(total)))
    elif total < m["al_tut_%"]:
        st.warning("{} kazandiriyor ({}), ama ayni aralikta **al-tut daha "
                   "iyi** ({}).".format(donem, pct(total), pct(m["al_tut_%"])))
    else:
        st.success("{} kazandiriyor ({}) ve al-tut'u geciyor ({})."
                   .format(donem, pct(total), pct(m["al_tut_%"])))


def _num(v: float) -> str:
    if v != v:
        return "-"
    if v == float("inf"):
        return "∞"
    return "{:.2f}".format(v).replace(".", ",")


def _int(v: int) -> str:
    return "{:,}".format(v).replace(",", ".")


def _share(v: float) -> str:
    return "-" if v != v else "%{:.0f}".format(v)


def _money(v: float) -> str:
    """Turk bicimi dolar: +$1.234,56"""
    s = "{:,.2f}".format(abs(v)).replace(",", " ").replace(".", ",").replace(" ", ".")
    return "{}${}".format("-" if v < 0 else "+" if v > 0 else "", s)


def _colors() -> dict:
    return dict(charts.BASE["dark"], **charts.SCHEMES["Klasik"]["dark"])


def _layout(fig: go.Figure, colors: dict, height: int) -> None:
    fig.update_layout(
        template=colors["template"],
        paper_bgcolor=colors["surface"], plot_bgcolor=colors["surface"],
        font=dict(color=colors["ink"], family="system-ui, Segoe UI, sans-serif"),
        height=height, margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified", xaxis_rangeslider_visible=False, dragmode="pan",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(color=colors["ink"], size=12),
                    bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=colors["grid"], linecolor=colors["axis"],
                     tickfont=dict(color=colors["ink_muted"], size=11))
    fig.update_yaxes(gridcolor=colors["grid"], linecolor=colors["axis"],
                     tickfont=dict(color=colors["ink_muted"], size=11))


def _equity_chart(daily: pl.DataFrame, colors: dict) -> go.Figure:
    x = daily["tday"].to_list()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=((daily["al_tut"] - 1) * 100).to_list(), name="Al-tut",
        line=dict(color=colors["ink_muted"], width=1.5, dash="dot"),
        hovertemplate="al-tut: %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=((daily["equity"] - 1) * 100).to_list(), name="Strateji",
        line=dict(color=theme.ACCENTS["violet"], width=2),
        hovertemplate="strateji: %{y:.1f}%<extra></extra>"))
    _layout(fig, colors, 380)
    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=colors["axis"])
    return fig


def _trade_chart(bars: pl.DataFrame, trades: pl.DataFrame, colors: dict,
                 session: str, katmanlar=((), ())) -> go.Figure:
    """Mum + stratejinin egrileri + gosterge sinyalleri + islemler.

    `katmanlar` = (egriler, isaretler):
      egriler   (sutun, ad, tema rengi) -- cizgi olarak cizilir (EMA, Range
                filtresi...). Sutun yoksa atlanir.
      isaretler (sutun, ad, tema rengi) -- sutun +1/-1 tasiyan bir GOSTERGE
                sinyalidir; mumun altina/ustune kucuk ucgen konur. Boylece
                "hangi gosterge ne zaman yandi, neden islem acilmadi"
                gorulur. Kalabaliklasmasin diye yalnizca dar pencerede.
    Saatler bu fonksiyona TR'ye cevrilmis gelir."""
    egriler, isaretler = (katmanlar or ((), ()))
    ts = bars["ts"].to_list()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=ts, open=bars["open"], high=bars["high"], low=bars["low"],
        close=bars["close"], name="Fiyat",
        increasing=dict(line=dict(color=colors["up"], width=1),
                        fillcolor=colors["up"]),
        decreasing=dict(line=dict(color=colors["down"], width=1),
                        fillcolor=colors["down"]),
    ))
    for col, ad, renk in (egriler or (("ema", "EMA", "yellow"),)):
        if col not in bars.columns:
            continue
        fig.add_trace(go.Scatter(
            x=ts, y=bars[col].to_list(), mode="lines", name=ad,
            line=dict(color=theme.ACCENTS[renk], width=1.6),
            hovertemplate=ad.lower() + ": %{y}<extra></extra>"))

    if bars.height <= MAX_MARK_BARS:
        for col, ad, renk in isaretler:
            if col not in bars.columns:
                continue
            for d, sym, alan, kay, etiket in (
                (1, "triangle-up", "low", 0.999, "AL"),
                (-1, "triangle-down", "high", 1.001, "SAT"),
            ):
                sub = bars.filter(pl.col(col) == d)
                if sub.is_empty():
                    continue
                fig.add_trace(go.Scatter(
                    x=sub["ts"].to_list(),
                    y=(sub[alan] * kay).to_list(),
                    mode="markers", name="{} {}".format(ad, etiket),
                    marker=dict(symbol=sym, size=7,
                                color=theme.rgba(theme.ACCENTS[renk], 0.85)),
                    hovertemplate="{} {}<extra></extra>".format(ad, etiket)))

    if not trades.is_empty():
        # Giris -> cikis cizgileri tek seride, None ile ayrilmis. Islem basina
        # ayri iz eklemek yuzlerce islemde grafigi yavaslatir.
        for win, color, lbl in ((True, colors["up"], "Kazanan islem"),
                                (False, colors["down"], "Kaybeden islem")):
            t = trades.filter((pl.col("getiri") > 0) == win)
            xs: list = []
            ys: list = []
            for r in t.iter_rows(named=True):
                xs += [r["giris_ts"], r["cikis_ts"], None]
                ys += [r["giris"], r["cikis"], None]
            if xs:
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines", name=lbl, hoverinfo="skip",
                    line=dict(color=color, width=2, dash="dot")))

        for d, symbol, color, lbl in (
            (1, "triangle-up", colors["up"], "AL giris"),
            (-1, "triangle-down", colors["down"], "SAT giris"),
        ):
            t = trades.filter(pl.col("yon") == d)
            if t.is_empty():
                continue
            fig.add_trace(go.Scatter(
                x=t["giris_ts"].to_list(), y=t["giris"].to_list(),
                mode="markers", name=lbl,
                marker=dict(symbol=symbol, size=12, color=color,
                            line=dict(width=1, color=colors["surface"])),
                hovertemplate=lbl.lower() + ": %{y}<extra></extra>"))

        fig.add_trace(go.Scatter(
            x=trades["cikis_ts"].to_list(), y=trades["cikis"].to_list(),
            mode="markers", name="Cikis", text=trades["neden"].to_list(),
            marker=dict(symbol="x", size=9, color=colors["ink"]),
            hovertemplate="cikis (%{text}): %{y}<extra></extra>"))

    _layout(fig, colors, 560)
    # Kripto 7/24 isler; hafta sonunu gizlemek gercek veriyi siler.
    breaks = [] if session == "24x7" else [dict(bounds=["sat", "sun"])]
    fig.update_xaxes(rangebreaks=breaks, tickformat="%d.%m<br>%H:%M",
                     hoverformat="%d.%m.%Y %H:%M")
    return fig

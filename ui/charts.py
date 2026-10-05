"""Grafikler ekrani -- mum grafigi, Chandelier Exit, MACD.

Anayasa 2.4: Streamlit, veri katmanindan AYRIK. Bu dosya storage/indicators/
modullerini cagirir; hicbir yerde dogrudan SQL yazmaz. Arayuz yarin
FastAPI+WebSocket'e tasinirsa veri katmani hic degismez.

Yonlendirme app.py'de; bu dosya yalnizca kendi ekranini cizer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from plotly.subplots import make_subplots

from finans_cortex import indicators, ingest, storage
from finans_cortex.instruments import INSTRUMENTS, get as get_instrument

# --------------------------------------------------------------------------
# Palet
#
#   "Klasik"  -- yesil/kirmizi. Piyasa standardi.
#   "Ayrik"   -- mavi/kirmizi. Yesil-kirmizi cifti en yaygin renk korlugu
#                turunde (deuteranopi) ayirt edilemez; mavi-kirmizi ayrilir.
# --------------------------------------------------------------------------
BASE = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink_muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7", "template": "plotly_white",
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#ffffff", "ink_muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "template": "plotly_dark",
    },
}

SCHEMES = {
    "Klasik": {
        "light": {"up": "#1a9c5b", "down": "#e34948"},
        "dark": {"up": "#26a269", "down": "#e66767"},
    },
    "Ayrik": {
        "light": {"up": "#2a78d6", "down": "#e34948"},
        "dark": {"up": "#3987e5", "down": "#e66767"},
    },
}

TIMEFRAMES = {"15 dakika": "15m", "1 saat": "1h", "4 saat": "4h", "1 gun": "1d"}

# Acilista yakin donem gelsin diye bar sayisi degil ZAMAN ARALIGI seciliyor.
PERIODS = {
    "Son 3 gun": 3,
    "Son 1 hafta": 7,
    "Son 2 hafta": 14,
    "Son 1 ay": 30,
    "Son 2 ay": 60,
    "Son 3 ay": 90,
    "Son 6 ay": 180,
    "Son 1 yil": 365,
}
# Varsayilan aralik ZAMAN DILIMINE gore degisir. Amac: her zaman diliminde
# ilk bakista yakin donemi, okunabilir yogunlukta gostermek. 15dk'da 1 ay
# ~2.000 bar ve ~60 sinyal demek (5 Ekim 2026: 15dk 3 gun, 4s 1 ay -> ~30 / ~17 sinyal) -- rozetler ust uste biniyor. Ayni bar
# yogunlugunu her dilimde tutturmak icin aralik olceklendiriliyor.
DEFAULT_PERIOD_BY_TF = {
    "15m": "Son 3 gun",
    "1h": "Son 1 ay",
    "4h": "Son 1 ay",
    "1d": "Son 1 yil",
}

# Gosterge isinmasi icin secilen araligin ONCESINDEN cekilen ek bar sayisi.
WARMUP_BARS = 300

# Plotly ~8000 mumdan sonra gozle gorulur yavaslar. Ustune cikilirsa en yeni
# kisim cizilir ve kullanici uyarilir -- sessizce yavaslamaktansa soylemek iyi.
MAX_RENDER_BARS = 8000

BAR_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}

# Bu sayidan fazla sinyal varsa rozet yerine kucuk ucgen isaret cizilir.
# Olculdu: 15dk/1 ay = 257 sinyal; rozetler fiyati tamamen ortuyor. Sinyalleri
# GIZLEMEK yaniltici olurdu, o yuzden gizlemek yerine kucultuyoruz.
BADGE_DENSITY_LIMIT = 80

# Anayasa 2.2: "Tum veri UTC'de saklanir, GORUNTULEMEDE TR saatine cevrilir."
# Saklama ve hesap UTC'de kalir; cevrim yalnizca ekrana yazarken yapilir.
DISPLAY_ZONES = {"Turkiye (UTC+3)": "Europe/Istanbul", "UTC": "UTC"}
DEFAULT_ZONE = "Turkiye (UTC+3)"

# Eksen etiketi bicimi. Gun ICINDE calisilan dilimlerde saat:dakika da
# gosterilir; gunluk barda saatin anlami yok.
TICK_FORMAT = {
    "15m": "%d.%m<br>%H:%M",
    "1h": "%d.%m<br>%H:%M",
    "4h": "%d.%m<br>%H:%M",
    "1d": "%d.%m.%Y",
}
HOVER_FORMAT = {
    "15m": "%d.%m.%Y %H:%M",
    "1h": "%d.%m.%Y %H:%M",
    "4h": "%d.%m.%Y %H:%M",
    "1d": "%d.%m.%Y",
}


@st.cache_resource
def _root_connection():
    """Salt-okunur KOK baglanti. Dolum betigi ayni anda calisabilsin diye.

    Dogrudan kullanilmaz (bkz. get_connection): bu nesne tum oturumlar ve is
    parcaciklari arasinda PAYLASILIR. Yalniz `refresh_data` onu kapatmak icin
    cagirir -- DuckDB dosya kilidini birakan tek sey kokun kapanmasidir.
    """
    return storage.connect(read_only=True)


def get_connection():
    """Bu cagriya/is parcacigina ozel salt-okunur baglanti.

    Paylasilan tek baglanti es zamanli kullanilinca sorgular birbirinin
    sonucunu eziyordu; Kural akisi ekrani bir kez "enstruman kayitli degil:
    XAUUSD" verdi, yenileyince gecti (22 Eylul 2026). Ureterek dogrulandi:
    8 is parcacigi paylasilan baglantida 7 hata, `thread_cursor` ile 0.
    Kok baglanti onbellekte kaldigi icin dosya yine bir kez acilir.
    """
    return storage.thread_cursor(_root_connection())


def refresh_data() -> int:
    """Dukascopy'den eksik barlari ceker. Donen: eklenen bar sayisi.

    DuckDB ayni dosyada TEK yaziciya izin verir. Arayuz salt-okunur bir
    baglanti tuttugu icin once o kapatilmali, yoksa yazma baglantisi acilmaz.
    Islem bitince onbellekler temizlenir ki ekran taze veriyi gostersin.
    """
    try:
        # KOK kapatilmali: cursor kapatmak kilidi birakmaz (olculdu).
        _root_connection().close()
    except Exception:  # noqa: BLE001 - baglanti zaten kapali olabilir
        pass
    _root_connection.clear()

    con = storage.connect()          # okuma-yazma
    try:
        # Arayuzdeki dugme de sonsuza kadar donmesin (bkz. ingest.py).
        added = ingest.backfill_all(con, sure_sn=120)
    finally:
        con.close()

    load_period.clear()
    load_coverage.clear()
    return added


def data_age() -> tuple[datetime | None, timedelta | None]:
    """En yeni barin zamani ve simdiye gore yasi."""
    cov = load_coverage()
    if cov.is_empty() or cov["last_ts"].null_count() == cov.height:
        return None, None
    last = cov["last_ts"].max()
    return last, datetime.now(timezone.utc) - last


def age_text(delta: timedelta | None) -> str:
    """Yasi insanca yazar: '18 dakika', '7 saat', '2,0 gun'.

    Tek yerde: ana ekran, Grafikler ve Veri Merkezi ayni ifadeyi kullansin.
    """
    if delta is None:
        return "-"
    saat = delta.total_seconds() / 3600
    if saat < 1:
        return "{:.0f} dakika".format(max(delta.total_seconds() / 60, 0))
    if saat < 48:
        return "{:.0f} saat".format(saat)
    return "{:.1f} gun".format(saat / 24).replace(".", ",")


def freshness(tz: str = "Europe/Istanbul") -> tuple[str, bool]:
    """(metin, bayat mi). Metin: '20.09 22:45 - 18 dakika once'.

    Bayatlik esigi 3 gun: hafta sonu piyasa kapali oldugu icin Cuma
    kapanisindan sonra 2 gune kadar gecikme normaldir.
    """
    son, yas = data_age()
    if son is None:
        return "veri yok", True
    return ("{} - {} once".format(
        son.astimezone(ZoneInfo(tz)).strftime("%d.%m %H:%M"), age_text(yas)),
        yas is not None and yas > timedelta(days=3))


@st.cache_data(ttl=120, show_spinner=False)
def load_period(code: str, timeframe: str, days: int) -> tuple[pl.DataFrame, int]:
    """Son `days` gunluk veriyi getirir (+ gosterge isinmasi icin ek pay).

    Donen: (isinma dahil cerceve, gosterilecek ilk satirin indeksi)
    """
    con = get_connection()
    df = storage.read_bars(con, code, timeframe)
    if df.is_empty():
        return df, 0

    end = df["ts"][-1]
    start = end - timedelta(days=days)
    warm = timedelta(minutes=BAR_MINUTES[timeframe] * WARMUP_BARS)

    framed = df.filter(pl.col("ts") >= start - warm)
    shown_from = framed.filter(pl.col("ts") < start).height
    return framed, shown_from


@st.cache_data(ttl=120, show_spinner=False)
def load_coverage() -> pl.DataFrame:
    return storage.coverage(get_connection())


@st.cache_data(ttl=120, show_spinner=False)
def load_bist_coverage() -> pl.DataFrame:
    """BIST tablosunun kapsami (hisse x zaman dilimi). Kuresel varliklarin
    `load_coverage`'i ile karismasin diye ayri: ayri tablo, ayri kaynak."""
    return storage.bist_coverage(get_connection())


def refresh_bist(timeframes: tuple[str, ...] = ("1d", "1h")) -> dict:
    """BIST gecmisini Yahoo'dan tazeler. Donen: bist.backfill sonucu.

    `refresh_data` ile ayni kural: DuckDB tek yaziciya izin verdigi icin once
    salt-okunur KOK baglanti kapatilir (cursor kapatmak yetmez).
    """
    from finans_cortex import bist
    try:
        _root_connection().close()
    except Exception:  # noqa: BLE001
        pass
    _root_connection.clear()

    try:
        con = storage.connect()      # okuma-yazma
    except Exception as exc:         # noqa: BLE001
        # DuckDB tek yaziciya izin verir. Programin BASKA bir kopyasi aciksa
        # (ikinci pencere, ikinci tarayici sekmesi degil -- ayri BASLAT)
        # dosya kilitli kalir ve yazma baglantisi acilmaz. Ham IO hatasi
        # kullaniciya hicbir sey anlatmiyordu.
        raise RuntimeError(
            "Veritabani baska bir program tarafindan tutuluyor, yazilamadi. "
            "DeepCortex'in baska bir penceresi acik olabilir: hepsini kapatip "
            "tek pencereyle yeniden deneyin. (Ayrinti: {})".format(exc)) from exc
    try:
        sonuc = bist.backfill(con, timeframes=timeframes)
    finally:
        con.close()
    load_bist_coverage.clear()
    return sonuc


def _rgba(hex_color: str, alpha: float) -> str:
    """#rrggbb -> rgba(r,g,b,a).

    Plotly'nin annotation.bgcolor alani 8 haneli hex (#rrggbbaa) KABUL ETMEZ;
    saydamlik icin rgba() bicimi zorunlu.
    """
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "rgba({},{},{},{})".format(r, g, b, alpha)


def _build_badges(
    df: pl.DataFrame, colors: dict, limit: int, short: bool
) -> list[dict]:
    """Chandelier ve MACD sinyallerini etiketli rozet olarak yerlestirir.

      chandelier -> kucuk, dolu zemin
      macd       -> buyuk, yari saydam zemin

    IKI SORUNU BIRDEN COZER:

    1. CAKISMA. Onceki surumde yakin sinyaller ust uste biniyor ve fiyati
       ortuyordu. Artik rozetler dikey KADEMEYE ayriliyor: cakisacak olan
       bir ust siraya cikiyor. Boylece hicbir sinyal gizlenmiyor -- ki
       gizlemek yaniltici olurdu.

    2. GENISLIK. Kisa etiket (B/S) uzun etikete (Buy/Sell) gore ~2 kat dar;
       yogun gorunumlerde cakisma kendiliginden azaliyor.

    Iki sinyal tipi TEK listede yerlestiriliyor -- ayri ayri yapilsaydi
    Chandelier rozeti MACD rozetinin ustune binerdi.

    PERFORMANS: rozetler fig.add_annotation() ile TEK TEK eklenirse plotly
    her cagrida tum layout'u yeniden dogruluyor; olculdu, 257 rozet 13,8
    saniye surdu. Bu yuzden burada yalnizca sozluk listesi uretiliyor ve
    cagiran taraf hepsini tek seferde layout'a yaziyor.
    """
    if limit <= 0 or df.height == 0:
        return []

    n = df.height
    ts_all = df["ts"].to_list()
    low_all = df["low"].to_list()
    high_all = df["high"].to_list()
    ch = df["signal"].to_list()
    mc = (df["macd_cross"].to_list()
          if "macd_cross" in df.columns else [None] * n)

    # Bir rozetin kapladigi yaklasik bar sayisi. Grafik ~1200px ise bar basina
    # 1200/n piksel duser; kisa etiket ~26px, uzun etiket ~48px yer kaplar.
    badge_px = 26 if short else 48
    min_gap = max(1, int(badge_px * n / 1200) + 1)

    items = []
    for i in range(n):
        if ch[i] is not None:
            items.append((i, ch[i], False))
        if mc[i] is not None:
            items.append((i, mc[i], True))

    if len(items) > limit:
        items = items[-limit:]

    # Kademe takibi: her kademede EN SON yerlestirilen barin indeksi tutulur.
    # items zaten artan sirada oldugu icin tek gecis yeter -- onceki surumdeki
    # "tum listeyi tara" yaklasimi O(n^2) idi.
    above_levels: list[int] = []
    below_levels: list[int] = []
    anns: list[dict] = []

    for i, sig, big in items:
        buy = sig == "BUY"
        base = colors["up"] if buy else colors["down"]
        levels = below_levels if buy else above_levels

        level = 0
        while level < len(levels) and i - levels[level] < min_gap:
            level += 1
        if level < len(levels):
            levels[level] = i
        else:
            levels.append(i)
        level = min(level, 3)  # 4 kademeden fazlasi grafigi tasiriyor

        # Buyuk harf = MACD, kucuk harf = Chandelier. Boyut farkiyla birlikte
        # iki ayirt edici kanal olur; kimlik yalnizca renge/boyuta bagli kalmaz.
        if big:
            text = ("B" if buy else "S") if short else (
                "BUY" if buy else "SELL")
            bg, size, pad, base_shift = _rgba(base, 0.30), 14, 4, 26
        else:
            text = ("b" if buy else "s") if short else (
                "Buy" if buy else "Sell")
            bg, size, pad, base_shift = base, 9, 2, 12

        shift = base_shift + level * 19

        anns.append(dict(
            x=ts_all[i], y=low_all[i] if buy else high_all[i],
            xref="x", yref="y",   # ilk alt panel (fiyat grafigi)
            text="<b>{}</b>".format(text), showarrow=False,
            yshift=-shift if buy else shift,
            font=dict(size=size, color="#ffffff"),
            bgcolor=bg, bordercolor=base, borderwidth=1, borderpad=pad,
        ))

    return anns


def make_chart(
    df: pl.DataFrame,
    trend: pl.DataFrame | None,
    colors: dict,
    show_macd_panel: bool,
    badge_limit: int,
    short_labels: bool,
    timeframe: str = "15m",
    session: str = "24h",
) -> go.Figure:
    """Mum grafigi + yone gore renkli Chandelier stopu + sinyal rozetleri.

    CIFT EKSEN YOK: 4H yon ve MACD ayri alt panellerde, kendi eksenlerinde.
    """
    panels = [("price", 0.62)]
    if trend is not None and not trend.is_empty():
        panels.append(("trend", 0.16))
    if show_macd_panel and "macd" in df.columns:
        panels.append(("macd", 0.22))

    total = sum(h for _, h in panels)
    idx = {name: i + 1 for i, (name, _) in enumerate(panels)}

    fig = make_subplots(
        rows=len(panels), cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=[h / total for _, h in panels],
    )

    ts = df["ts"].to_list()
    badges: list[dict] = []

    fig.add_trace(
        go.Candlestick(
            x=ts, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Fiyat",
            increasing=dict(line=dict(color=colors["up"], width=1),
                            fillcolor=colors["up"]),
            decreasing=dict(line=dict(color=colors["down"], width=1),
                            fillcolor=colors["down"]),
        ),
        row=1, col=1,
    )

    # Chandelier stopu YONE GORE RENKLI. Tek cizgiyi parca parca boyamak
    # plotly'de mumkun olmadigi icin iki ayri seri: her biri kendi yonunde
    # dolu, digerinde null. connectgaps=False oldugu icin yon degisiminde
    # cizgi kirilir -- referans gorseldeki gibi.
    if "direction" in df.columns:
        for want, key, color, label in (
            (1, "long_stop", colors["up"], "Stop (uzun)"),
            (-1, "short_stop", colors["down"], "Stop (kisa)"),
        ):
            seg = df.with_columns(
                pl.when(pl.col("direction") == want)
                .then(pl.col(key)).otherwise(None).alias("_v")
            )["_v"]
            fig.add_trace(
                go.Scatter(x=ts, y=seg.to_list(), mode="lines", name=label,
                           line=dict(color=color, width=2), connectgaps=False,
                           hovertemplate="stop: %{y}<extra></extra>"),
                row=1, col=1,
            )

        n_signals = df.filter(pl.col("signal").is_not_null()).height
        if "macd_cross" in df.columns:
            n_signals += df.filter(pl.col("macd_cross").is_not_null()).height

        if badge_limit > 0 and n_signals > BADGE_DENSITY_LIMIT:
            # Yogun gorunum: rozet yerine ucgen isaret.
            for col, sig, symbol, color, size, label in (
                ("signal", "BUY", "triangle-up", colors["up"], 7,
                 "Chandelier al"),
                ("signal", "SELL", "triangle-down", colors["down"], 7,
                 "Chandelier sat"),
                ("macd_cross", "BUY", "triangle-up", colors["up"], 12,
                 "MACD al"),
                ("macd_cross", "SELL", "triangle-down", colors["down"], 12,
                 "MACD sat"),
            ):
                if col not in df.columns:
                    continue
                s = df.filter(pl.col(col) == sig)
                if s.is_empty():
                    continue
                buy = sig == "BUY"
                fig.add_trace(
                    go.Scatter(
                        x=s["ts"].to_list(),
                        y=(s["low"] * 0.999 if buy
                           else s["high"] * 1.001).to_list(),
                        mode="markers", name=label,
                        marker=dict(symbol=symbol, size=size, color=color,
                                    line=dict(width=1,
                                              color=colors["surface"])),
                        hovertemplate=label + "<extra></extra>",
                    ),
                    row=1, col=1,
                )
        else:
            badges = _build_badges(df, colors, badge_limit, short_labels)

    if "trend" in idx:
        r = idx["trend"]
        fig.add_trace(
            go.Scatter(x=trend["ts"].to_list(), y=trend["direction"].to_list(),
                       mode="lines", name="4H yon",
                       line=dict(color=colors["ink_muted"], width=2,
                                 shape="hv"),
                       hovertemplate="4H yon: %{y}<extra></extra>"),
            row=r, col=1,
        )
        fig.update_yaxes(row=r, col=1, tickvals=[-1, 1],
                         ticktext=["Kisa", "Uzun"], range=[-1.6, 1.6],
                         zeroline=False)

    if "macd" in idx:
        r = idx["macd"]
        hist = df["macd_hist"].to_list()
        fig.add_trace(
            go.Bar(x=ts, y=hist, name="MACD histogram",
                   marker=dict(color=[
                       colors["up"] if (h is not None and h >= 0)
                       else colors["down"] for h in hist]),
                   hovertemplate="hist: %{y}<extra></extra>"),
            row=r, col=1,
        )
        fig.add_trace(
            go.Scatter(x=ts, y=df["macd"].to_list(), mode="lines", name="MACD",
                       line=dict(color=colors["ink"], width=1.5),
                       hovertemplate="macd: %{y}<extra></extra>"),
            row=r, col=1,
        )
        fig.add_trace(
            go.Scatter(x=ts, y=df["macd_signal"].to_list(), mode="lines",
                       name="MACD sinyal",
                       line=dict(color=colors["ink_muted"], width=1.5,
                                 dash="dot"),
                       hovertemplate="sinyal: %{y}<extra></extra>"),
            row=r, col=1,
        )
        fig.update_yaxes(row=r, col=1, zeroline=True,
                         zerolinecolor=colors["axis"])

    fig.update_layout(
        template=colors["template"],
        paper_bgcolor=colors["surface"], plot_bgcolor=colors["surface"],
        font=dict(color=colors["ink"], family="system-ui, Segoe UI, sans-serif"),
        height=760 if len(panels) > 2 else 680,
        margin=dict(l=8, r=8, t=36, b=8),
        hovermode="x unified", xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(color=colors["ink"], size=12),
                    bgcolor="rgba(0,0,0,0)"),
        dragmode="pan", bargap=0,
        # Rozetler tek seferde yaziliyor -- tek tek add_annotation cagirmak
        # 257 rozette 13,8 saniye suruyordu (olculdu).
        annotations=badges,
    )
    # rangebreaks: Cumartesi hic islem yok; gizlenmezse grafigin buyuk bir
    # kismi olu alan olur. Pazar aksami (22:00 UTC acilis) verisi KORUNUR.
    #
    # AMA kripto 7/24 isler -- BTC'de hafta sonunu gizlemek GERCEK VERIYI
    # ekrandan siler. Bu yuzden kural seansa bagli.
    breaks = [] if session == "24x7" else [dict(bounds=["sat", "sun"])]
    fig.update_xaxes(gridcolor=colors["grid"], linecolor=colors["axis"],
                     rangebreaks=breaks,
                     tickformat=TICK_FORMAT[timeframe],
                     hoverformat=HOVER_FORMAT[timeframe],
                     tickfont=dict(color=colors["ink_muted"], size=11))
    fig.update_yaxes(gridcolor=colors["grid"], linecolor=colors["axis"],
                     tickfont=dict(color=colors["ink_muted"], size=11))
    return fig


def render() -> None:
    st.sidebar.markdown("[← Ana ekran](?ekran=home)")
    st.sidebar.title("Grafikler")

    # ---------------- veri tazeligi ----------------
    # Arayuz yalnizca OKUR; veritabanini kimse kendiliginden guncellemez.
    # Bu yuzden tazelik gorunur olmali, yoksa eski fiyata bakip guncel saniyorsunuz.
    if "refresh_result" in st.session_state:
        added = st.session_state.pop("refresh_result")
        st.sidebar.success("{} yeni bar eklendi.".format(added) if added
                           else "Veri zaten guncel.")

    if st.sidebar.button("Verileri guncelle", type="primary", width="stretch"):
        with st.spinner("Dukascopy'den yeni barlar cekiliyor..."):
            st.session_state["refresh_result"] = refresh_data()
        st.rerun()

    # "Bu ekrandaki fiyat ne kadar taze" sorusu dugmenin yanindayken cevaplansin.
    taze_metin, bayat = freshness()
    st.sidebar.caption("{}Son veri: {}".format("⚠ " if bayat else "", taze_metin))

    zone_label = st.sidebar.selectbox("Saat dilimi", list(DISPLAY_ZONES))
    tz = DISPLAY_ZONES[zone_label]

    st.sidebar.divider()

    code = st.sidebar.selectbox(
        "Enstruman", [i.code for i in INSTRUMENTS], index=1
    )
    tf_label = st.sidebar.selectbox("Zaman dilimi", list(TIMEFRAMES), index=0)
    timeframe = TIMEFRAMES[tf_label]

    period_label = st.sidebar.selectbox(
        "Zaman araligi", list(PERIODS),
        index=list(PERIODS).index(DEFAULT_PERIOD_BY_TF[timeframe]),
        key="period_{}".format(timeframe),  # dilim degisince varsayilan yenilensin
    )
    days = PERIODS[period_label]

    st.sidebar.divider()
    profile_name = st.sidebar.radio(
        "Chandelier profili", ["normal", "maverick"], horizontal=True
    )
    config = indicators.PROFILES[profile_name]

    show_macd_sig = st.sidebar.checkbox("MACD sinyalleri (buyuk rozet)", True)
    show_macd_panel = st.sidebar.checkbox("MACD paneli", False)
    show_trend = st.sidebar.checkbox("4H yon paneli", value=(timeframe == "15m"))
    # Varsayilan: HEPSI. Onceki surum "son N" aliyordu ve rozetler grafigin
    # sag kosesinde kumeleniyordu -- sinyaller sadece son gunlerde olmus gibi
    # gorunuyordu, yaniltiyordu. Simdi tum aralik boyunca ciziliyor.
    label_style = st.sidebar.radio(
        "Etiket", ["Kisa (B / S)", "Uzun (Buy / Sell)"], horizontal=False,
        help="Kisa etiket ~2 kat dar yer kaplar; yogun gorunumlerde "
             "cakismayi ciddi olcude azaltir. Buyuk harf = MACD, "
             "kucuk harf = Chandelier.",
    )
    short_labels = label_style.startswith("Kisa")

    badge_limit = st.sidebar.slider(
        "En fazla rozet", 0, 300, 300,
        help="0 = rozetleri kapat. Cakisanlar dikey kademeye ayrilir.",
    )

    st.sidebar.divider()
    theme_name = st.sidebar.radio("Tema", ["Koyu", "Acik"], horizontal=True)
    mode = "dark" if theme_name == "Koyu" else "light"
    scheme_name = st.sidebar.radio(
        "Renk duzeni", list(SCHEMES), horizontal=True,
        help="Ayrik = mavi/kirmizi, renk korlugunde de ayirt edilir.",
    )
    colors = dict(BASE[mode], **SCHEMES[scheme_name][mode])

    st.sidebar.caption(
        "Chandelier ATR {} / carpan {}  ·  MACD {}/{}/{}".format(
            config.atr_period, config.atr_multiplier,
            indicators.MACD_DEFAULT.fast, indicators.MACD_DEFAULT.slow,
            indicators.MACD_DEFAULT.signal,
        )
    )

    # ---------------- veri ----------------
    framed, shown_from = load_period(code, timeframe, days)
    if framed.is_empty():
        st.warning("Veri yok. Once: python scripts/backfill.py")
        return

    out = indicators.chandelier_exit(framed, config)
    if show_macd_sig or show_macd_panel:
        out = indicators.macd(out)
    # Isinma barlarini kes -- gosterge hesaplandiktan SONRA.
    out = out.slice(shown_from)

    if not show_macd_sig and "macd_cross" in out.columns:
        out = out.with_columns(pl.lit(None, dtype=pl.Utf8).alias("macd_cross"))

    truncated = 0
    if out.height > MAX_RENDER_BARS:
        truncated = out.height - MAX_RENDER_BARS
        out = out.tail(MAX_RENDER_BARS)

    trend = None
    if show_trend:
        t, _ = load_period(code, "4h", days)
        if not t.is_empty():
            trend = indicators.chandelier_exit(t, config).select(
                "ts", "direction"
            ).filter(pl.col("ts") >= out["ts"][0])

    # ---------------- ust satir ----------------
    last = out.tail(1)
    direction = int(last["direction"][0])
    last_atr = last["atr"][0]
    sig_rows = out.filter(pl.col("signal").is_not_null())

    bar_ts = last["ts"][0].astimezone(ZoneInfo(tz))
    _, age = data_age()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Son fiyat",
              "{:,.5f}".format(float(last["close"][0])).rstrip("0").rstrip("."))
    # Kisa bicim: tam tarih sutuna sigmiyor, "21.08.2026 2..." diye kesiliyordu.
    c2.metric("Son bar", bar_ts.strftime("%d.%m %H:%M"),
              help="{} ({})".format(bar_ts.strftime("%d.%m.%Y %H:%M"),
                                    zone_label))
    c3.metric("Yon", "Uzun" if direction == 1 else "Kisa")
    c4.metric("ATR", "{:.5f}".format(last_atr).rstrip("0").rstrip(".")
              if last_atr == last_atr else "-")
    c5.metric("Chandelier sinyali", str(sig_rows.tail(1)["signal"][0])
              if not sig_rows.is_empty() else "-",
              help=str(sig_rows.tail(1)["ts"][0])
              if not sig_rows.is_empty() else None)

    # Bayat veri uyarisi. Hafta sonu piyasa kapali oldugu icin 3 gune kadar
    # gecikme normaldir; esik ona gore.
    if age is not None and age > timedelta(days=3):
        st.warning(
            "Veritabanindaki en yeni bar **{} gun** onceye ait. Ekrandaki "
            "fiyatlar guncel DEGIL. Kenar cubugundaki **Verileri guncelle** "
            "dugmesine basin.".format(age.days)
        )

    # ---------------- grafik ----------------
    st.subheader(
        "{} · {} · {}".format(code, tf_label, period_label), anchor=False
    )
    if truncated:
        st.info(
            "Bu aralikta {:,} bar var; grafik en yeni {:,} bari cizdi. "
            "Daha genis bir zaman dilimi secerseniz tamami gorunur.".format(
                out.height + truncated, MAX_RENDER_BARS
            ).replace(",", ".")
        )

    # Cevrim YALNIZCA gorunum icin. Hesap ve saklama UTC'de kaldi; 4H kova
    # hizalamasi (00/04/08/12/16/20 UTC) bu yuzden bozulmuyor.
    disp = out.with_columns(pl.col("ts").dt.convert_time_zone(tz))
    disp_trend = (trend.with_columns(pl.col("ts").dt.convert_time_zone(tz))
                  if trend is not None else None)

    st.plotly_chart(
        make_chart(disp, disp_trend, colors, show_macd_panel, badge_limit,
                   short_labels, timeframe, get_instrument(code).session),
        width="stretch",
        config={"scrollZoom": True, "displaylogo": False},
    )
    n_sig_total = sig_rows.height + (
        out.filter(pl.col("macd_cross").is_not_null()).height
        if "macd_cross" in out.columns else 0
    )
    dense = badge_limit > 0 and n_sig_total > BADGE_DENSITY_LIMIT
    st.caption(
        "{} bar · {} - {} ({}) · {} sinyal · {}".format(
            "{:,}".format(out.height).replace(",", "."),
            disp["ts"][0].strftime("%d.%m.%Y %H:%M"),
            disp["ts"][-1].strftime("%d.%m.%Y %H:%M"),
            zone_label,
            n_sig_total,
            "yogun gorunum: ucgen isaret (rozet icin daha kisa bir aralik "
            "secin)" if dense
            else "kucuk rozet = Chandelier, buyuk rozet = MACD",
        )
    )

    # ---------------- tablo gorunumu ----------------
    with st.expander("Sinyal tablosu"):
        cols = ["ts", "signal", "close", "atr", "long_stop", "short_stop"]
        has_macd = "macd_cross" in out.columns
        if has_macd:
            cols.insert(2, "macd_cross")
        cond = pl.col("signal").is_not_null()
        if has_macd:
            cond = cond | pl.col("macd_cross").is_not_null()
        table = disp.filter(cond)   # tabloda da secili saat dilimi
        if table.is_empty():
            st.caption("Bu aralikta sinyal yok.")
        else:
            st.dataframe(table.select(cols).reverse().to_pandas(),
                         width="stretch", height=320)

    with st.expander("Veri kapsami"):
        st.dataframe(load_coverage().to_pandas(), width="stretch")

    st.caption(
        "Veri: Dukascopy · saklama: DuckDB tek dosya · UTC saklanir, "
        "ekranda {} gosterilir. Ust zaman dilimleri 15dk barlarindan "
        "turetilir (4H kovalari 00/04/08/12/16/20 UTC hizali).".format(
            zone_label)
    )

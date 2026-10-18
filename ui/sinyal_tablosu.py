"""Sinyal tablosu: secilen varlikta son N AL/SAT sinyalinin kisa raporu.

Kural akisi ekraniyla ayni sinyal kaynagi (`akis._sonuc`), ama ekranin tamami
tablo: baslangic fiyati, son fiyat, islem boyunca en dusuk/en yuksek fiyat,
kar/zarar yuzdesi ve tutari. Hesap burada degil motorun islem listesinde;
min/max yalniz o islemin baslangic-bitis aralindaki barlardan okunur.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import polars as pl
import streamlit as st

from finans_cortex import stoploss

from . import akis, theme
from .strategies import stop_widgets

TZ = akis.TZ
ADETLER = (10, 20, 30, 50)


def _tl(v: float) -> str:
    s = "{:,.2f}".format(abs(v)).replace(",", " ").replace(".", ",").replace(
        " ", ".")
    return "{}${}".format("-" if v < 0 else "+" if v > 0 else "", s)


def _yz(v: float) -> str:
    return "{}%{:.2f}".format("+" if v > 0 else "-" if v < 0 else "",
                              abs(v)).replace(".", ",")


def _satirlar(res, trades: pl.DataFrame, kapital: float,
              kaldirac: float) -> list[dict]:
    bars = res.bars
    ts = bars["ts"]
    son_kapanis = float(bars["close"][-1])
    tz = ZoneInfo(TZ)
    satirlar = []
    for t in reversed(trades.to_dicts()):
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


def _ozet(satirlar: list[dict], pb: str = "$") -> None:
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
    c[0].metric("Net", _tl(toplam).replace("$", pb))
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


STOP_BASAMAK = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)


def _stop_etudu(res, ham: pl.DataFrame, kapital: float,
                kaldirac: float) -> list[tuple[float, float, int]]:
    """Ayni islemlere % stop konsaydi: (stop %, net $, stoplanan islem)."""
    sonuc = []
    for p in STOP_BASAMAK:
        yeni = stoploss.trades_uygula(
            ham, res.bars, stoploss.StopAyar(stoploss.YUZDE, p), res.cost_bp)
        net = float(yeni["getiri"].sum()) * kapital * kaldirac
        sonuc.append((p, net, int((yeni["neden"] == stoploss.NEDEN).sum())))
    return sonuc


KAR_BASAMAK = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0)


def _kar_etudu(res, ham: pl.DataFrame, kapital: float,
               kaldirac: float) -> list[tuple[float, float, int]]:
    sonuc = []
    for p in KAR_BASAMAK:
        yeni = stoploss.trades_uygula(
            ham, res.bars, stoploss.StopAyar(), res.cost_bp,
            stoploss.StopAyar(stoploss.YUZDE, p))
        net = float(yeni["getiri"].sum()) * kapital * kaldirac
        sonuc.append((p, net, int((yeni["neden"] == stoploss.KAR_NEDEN).sum())))
    return sonuc


def _matris(res, ham: pl.DataFrame, kapital: float,
            kaldirac: float) -> list[tuple[float, float, float]]:
    """(stop %, kar al %, net $) -- tum ciftler."""
    out = []
    for sp in STOP_BASAMAK:
        for kp in KAR_BASAMAK:
            yeni = stoploss.trades_uygula(
                ham, res.bars, stoploss.StopAyar(stoploss.YUZDE, sp),
                res.cost_bp, stoploss.StopAyar(stoploss.YUZDE, kp))
            out.append((sp, kp, float(yeni["getiri"].sum()) * kapital
                        * kaldirac))
    return out


def _matris_md(matris: list[tuple[float, float, float]]) -> list[str]:
    kolonlar = sorted({m[1] for m in matris})
    satirlar = ["| Stop / Kar al | " + " | ".join("%" + _say(k)
                                                  for k in kolonlar) + " |",
                "|---|" + "---|" * len(kolonlar)]
    for sp in sorted({m[0] for m in matris}):
        deger = {m[1]: m[2] for m in matris if m[0] == sp}
        satirlar.append("| %{} | ".format(_say(sp)) + " | ".join(
            _tl(deger[k]) for k in kolonlar) + " |")
    return satirlar


def _ort(x: list[float]) -> float:
    return sum(x) / len(x) if x else 0.0


def _say(v: float) -> str:
    return "{:g}".format(v).replace(".", ",")


def rapor(res, ham: pl.DataFrame, satirlar: list[dict], kapital: float,
          kaldirac: float, kod: str, ad: str, tf_label: str) -> tuple[str, str]:
    """(ekranda gosterilecek markdown, indirilecek metin) -- ikisi ayni.

    `ham`: stop-loss UYGULANMAMIS son N islem (etut buna konur);
    `satirlar`: kullanicinin sectigi stop ile gosterilen islemler."""
    kapali = [s for s in satirlar if not s["acik"]]
    n = len(kapali)
    if n == 0:
        return ("Kapanmis islem yok; rapor icin en az bir kapanmis islem "
                "gerekir.", "")
    kaz = [s for s in kapali if s["getiri"] > 0]
    kay = [s for s in kapali if s["getiri"] <= 0]
    ort_kaz = _ort([s["getiri"] * 100 for s in kaz])
    ort_kay = _ort([s["getiri"] * 100 for s in kay])
    oran = len(kaz) / n
    beklenti = _ort([s["getiri"] * 100 for s in kapali])
    toplam = sum(s["tutar"] for s in satirlar)
    baslabas = (abs(ort_kay) / (ort_kaz + abs(ort_kay)) if kaz and kay
                else float("nan"))
    sure_kaz = _ort([s["sure"].total_seconds() for s in kaz])
    sure_kay = _ort([s["sure"].total_seconds() for s in kay])

    def yon_satiri(yon: int, ad_: str) -> str:
        x = [s for s in kapali if s["yon"] == yon]
        if not x:
            return "- {}: islem yok".format(ad_)
        return "- {}: {} islem, kazanma %{:.0f}, net {}, ort. {}".format(
            ad_, len(x), 100 * sum(1 for s in x if s["getiri"] > 0) / len(x),
            _tl(sum(s["tutar"] for s in x)),
            _yz(_ort([s["getiri"] * 100 for s in x])))

    nedenler: dict[str, list[float]] = {}
    for s in kapali:
        nedenler.setdefault(s["neden"], []).append(s["getiri"] * 100)
    neden_satir = ["- {}: {} islem, ort. {}".format(k, len(v), _yz(_ort(v)))
                   for k, v in sorted(nedenler.items(),
                                      key=lambda kv: -len(kv[1]))]

    kay_mae = _ort([s["mae"] for s in kay])
    kaz_mae = _ort([s["mae"] for s in kaz])
    kaz_mfe = _ort([s["mfe"] for s in kaz])
    kay_once_kar = [s for s in kay if s["mfe"] >= 0.5]
    geri_verilen = _ort([s["mfe"] - s["getiri"] * 100 for s in kaz])

    etut = _stop_etudu(res, ham, kapital, kaldirac)
    kar_etut = _kar_etudu(res, ham, kapital, kaldirac)
    kar_en_iyi = max(kar_etut, key=lambda r: r[1])
    temel_net = float(ham["getiri"].sum()) * kapital * kaldirac
    en_iyi = max(etut, key=lambda r: r[1])
    etut_satir = ["| Stop | Net $ | Fark | Stoplanan islem |",
                  "|---|---|---|---|"]
    for p, net, k in etut:
        etut_satir.append("| %{} | {} | {} | {} |".format(
            _say(p), _tl(net), _tl(net - temel_net), k))

    matris = _matris(res, ham, kapital, kaldirac)
    m_en = max(matris, key=lambda r: r[2])
    seri = en_uzun = 0
    for s in reversed(satirlar):
        seri = seri + 1 if s["getiri"] <= 0 else 0
        en_uzun = max(en_uzun, seri)

    oneri = []
    if n < 30:
        oneri.append("Orneklem kucuk ({} kapanmis islem): sonuclar yon "
                     "gosterir, kanit sayilmaz; 50 sinyale cikarip "
                     "bakin.".format(n))
    if beklenti <= 0:
        oneri.append("Islem basina beklenti negatif ({}): bu donemde strateji "
                     "maliyeti cikaramiyor.".format(_yz(beklenti)))
    if baslabas == baslabas and oran < baslabas:
        oneri.append("Kazanma orani (%{:.0f}) basabas oraninin (%{:.0f}) "
                     "altinda: kazananlari daha uzun tasimak ya da "
                     "kaybedenleri daha erken kesmek gerekir.".format(
                         100 * oran, 100 * baslabas))
    for yon, ad_ in ((1, "AL"), (-1, "SAT")):
        x = [s for s in kapali if s["yon"] == yon]
        net_x = sum(s["tutar"] for s in x)
        if len(x) >= 5 and net_x < 0:
            oneri.append("{} islemleri toplamda zarar yazdi ({}): {} tarafini "
                         "kapatmayi ya da o yone ayri kural koymayi "
                         "deneyin.".format(ad_, _tl(net_x), ad_))
    if en_iyi[1] > temel_net:
        oneri.append("Bu {} islemde %{} stop-loss net sonucu {} -> {} "
                     "yapardi (stop-loss kutusundan deneyin).".format(
                         len(ham), _say(en_iyi[0]), _tl(temel_net),
                         _tl(en_iyi[1])))
    else:
        oneri.append("Denenen sabit % stoplarin hicbiri sonucu "
                     "iyilestirmedi: kayiplar zaten strateji cikisiyla "
                     "kapaniyor ya da stop kazananlari da kesiyor.")
    if kar_en_iyi[1] > temel_net:
        oneri.append("Tek basina %{} kar al net sonucu {} -> {} yapardi.".format(
            _say(kar_en_iyi[0]), _tl(temel_net), _tl(kar_en_iyi[1])))
    else:
        oneri.append("Sabit % kar al tek basina sonucu iyilestirmedi: "
                     "kazananlari erken kesmek zarar veriyor olabilir; "
                     "strateji cikisi kari daha iyi tasiyor gorunuyor.")
    if m_en[2] > max(temel_net, en_iyi[1], kar_en_iyi[1]):
        oneri.append("Stop %{} + kar al %{} birlikte en iyi cift: net {} "
                     "(stopsuz-karsiz {}). Bu bir secim sonucu: ayni "
                     "islemlerden secildigi icin fazla iyimser, baska "
                     "doneme/varliga da bakin.".format(
                         _say(m_en[0]), _say(m_en[1]), _tl(m_en[2]),
                         _tl(temel_net)))
    if kay and len(kay_once_kar) / len(kay) >= 0.4:
        oneri.append("Kaybeden islemlerin %{:.0f}'i once en az %0,5 karda "
                     "gitti: kar al ya da kari kilitleyen (iz suren) stop "
                     "dusunulebilir.".format(100 * len(kay_once_kar) / len(kay)))
    if kaz and kaz_mfe > 0 and geri_verilen / kaz_mfe > 0.5:
        oneri.append("Kazananlar zirvedeki kari ortalama {} geri veriyor "
                     "(zirve {}): cikis gec kaliyor olabilir.".format(
                         _yz(geri_verilen), _yz(kaz_mfe)))
    if en_uzun >= 4:
        oneri.append("{} islemlik ust uste kayip serisi var: pozisyon "
                     "buyuklugu ya da seri sonrasi bekleme kurali "
                     "dusunulebilir.".format(en_uzun))
    if sure_kaz > 0 and sure_kay > 2 * sure_kaz:
        oneri.append("Kaybedenler kazananlardan {} kat uzun tutuluyor: zaman "
                     "stopu (N bar sonra kar yoksa cik) denenebilir.".format(
                         _say(round(sure_kay / sure_kaz, 1))))
    if not oneri:
        oneri.append("Belirgin bir zayiflik yakalanmadi; asil karar icin "
                     "Backtest'te daha uzun donem ve tum varliklara bakin.")

    md = "\n".join([
        "#### Rapor · {} · {} · {} · son {} sinyal".format(
            kod, ad, tf_label, len(satirlar)),
        "",
        "**Genel**",
        "- Kapanmis {} islem (+{} acik): {} kazanan, {} kaybeden, kazanma "
        "%{:.0f}".format(n, len(satirlar) - n, len(kaz), len(kay), 100 * oran),
        "- Ort. kazanc {} / ort. kayip {} · basabas kazanma orani {}".format(
            _yz(ort_kaz), _yz(ort_kay),
            "%{:.0f}".format(100 * baslabas) if baslabas == baslabas else "-"),
        "- Islem basina beklenti {} · net {} (kapital {}, kaldirac {}x)".format(
            _yz(beklenti), _tl(toplam), _tl(kapital)[1:], _say(kaldirac)),
        "- Ort. sure: kazanan {} · kaybeden {}".format(
            akis._sure(timedelta(seconds=sure_kaz)),
            akis._sure(timedelta(seconds=sure_kay))),
        "- En uzun ust uste kayip: {}".format(en_uzun),
        "",
        "**Yon**", yon_satiri(1, "AL"), yon_satiri(-1, "SAT"),
        "",
        "**Cikis nedenleri**", *neden_satir,
        "",
        "**Islem ici seyir (girise gore)**",
        "- Kazananlar: en kotu {} · en iyi {} · gercek sonuc {}".format(
            _yz(kaz_mae), _yz(kaz_mfe), _yz(ort_kaz)),
        "- Kaybedenler: en kotu {} · gercek sonuc {}".format(
            _yz(kay_mae), _yz(ort_kay)),
        "",
        "**Stop-loss etudu** (ayni {} islem; yalniz sabit % stop eklenseydi. "
        "Stop yokken net {})".format(len(ham), _tl(temel_net)),
        "",
        *etut_satir,
        "",
        "**Kar al etudu** (yalniz sabit % kar al; stop yok)",
        "",
        *["| Kar al | Net $ | Fark | Kar alinan islem |", "|---|---|---|---|"],
        *["| %{} | {} | {} | {} |".format(_say(p), _tl(net),
                                          _tl(net - temel_net), k)
          for p, net, k in kar_etut],
        "",
        "**Stop x Kar al matrisi** (net $; satir = stop %, sutun = kar al %)",
        "",
        *_matris_md(matris),
        "",
        "**Oneriler** (kural tabanli; karar sizin)",
        "",
        *["{}. {}".format(i + 1, o) for i, o in enumerate(oneri)],
    ])
    return md, md.replace("#### ", "").replace("**", "")


@st.cache_resource(ttl=600, max_entries=16, show_spinner=False)
def _bist_sonuc(temel: str, code: str, timeframe: str, cfg):
    """BIST hissesi icin gecmis calistirma (ayri tablo, 20 bp maliyet)."""
    from finans_cortex import backtest as bt_cost

    from .backtest import _raw_bars
    from .strategies import motor
    return motor(temel).run_bars(
        _raw_bars(code, timeframe, "bist"), code, timeframe, cfg,
        days=akis.GUN.get(timeframe, 180),
        cost_bp=bt_cost.bist_cost_for(code).roundtrip_bp)


def render(strat: dict, cfg, timeframe: str, tf_label: str) -> None:
    """Stratejiler > <strateji> > Sinyal tablosu bolumu."""
    from dataclasses import replace

    from finans_cortex.instruments import HESAP_KODLARI

    from .backtest import BIST_TF, PIYASALAR, _kodlar
    from .strategies import timeframes

    ust = st.columns([1, 1, 0.9, 0.8, 0.8, 0.8], gap="small",
                     vertical_alignment="bottom")
    piyasa = PIYASALAR[ust[0].selectbox("Piyasa", list(PIYASALAR),
                                        key="st_piyasa")]
    bist = piyasa == "bist"
    kodlar = _kodlar(piyasa) if bist else list(HESAP_KODLARI)
    if not kodlar:
        st.info("BIST gecmisi henuz indirilmedi. **Veri Merkezi > BIST "
                "gecmisini guncelle**'ye bir kez basin.")
        return
    tf_not = ""
    if bist:
        # Backtest panelindeki kural: stratejinin dilimleri ∩ BIST'te olanlar.
        uygun = {lbl: kod for lbl, kod in timeframes(strat).items()
                 if kod in BIST_TF}
        if not uygun:
            st.warning("**{}** BIST'te calistirilamiyor: bu strateji {} "
                       "diliminde calisiyor, BIST'te yalniz gunluk ve 1 saat "
                       "var.".format(strat["ad"], " / ".join(timeframes(strat))))
            return
        tf_label = ust[2].selectbox("Zaman dilimi", list(uygun),
                                    key="st_bist_tf_" + strat["key"])
        timeframe = uygun[tf_label]
        if getattr(cfg, "onay_15m", False):
            cfg = replace(cfg, onay_15m=False)
            tf_not = " · BIST'te 15dk teyidi yok, kapali calisti"
    else:
        ust[2].caption("Zaman dilimi: **{}**".format(tf_label))
    code = ust[1].selectbox("Hisse" if bist else "Varlik", kodlar,
                            index=min(1, len(kodlar) - 1),
                            key="st_hisse" if bist else "st_varlik")
    pb = "₺" if bist else "$"
    adet = ust[3].selectbox("Son kac sinyal", ADETLER, index=1, key="st_adet")
    kapital = ust[4].number_input("Kapital ({})".format(pb), min_value=10.0,
                                  value=1000.0, step=100.0, key="st_kapital")
    kaldirac = ust[5].number_input("Kaldirac (x)", min_value=1.0, value=1.0,
                                   step=1.0, key="st_kaldirac")
    stop = stop_widgets("st_stop")
    kar = stop_widgets("st_kar", kar=True)
    try:
        res = (_bist_sonuc(strat["temel"], code, timeframe, cfg) if bist
               else akis._sonuc(strat["temel"], code, timeframe, cfg))
    except Exception as exc:      # noqa: BLE001 -- kullaniciya gosterilir
        st.error("Sinyaller hesaplanamadi: {}".format(exc))
        return
    if res.trades.is_empty():
        st.info("{} icin son {} gunde bu ayarlarla sinyal yok.".format(
            code, akis.GUN.get(timeframe, 180)))
        return
    ham = res.trades.tail(adet)
    trades = stoploss.trades_uygula(ham, res.bars, stop, res.cost_bp, kar)
    satirlar = _satirlar(res, trades, kapital, kaldirac)
    st.caption(
        "Son {} sinyal · {} · maliyet dahil ({} bp gidis-donus) · her "
        "islemde ayni kapital · en dusuk/en yuksek = islem suresince goren "
        "fiyat; en iyi/en kotu ara = girisinize gore{}".format(
            len(satirlar), tf_label, _say(res.cost_bp), tf_not))
    _ozet(satirlar, pb)
    st.markdown(_tablo(satirlar).replace("$", pb), unsafe_allow_html=True)
    st.markdown("---")
    md, metin = rapor(res, ham, satirlar, kapital, kaldirac, code,
                      strat.get("ad", ""), tf_label)
    if bist:
        md, metin = md.replace("$", pb), metin.replace("$", pb)
    else:
        md = md.replace("$", "\\$")      # Streamlit $...$ = LaTeX sanmasin
    st.markdown(md)
    if metin:
        st.download_button("Raporu indir (.txt)", metin,
                           file_name="sinyal_raporu_{}.txt".format(code),
                           key="st_indir")

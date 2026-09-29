"""Gorsel dil: palet + neon CSS.

Neden ayri dosya: renk ve stil kararlari tek yerde dursun ki her yeni ekran
ayni dili konussun. Anayasa 2.4'teki "arayuz veri katmanindan ayrik" ilkesinin
devami -- burasi tamamen sunum katmani, veri bilmez.

TASARIM NOTU (renk secimi rastgele degil):
Kutucuk vurgu renkleri, dogrulanmis bir kategorik paletin koyu-mod
basamaklarindan alindi. Bu sira renk korlugu ayirt edilebilirligi icin
sinanmis bir siradir; "guzel duran renk" diye degistirilmemeli.
"""

from __future__ import annotations

# Yuzeyler. Grafik ekraniyla uyumlu kalsin diye ayni aileden, neon
# kontrasti icin bir tik daha koyu.
PAGE = "#0b0b0d"
PANEL = "#131316"
PANEL_HI = "#191920"
INK = "#f2f2f0"
INK_DIM = "#8b8a93"
HAIRLINE = "rgba(255,255,255,0.09)"

# Fiyat yonu -- grafik ekranindaki "Klasik" duzenle ayni.
UP = "#26a269"
DOWN = "#e66767"

# Kategorik vurgu sirasi (koyu mod basamaklari).
ACCENTS = {
    "blue": "#3987e5",
    "aqua": "#199e70",
    "violet": "#9085e9",
    "orange": "#d95926",
    "magenta": "#d55181",
    "yellow": "#c98500",
}


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "rgba({},{},{},{})".format(r, g, b, alpha)


def global_css() -> str:
    """HER sayfanin basinda uygulanan ortak kurallar (app.py cagirir).

    Kullanici (21.09.2026): "ustte gereksiz bir bosluk var her sayfada, o
    bosluk hic olmasin". Bosluk Streamlit'in kendi ust cubugu (~3,75rem) +
    ana kabin ust dolgusu (~6rem) toplamiydi. Cubuk sifir yukseklige
    indirildi ama `overflow: visible` -- kenar cubugu kapaliyken acma dugmesi
    ve sag ustteki "calisiyor" gostergesi yine gorunsun, tiklansin.
    Deploy dugmesi .streamlit/config.toml (toolbarMode = minimal) ile gitti.
    """
    return """
<style>
  header[data-testid="stHeader"] {{
     height:0 !important; min-height:0 !important;
     background:transparent !important; overflow:visible !important;
  }}
  [data-testid="stMainBlockContainer"], .block-container {{
     padding-top:1.1rem !important;
  }}
  [data-testid="stSidebarHeader"] {{
     padding:.55rem 1rem .1rem 1rem !important; height:auto !important;
     min-height:0 !important;
  }}
  [data-testid="stSidebarUserContent"] {{padding-top:.2rem !important;}}
  /* Ust cubuk sifir yukseklikte: icindeki dugmeler yukari tasiyordu (kenar
     cubugunu ACMA dugmesi -14 px'te, yarisi ekran disindaydi). Sabitlenir. */
  [data-testid="stExpandSidebarButton"],
  [data-testid="stSidebarCollapsedControl"] {{
     position:fixed !important; top:.6rem !important; left:.6rem !important;
     z-index:999990 !important;
  }}
  [data-testid="stStatusWidget"] {{
     position:fixed !important; top:.5rem !important; right:1rem !important;
     z-index:999990 !important;
  }}

  /* Strateji sayfasinin tek satirlik basligi */
  .dc-sbaslik {{font-size:16.5px; font-weight:600; color:{ink};
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
  .dc-sbaslik .no {{display:inline-block; min-width:22px; padding:0 7px;
                    margin-right:8px; border:1px solid {accent_40};
                    border-radius:20px; font-size:12px; font-weight:600;
                    color:{accent}; text-align:center;}}
</style>
""".format(ink=INK, accent=ACCENTS["blue"],
           accent_40=rgba(ACCENTS["blue"], 0.55))


def css() -> str:
    """Ana ekranin stil sayfasi.

    Streamlit'in kendi kabugunu (ust bosluk, menu) sadelestirip uzerine
    kendi duzenimizi koyuyoruz.
    """
    return """
<style>
  /* --- Streamlit kabugunu sadelestir --- */
  #MainMenu, footer, header {{visibility: hidden;}}
  .block-container {{padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}}
  .stApp {{background: {page};}}

  /* --- Baslik --- */
  .dc-head {{
     display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
     margin: 0 0 4px 0;
  }}
  /* Veri tazeligi rozeti -- basligin sag ucunda, Veri Merkezi'ne baglanti */
  .dc-fresh {{
     margin-left:auto; font-size:11.5px; letter-spacing:.04em;
     color:{dim} !important; text-decoration:none !important;
     border:1px solid {hair}; border-radius:20px; padding:3px 12px;
     white-space:nowrap; transition:color .16s ease, border-color .16s ease;
  }}
  .dc-fresh:hover {{color:{ink} !important; border-color:{accent_40};}}
  .dc-fresh .dot {{color:{ok}; font-size:13px; line-height:1;}}
  .dc-fresh.stale {{color:{warn} !important; border-color:{warn_dim};}}
  .dc-fresh.stale .dot {{color:{warn};}}
  .dc-title {{
     font-family: system-ui, "Segoe UI", sans-serif;
     font-size: 32px; font-weight: 200; letter-spacing: .17em;
     color: {ink} !important; text-transform: uppercase; margin:0;
     text-shadow: 0 0 20px {glow};
  }}
  .dc-title b {{
     font-weight:600; color:{accent} !important;
     text-shadow: 0 0 16px {accent};
  }}
  .dc-sub {{
     font-size: 12.5px; color:{dim}; letter-spacing:.06em; margin:0;
  }}
  .dc-rule {{
     height:1px; margin:14px 0 22px 0;
     background: linear-gradient(90deg, {accent_40}, rgba(0,0,0,0) 70%);
  }}

  /* --- Fiyat seridi --- */
  .dc-ticker {{
     display:grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
     gap:10px; margin-bottom:26px;
  }}
  .dc-tick {{
     background:{panel}; border:1px solid {hair}; border-radius:9px;
     padding:11px 13px 10px 13px; position:relative; overflow:hidden;
  }}
  .dc-tick::before {{
     content:""; position:absolute; left:0; top:0; bottom:0; width:2px;
     background:var(--c); box-shadow:0 0 9px var(--c);
  }}
  .dc-tick .n {{
     font-size:10.5px; letter-spacing:.13em; color:{dim};
     text-transform:uppercase; display:block; margin-bottom:5px;
  }}
  .dc-tick .p {{
     font-size:19px; color:{ink}; font-variant-numeric: tabular-nums;
     letter-spacing:-.01em;
  }}
  .dc-tick .d {{
     font-size:12px; font-variant-numeric: tabular-nums; margin-left:7px;
  }}

  /* --- Menu kutucuklari --- */
  /* Sabit 3 sutun: "az menu olacagi icin biraz buyuk olabilir" istegi.
     auto-fit birakilirsa genis ekranda 4-5 sutuna dusup kucululyordu. */
  .dc-grid {{
     display:grid; grid-template-columns: repeat(3, 1fr);
     gap:18px;
  }}
  @media (max-width: 860px) {{
     .dc-grid {{grid-template-columns: repeat(2, 1fr);}}
  }}
  .dc-tile {{
     position:relative; display:flex; flex-direction:column;
     justify-content:center; gap:13px;
     aspect-ratio: 1 / 1;
     background:{panel}; border:1px solid var(--c-dim); border-radius:16px;
     padding:26px;
     transition: transform .16s ease, box-shadow .16s ease,
                 border-color .16s ease, background .16s ease;
     box-shadow: inset 0 0 26px rgba(0,0,0,.38);
  }}
  /* Streamlit'in kendi baglanti stili (mavi + alti cizili) kutucuklarin
     icine siziyordu; hepsini burada bastiriyoruz. */
  .dc-tile, .dc-tile:hover, .dc-tile:visited,
  .dc-tile *, .dc-tile:hover * {{
     text-decoration: none !important;
  }}
  .dc-tile:hover {{
     transform: translateY(-3px);
     border-color: var(--c);
     background:{panel_hi};
     box-shadow: 0 0 26px var(--c-glow), inset 0 0 26px rgba(0,0,0,.3);
  }}
  .dc-tile .ico {{
     color:var(--c) !important;
     filter: drop-shadow(0 0 8px var(--c-glow));
     line-height:0;
  }}
  .dc-tile .lbl {{
     font-size:17px; color:{ink} !important; letter-spacing:.02em;
     font-weight:500; display:block;
  }}
  .dc-tile .desc {{
     font-size:12px; color:{dim} !important; line-height:1.5; margin-top:7px;
  }}
  .dc-tile .soon {{
     position:absolute; top:14px; right:14px; font-size:9.5px;
     letter-spacing:.1em; color:{dim}; border:1px solid {hair};
     border-radius:20px; padding:2px 8px; text-transform:uppercase;
  }}
  .dc-tile.ready .soon {{
     color:var(--c); border-color:var(--c-dim);
  }}

  .dc-foot {{
     margin-top:30px; font-size:11px; color:{dim}; letter-spacing:.04em;
  }}
</style>
""".format(
        page=PAGE, panel=PANEL, panel_hi=PANEL_HI, ink=INK, dim=INK_DIM,
        hair=HAIRLINE, accent=ACCENTS["blue"],
        ok=ACCENTS["aqua"], warn=ACCENTS["yellow"],
        warn_dim=rgba(ACCENTS["yellow"], 0.45),
        accent_40=rgba(ACCENTS["blue"], 0.40),
        glow=rgba(ACCENTS["blue"], 0.30),
    )

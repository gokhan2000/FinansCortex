"""Enstrüman kayıt defteri.

Anayasa 2.2'deki `Unified_Ticker` fikrinin somut hali. İki kritik karar burada:

1. Kimlik olarak ticker string'i DEĞİL, sabit bir `code` kullanılıyor ve veritabanında
   surrogate `instrument_id`'ye bağlanıyor. Kaynak sembolü (`source_symbol`) değişirse
   ya da başka bir sağlayıcıya geçilirse geçmiş veri kopmaz.
2. `source_symbol` yalnızca burada geçer. Sistemin geri kalanı `code` ile konuşur --
   anayasadaki "veri sağlayıcı pluggable olmalı" kuralının uygulaması.

Tarihler `scripts/probe_dukascopy.py` ile ÖLÇÜLDÜ, tahmin değil.
Bkz. docs/VERI_KAYNAGI_BULGULARI.md bölüm 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from dukascopy_python.instruments import (
    INSTRUMENT_CMD_ENERGY_E_BRENT,
    INSTRUMENT_CMD_ENERGY_E_LIGHT,
    INSTRUMENT_FX_MAJORS_EUR_USD,
    INSTRUMENT_FX_METALS_XAG_USD,
    INSTRUMENT_FX_METALS_XAU_USD,
    INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    INSTRUMENT_IDX_EUROPE_E_DAAX,
    INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
    INSTRUMENT_VCCY_BTC_USD,
)


@dataclass(frozen=True)
class Instrument:
    code: str
    """Sistem geneli sabit kimlik. Asla değişmez."""

    source_symbol: str
    """Dukascopy sembolü. Sağlayıcı değişirse burası değişir, `code` değişmez."""

    category: str
    tags: tuple[str, ...]
    history_start: date
    """Ölçülmüş veri başlangıcı. Dolum bu tarihten öncesini denemez."""

    session: str
    """Seans profili -- boşluk analizinde beklenen bar sayısını belirler."""

    hesapta: bool = True
    """Strateji hesaplarına (Backtest, Geliştir, sinyal listesi) girer mi.
    False: veri güncellenir, grafikte görünür ama hiçbir hesaba katılmaz."""


# 24 saatlik piyasalar günde 96 adet 15dk barı üretir (24*4).
# Endeksler nakit seans süresince işlem gördüğü için çok daha az.
INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument(
        code="EURUSD",
        source_symbol=INSTRUMENT_FX_MAJORS_EUR_USD,
        category="fx",
        tags=("FX", "Major", "24x5"),
        history_start=date(2012, 1, 1),
        session="24h",
    ),
    Instrument(
        code="XAUUSD",
        source_symbol=INSTRUMENT_FX_METALS_XAU_USD,
        category="metal",
        tags=("Metal", "Spot", "SafeHaven", "24x5"),
        history_start=date(2003, 6, 1),
        session="24h",
    ),
    Instrument(
        code="XAGUSD",
        source_symbol=INSTRUMENT_FX_METALS_XAG_USD,
        category="metal",
        tags=("Metal", "Spot", "High_Volatility", "24x5"),
        history_start=date(2015, 1, 1),
        session="24h",
    ),
    Instrument(
        code="BRENT",
        source_symbol=INSTRUMENT_CMD_ENERGY_E_BRENT,
        category="energy",
        tags=("Energy", "Continuous", "24x5"),
        history_start=date(2015, 1, 1),
        session="24h",
    ),
    Instrument(
        code="WTI",
        source_symbol=INSTRUMENT_CMD_ENERGY_E_LIGHT,
        category="energy",
        tags=("Energy", "Continuous", "24x5"),
        history_start=date(2013, 1, 1),
        session="24h",
    ),
    Instrument(
        code="DJ",
        source_symbol=INSTRUMENT_IDX_AMERICA_E_D_J_IND,
        category="index",
        tags=("Index", "US", "CashSession"),
        history_start=date(2015, 1, 1),
        session="us_cash",
    ),
    Instrument(
        code="DAX",
        source_symbol=INSTRUMENT_IDX_EUROPE_E_DAAX,
        category="index",
        tags=("Index", "EU", "CashSession"),
        history_start=date(2015, 1, 1),
        session="eu_cash",
    ),
    Instrument(
        code="FTSE",
        source_symbol=INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
        category="index",
        tags=("Index", "UK", "CashSession"),
        history_start=date(2015, 1, 1),
        session="eu_cash",
    ),
    # Tek 7/24 enstruman. Olculdu (scratchpad/btc_probe.py): hafta sonu da
    # islem goruyor -- Cumartesi 96, Pazar 96 bar. Bu yuzden session="24x7";
    # grafikteki "hafta sonunu gizle" (rangebreaks) kurali BTC'ye
    # UYGULANMAMALI, yoksa gercek veri ekrandan silinir.
    # Gecmis 2017'de basliyor (2015-2016 bos dondu).
    Instrument(
        code="BTCUSD",
        source_symbol=INSTRUMENT_VCCY_BTC_USD,
        category="crypto",
        tags=("Crypto", "High_Volatility", "24x7"),
        history_start=date(2017, 1, 1),
        session="24x7",
        # Kullanici (24.09.2026): "BTC'ye hicbir zaman girmem, hesaplardan
        # cikar." Ayrica 7/24 oldugu icin hafta sonu portfoy hesabini
        # bozuyordu (bkz. gelistir._portfoy_gunluk).
        hesapta=False,
    ),
)

BY_CODE: dict[str, Instrument] = {i.code: i for i in INSTRUMENTS}

HESAP_KODLARI: tuple[str, ...] = tuple(i.code for i in INSTRUMENTS if i.hesapta)
"""Strateji hesaplarina giren varliklar (Backtest, Gelistir, sinyal listesi)."""


def get(code: str) -> Instrument:
    try:
        return BY_CODE[code]
    except KeyError:
        known = ", ".join(BY_CODE)
        raise KeyError("bilinmeyen enstruman: {} (mevcut: {})".format(code, known))

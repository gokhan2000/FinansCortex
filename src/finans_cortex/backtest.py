"""Vektörel backtest motoru.

--------------------------------------------------------------------------
ANAYASADAN SAPMA (3.1) -- gerekçesiyle
--------------------------------------------------------------------------
Anayasa Backtrader diyordu. Faz 1 için kullanılmadı, sebepleri:

1. Backtrader pandas ister; verimiz Polars/DuckDB'de. Her testte dönüşüm
   maliyeti ve iki kütüphanenin her yere sızma riski var.
2. Backtrader'ın aktif bakımı yıllardır durmuş durumda.
3. Stratejimiz TEK pozisyonlu ve sinyaller zaten vektörel hesaplanıyor.
   Bu yapı için olay-döngüsü motoru gereksiz ağır; 150 satırlık vektörel
   hesap hem daha hızlı hem denetlenebilir.

Backtrader Faz 2'de (çoklu pozisyon, piramitleme, portföy seviyesi risk)
yeniden değerlendirilmeli. O zaman gerçekten kazanç sağlar.

--------------------------------------------------------------------------
LOOK-AHEAD KORUMASI
--------------------------------------------------------------------------
Pozisyon bir barın KAPANIŞINDA belirlenir, getirisi BİR SONRAKİ bardan
itibaren işler: `pozisyon.shift(1) * bar_getirisi`. Sinyalin oluştuğu barın
hareketinden kâr edilmez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

BARS_PER_YEAR = 252.0


@dataclass(frozen=True)
class CostModel:
    """Gidiş-dönüş işlem maliyeti, baz puan (1 bp = %0,01).

    UYARI: aşağıdaki varsayılanlar TAHMİNDİR, ölçüm değil. Gerçek aracı
    kurum spread/komisyonuyla değiştirilmelidir. Anayasa 3.5'in "kağıt üstü
    getiri ile gerçek getiri ayrımı" şartı ancak gerçek rakamlarla sağlanır.
    """

    spread_bp: float
    commission_bp: float = 0.0

    @property
    def roundtrip_bp(self) -> float:
        return self.spread_bp + 2 * self.commission_bp


# Tipik spread mertebeleri -- DOĞRULANMALI.
DEFAULT_COSTS: dict[str, CostModel] = {
    "EURUSD": CostModel(spread_bp=1.0),
    "XAUUSD": CostModel(spread_bp=3.0),
    "XAGUSD": CostModel(spread_bp=10.0),
    "BRENT": CostModel(spread_bp=5.0),
    "WTI": CostModel(spread_bp=5.0),
    "DJ": CostModel(spread_bp=2.0),
    "DAX": CostModel(spread_bp=2.0),
    "FTSE": CostModel(spread_bp=3.0),
}
FALLBACK_COST = CostModel(spread_bp=5.0)

# BIST hisseleri (23 Eylul 2026). Kuresel enstrumanlardan PAHALIDIR: spread'in
# ustune araci kurum komisyonu biner. Buradaki degerler de TAHMIN -- kullanici
# kendi araci kurumunun oranini yazmali, yoksa backtest gercekten iyimser
# cikar. Tipik: spread ~10 bp (likit BIST 30 hissesi), komisyon yonde ~5 bp.
BIST_COST = CostModel(spread_bp=10.0, commission_bp=5.0)   # gidis-donus 20 bp


def bist_cost_for(code: str) -> CostModel:
    """BIST hissesinin maliyet modeli. Ayri fonksiyon: kuresel varliklarin
    tablosuna 30 hisse karistirmamak icin (kod cakismasi da olabilir)."""
    return BIST_COST


def build_positions(df: pl.DataFrame, mode: str = "timed") -> pl.DataFrame:
    """Giriş sinyallerinden bar bazlı pozisyon serisi üretir.

    mode:
        'timed' -- ilk hizalı 15dk sinyalinde gir (strategy.entry)
        'naive' -- 4H bacağı başlar başlamaz gir (zamanlama yok)

    Çıkış her iki modda da aynı: 4H trendi döndüğünde (bacak değişimi).
    Böylece iki mod yalnızca GİRİŞ ANI bakımından farklı olur; karşılaştırma
    temiz kalır.
    """
    if df.is_empty():
        return df

    if mode == "naive":
        # Bacağın ilk barında, o anki 4H yönüyle pozisyon aç.
        entry = (
            pl.when(pl.int_range(pl.len()).over("leg") == 0)
            .then(pl.col("trend"))
            .otherwise(None)
        )
    elif mode == "timed":
        entry = (
            pl.when(pl.col("entry") == "LONG")
            .then(1)
            .when(pl.col("entry") == "SHORT")
            .then(-1)
            .otherwise(None)
        )
    else:
        raise ValueError("bilinmeyen mod: {}".format(mode))

    out = df.with_columns(entry.cast(pl.Int8).alias("_entry"))

    # Pozisyon: bacak içinde girişten sonra sabit kalır, bacak bitince sıfırlanır.
    return out.with_columns(
        pl.col("_entry").forward_fill().over("leg").fill_null(0).alias("position")
    )


def run(
    df: pl.DataFrame,
    cost: CostModel,
    mode: str = "timed",
) -> dict:
    """Tek enstrüman backtest'i. Dönen değer: metrik sözlüğü."""
    if df.is_empty():
        return {}

    d = build_positions(df, mode=mode).with_columns(
        pl.col("close").pct_change().alias("bar_ret")
    )

    # Look-ahead koruması: pozisyon bir bar gecikmeli uygulanır.
    d = d.with_columns(pl.col("position").shift(1).fill_null(0).alias("pos_eff"))

    # İşlem maliyeti: pozisyon her değiştiğinde gidiş-dönüşün yarısı.
    d = d.with_columns(
        (pl.col("pos_eff") != pl.col("pos_eff").shift(1).fill_null(0))
        .cast(pl.Float64)
        .alias("_switch")
    )
    half_cost = cost.roundtrip_bp / 2.0 / 10000.0

    d = d.with_columns(
        (
            pl.col("pos_eff") * pl.col("bar_ret").fill_null(0.0)
            - pl.col("_switch") * half_cost
        ).alias("ret")
    )

    equity = (1.0 + d["ret"]).cum_prod()
    d = d.with_columns(equity.alias("equity"))

    # Günlük seriye indirgeyip Sharpe/Drawdown hesapla.
    daily = (
        d.group_by_dynamic("ts", every="1d")
        .agg(pl.col("ret").sum().alias("r"))
        .sort("ts")
    )
    r = daily["r"].to_numpy()
    if len(r) < 2:
        return {}

    total_ret = float(equity[-1] - 1.0)
    years = (d["ts"][-1] - d["ts"][0]).total_seconds() / (365.25 * 86400)
    cagr = ((1.0 + total_ret) ** (1.0 / years) - 1.0) if years > 0 and total_ret > -1 else float("nan")

    sd = float(r.std(ddof=1))
    sharpe = float(r.mean() / sd * math.sqrt(BARS_PER_YEAR)) if sd > 0 else float("nan")

    eq_daily = (1.0 + daily["r"]).cum_prod()
    peak = eq_daily.cum_max()
    max_dd = float(((eq_daily - peak) / peak).min())

    # İşlem bazlı istatistikler
    trades = _trade_stats(d, half_cost)

    return {
        "mod": mode,
        "islem": trades["n"],
        "getiri_%": round(100 * total_ret, 1),
        "CAGR_%": round(100 * cagr, 2) if cagr == cagr else float("nan"),
        "Sharpe": round(sharpe, 2) if sharpe == sharpe else float("nan"),
        "MaxDD_%": round(100 * max_dd, 1),
        "kazanan_%": trades["win_rate"],
        "kar_faktoru": trades["profit_factor"],
        "ort_islem_bp": trades["avg_bp"],
    }


def _trade_stats(d: pl.DataFrame, half_cost: float) -> dict:
    """Pozisyon bazlı işlem istatistikleri."""
    t = d.filter(pl.col("pos_eff") != 0).with_columns(
        (pl.col("pos_eff") != pl.col("pos_eff").shift(1).fill_null(0))
        .cum_sum()
        .alias("trade_id")
    )
    if t.is_empty():
        return {"n": 0, "win_rate": float("nan"),
                "profit_factor": float("nan"), "avg_bp": float("nan")}

    per_trade = t.group_by("trade_id").agg(
        pl.col("ret").sum().alias("pnl")
    )["pnl"]

    wins = per_trade.filter(per_trade > 0)
    losses = per_trade.filter(per_trade < 0)
    gross_win = float(wins.sum()) if wins.len() else 0.0
    gross_loss = abs(float(losses.sum())) if losses.len() else 0.0

    return {
        "n": per_trade.len(),
        "win_rate": round(100.0 * wins.len() / per_trade.len(), 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "avg_bp": round(float(per_trade.mean()) * 10000, 1),
    }


def cost_for(code: str) -> CostModel:
    return DEFAULT_COSTS.get(code, FALLBACK_COST)

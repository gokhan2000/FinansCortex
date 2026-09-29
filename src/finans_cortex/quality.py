"""Veri kalite kontrolü.

Bu modül isteğe bağlı bir ek değil. Yoklama sırasında Dukascopy'de gerçek delikler
görüldü (WTI 2012'de bir günde 4 bar, DAX 2015'te 57 bar -- normali ~92).
Bkz. docs/VERI_KAYNAGI_BULGULARI.md bölüm 11.

Sessiz veri deliği, çöken bir sistemden çok daha pahalıdır: backtest çalışır,
sonuç üretir, sonuç yanlıştır. Bu yüzden dolumdan sonra kontrol zorunludur.

Ayrıca: eksik barlar burada DOLDURULMAZ. Boşluk boşluk olarak kalır, sadece
raporlanır. Saklama katmanında forward-fill yapılırsa "veri var mı yok mu"
sorusu bir daha asla cevaplanamaz.
"""

from __future__ import annotations

import polars as pl

from . import storage
from .instruments import INSTRUMENTS

# 15dk barında 24 saatlik piyasa günde 96 bar üretir. Endeksler nakit seans
# kadar işlem gördüğü için beklenen sayı çok daha düşük; bu yüzden sabit bir
# eşik yerine enstrümanın KENDİ medyanı referans alınır.
LOW_DAY_RATIO = 0.5
"""Medyanın bu oranının altındaki günler 'eksik gün' sayılır."""


def flat_days(con, code: str) -> pl.DataFrame:
    """Gün boyunca fiyatı hiç değişmeyen günler -- HAYALET VERİ.

    Piyasa kapalıyken besleme son fiyatı tekrar tekrar bar olarak yayınlıyor.
    EURUSD 2012-2014 arası Cumartesileri böyle: günde 96 bar, hepsi aynı fiyat,
    günlük aralık %0.0.

    Chandelier Exit için ölümcül: bu barlarda True Range = 0 olduğu için ATR
    yapay olarak çöker, stoplar aşırı daralır ve piyasa açılınca sahte sinyal
    üretilir. Tespit edilip SİLİNMELİ -- bu veri doldurma değil, uydurma verinin
    kaldırılmasıdır; geriye piyasanın gerçekten kapalı olduğu boşluk kalır.
    """
    return con.execute(
        """
        SELECT CAST(ts AS DATE) AS day, count(*) AS bars, max(high) - min(low) AS range
        FROM bars_15m
        WHERE instrument_id = ?
        GROUP BY 1
        HAVING max(high) = min(low)
        ORDER BY 1
        """,
        [storage.instrument_id(con, code)],
    ).pl()


def remove_flat_days(con, code: str) -> int:
    """Hayalet günleri siler. Dönen değer: silinen bar sayısı."""
    iid = storage.instrument_id(con, code)
    before = con.execute(
        "SELECT count(*) FROM bars_15m WHERE instrument_id = ?", [iid]
    ).fetchone()[0]

    con.execute(
        """
        DELETE FROM bars_15m
        WHERE instrument_id = ?
          AND CAST(ts AS DATE) IN (
              SELECT CAST(ts AS DATE) FROM bars_15m
              WHERE instrument_id = ?
              GROUP BY 1 HAVING max(high) = min(low)
          )
        """,
        [iid, iid],
    )
    con.commit()

    after = con.execute(
        "SELECT count(*) FROM bars_15m WHERE instrument_id = ?", [iid]
    ).fetchone()[0]
    return int(before - after)


def daily_bar_counts(con, code: str) -> pl.DataFrame:
    return con.execute(
        """
        SELECT CAST(ts AS DATE) AS day, count(*) AS bars
        FROM bars_15m
        WHERE instrument_id = ?
        GROUP BY 1 ORDER BY 1
        """,
        [storage.instrument_id(con, code)],
    ).pl()


def sanity_violations(con, code: str) -> dict[str, int]:
    """Bar içi mantık hataları. Hepsinin sıfır olması beklenir."""
    row = con.execute(
        """
        SELECT
            sum(CASE WHEN high < low THEN 1 ELSE 0 END),
            sum(CASE WHEN open > high OR open < low THEN 1 ELSE 0 END),
            sum(CASE WHEN close > high OR close < low THEN 1 ELSE 0 END),
            sum(CASE WHEN low <= 0 THEN 1 ELSE 0 END)
        FROM bars_15m WHERE instrument_id = ?
        """,
        [storage.instrument_id(con, code)],
    ).fetchone()
    keys = ("high<low", "open_disi", "close_disi", "fiyat<=0")
    return {k: int(v or 0) for k, v in zip(keys, row)}


def report(con) -> pl.DataFrame:
    """Tüm enstrümanlar için tek satırlık kalite özeti.

    ÖNEMLİ: eksik gün sayımı yalnızca Pazartesi-Cuma üzerinden yapılır.
    İlk sürüm tüm günleri sayıyordu ve %14-19 gibi korkutucu oranlar veriyordu;
    doğrulayınca bunların neredeyse tamamının PAZAR olduğu görüldü -- forex
    Pazar 22:00 UTC'de açıldığı için o gün doğal olarak ~8 bar içerir. Yani
    ölçüt yanlış alarm veriyordu. Hafta içine kısıtlayınca gerçek oran %0-1,5.
    """
    rows = []
    for inst in INSTRUMENTS:
        counts = daily_bar_counts(con, inst.code)
        if counts.is_empty():
            rows.append({
                "code": inst.code, "hafta_ici_gun": 0, "medyan_bar": 0.0,
                "eksik_gun": 0, "eksik_oran": 0.0,
                "hayalet_gun": 0, "sorunlu_bar": 0,
            })
            continue

        # dayofweek: 0=Pazar ... 6=Cumartesi (DuckDB)
        weekdays = counts.filter(
            pl.col("day").dt.weekday().is_between(1, 5)
        )
        if weekdays.is_empty():
            weekdays = counts

        median = float(weekdays["bars"].median())
        low_days = int(
            weekdays.filter(pl.col("bars") < median * LOW_DAY_RATIO).height
        )
        bad = sum(sanity_violations(con, inst.code).values())
        ghosts = flat_days(con, inst.code).height

        rows.append({
            "code": inst.code,
            "hafta_ici_gun": weekdays.height,
            "medyan_bar": median,
            "eksik_gun": low_days,
            "eksik_oran": round(100 * low_days / weekdays.height, 1),
            "hayalet_gun": ghosts,
            "sorunlu_bar": bad,
        })

    return pl.DataFrame(rows)


def worst_days(con, code: str, limit: int = 10) -> pl.DataFrame:
    """En az bar içeren günler -- deliğin nerede olduğunu görmek için."""
    counts = daily_bar_counts(con, code)
    if counts.is_empty():
        return counts
    median = float(counts["bars"].median())
    return (
        counts.filter(pl.col("bars") < median * LOW_DAY_RATIO)
        .sort("bars")
        .head(limit)
    )

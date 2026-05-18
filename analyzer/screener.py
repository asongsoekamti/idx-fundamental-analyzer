"""Screener batch untuk beberapa emiten sekaligus.

Output: DataFrame ringkas dengan rasio kunci (ROE/ROA/PER/PBV/PEG/MOS Graham)
plus skor sederhana ala Magic Formula / Greenblatt-light yang bisa dipakai untuk
sortir watchlist.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analyzer.fetcher import StockFetcher, normalize_ticker
from analyzer.metrics import compute_metrics
from analyzer.valuation import graham_number, margin_of_safety


SCREENER_COLUMNS = [
    "ticker",
    "name",
    "sector",
    "current_price",
    "market_cap",
    "per",
    "pbv",
    "peg",
    "roe",
    "roa",
    "roic",
    "der",
    "dividend_yield",
    "revenue_growth_yoy",
    "earnings_growth_yoy",
    "graham_value",
    "mos_graham",
]


def screen_watchlist(
    tickers: list[str],
    fetcher: StockFetcher | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """Jalankan compute_metrics untuk semua ticker, return DataFrame ringkas + score.

    `progress_callback(i, total, ticker)` opsional untuk update UI Streamlit.
    """
    fetcher = fetcher or StockFetcher()
    rows: list[dict] = []
    total = len(tickers)
    for i, raw in enumerate(tickers, start=1):
        ticker = normalize_ticker(raw)
        if progress_callback is not None:
            try:
                progress_callback(i, total, ticker)
            except Exception:
                pass
        try:
            data = fetcher.fetch(ticker)
            m = compute_metrics(data)
            graham = graham_number(m.get("eps"), m.get("book_value_per_share"))
            mos = margin_of_safety(graham, m.get("current_price"))
            row = {col: m.get(col) for col in SCREENER_COLUMNS if col not in {"graham_value", "mos_graham"}}
            row["graham_value"] = graham
            row["mos_graham"] = mos
            rows.append(row)
        except Exception as e:
            rows.append({"ticker": ticker, "name": f"ERROR: {e}"})

    df = pd.DataFrame(rows, columns=SCREENER_COLUMNS)
    df["score"] = _composite_score(df)
    df = df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    return df


def _composite_score(df: pd.DataFrame) -> pd.Series:
    """Skor komposit sederhana (0-100). Bukan rekomendasi beli, hanya untuk sortir.

    Rumus: rata-rata persentil dari (ROE tinggi, MOS Graham tinggi, PER rendah,
    DER rendah, PEG rendah-positif).
    """
    def _pct(series: pd.Series, higher_is_better: bool) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce")
        ranks = s.rank(pct=True, na_option="keep")
        if not higher_is_better:
            ranks = 1 - ranks
        return ranks

    parts = [
        _pct(df["roe"], higher_is_better=True),
        _pct(df["roic"], higher_is_better=True),
        _pct(df["mos_graham"], higher_is_better=True),
        _pct(df["per"], higher_is_better=False),
        _pct(df["der"], higher_is_better=False),
    ]
    # PEG: positif kecil = bagus, negatif buruk.
    peg = pd.to_numeric(df["peg"], errors="coerce")
    peg_score = peg.where(peg > 0).rank(pct=True, na_option="keep")
    peg_score = 1 - peg_score
    parts.append(peg_score)

    stacked = pd.concat(parts, axis=1)
    return (stacked.mean(axis=1) * 100).round(1)


def load_watchlist(path: str | Path) -> list[str]:
    """Baca file CSV (kolom `ticker`) atau plain text (satu ticker per baris)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Watchlist tidak ditemukan: {p}")
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
        if "ticker" not in df.columns:
            raise ValueError("Kolom 'ticker' wajib ada di CSV watchlist.")
        return [str(t) for t in df["ticker"].dropna().tolist()]
    return [line.strip() for line in p.read_text().splitlines() if line.strip() and not line.startswith("#")]

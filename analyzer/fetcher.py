"""Data fetcher untuk saham IDX via yfinance.

Saham IDX di yfinance pakai suffix `.JK` (contoh: BBCA.JK, TLKM.JK, BMRI.JK).
Modul ini membungkus yfinance dan mengembalikan dict yang konsisten,
plus melakukan caching ke disk supaya tidak hit API berulang-ulang.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache 6 jam supaya saat market jam aktif data masih relatif fresh,
# tapi tidak hammering API tiap kali user refresh dashboard.
DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60


def normalize_ticker(ticker: str) -> str:
    """Pastikan ticker IDX punya suffix .JK (BBCA -> BBCA.JK)."""
    t = ticker.strip().upper()
    if not t:
        raise ValueError("Ticker kosong")
    if "." not in t:
        t = f"{t}.JK"
    return t


@dataclass
class StockData:
    """Container hasil fetch lengkap untuk satu emiten."""

    ticker: str
    info: dict[str, Any] = field(default_factory=dict)
    financials: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    fetched_at: float = 0.0

    @property
    def current_price(self) -> float | None:
        price = self.info.get("currentPrice") or self.info.get("regularMarketPrice")
        if price is None and not self.history.empty:
            price = float(self.history["Close"].iloc[-1])
        return price


class StockFetcher:
    """Wrapper yfinance dengan disk cache JSON untuk `info` dan parquet untuk dataframe."""

    def __init__(self, cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS, use_cache: bool = True):
        self.cache_ttl = cache_ttl
        self.use_cache = use_cache

    def _cache_path(self, ticker: str, kind: str) -> Path:
        safe = ticker.replace(".", "_")
        return CACHE_DIR / f"{safe}_{kind}"

    def _is_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) < self.cache_ttl

    def _load_info_cache(self, ticker: str) -> tuple[dict, float] | None:
        path = self._cache_path(ticker, "info.json")
        if not self.use_cache or not self._is_fresh(path):
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data, path.stat().st_mtime
        except Exception:
            return None

    def _save_info_cache(self, ticker: str, info: dict) -> None:
        path = self._cache_path(ticker, "info.json")
        try:
            with path.open("w", encoding="utf-8") as f:
                # default=str untuk handle Timestamp/Decimal yang non-serializable
                json.dump(info, f, default=str)
        except Exception:
            # cache miss bukan fatal; lanjut saja
            pass

    def _load_df_cache(self, ticker: str, kind: str) -> pd.DataFrame | None:
        path = self._cache_path(ticker, f"{kind}.parquet")
        if not self.use_cache or not self._is_fresh(path):
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            return None

    def _save_df_cache(self, ticker: str, kind: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        path = self._cache_path(ticker, f"{kind}.parquet")
        try:
            df.to_parquet(path)
        except Exception:
            pass

    def fetch(self, ticker: str) -> StockData:
        """Fetch info + laporan keuangan + history harga 5 tahun terakhir."""
        t = normalize_ticker(ticker)
        data = StockData(ticker=t)

        cached_info = self._load_info_cache(t)
        if cached_info is not None:
            data.info, data.fetched_at = cached_info
        else:
            yt = yf.Ticker(t)
            try:
                data.info = yt.info or {}
            except Exception:
                data.info = {}
            data.fetched_at = time.time()
            self._save_info_cache(t, data.info)

        # Dataframe-dataframe ini di-cache terpisah supaya kalau salah satu
        # gagal fetch, yang lain masih bisa terpakai.
        for kind, getter_name in [
            ("financials", "financials"),
            ("balance_sheet", "balance_sheet"),
            ("cashflow", "cashflow"),
        ]:
            cached = self._load_df_cache(t, kind)
            if cached is not None:
                setattr(data, kind, cached)
                continue
            try:
                yt = yf.Ticker(t)
                df = getattr(yt, getter_name)
                if df is None:
                    df = pd.DataFrame()
                setattr(data, kind, df)
                self._save_df_cache(t, kind, df)
            except Exception:
                setattr(data, kind, pd.DataFrame())

        cached_hist = self._load_df_cache(t, "history")
        if cached_hist is not None:
            data.history = cached_hist
        else:
            try:
                yt = yf.Ticker(t)
                hist = yt.history(period="5y", auto_adjust=False)
                data.history = hist if hist is not None else pd.DataFrame()
                self._save_df_cache(t, "history", data.history)
            except Exception:
                data.history = pd.DataFrame()

        return data

    def fetch_many(self, tickers: list[str]) -> dict[str, StockData]:
        return {t: self.fetch(t) for t in tickers}

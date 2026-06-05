"""Fetches previous trading day's major gainers and losers.

Universe:
  - US/NASDAQ: S&P 500 + NASDAQ 100 constituents (Wikipedia, cached 24h)
  - TSX: S&P/TSX Composite (reuses ticker_universes)
"""
from __future__ import annotations

import io
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from ticker_universes import get_tsx_tickers

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_SEC = 24 * 60 * 60

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NDX100_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

TOP_N = 10  # number of gainers / losers to return


def _fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SEC


def _get_sp500_tickers() -> list[str]:
    cache = CACHE_DIR / "sp500_tickers.txt"
    if _fresh(cache):
        return cache.read_text().splitlines()
    resp = requests.get(SP500_WIKI_URL, timeout=20,
                        headers={"User-Agent": "Mozilla/5.0 (premarket-scanner)"})
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = next(t for t in tables if "Symbol" in t.columns)
    tickers = df["Symbol"].dropna().astype(str).str.strip().tolist()
    cache.write_text("\n".join(tickers))
    return tickers


def _get_ndx100_tickers() -> list[str]:
    cache = CACHE_DIR / "ndx100_tickers.txt"
    if _fresh(cache):
        return cache.read_text().splitlines()
    resp = requests.get(NDX100_WIKI_URL, timeout=20,
                        headers={"User-Agent": "Mozilla/5.0 (premarket-scanner)"})
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if "ticker" in cols or "symbol" in cols:
            df = t
            break
    if df is None:
        return []
    df.columns = [str(c).strip().lower() for c in df.columns]
    col = "ticker" if "ticker" in df.columns else "symbol"
    tickers = df[col].dropna().astype(str).str.strip().tolist()
    cache.write_text("\n".join(tickers))
    return tickers


def _previous_trading_day() -> date:
    """Return the most recent completed trading day (Mon–Fri)."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:   # skip Sat(5), Sun(6)
        d -= timedelta(days=1)
    return d


def _compute_movers(tickers: list[str], n: int = TOP_N) -> dict:
    """Batch-download 5 days of closes; return top-n gainers & losers for prev day."""
    if not tickers:
        return {"gainers": [], "losers": [], "prev_date": str(_previous_trading_day())}

    try:
        raw = yf.download(
            tickers,
            period="5d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"[movers] download failed: {e}")
        return {"gainers": [], "losers": [], "prev_date": str(_previous_trading_day())}

    # Extract Close; handle single-ticker edge case (no MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]] if "Close" in raw.columns else raw

    closes = closes.dropna(how="all")
    if len(closes) < 2:
        return {"gainers": [], "losers": [], "prev_date": str(_previous_trading_day())}

    prev_close = closes.iloc[-2]
    last_close = closes.iloc[-1]
    prev_date = str(closes.index[-1].date())

    pct_change = ((last_close - prev_close) / prev_close * 100).dropna()
    pct_change = pct_change.sort_values(ascending=False)

    def _row(sym: str) -> dict:
        return {
            "symbol": sym,
            "prev_close": round(float(prev_close.get(sym, float("nan"))), 2),
            "last_close": round(float(last_close.get(sym, float("nan"))), 2),
            "pct_change": round(float(pct_change[sym]), 2),
        }

    gainers = [_row(s) for s in pct_change.head(n).index]
    losers  = [_row(s) for s in pct_change.tail(n).index[::-1]]

    return {"gainers": gainers, "losers": losers, "prev_date": prev_date}


class MarketMoversScanner:
    def get_us_movers(self, n: int = TOP_N) -> dict:
        """Top-N gainers/losers from S&P 500 + NASDAQ 100 universe."""
        print("[movers] fetching US universe (S&P 500 + NASDAQ 100)...")
        try:
            sp = _get_sp500_tickers()
        except Exception as e:
            print(f"[movers] S&P 500 fetch failed: {e}"); sp = []
        try:
            ndx = _get_ndx100_tickers()
        except Exception as e:
            print(f"[movers] NASDAQ 100 fetch failed: {e}"); ndx = []
        universe = list(set(sp + ndx))
        print(f"[movers] US universe: {len(universe)} tickers")
        return _compute_movers(universe, n)

    def get_tsx_movers(self, n: int = TOP_N) -> dict:
        """Top-N gainers/losers from TSX Composite universe."""
        print("[movers] fetching TSX universe...")
        try:
            universe = get_tsx_tickers()
        except Exception as e:
            print(f"[movers] TSX universe fetch failed: {e}"); universe = []
        print(f"[movers] TSX universe: {len(universe)} tickers")
        return _compute_movers(universe, n)

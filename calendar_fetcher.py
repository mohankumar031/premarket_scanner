"""Calendar fetchers for NASDAQ and TSX earnings + upcoming IPOs.

NASDAQ: Finnhub free tier gives all US earnings; we filter to NASDAQ-listed
        symbols using the official NASDAQ symbol directory.
TSX:    Finnhub free tier doesn't cover Canadian exchanges, so we iterate
        through the S&P/TSX Composite via yfinance and check each ticker's
        upcoming earnings date. ~230 symbols, parallelized — runs in ~30s.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

import finnhub
import pandas as pd
import yfinance as yf

from config import FINNHUB_API_KEY, IPO_LOOKAHEAD_DAYS
from ticker_universes import get_nasdaq_tickers, get_tsx_tickers


# ----------------- NASDAQ (Finnhub) -----------------

class NasdaqCalendar:
    def __init__(self):
        if not FINNHUB_API_KEY:
            raise RuntimeError("FINNHUB_API_KEY missing. Add it to your .env file.")
        self.client = finnhub.Client(api_key=FINNHUB_API_KEY)

    def earnings_today(self) -> list[dict]:
        """All NASDAQ-listed earnings announcements scheduled for today."""
        today = date.today().isoformat()
        try:
            resp = self.client.earnings_calendar(
                _from=today, to=today, symbol="", international=False
            )
        except Exception as e:
            print(f"[nasdaq] earnings fetch failed: {e}")
            return []

        try:
            nasdaq_universe = get_nasdaq_tickers()
        except Exception as e:
            print(f"[nasdaq] could not load NASDAQ universe ({e}); returning unfiltered US list.")
            nasdaq_universe = None

        out = []
        for e in resp.get("earningsCalendar", []) or []:
            sym = (e.get("symbol") or "").strip()
            if not sym:
                continue
            if nasdaq_universe is not None and sym not in nasdaq_universe:
                continue
            out.append({
                "symbol": sym,
                "exchange": "NASDAQ",
                "eps_estimate": e.get("epsEstimate"),
                "revenue_estimate": e.get("revenueEstimate"),
                "timing": e.get("hour") or "unknown",  # bmo / amc / dmt
                "event_type": "earnings",
            })
        return out

    def upcoming_ipos(self) -> list[dict]:
        """IPOs in the next N days listing on NASDAQ."""
        today = date.today()
        end = today + timedelta(days=IPO_LOOKAHEAD_DAYS)
        try:
            resp = self.client.ipo_calendar(_from=today.isoformat(), to=end.isoformat())
        except Exception as e:
            print(f"[nasdaq] IPO fetch failed: {e}")
            return []

        out = []
        for i in resp.get("ipoCalendar", []) or []:
            exch = (i.get("exchange") or "").upper()
            if "NASDAQ" not in exch:
                continue
            out.append({
                "symbol": i.get("symbol") or "N/A",
                "name": i.get("name"),
                "date": i.get("date"),
                "price_range": i.get("price"),
                "shares": i.get("numberOfShares"),
                "exchange": i.get("exchange"),
                "status": i.get("status"),
                "event_type": "ipo",
            })
        return out


# ----------------- TSX (yfinance) -----------------

class TsxCalendar:
    """Uses yfinance to check each TSX Composite member for an earnings date today."""

    def __init__(self, max_workers: int = 20):
        self.max_workers = max_workers

    def earnings_today(self) -> list[dict]:
        try:
            tickers = get_tsx_tickers()
        except Exception as e:
            print(f"[tsx] could not load TSX universe: {e}")
            return []

        today = date.today()
        out: list[dict] = []

        def _check(sym: str) -> dict | None:
            try:
                t = yf.Ticker(sym)
                # get_earnings_dates returns a DataFrame indexed by datetime, with the
                # next scheduled earnings included alongside the historical ones.
                df = t.get_earnings_dates(limit=8)
                if df is None or df.empty:
                    return None
                # Index is tz-aware; convert to date for comparison.
                hit = None
                for idx in df.index:
                    try:
                        d = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
                    except Exception:
                        continue
                    if d == today:
                        hit = idx
                        break
                if hit is None:
                    return None

                row = df.loc[hit]
                eps_est = row.get("EPS Estimate") if hasattr(row, "get") else None
                # Map UTC hour to bmo/amc heuristic (TSX trades 9:30-16:00 ET)
                try:
                    et_hour = pd.Timestamp(hit).tz_convert("America/Toronto").hour
                    if et_hour < 9:
                        timing = "bmo"
                    elif et_hour >= 16:
                        timing = "amc"
                    else:
                        timing = "dmt"
                except Exception:
                    timing = "unknown"

                return {
                    "symbol": sym,
                    "exchange": "TSX",
                    "eps_estimate": float(eps_est) if pd.notna(eps_est) else None,
                    "revenue_estimate": None,
                    "timing": timing,
                    "event_type": "earnings",
                }
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(_check, s) for s in tickers]
            for f in as_completed(futures):
                r = f.result()
                if r:
                    out.append(r)

        return out

    def upcoming_ipos(self) -> list[dict]:
        """Placeholder: TSX/TMX doesn't expose a clean free IPO API.

        TMX publishes new listings at:
          https://www.tsx.com/listings/recent-listings
        Scraping that page is fragile and changes often. Left as a TODO —
        check TMX New Listings manually for Canadian IPO awareness.
        """
        return []


# ----------------- Combined -----------------

class CalendarFetcher:
    """Unified facade across exchanges."""

    def __init__(self):
        self.nasdaq = NasdaqCalendar()
        self.tsx = TsxCalendar()

    def earnings_today(self) -> dict[str, list[dict]]:
        return {
            "NASDAQ": self.nasdaq.earnings_today(),
            "TSX": self.tsx.earnings_today(),
        }

    def upcoming_ipos(self) -> dict[str, list[dict]]:
        return {
            "NASDAQ": self.nasdaq.upcoming_ipos(),
            "TSX": self.tsx.upcoming_ipos(),
        }

"""Ticker universes for NASDAQ and TSX.

- NASDAQ: downloads the official NASDAQ-listed file from nasdaqtrader.com
  (this is the canonical list, refreshed nightly by NASDAQ).
- TSX: pulls the S&P/TSX Composite constituent list from Wikipedia and
  appends `.TO` for yfinance. The Composite is ~230 names and captures
  essentially all liquid TSX trading. Add custom tickers via TSX_EXTRA.

Both lists are cached on disk for 24h to avoid repeated downloads.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL_SEC = 24 * 60 * 60  # 1 day

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
TSX_WIKI_URL = "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index"

# Extra TSX tickers to include beyond the Composite (without `.TO`)
TSX_EXTRA: list[str] = [
    # Add anything you specifically watch, e.g. "SHOP", "LSPD", "BB"
]


def _fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SEC


def get_nasdaq_tickers() -> set[str]:
    """All NASDAQ-listed common stock symbols (excludes test issues + ETFs)."""
    cache = CACHE_DIR / "nasdaq_listed.txt"
    if _fresh(cache):
        text = cache.read_text()
    else:
        r = requests.get(
            NASDAQ_LISTED_URL,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (premarket-scanner)"},
        )
        r.raise_for_status()
        text = r.text
        cache.write_text(text)

    tickers: set[str] = set()
    lines = text.splitlines()
    if not lines:
        return tickers

    # Format is pipe-delimited. First row is header, last row is a "File Creation Time" footer.
    header = lines[0].split("|")
    try:
        sym_i = header.index("Symbol")
        test_i = header.index("Test Issue")
        etf_i = header.index("ETF")
    except ValueError:
        return tickers

    for ln in lines[1:]:
        if ln.startswith("File Creation Time"):
            continue
        parts = ln.split("|")
        if len(parts) <= max(sym_i, test_i, etf_i):
            continue
        sym = parts[sym_i].strip()
        if not sym:
            continue
        if parts[test_i].strip().upper() == "Y":
            continue
        if parts[etf_i].strip().upper() == "Y":
            continue
        tickers.add(sym)
    return tickers


def get_tsx_tickers() -> list[str]:
    """S&P/TSX Composite constituents, formatted for yfinance (`.TO` suffix)."""
    cache = CACHE_DIR / "tsx_composite.csv"

    if _fresh(cache):
        df = pd.read_csv(cache)
    else:
        # Wikipedia keeps a current constituent table; read_html parses it.
        # Setting a UA avoids 403s.
        resp = requests.get(
            TSX_WIKI_URL,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (premarket-scanner)"},
        )
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))

        # Find the constituent table: it has a "Symbol" or "Ticker" column.
        df = None
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any(c in ("symbol", "ticker") for c in cols):
                df = t
                break
        if df is None:
            raise RuntimeError("Could not find TSX Composite constituent table on Wikipedia.")

        df.columns = [str(c).strip().lower() for c in df.columns]
        df.to_csv(cache, index=False)

    sym_col = "symbol" if "symbol" in df.columns else "ticker"
    raw = df[sym_col].dropna().astype(str).str.strip().str.upper()

    # Normalize to yfinance format. Wikipedia sometimes writes "TSX: ABC" or "ABC.TO".
    out: list[str] = []
    for s in raw:
        s = s.replace("TSX:", "").replace("TSE:", "").strip()
        if not s or s.lower() == "nan":
            continue
        # Convert "BNS" → "BNS.TO"; keep "BNS.TO" as-is. Canadian dual-class often
        # uses dot in original ticker (e.g. "BBD.B"); yfinance expects dashes for those.
        if not s.endswith(".TO") and not s.endswith(".V"):
            # If there's already a dot for share class, keep it but still need .TO
            # e.g. "BBD.B" -> "BBD-B.TO"
            if "." in s:
                base, cls = s.split(".", 1)
                s = f"{base}-{cls}.TO"
            else:
                s = f"{s}.TO"
        out.append(s)

    # Append any user extras
    for e in TSX_EXTRA:
        e = e.strip().upper()
        if not e:
            continue
        if not (e.endswith(".TO") or e.endswith(".V")):
            e = f"{e}.TO"
        if e not in out:
            out.append(e)

    return sorted(set(out))

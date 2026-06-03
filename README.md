# Pre-Market Scanner (NASDAQ + TSX)

Every morning before market open, this script:

1. Pulls all **NASDAQ tickers with earnings announcements today** (via Finnhub).
2. Pulls all **TSX tickers with earnings announcements today** (via yfinance, against the S&P/TSX Composite universe).
3. Pulls upcoming **NASDAQ IPOs** (next 7 days, via Finnhub).
4. For each reporting ticker, downloads the **last ~3 months of OHLCV** and computes 3-month return, 20-day momentum, RSI, MACD, SMA20/50 position, Bollinger position, volatility, recent volume change.
5. Combines those into a **rule-based signal score** (BULLISH / NEUTRAL / BEARISH) with the reasons listed.
6. Emails a consolidated HTML report and saves a CSV.

## ⚠️ This is not investment advice

A screening / awareness tool, not a price prediction. In particular:

- Earnings reactions depend on **surprise vs. expectations**, which this tool does **not** model. A ticker can be technically bullish and still gap down 15% on a soft guide.
- Newly priced IPOs have **no price history**, so the technical analysis only applies to the earnings list.
- Past performance doesn't predict future returns.

Use it as one input, size positions accordingly, and respect that earnings days are binary events.

## Data sources

| Need | Source | Cost |
|---|---|---|
| NASDAQ earnings calendar | Finnhub `earnings_calendar` (US only) | Free tier |
| NASDAQ ticker universe (filter) | `nasdaqtrader.com` symbol directory | Free, no key |
| TSX earnings dates | `yfinance.Ticker.get_earnings_dates`, queried per ticker in parallel | Free, no key |
| TSX ticker universe | S&P/TSX Composite from Wikipedia (~230 names) | Free, no key |
| NASDAQ IPO calendar | Finnhub `ipo_calendar` | Free tier |
| Price history | `yfinance` (handles `.TO` for TSX) | Free, no key |

**Why not Finnhub for TSX?** Finnhub's free tier is US-only. Canadian exchanges require a paid plan.

**Why only the TSX Composite (~230 names) and not all 1,500+ TSX/TSXV listings?**
The Composite captures essentially all the liquid Canadian trading. Small/micro caps usually get filtered out anyway by the `MIN_PRICE` and `MIN_AVG_VOLUME` checks in `analyzer.py`. To watch others, add them to `TSX_EXTRA` in `ticker_universes.py`.

## Setup

```bash
cd premarket_scanner
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

1. **Finnhub API key** — free at https://finnhub.io/register (used for NASDAQ only).
2. **Gmail App Password** for sending email — https://support.google.com/accounts/answer/185833 (2FA must be on; don't use your real password). Or switch SMTP server.

## Running

```bash
# Run once, now (good for testing)
python main.py run

# Schedule daily at RUN_TIME in TIMEZONE (default 07:00 US/Eastern, weekdays only)
python main.py schedule
```

The TSX scan iterates ~230 tickers in parallel via yfinance and typically completes in 20–40 seconds depending on Yahoo's response times.

For production, run under a process manager (systemd, supervisord) or use cron:

```cron
# 7:00 AM Eastern, Mon–Fri
0 7 * * 1-5  cd /path/to/premarket_scanner && /path/to/.venv/bin/python main.py run >> scanner.log 2>&1
```

## Files

| File | What it does |
|---|---|
| `main.py` | Orchestrator + CLI / scheduler |
| `calendar_fetcher.py` | NASDAQ earnings/IPOs (Finnhub) + TSX earnings (yfinance) |
| `ticker_universes.py` | Downloads + caches NASDAQ symbol directory and TSX Composite list |
| `analyzer.py` | Pulls 3-month history and computes technical indicators |
| `predictor.py` | Combines indicators into a directional score |
| `emailer.py` | HTML report (separate NASDAQ / TSX sections) + SMTP send |
| `config.py` | Loads `.env` |

## Output

Each run produces:

- `reports/scan_YYYY-MM-DD.csv` — all analyzed tickers, with `exchange` column
- `reports/report_YYYY-MM-DD.html` — same as the email
- An HTML email to `EMAIL_TO`

## Limitations

- **Finnhub free tier**: 60 calls/min. NASDAQ earnings + IPO calls are 2 requests total — no risk of hitting the limit.
- **yfinance is unofficial**: Yahoo can change endpoints. If TSX earnings stop returning, upgrade `yfinance`.
- **TSX Composite changes quarterly**: the Wikipedia source is cached for 24h. Composition changes are picked up automatically on the next refresh.
- **TSX IPO calendar is not implemented** — TMX doesn't expose a clean free API for new listings. Check https://www.tsx.com/listings/recent-listings manually if you want IPO awareness for Canada.

## Customizing

In `config.py`:

- `MIN_PRICE`, `MIN_AVG_VOLUME` — liquidity filters (note: TSX volumes are lower than US; consider tuning down `MIN_AVG_VOLUME` to e.g. 50,000 if too many TSX names are filtered out).
- `LOOKBACK_DAYS` — analysis window (default 90)
- `IPO_LOOKAHEAD_DAYS` — how far ahead to flag IPOs

In `ticker_universes.py`:

- `TSX_EXTRA` — additional TSX tickers to watch beyond the Composite

In `predictor.py`:

- Tune weights in `score()` or add more indicators (Stochastic, OBV, ATR, etc.)

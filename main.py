"""Main entry point for the pre-market scanner.

Usage:
  python main.py run        # run once, now
  python main.py schedule   # run every weekday at RUN_TIME (per .env)
"""
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pytz
import schedule

from analyzer import TechnicalAnalyzer
from calendar_fetcher import CalendarFetcher
from config import CSV_DIR, RUN_TIME, SAVE_CSV, TIMEZONE
from emailer import ReportEmailer
from market_movers import MarketMoversScanner
from predictor import NextDayPredictor, SignalScorer


def _score_earnings_list(earnings: list[dict], analyzer, scorer) -> list[dict]:
    scored = []
    for e in earnings:
        sym = e["symbol"]
        a = analyzer.analyze(sym)
        if not a:
            continue
        s = scorer.score(a)
        scored.append({
            "symbol": sym,
            "exchange": e.get("exchange"),
            "timing": e.get("timing"),
            "eps_estimate": e.get("eps_estimate"),
            "revenue_estimate": e.get("revenue_estimate"),
            "analysis": a,
            "signal": s,
        })
        print(f"  {sym:14s} [{e.get('exchange','?'):6s}]  {s['direction']:14s}  score={s['score']:>5}")
    return scored


def _enrich_movers_with_predictions(movers: dict, analyzer: TechnicalAnalyzer,
                                     predictor: NextDayPredictor) -> dict:
    """Attach technical analysis + next-day prediction to each mover entry."""
    for key in ("gainers", "losers"):
        enriched = []
        for item in movers.get(key, []):
            sym = item["symbol"]
            analysis = analyzer.analyze(sym)
            if analysis:
                item["prediction"] = predictor.predict(analysis)
            else:
                item["prediction"] = {}
            enriched.append(item)
        movers[key] = enriched
    return movers


def run_once():
    print(f"\n=== Pre-Market Scanner :: {datetime.now().isoformat(timespec='seconds')} ===")

    fetcher   = CalendarFetcher()
    analyzer  = TechnicalAnalyzer()
    scorer    = SignalScorer()
    predictor = NextDayPredictor()
    emailer   = ReportEmailer()
    mover_scanner = MarketMoversScanner()

    print("[fetch] pulling earnings calendars...")
    earnings_by_exch = fetcher.earnings_today()
    print(f"[fetch] NASDAQ: {len(earnings_by_exch['NASDAQ'])} earnings, "
          f"TSX: {len(earnings_by_exch['TSX'])} earnings")

    print("[fetch] pulling IPO calendars...")
    ipos_by_exch = fetcher.upcoming_ipos()
    print(f"[fetch] NASDAQ IPOs: {len(ipos_by_exch['NASDAQ'])}, "
          f"TSX IPOs: {len(ipos_by_exch['TSX'])}")

    # --- Previous day movers ---
    print("[movers] scanning previous day movers...")
    us_movers  = mover_scanner.get_us_movers()
    tsx_movers = mover_scanner.get_tsx_movers()
    print(f"[movers] US: {len(us_movers['gainers'])} gainers, {len(us_movers['losers'])} losers")
    print(f"[movers] TSX: {len(tsx_movers['gainers'])} gainers, {len(tsx_movers['losers'])} losers")

    print("[movers] enriching movers with next-day predictions...")
    us_movers  = _enrich_movers_with_predictions(us_movers,  analyzer, predictor)
    tsx_movers = _enrich_movers_with_predictions(tsx_movers, analyzer, predictor)
    movers_by_exch = {"US": us_movers, "TSX": tsx_movers}

    # --- Earnings analysis ---
    scored_by_exch: dict[str, list[dict]] = {}
    for exch, lst in earnings_by_exch.items():
        print(f"[analyze] {exch} ({len(lst)} symbols)...")
        scored_by_exch[exch] = _score_earnings_list(lst, analyzer, scorer)

    # --- Save CSV (combined) ---
    if SAVE_CSV:
        Path(CSV_DIR).mkdir(parents=True, exist_ok=True)
        path = Path(CSV_DIR) / f"scan_{date.today().isoformat()}.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "exchange", "symbol", "timing", "direction", "score",
                "price", "return_3m_pct", "momentum_20d_pct", "rsi",
                "macd_diff", "px_vs_sma20_pct", "px_vs_sma50_pct",
                "bb_position", "volatility_pct", "volume_change_pct",
                "reasons",
            ])
            for exch, lst in scored_by_exch.items():
                for x in lst:
                    a, s = x["analysis"], x["signal"]
                    w.writerow([
                        exch, x["symbol"], x.get("timing"), s["direction"], s["score"],
                        a["current_price"], a["return_3m_pct"], a["momentum_20d_pct"], a["rsi"],
                        a["macd_diff"], a["price_vs_sma20_pct"], a["price_vs_sma50_pct"],
                        a["bb_position"], a["volatility_pct"], a["volume_change_pct"],
                        "; ".join(s["reasons"]),
                    ])
        print(f"[csv] wrote {path}")

    # --- Build & send report ---
    html = emailer.build_html(scored_by_exch, ipos_by_exch, movers_by_exch)
    emailer.send(html)

    if SAVE_CSV:
        html_path = Path(CSV_DIR) / f"report_{date.today().isoformat()}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html)
        print(f"[html] wrote {html_path}")

    print("=== done ===\n")


def _scheduled_job():
    if datetime.now(pytz.timezone(TIMEZONE)).weekday() >= 5:
        print("[skip] weekend")
        return
    try:
        run_once()
    except Exception as e:
        print(f"[ERROR] run_once failed: {e}")


def schedule_loop():
    tz = pytz.timezone(TIMEZONE)
    print(f"Scheduling daily run at {RUN_TIME} {TIMEZONE} (weekdays only).")
    print(f"Current time there: {datetime.now(tz).isoformat(timespec='seconds')}")
    schedule.every().day.at(RUN_TIME).do(_scheduled_job)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run_once()
    elif cmd == "schedule":
        schedule_loop()
    else:
        print("Usage: python main.py [run|schedule]")
        sys.exit(1)

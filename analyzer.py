"""Pulls ~3 months of OHLCV data via yfinance and computes technical metrics."""
import numpy as np
import pandas as pd
import yfinance as yf

from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

from config import LOOKBACK_DAYS, MIN_PRICE, MIN_AVG_VOLUME


class TechnicalAnalyzer:
    def analyze(self, symbol: str):
        """Return a dict of metrics, or None if the ticker fails our filters."""
        try:
            tkr = yf.Ticker(symbol)
            # Pad with extra days so we always get >= LOOKBACK_DAYS trading days
            hist = tkr.history(period=f"{LOOKBACK_DAYS + 30}d", auto_adjust=True)
        except Exception as e:
            print(f"[analyzer] {symbol}: history fetch failed: {e}")
            return None

        if hist is None or hist.empty or len(hist) < 25:
            return None

        # Trim to the actual lookback window
        hist = hist.tail(LOOKBACK_DAYS) if len(hist) > LOOKBACK_DAYS else hist

        close = hist["Close"]
        volume = hist["Volume"]
        current_price = float(close.iloc[-1])
        avg_volume = float(volume.mean())

        # Liquidity / price filters
        if current_price < MIN_PRICE or avg_volume < MIN_AVG_VOLUME:
            return None

        # Performance over the lookback window
        start_price = float(close.iloc[0])
        return_3m = ((current_price - start_price) / start_price) * 100.0

        # Annualized volatility from daily returns
        daily_ret = close.pct_change().dropna()
        volatility = float(daily_ret.std() * np.sqrt(252) * 100.0) if len(daily_ret) else 0.0

        # 20-day momentum
        recent = close.tail(20)
        momentum_20d = ((recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0]) * 100.0

        # RSI(14)
        rsi = float(RSIIndicator(close=close, window=14).rsi().iloc[-1])

        # MACD
        macd_obj = MACD(close=close)
        macd_diff = float(macd_obj.macd().iloc[-1] - macd_obj.macd_signal().iloc[-1])

        # SMAs
        sma_20 = float(SMAIndicator(close=close, window=20).sma_indicator().iloc[-1])
        sma_50 = (
            float(SMAIndicator(close=close, window=50).sma_indicator().iloc[-1])
            if len(close) >= 50 else sma_20
        )

        # Bollinger position (0 = lower band, 1 = upper band)
        bb = BollingerBands(close=close, window=20)
        bb_upper = float(bb.bollinger_hband().iloc[-1])
        bb_lower = float(bb.bollinger_lband().iloc[-1])
        bb_pos = (
            (current_price - bb_lower) / (bb_upper - bb_lower)
            if bb_upper > bb_lower else 0.5
        )

        # Volume trend: last-5-day avg vs full-window avg
        recent_vol = float(volume.tail(5).mean())
        vol_change_pct = ((recent_vol - avg_volume) / avg_volume) * 100.0 if avg_volume else 0.0

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "return_3m_pct": round(return_3m, 2),
            "volatility_pct": round(volatility, 2),
            "momentum_20d_pct": round(float(momentum_20d), 2),
            "rsi": round(rsi, 2),
            "macd_diff": round(macd_diff, 4),
            "price_vs_sma20_pct": round(((current_price - sma_20) / sma_20) * 100.0, 2),
            "price_vs_sma50_pct": round(((current_price - sma_50) / sma_50) * 100.0, 2),
            "bb_position": round(float(bb_pos), 2),
            "volume_change_pct": round(vol_change_pct, 2),
            "avg_volume": int(avg_volume),
        }

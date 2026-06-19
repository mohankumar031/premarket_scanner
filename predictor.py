"""Rule-based signal scoring and next-day return prediction.

SignalScorer  — directional score for earnings / IPO screening.
NextDayPredictor — weighted-feature model estimating next-day % return.

Neither is investment advice or a guarantee of future performance.
"""
import math


class SignalScorer:
    def score(self, a: dict) -> dict:
        if not a:
            return {}

        score = 0.0
        reasons = []

        # --- RSI ---
        rsi = a["rsi"]
        if rsi < 30:
            score += 2; reasons.append(f"RSI {rsi} oversold")
        elif rsi < 45:
            score += 1; reasons.append(f"RSI {rsi} low")
        elif rsi > 70:
            score -= 2; reasons.append(f"RSI {rsi} overbought")
        elif rsi > 55:
            score -= 1; reasons.append(f"RSI {rsi} elevated")

        # --- MACD ---
        if a["macd_diff"] > 0:
            score += 1; reasons.append("MACD above signal")
        else:
            score -= 1; reasons.append("MACD below signal")

        # --- Moving averages ---
        above20 = a["price_vs_sma20_pct"] > 0
        above50 = a["price_vs_sma50_pct"] > 0
        if above20 and above50:
            score += 1; reasons.append("Above SMA20 & SMA50")
        elif (not above20) and (not above50):
            score -= 1; reasons.append("Below SMA20 & SMA50")

        # --- Momentum ---
        m = a["momentum_20d_pct"]
        if m > 5:
            score += 1; reasons.append(f"+{m}% 20d momentum")
        elif m < -5:
            score -= 1; reasons.append(f"{m}% 20d momentum")

        # --- Volume confirmation (amplifies existing lean) ---
        if a["volume_change_pct"] > 20:
            reasons.append("Volume +20% vs avg")
            if score > 0: score += 0.5
            elif score < 0: score -= 0.5

        # --- Bollinger position ---
        bb = a["bb_position"]
        if bb < 0.2:
            score += 1; reasons.append("Near lower Bollinger")
        elif bb > 0.8:
            score -= 1; reasons.append("Near upper Bollinger")

        # --- Translate to bucket ---
        if score >= 4:
            direction, label = "BULLISH", "Strong bullish signal"
        elif score >= 2:
            direction, label = "BULLISH", "Bullish signal"
        elif score >= 0.5:
            direction, label = "MILD BULLISH", "Mildly bullish"
        elif score > -0.5:
            direction, label = "NEUTRAL", "Neutral / no edge"
        elif score > -2:
            direction, label = "MILD BEARISH", "Mildly bearish"
        elif score > -4:
            direction, label = "BEARISH", "Bearish signal"
        else:
            direction, label = "BEARISH", "Strong bearish signal"

        return {
            "score": round(score, 1),
            "direction": direction,
            "label": label,
            "reasons": reasons,
        }


class NextDayPredictor:
    """Predicts next-day expected % return using a weighted technical-feature model.

    The model combines mean-reversion (RSI, Bollinger) and trend-following
    (momentum, MACD, SMA) signals, scaled by daily historical volatility to
    produce a point estimate and ±1σ range.

    Weights are calibrated so that extreme readings (RSI<30, strong momentum,
    etc.) contribute at most ~1–2× the daily volatility of the instrument.
    """

    # Feature weights (tunable)
    W_RSI_REV  = 0.030   # RSI mean-reversion: per unit deviation from 50
    W_MOM      = 0.018   # 20-day momentum carry-forward (dampened)
    W_MACD     = 0.25    # MACD direction binary ±
    W_BB_REV   = 0.40    # Bollinger mean-reversion: per unit distance from mid
    W_SMA20    = 0.012   # price vs SMA-20 trend component
    W_VOL_CONF = 0.10    # volume surge adds/removes conviction

    def predict(self, analysis: dict) -> dict:
        """Return predicted_pct, range_low, range_high, daily_vol_pct, confidence."""
        if not analysis:
            return {}

        rsi       = analysis["rsi"]
        mom       = analysis["momentum_20d_pct"]
        macd_diff = analysis["macd_diff"]
        bb_pos    = analysis["bb_position"]         # 0=lower band, 1=upper band
        sma20_pct = analysis["price_vs_sma20_pct"]
        vol_chg   = analysis["volume_change_pct"]
        ann_vol   = analysis["volatility_pct"]       # annualised %

        # Daily volatility (σ_daily)
        daily_vol = ann_vol / math.sqrt(252)

        # --- Mean-reversion components ---
        rsi_component  = (50.0 - rsi) * self.W_RSI_REV          # oversold → +ve
        bb_component   = (0.5 - bb_pos) * self.W_BB_REV          # near lower → +ve

        # --- Trend-following components ---
        mom_component  = mom * self.W_MOM
        macd_component = self.W_MACD if macd_diff > 0 else -self.W_MACD
        sma_component  = sma20_pct * self.W_SMA20

        # --- Volume conviction amplifier ---
        raw = rsi_component + bb_component + mom_component + macd_component + sma_component
        if abs(vol_chg) > 20:
            direction = 1 if raw >= 0 else -1
            raw += direction * self.W_VOL_CONF

        # Clamp to ±3× daily vol so extreme readings stay realistic
        predicted = max(min(raw, 3 * daily_vol), -3 * daily_vol)

        # Confidence: higher when indicators agree (low spread between components)
        components = [rsi_component, bb_component, mom_component, macd_component, sma_component]
        positive = sum(1 for c in components if c > 0)
        agreement = max(positive, len(components) - positive) / len(components)
        if agreement >= 0.8:
            confidence = "HIGH"
        elif agreement >= 0.6:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "predicted_pct":  round(predicted, 2),
            "range_low":      round(predicted - daily_vol, 2),
            "range_high":     round(predicted + daily_vol, 2),
            "daily_vol_pct":  round(daily_vol, 2),
            "confidence":     confidence,
        }

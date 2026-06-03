"""Rule-based signal scoring.

This is NOT a price prediction model. It blends well-known technical
indicators into a directional score. Earnings reactions in particular are
driven by surprise vs. expectations, not by 3-month price action, so treat
these signals as a screening tool, not a trade trigger.
"""


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

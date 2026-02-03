from typing import Optional, Dict
from strategy.volume_filter import volume_spike_confirmed
from strategy.volatility_filter import compute_atr


# ==================================================
# 1️⃣ COMPRESSION DETECTION (UNCHANGED)
# ==================================================

def detect_compression(
    prices: list[float],
    lookback: int = 20,
    compression_ratio: float = 0.65
) -> bool:
    if len(prices) < lookback * 2:
        return False

    recent = prices[-lookback:]
    previous = prices[-lookback * 2:-lookback]

    recent_range = max(recent) - min(recent)
    previous_range = max(previous) - min(previous)

    if previous_range <= 0:
        return False

    return recent_range < previous_range * compression_ratio


# ==================================================
# 2️⃣ STRICT BREAKOUT / INTENT DETECTOR
# ==================================================

def breakout_signal(
    inst_key: str,
    prices: list[float],
    volume_history: Optional[list[float]] = None,
    high_prices: Optional[list[float]] = None,
    low_prices: Optional[list[float]] = None,
    close_prices: Optional[list[float]] = None,
    min_range_bars: int = 20,
    min_break_pct_of_range: float = 0.08,   # 🔥 IMPORTANT
    vol_threshold: float = 1.3,
    atr_multiplier: float = 1.0
) -> Optional[Dict]:
    """
    STRICT institutional breakout detector.
    Produces VERY FEW but HIGH QUALITY signals.
    """

    if not prices or len(prices) < 40:
        return None

    last_close = close_prices[-1]
    prev_close = close_prices[-2]

    # ---------------------
    # Reference Range (ONLY CLOSED BARS)
    # ---------------------

    base = prices[-(min_range_bars + 1):-1]
    range_high = max(base)
    range_low = min(base)
    range_span = max(range_high - range_low, 1e-9)

    # ---------------------
    # Direction (CLOSE BASED)
    # ---------------------

    if last_close > range_high:
        direction = "LONG"
        break_distance = last_close - range_high
    elif last_close < range_low:
        direction = "SHORT"
        break_distance = range_low - last_close
    else:
        return None

    # ---------------------
    # 🔥 MINIMUM BREAKOUT STRENGTH
    # ---------------------

    if break_distance / range_span < min_break_pct_of_range:
        # weak poke → ignore
        return None

    # ---------------------
    # ATR CONFIRMATION (MANDATORY)
    # ---------------------

    atr_ok = False
    atr_val = None
    if high_prices and low_prices and close_prices:
        atr_val = compute_atr(high_prices, low_prices, close_prices, period=14)
        if atr_val and abs(last_close - prev_close) >= atr_val * atr_multiplier:
            atr_ok = True

    if not atr_ok:
        return None

    # ---------------------
    # VOLUME CONFIRMATION (MANDATORY)
    # ---------------------

    volume_ok = False
    if volume_history and len(volume_history) >= 20:
        if volume_spike_confirmed(volume_history, threshold_multiplier=vol_threshold):
            volume_ok = True

    if not volume_ok:
        return None

    # ---------------------
    # COMPRESSION CONTEXT (BONUS ONLY)
    # ---------------------

    compression = detect_compression(prices)

    # ---------------------
    # FOLLOW-THROUGH CHECK
    # ---------------------

    follow_through = abs(last_close - prev_close) > 0.4 * range_span / min_range_bars

    # ---------------------
    # FINAL CONFIRMED SIGNAL
    # ---------------------

    intent_score = 3.0
    if compression:
        intent_score += 0.5
    if follow_through:
        intent_score += 0.5

    return {
        "signal": "CONFIRMED",
        "direction": direction,
        "intent_score": round(intent_score, 2),
        "range_high": range_high,
        "range_low": range_low,
        "range_span": round(range_span, 6),
        "break_distance": round(break_distance, 6),
        "atr": round(atr_val, 6) if atr_val else None,
        "compression": compression,
        "follow_through": follow_through,
        "reason": f"STRICT_CONFIRMED_{direction}"
    }

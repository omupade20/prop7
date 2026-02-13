from typing import Optional, Dict, List
from strategy.sr_levels import compute_sr_levels, get_nearest_sr
from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import compute_atr, analyze_volatility
from strategy.price_action import rejection_info


def detect_pullback_signal(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    htf_direction: str,
    max_proximity: float = 0.015,
    min_bars: int = 45
) -> Optional[Dict]:
    """
    STRICT PULLBACK DETECTOR (Continuation-focused)

    Only detects high-quality institutional pullbacks.
    """

    if len(prices) < min_bars:
        return None

    last_price = closes[-1]

    # ==================================================
    # 1️⃣ STRUCTURAL LOCATION (STRONG SR ONLY)
    # ==================================================

    sr = compute_sr_levels(highs, lows)
    nearest = get_nearest_sr(last_price, sr, max_search_pct=max_proximity)

    if not nearest:
        return None

    # Require minimum SR strength
    if nearest.get("strength", 0) < 2:
        return None

    trade_direction = None

    if nearest["type"] == "support" and htf_direction == "BULLISH":
        trade_direction = "LONG"
    elif nearest["type"] == "resistance" and htf_direction == "BEARISH":
        trade_direction = "SHORT"
    else:
        return None

    # ==================================================
    # 2️⃣ EXTENSION FILTER (AVOID CHASING)
    # ==================================================

    atr = compute_atr(highs, lows, closes)

    if not atr:
        return None

    recent_move = abs(closes[-1] - closes[-8])

    if recent_move > atr * 1.4:
        return None  # too extended

    # ==================================================
    # 3️⃣ VOLATILITY QUALITY
    # ==================================================

    volat_ctx = analyze_volatility(
        current_move=closes[-1] - closes[-2],
        atr_value=atr
    )

    if volat_ctx.state != "EXPANDING":
        return None

    # ==================================================
    # 4️⃣ STRONG PRICE REACTION REQUIRED
    # ==================================================

    last_bar_rejection = rejection_info(
        closes[-2], highs[-1], lows[-1], closes[-1]
    )

    price_reaction = False

    # Must have either strong rejection OR strong directional close
    if trade_direction == "LONG":
        if last_bar_rejection["rejection_type"] == "BULLISH" and last_bar_rejection["rejection_score"] > 0.4:
            price_reaction = True
        elif closes[-1] > max(closes[-4:-1]):
            price_reaction = True

    elif trade_direction == "SHORT":
        if last_bar_rejection["rejection_type"] == "BEARISH" and last_bar_rejection["rejection_score"] > 0.4:
            price_reaction = True
        elif closes[-1] < min(closes[-4:-1]):
            price_reaction = True

    if not price_reaction:
        return None

    # ==================================================
    # 5️⃣ STRONG VOLUME CONFIRMATION
    # ==================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    if vol_ctx.score < 1.0:
        return None

    # ==================================================
    # 6️⃣ MOMENTUM CONFIRMATION
    # ==================================================

    short_term_trend = closes[-1] - closes[-6]

    if trade_direction == "LONG" and short_term_trend <= 0:
        return None

    if trade_direction == "SHORT" and short_term_trend >= 0:
        return None

    # ==================================================
    # 7️⃣ CONFIDENCE SCORING
    # ==================================================

    components = {
        "location": 0.0,
        "price_action": 0.0,
        "volume": 0.0,
        "volatility": 0.0,
        "momentum": 0.0
    }

    # Stronger proximity scoring
    proximity_score = max(0, (max_proximity - nearest["dist_pct"]) * 80)
    components["location"] = min(proximity_score, 2.5)

    components["price_action"] = 2.0
    components["volume"] = min(vol_ctx.score, 2.0)
    components["volatility"] = 1.5
    components["momentum"] = 1.5

    total_score = sum(components.values())

    # ==================================================
    # 8️⃣ CLASSIFICATION (RAISED THRESHOLDS)
    # ==================================================

    if total_score >= 6.5:
        signal = "CONFIRMED"
    elif total_score >= 4.5:
        signal = "POTENTIAL"
    else:
        return None

    return {
        "signal": signal,
        "direction": trade_direction,
        "score": round(total_score, 2),
        "nearest_level": nearest,
        "components": components,
        "context": {
            "volatility": volat_ctx.state,
            "volume": vol_ctx.strength,
            "rejection": last_bar_rejection["rejection_type"]
        },
        "reason": f"{signal}_{trade_direction}"
    }

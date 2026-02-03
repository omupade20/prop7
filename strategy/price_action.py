"""
Price action helpers (STRONGER filters for higher-quality alerts).

Uses:
- Pullback only when deep enough and trend matches EMA.
- Rejection only when wick is significant relative to bar and context.
- Confirmation of breakout retests added.
"""

from typing import List, Optional, Dict


def _safe_last(seq: List[float], idx: int = -1) -> Optional[float]:
    try:
        return seq[idx]
    except Exception:
        return None


def detect_pullback_in_trend(
    prices: List[float],
    ema_short: Optional[float] = None,
    ema_long: Optional[float] = None,
    lookback: int = 8,
    max_depth_pct: float = 0.004
) -> Optional[Dict]:
    """
    Detect a real pullback that respects trend direction
    and is not overly deep (filtered).
    """

    if not prices or len(prices) < lookback + 1:
        return None

    last = prices[-1]
    window = prices[-(lookback + 1):-1]
    if not window:
        return None

    high = max(window)
    low = min(window)

    if ema_short is not None and ema_long is not None:
        trend = "UP" if ema_short > ema_long else "DOWN"
    else:
        trend = None

    pull_up = (high - last) / high
    pull_down = (last - low) / low

    if trend == "UP" and 0 < pull_up <= max_depth_pct:
        return {"type": "PULLBACK_UP", "depth": round(pull_up, 6)}
    if trend == "DOWN" and 0 < pull_down <= max_depth_pct:
        return {"type": "PULLBACK_DOWN", "depth": round(pull_down, 6)}

    return None


def rejection_info(open_p: float, high: float, low: float, close: float) -> Dict:
    """
    Quantifies strong rejection wicks.
    """
    body = abs(close - open_p)
    total = max(high - low, 1e-9)
    upper = max(0.0, high - max(close, open_p))
    lower = max(0.0, min(close, open_p) - low)

    upper_rel = upper / total
    lower_rel = lower / total
    body_rel = body / total

    rejection_type = None
    score = 0.0

    # stronger bias threshold
    if lower_rel > body_rel * 2 and lower_rel > 0.15:
        rejection_type = "BULLISH"
        score = min(1.0, (lower_rel - 0.15) / 0.5)
    elif upper_rel > body_rel * 2 and upper_rel > 0.15:
        rejection_type = "BEARISH"
        score = min(1.0, (upper_rel - 0.15) / 0.5)

    return {
        "rejection_type": rejection_type,
        "rejection_score": round(score, 3),
        "upper_wick": round(upper, 6),
        "lower_wick": round(lower, 6),
        "body": round(body, 6),
        "range": round(total, 6)
    }


def price_action_context(
    prices: List[float],
    highs: List[float],
    lows: List[float],
    opens: List[float],
    closes: List[float],
    ema_short: Optional[float] = None,
    ema_long: Optional[float] = None
) -> Dict:
    """
    Improved price action scoring (conservative).
    """

    result = {
        "pullback": None,
        "pullback_depth": 0.0,
        "rejection_type": None,
        "rejection_score": 0.0,
        "retest_ok": False,
        "score": 0.0,
        "comment": ""
    }

    if not prices or len(prices) < 8:
        result["comment"] = "insufficient data"
        return result

    # pullback
    pb = detect_pullback_in_trend(prices, ema_short, ema_long)
    if pb:
        result["pullback"] = pb["type"]
        result["pullback_depth"] = pb["depth"]

    # rejection wick
    rej = rejection_info(opens[-1], highs[-1], lows[-1], closes[-1])
    result["rejection_type"] = rej["rejection_type"]
    result["rejection_score"] = rej["rejection_score"]

    score = 0.0
    comments = []

    # pullback adds only small support
    if result["pullback"] == "PULLBACK_UP":
        score += 0.2
        comments.append("pullback_up")
    elif result["pullback"] == "PULLBACK_DOWN":
        score -= 0.2
        comments.append("pullback_down")

    # rejection provides a stronger confirmation
    if rej["rejection_type"] == "BULLISH":
        score += 0.5 * rej["rejection_score"]
        comments.append(f"bullish_rejection {rej['rejection_score']}")
    elif rej["rejection_type"] == "BEARISH":
        score -= 0.5 * rej["rejection_score"]
        comments.append(f"bearish_rejection {rej['rejection_score']}")

    # trend alignment matters
    if ema_short is not None and ema_long is not None:
        trending_up = ema_short > ema_long
        trending_down = ema_short < ema_long
        if trending_up and result["rejection_type"] == "BULLISH":
            score += 0.15
            comments.append("trend_align_bull")
        if trending_down and result["rejection_type"] == "BEARISH":
            score -= 0.15
            comments.append("trend_align_bear")

    # check for retest (recent bar closed above/below breakout price)
    if len(closes) > 1:
        if closes[-1] > highs[-2]:
            result["retest_ok"] = True
            score += 0.3
            comments.append("retest_confirm")

    score = max(-1.0, min(score, 1.0))
    result["score"] = round(score, 3)
    result["comment"] = " | ".join(comments) if comments else "no_pa"

    return result

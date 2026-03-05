# strategy/decision_engine.py

from dataclasses import dataclass
from typing import Optional, Dict

from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import analyze_volatility, compute_atr
from strategy.liquidity_filter import analyze_liquidity
from strategy.price_action import price_action_context
from strategy.sr_levels import sr_location_score
from strategy.vwap_filter import VWAPContext


# =========================
# Output Structure
# =========================

@dataclass
class DecisionResult:
    state: str
    score: float
    direction: Optional[str]
    components: Dict[str, float]
    reason: str


# =========================
# FINAL DECISION ENGINE
# =========================

def final_trade_decision(
    inst_key: str,
    prices: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    market_regime: str,
    htf_bias_direction: str,
    htf_bias_strength: float,
    vwap_ctx: VWAPContext,
    pullback_signal: Optional[Dict],
) -> DecisionResult:

    components: Dict[str, float] = {}
    score = 0.0

    # ==================================================
    # 1️⃣ STRUCTURE GATE
    # ==================================================

    if not pullback_signal:
        return DecisionResult("IGNORE", 0.0, None, {}, "no pullback setup")

    direction = pullback_signal["direction"]
    signal_type = pullback_signal["signal"]

    if signal_type == "POTENTIAL":

        components["structure"] = 1.5

        return DecisionResult(
            state=f"PREPARE_{direction}",
            score=1.5,
            direction=direction,
            components=components,
            reason="potential pullback"
        )

    components["structure"] = 3.0
    score += 3.0

    # ==================================================
    # 2️⃣ HTF BIAS (SOFT SCORE, NOT HARD FILTER)
    # ==================================================

    if direction == "LONG":
        if htf_bias_direction == "BULLISH":
            htf_score = min(htf_bias_strength / 5.0, 2.0)
        else:
            htf_score = -0.5

    elif direction == "SHORT":
        if htf_bias_direction == "BEARISH":
            htf_score = min(htf_bias_strength / 5.0, 2.0)
        else:
            htf_score = -0.5

    else:
        htf_score = 0.0

    components["htf"] = round(htf_score, 2)
    score += htf_score

    # ==================================================
    # 3️⃣ MARKET REGIME
    # ==================================================

    if market_regime in ("WEAK", "COMPRESSION"):
        return DecisionResult("IGNORE", 0.0, None, {}, "bad market regime")

    if market_regime == "EARLY_TREND":
        components["regime"] = 1.0
        score += 1.0

    elif market_regime == "TRENDING":
        components["regime"] = 1.4
        score += 1.4

    # ==================================================
    # 4️⃣ VWAP CONTEXT
    # ==================================================

    if direction == "LONG" and vwap_ctx.acceptance == "BELOW":
        return DecisionResult("IGNORE", 0.0, None, {}, "below VWAP")

    if direction == "SHORT" and vwap_ctx.acceptance == "ABOVE":
        return DecisionResult("IGNORE", 0.0, None, {}, "above VWAP")

    vwap_score = vwap_ctx.score * 0.7

    components["vwap"] = round(vwap_score, 2)
    score += vwap_score

    # ==================================================
    # 5️⃣ VOLUME QUALITY
    # ==================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    if vol_ctx.score < 0:
        return DecisionResult("IGNORE", 0.0, None, {}, "bad volume")

    volume_score = vol_ctx.score * 0.8

    components["volume"] = round(volume_score, 2)
    score += volume_score

    # ==================================================
    # 6️⃣ VOLATILITY QUALITY
    # ==================================================

    atr = compute_atr(highs, lows, closes)

    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0

    volat_ctx = analyze_volatility(move, atr)

    if volat_ctx.state in ["CONTRACTING", "EXHAUSTION"]:
        return DecisionResult("IGNORE", 0.0, None, {}, "bad volatility")

    volatility_score = volat_ctx.score

    components["volatility"] = round(volatility_score, 2)
    score += volatility_score

    # ==================================================
    # 7️⃣ LIQUIDITY
    # ==================================================

    liq_ctx = analyze_liquidity(volumes)

    if liq_ctx.score < 0:
        return DecisionResult("IGNORE", 0.0, None, {}, "illiquid instrument")

    liquidity_score = liq_ctx.score * 0.6

    components["liquidity"] = round(liquidity_score, 2)
    score += liquidity_score

    # ==================================================
    # 8️⃣ PRICE ACTION TIMING
    # ==================================================

    pa_ctx = price_action_context(
        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes
    )

    pa_score = pa_ctx["score"]

    components["price_action"] = round(pa_score, 2)
    score += pa_score

    # ==================================================
    # 9️⃣ SR LOCATION
    # ==================================================

    nearest = pullback_signal.get("nearest_level")

    sr_score = sr_location_score(closes[-1], nearest, direction)

    sr_score = sr_score * 1.2

    components["sr"] = round(sr_score, 2)
    score += sr_score

    # ==================================================
    # 🔟 FINAL DECISION
    # ==================================================

    score = round(max(min(score, 10.0), 0.0), 2)

    if score >= 7.5:

        state = f"EXECUTE_{direction}"
        reason = "high quality pullback trade"

    elif score >= 6.0:

        state = f"PREPARE_{direction}"
        reason = "developing pullback setup"

    else:

        state = "IGNORE"
        reason = "insufficient edge"

    return DecisionResult(
        state=state,
        score=score,
        direction=direction if state != "IGNORE" else None,
        components=components,
        reason=reason
    )

from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime

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
# STRICT CAPITAL-PROTECTING ENGINE
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
    vwap_ctx: VWAPContext,
    pullback_signal: Optional[Dict],
) -> DecisionResult:

    components: Dict[str, float] = {}
    score = 0.0

    # ==================================================
    # 1️⃣ STRUCTURE (MANDATORY)
    # ==================================================

    if not pullback_signal:
        return DecisionResult("IGNORE", 0.0, None, {}, "no pullback setup")

    direction = pullback_signal["direction"]
    signal_type = pullback_signal["signal"]

    if signal_type != "CONFIRMED":
        return DecisionResult("IGNORE", 0.0, None, {}, "not confirmed pullback")

    components["structure"] = 3.5
    score += 3.5

    # ==================================================
    # 2️⃣ HIGHER TIMEFRAME ALIGNMENT (STRICT)
    # ==================================================

    if direction == "LONG" and htf_bias_direction != "BULLISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "htf not bullish")

    if direction == "SHORT" and htf_bias_direction != "BEARISH":
        return DecisionResult("IGNORE", 0.0, None, {}, "htf not bearish")

    components["htf"] = 2.0
    score += 2.0

    # ==================================================
    # 3️⃣ MARKET REGIME FILTER
    # ==================================================

    if market_regime != "TRENDING":
        return DecisionResult("IGNORE", 0.0, None, {}, "only trade trending regime")

    components["regime"] = 1.5
    score += 1.5

    # ==================================================
    # 4️⃣ VWAP CONFIRMATION (STRONG)
    # ==================================================

    if direction == "LONG":
        if vwap_ctx.acceptance != "ABOVE" or vwap_ctx.score < 1.0:
            return DecisionResult("IGNORE", 0.0, None, {}, "weak VWAP structure")

    if direction == "SHORT":
        if vwap_ctx.acceptance != "BELOW" or vwap_ctx.score > -1.0:
            return DecisionResult("IGNORE", 0.0, None, {}, "weak VWAP structure")

    components["vwap"] = abs(vwap_ctx.score)
    score += abs(vwap_ctx.score)

    # ==================================================
    # 5️⃣ VOLUME MUST BE STRONG
    # ==================================================

    vol_ctx = analyze_volume(volumes, close_prices=closes)

    if vol_ctx.score < 1.0:
        return DecisionResult("IGNORE", 0.0, None, {}, "insufficient volume")

    components["volume"] = vol_ctx.score
    score += vol_ctx.score

    # ==================================================
    # 6️⃣ VOLATILITY MUST BE EXPANDING
    # ==================================================

    atr = compute_atr(highs, lows, closes)
    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
    volat_ctx = analyze_volatility(move, atr)

    if volat_ctx.state != "EXPANDING":
        return DecisionResult("IGNORE", 0.0, None, {}, "volatility not expanding")

    components["volatility"] = volat_ctx.score
    score += volat_ctx.score

    # ==================================================
    # 7️⃣ LIQUIDITY FILTER
    # ==================================================

    liq_ctx = analyze_liquidity(volumes)

    if liq_ctx.level in ("LOW", "ILLIQUID"):
        return DecisionResult("IGNORE", 0.0, None, {}, "low liquidity")

    components["liquidity"] = liq_ctx.score
    score += liq_ctx.score

    # ==================================================
    # 8️⃣ PRICE ACTION CONFIRMATION
    # ==================================================

    pa_ctx = price_action_context(
        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes
    )

    if abs(pa_ctx["score"]) < 0.15:
        return DecisionResult("IGNORE", 0.0, None, {}, "weak price action")

    components["price_action"] = pa_ctx["score"]
    score += pa_ctx["score"]

    # ==================================================
    # 9️⃣ SR LOCATION BOOST
    # ==================================================

    nearest = pullback_signal.get("nearest_level")
    sr_score = sr_location_score(closes[-1], nearest, direction)

    components["sr"] = sr_score
    score += sr_score * 1.5

    # ==================================================
    # 🔟 LATE SESSION FILTER (ANTI-CHOP)
    # ==================================================

    now = datetime.now()
    if now.hour >= 12:
        score -= 1.0
        components["late_session_penalty"] = -1.0

    # ==================================================
    # FINAL DECISION
    # ==================================================

    score = round(max(min(score, 10.0), 0.0), 2)

    if score >= 7.5:
        state = f"EXECUTE_{direction}"
        reason = "institutional continuation trade"

    elif score >= 6.0:
        state = f"PREPARE_{direction}"
        reason = "developing strong setup"

    else:
        state = "IGNORE"
        reason = "edge insufficient"

    return DecisionResult(
        state=state,
        score=score,
        direction=direction if state != "IGNORE" else None,
        components=components,
        reason=reason
    )

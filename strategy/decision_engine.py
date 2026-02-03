from dataclasses import dataclass
from typing import Optional, Dict

from strategy.indicators import exponential_moving_average, relative_strength_index
from strategy.volume_filter import analyze_volume
from strategy.volatility_filter import analyze_volatility, compute_atr
from strategy.liquidity_filter import analyze_liquidity
from strategy.price_action import price_action_context
from strategy.sr_levels import compute_sr_levels, get_nearest_sr, sr_location_score
from strategy.vwap_filter import VWAPContext


@dataclass
class DecisionResult:
    state: str
    score: float
    direction: Optional[str]
    components: Dict[str, float]
    reason: str


def final_trade_decision(
    inst_key: str,
    prices: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    market_regime: str,
    htf_bias_label: str,
    vwap_ctx: VWAPContext,
    breakout_signal: Optional[Dict],
) -> DecisionResult:
    components: Dict[str, float] = {}
    score = 0.0

    # 🚫 STRUCTURE GATE — REQUIRE BREAKOUT
    if not breakout_signal or breakout_signal["signal"] != "CONFIRMED":
        return DecisionResult("IGNORE", 0.0, None, {}, "no confirmed breakout")

    direction = breakout_signal["direction"]

    # 🚫 HTF MUST ALIGN
    if direction == "LONG" and htf_bias_label.startswith("BEARISH"):
        return DecisionResult("IGNORE", 0.0, None, {}, "htf opposes long")
    if direction == "SHORT" and htf_bias_label.startswith("BULLISH"):
        return DecisionResult("IGNORE", 0.0, None, {}, "htf opposes short")

    # 🚫 BAD MARKET REGIME STOP
    if market_regime in ("WEAK", "COMPRESSION"):
        return DecisionResult("IGNORE", 0.0, None, {}, "bad market regime")

    # 📊 BREAKOUT BASE SCORE
    components["breakout"] = 3.5
    score += 3.5

    # 🔥 TREND CONFIRMATION
    components["htf"] = 1.5
    score += 1.5

    # 🧭 REGIME AUTHORITY
    if market_regime == "EARLY_TREND":
        components["regime"] = 1.0
        score += 1.0
    elif market_regime == "TRENDING":
        components["regime"] = 1.5
        score += 1.5

    # 📈 VWAP ENVIRONMENT CHECK (soft check)
    if direction == "LONG" and vwap_ctx.acceptance == "BELOW":
        return DecisionResult("IGNORE", 0.0, None, {}, "below VWAP")
    if direction == "SHORT" and vwap_ctx.acceptance == "ABOVE":
        return DecisionResult("IGNORE", 0.0, None, {}, "above VWAP")
    components["vwap"] = vwap_ctx.score
    score += vwap_ctx.score

    # 📊 PARTICIPATION: VOLUME + VOLATILITY + LIQUIDITY
    vol_ctx = analyze_volume(volumes, close_prices=closes)
    components["volume"] = vol_ctx.score
    score += vol_ctx.score

    atr = compute_atr(highs, lows, closes)
    move = closes[-1] - closes[-2] if len(closes) > 1 else 0.0
    volat_ctx = analyze_volatility(move, atr)
    components["volatility"] = volat_ctx.score
    score += volat_ctx.score

    liq_ctx = analyze_liquidity(volumes)
    if liq_ctx.score < 0:
        return DecisionResult("IGNORE", 0.0, None, {}, "illiquid")
    components["liquidity"] = liq_ctx.score
    score += liq_ctx.score

    # 📌 PRICE ACTION CONTEXT
    pa_ctx = price_action_context(
        prices=closes,
        highs=highs,
        lows=lows,
        opens=closes,
        closes=closes,
        ema_short=exponential_moving_average(prices, 9),
        ema_long=exponential_moving_average(prices, 21),
    )
    components["price_action"] = pa_ctx["score"]
    score += pa_ctx["score"]

    # 📌 SUPPORT / RESISTANCE LOCATION
    sr_levels = compute_sr_levels(highs, lows)
    nearest = get_nearest_sr(closes[-1], sr_levels)
    sr_score = sr_location_score(closes[-1], nearest, direction)
    components["sr"] = sr_score
    score += sr_score * 1.0  # slightly increased weight for precision

    # 🧠 MOMENTUM SANITY CHECK (RSI)
    rsi = relative_strength_index(prices, 14)
    if rsi:
        if direction == "LONG" and rsi < 50:
            score -= 0.6
        elif direction == "SHORT" and rsi > 50:
            score -= 0.6

    # 🟢 FINAL SCORE CLAMP
    score = round(max(min(score, 10.0), 0.0), 2)

    # ⚖️ CALIBRATION FOR EXECUTE / PREPARE
    if score >= 7.5:
        state = f"EXECUTE_{direction}"
        reason = "high conviction confirmed"
    elif score >= 5.0:
        state = f"PREPARE_{direction}"
        reason = "setup forming"
    else:
        state = "IGNORE"
        reason = "weak conviction"

    return DecisionResult(
        state=state,
        score=score,
        direction=direction if state != "IGNORE" else None,
        components=components,
        reason=reason
    )

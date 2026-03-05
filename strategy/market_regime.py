# strategy/market_regime.py

from typing import List, Optional
from dataclasses import dataclass


# =========================
# True Range
# =========================

def compute_true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:

    if len(highs) < 2:
        return []

    tr = []

    for i in range(1, len(highs)):

        tr.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
        )

    return tr


# =========================
# ATR
# =========================

def compute_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:

    tr = compute_true_range(highs, lows, closes)

    if len(tr) < period:
        return None

    return sum(tr[-period:]) / period


# =========================
# ADX (corrected)
# =========================

def compute_adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:

    if len(highs) < period + 1:
        return None

    plus_dm = []
    minus_dm = []

    for i in range(1, len(highs)):

        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)

    atr = compute_atr(highs, lows, closes, period)

    if atr is None or atr == 0:
        return None

    plus_di = (sum(plus_dm[-period:]) / atr) * 100
    minus_di = (sum(minus_dm[-period:]) / atr) * 100

    if plus_di + minus_di == 0:
        return 0.0

    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100

    return dx


# =========================
# Regime Output
# =========================

@dataclass
class MarketRegime:

    state: str
    mode: str
    strength: float
    volatility: float
    comment: str


# =========================
# Regime Detection
# =========================

def detect_market_regime(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    index_regime: Optional["MarketRegime"] = None,
    min_bars: int = 30
) -> MarketRegime:

    # ---------------------
    # Safety
    # ---------------------

    if len(highs) < min_bars or len(lows) < min_bars or len(closes) < min_bars:

        return MarketRegime(
            state="WEAK",
            mode="RANGE_DAY",
            strength=0.5,
            volatility=0.0,
            comment="insufficient data"
        )

    adx = compute_adx(highs, lows, closes)
    atr = compute_atr(highs, lows, closes)

    if adx is None or atr is None:

        return MarketRegime(
            state="WEAK",
            mode="RANGE_DAY",
            strength=0.5,
            volatility=0.0,
            comment="indicators unavailable"
        )

    # ---------------------
    # Volatility Normalization
    # ---------------------

    avg_price = sum(closes[-10:]) / min(len(closes), 10)

    vol_norm = atr / avg_price if avg_price > 0 else 0.0

    # ---------------------
    # Range Comparison
    # ---------------------

    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])
    recent_range = recent_high - recent_low

    prev_slice_start = max(0, len(highs) - 20)
    prev_slice_end = max(0, len(highs) - 10)

    prev_highs = highs[prev_slice_start:prev_slice_end]
    prev_lows = lows[prev_slice_start:prev_slice_end]

    if not prev_highs or not prev_lows:
        prev_range = recent_range
    else:
        prev_range = max(prev_highs) - min(prev_lows)

    if prev_range <= 0:
        prev_range = max(recent_range * 0.8, 1e-9)

    # ---------------------
    # Helper
    # ---------------------

    def cap(x: float) -> float:
        return max(0.0, min(10.0, x))

    # =====================
    # REGIME LOGIC
    # =====================

    # EARLY TREND

    if adx >= 18 and recent_range > prev_range * 1.3:

        strength = cap(4.5 + (adx - 18) * 0.2)

        regime = MarketRegime(
            state="EARLY_TREND",
            mode="TREND_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="fresh expansion"
        )

    # TRENDING

    elif adx >= 28:

        strength = cap(6.5 + (adx - 28) * 0.15)

        regime = MarketRegime(
            state="TRENDING",
            mode="TREND_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="established trend"
        )

    # COMPRESSION

    elif recent_range < prev_range * 0.7:

        strength = cap(2.5 + (prev_range - recent_range) / (prev_range + 1e-9))

        regime = MarketRegime(
            state="COMPRESSION",
            mode="RANGE_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="volatility contraction"
        )

    # EXHAUSTION

    elif adx > 28 and recent_range < prev_range * 0.85 and vol_norm < 0.008:

        strength = cap(3.5 + (adx - 28) * 0.1)

        regime = MarketRegime(
            state="EXHAUSTION",
            mode="RANGE_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="trend exhaustion"
        )

    # DEFAULT

    else:

        strength = cap(1.5 + (adx / 30.0) * 1.2)

        regime = MarketRegime(
            state="WEAK",
            mode="RANGE_DAY",
            strength=strength,
            volatility=vol_norm,
            comment="choppy market"
        )

    # ---------------------
    # Optional Index Bias
    # ---------------------

    if index_regime:

        try:

            if index_regime.mode == "TREND_DAY":

                regime.strength = cap(
                    regime.strength + min(1.2, index_regime.strength * 0.15)
                )

                regime.comment += " | index aligned"

            else:

                regime.strength = cap(regime.strength - 0.7)

                regime.comment += " | index weak"

        except Exception:
            pass

    return regime

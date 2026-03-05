# strategy/volume_context.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VolumeContext:
    score: float
    strength: str
    trend: str
    comment: str


def analyze_volume(
    volume_history: List[float],
    close_prices: Optional[List[float]] = None,
    lookback: int = 20,
    rising_bars: int = 4
) -> VolumeContext:

    """
    Institutional volume analysis.

    Returns:
        score: -2 → +2
        strength: STRONG / MODERATE / WEAK / NONE
        trend: RISING / FALLING / FLAT
        comment: explanation
    """

    # --------------------------------------------------
    # DATA SAFETY
    # --------------------------------------------------

    if not volume_history or len(volume_history) < lookback + rising_bars:
        return VolumeContext(
            score=0.0,
            strength="NONE",
            trend="FLAT",
            comment="insufficient volume data"
        )

    recent = volume_history[-lookback:]
    current_volume = volume_history[-1]

    avg_volume = sum(recent) / len(recent) if recent else 0.0

    # --------------------------------------------------
    # 1️⃣ VOLUME RELATIVE STRENGTH
    # --------------------------------------------------

    rel = current_volume / avg_volume if avg_volume > 0 else 1.0

    if rel >= 1.8:
        strength = "STRONG"
        score = 2.0

    elif rel >= 1.4:
        strength = "MODERATE"
        score = 1.2

    elif rel >= 0.95:
        strength = "WEAK"
        score = 0.4

    else:
        strength = "NONE"
        score = -0.5

    # --------------------------------------------------
    # 2️⃣ VOLUME TREND
    # --------------------------------------------------

    last_n = recent[-rising_bars:]

    if len(last_n) >= 2 and all(last_n[i] > last_n[i - 1] for i in range(1, len(last_n))):
        trend = "RISING"
        score += 0.5

    elif len(last_n) >= 2 and all(last_n[i] < last_n[i - 1] for i in range(1, len(last_n))):
        trend = "FALLING"
        score -= 0.5

    else:
        trend = "FLAT"

    # --------------------------------------------------
    # 3️⃣ PRICE-VOLUME RELATIONSHIP
    # --------------------------------------------------

    comment = ""

    if close_prices and len(close_prices) >= rising_bars:

        price_move = close_prices[-1] - close_prices[-rising_bars]

        threshold = 0.002 * close_prices[-1]

        if abs(price_move) < threshold:

            if strength in ("STRONG", "MODERATE"):
                score -= 0.7
                comment = "volume absorption suspected"

            else:
                comment = "volume without price move"

        else:
            comment = "volume confirms price move"

    else:
        comment = "volume context only"

    # --------------------------------------------------
    # CLAMP SCORE
    # --------------------------------------------------

    final_score = max(min(score, 2.0), -2.0)

    return VolumeContext(
        score=round(final_score, 2),
        strength=strength,
        trend=trend,
        comment=comment
    )


# --------------------------------------------------
# LEGACY BOOLEAN (Backward Compatibility)
# --------------------------------------------------

def volume_spike_confirmed(
    volume_history: List[float],
    threshold_multiplier: float = 1.25,
    lookback: int = 20,
    rising_bars: int = 4
) -> bool:

    ctx = analyze_volume(
        volume_history,
        lookback=lookback,
        rising_bars=rising_bars
    )

    return ctx.score > 0.5

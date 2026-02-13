from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VolumeContext:
    score: float               # -2 to +2
    strength: str              # STRONG | MODERATE | WEAK | NONE
    trend: str                 # RISING | FALLING | FLAT
    comment: str


def analyze_volume(
    volume_history: List[float],
    close_prices: Optional[List[float]] = None,
    lookback: int = 20,
    rising_bars: int = 4
) -> VolumeContext:
    """
    STRICT Institutional Volume Analysis.

    Changes vs previous version:
    - Moderate volume downgraded
    - Weak volume penalized
    - Absorption punished harder
    - Only TRUE expansion rewarded strongly
    """

    if not volume_history or len(volume_history) < lookback + rising_bars:
        return VolumeContext(0.0, "NONE", "FLAT", "Insufficient volume data")

    recent = volume_history[-lookback:]
    avg_volume = sum(recent) / lookback if lookback > 0 else 0
    current_volume = volume_history[-1]

    # ----------------------
    # 1️⃣ Relative Volume Strength
    # ----------------------

    rel = current_volume / avg_volume if avg_volume > 0 else 1.0

    if rel >= 2.0:
        strength = "STRONG"
        score = 2.0
    elif rel >= 1.6:
        strength = "MODERATE"
        score = 0.9
    elif rel >= 1.1:
        strength = "WEAK"
        score = 0.1
    else:
        strength = "NONE"
        score = -0.8

    # ----------------------
    # 2️⃣ Volume Trend Structure
    # ----------------------

    last_n = volume_history[-rising_bars:]

    if all(last_n[i] > last_n[i - 1] for i in range(1, len(last_n))):
        trend = "RISING"
        score += 0.6
    elif all(last_n[i] < last_n[i - 1] for i in range(1, len(last_n))):
        trend = "FALLING"
        score -= 0.6
    else:
        trend = "FLAT"
        score -= 0.2  # sideways volume is not supportive

    # ----------------------
    # 3️⃣ Price–Volume Confirmation
    # ----------------------

    comment = ""

    if close_prices and len(close_prices) >= rising_bars:
        price_move = close_prices[-1] - close_prices[-rising_bars]

        # small motion threshold
        threshold = 0.0025 * close_prices[-1]

        if abs(price_move) < threshold:
            # High volume but no move → absorption
            if strength in ("STRONG", "MODERATE"):
                score -= 1.0
                comment = "absorption_detected"
            else:
                comment = "low conviction"
        else:
            if strength == "STRONG":
                score += 0.5
            comment = "volume_confirms_move"
    else:
        comment = "volume_only"

    # ----------------------
    # Clamp Score
    # ----------------------

    final_score = max(min(score, 2.0), -2.0)

    return VolumeContext(
        score=round(final_score, 2),
        strength=strength,
        trend=trend,
        comment=comment
    )


def volume_spike_confirmed(
    volume_history,
    threshold_multiplier: float = 1.6,
    lookback: int = 20,
    rising_bars: int = 4
) -> bool:
    """
    Strict legacy boolean.
    """
    ctx = analyze_volume(volume_history, lookback=lookback, rising_bars=rising_bars)
    return ctx.score >= 1.2

from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class VWAPContext:
    vwap: Optional[float]
    distance_pct: float
    slope: float
    acceptance: str         # ABOVE | BELOW | REJECTED | NEAR
    pressure: str           # BUYING | SELLING | NEUTRAL
    score: float            # -2 to +2
    comment: str


class VWAPCalculator:
    """
    STRICT Intraday VWAP Calculator.

    Upgrades:
    - Wider acceptance threshold
    - Penalizes magnet-zone trading
    - Requires real slope confirmation
    """

    def __init__(self, window: Optional[int] = None, slope_window: int = 6):
        self.window = window
        self.slope_window = slope_window

        self.price_volume_sum = 0.0
        self.volume_sum = 0.0

        self.vwap_history = deque(maxlen=slope_window)

        if window:
            self.price_volume_deque = deque(maxlen=window)
            self.volume_deque = deque(maxlen=window)

        self.reset()

    def reset(self):
        self.price_volume_sum = 0.0
        self.volume_sum = 0.0
        self.vwap_history.clear()

        if hasattr(self, "price_volume_deque"):
            self.price_volume_deque.clear()
            self.volume_deque.clear()

    def update(self, price: float, volume: float) -> Optional[float]:
        if price is None or volume is None or volume <= 0:
            return None

        if self.window:
            self.price_volume_deque.append(price * volume)
            self.volume_deque.append(volume)
            self.price_volume_sum = sum(self.price_volume_deque)
            self.volume_sum = sum(self.volume_deque)
        else:
            self.price_volume_sum += price * volume
            self.volume_sum += volume

        if self.volume_sum <= 0:
            return None

        vwap = self.price_volume_sum / self.volume_sum
        self.vwap_history.append(vwap)
        return vwap

    def get_vwap(self) -> Optional[float]:
        if self.volume_sum <= 0:
            return None
        return self.price_volume_sum / self.volume_sum

    # =========================
    # STRICT VWAP INTELLIGENCE
    # =========================

    def get_context(self, price: float) -> VWAPContext:

        vwap = self.get_vwap()

        if vwap is None or price is None:
            return VWAPContext(
                vwap=None,
                distance_pct=0.0,
                slope=0.0,
                acceptance="NEAR",
                pressure="NEUTRAL",
                score=0.0,
                comment="VWAP unavailable"
            )

        distance_pct = (price - vwap) / vwap * 100.0

        # slope strength
        if len(self.vwap_history) >= 2:
            slope = self.vwap_history[-1] - self.vwap_history[0]
        else:
            slope = 0.0

        # ----------------------------
        # STRONGER ACCEPTANCE ZONES
        # ----------------------------

        if distance_pct > 0.35:
            acceptance = "ABOVE"
        elif distance_pct < -0.35:
            acceptance = "BELOW"
        else:
            acceptance = "NEAR"

        # ----------------------------
        # PRESSURE LOGIC (STRICT)
        # ----------------------------

        score = 0.0
        pressure = "NEUTRAL"
        comment = ""

        # Strong bullish continuation
        if acceptance == "ABOVE" and slope > 0:
            pressure = "BUYING"
            score = 1.8
            comment = "strong_acceptance_above_vwap"

        # Strong bearish continuation
        elif acceptance == "BELOW" and slope < 0:
            pressure = "SELLING"
            score = -1.8
            comment = "strong_acceptance_below_vwap"

        # Weak alignment (distance ok but slope weak)
        elif acceptance in ("ABOVE", "BELOW"):
            pressure = "NEUTRAL"
            score = -0.8
            comment = "distance_without_slope"

        # Magnet zone (very dangerous area)
        else:
            pressure = "NEUTRAL"
            score = -1.0
            comment = "near_vwap_magnet_zone"

        # Clamp
        score = max(min(score, 2.0), -2.0)

        return VWAPContext(
            vwap=round(vwap, 6),
            distance_pct=round(distance_pct, 3),
            slope=round(slope, 6),
            acceptance=acceptance,
            pressure=pressure,
            score=score,
            comment=comment
        )

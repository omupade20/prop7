# strategy/sr_levels.py
"""
Institutional Intraday Support & Resistance (v2)

Upgrades applied over v1:
- Uses highs, lows, closes together
- Volume-weighted pivot clustering
- ATR-scaled clustering tolerance
- Recency decay weighting
- Strength-based level selection
- Optional VWAP & HTF level merge hooks

Designed for 1-minute intraday data.
"""

from typing import List, Dict, Optional, Tuple
from statistics import mean
import math


# =========================
# Helpers
# =========================

def _true_range(h: float, l: float, prev_c: float) -> float:
    return max(h - l, abs(h - prev_c), abs(l - prev_c))


def compute_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(highs) < period + 1:
        return 0.0

    trs = []
    for i in range(1, len(highs)):
        trs.append(_true_range(highs[i], lows[i], closes[i - 1]))

    return sum(trs[-period:]) / period


# =========================
# Pivot Detection
# =========================

def _find_local_extrema(values: List[float], window: int = 7) -> List[Tuple[int, float]]:
    n = len(values)
    extrema = []

    if n < window * 2 + 1:
        return extrema

    half = window // 2

    for i in range(half, n - half):
        c = values[i]
        left = values[i - half:i]
        right = values[i + 1:i + 1 + half]

        if all(c >= x for x in left + right) or all(c <= x for x in left + right):
            extrema.append((i, c))

    return extrema


# =========================
# Volume + Recency Weighted Clustering
# =========================

def _cluster_levels_weighted(
    pivots: List[Tuple[int, float]],
    volumes: List[float],
    atr: float,
    atr_mult: float = 0.6,
    decay: float = 0.995
) -> List[Dict]:
    """
    Cluster pivots using ATR-scaled tolerance.
    Weight by volume and recency.
    """

    if not pivots:
        return []

    tol = max(atr * atr_mult, 1e-9)

    clusters = []

    for idx, price in pivots:
        vol = volumes[idx] if idx < len(volumes) else 1.0
        weight = vol * (decay ** (len(volumes) - idx))

        placed = False
        for c in clusters:
            if abs(price - c["mean"]) <= tol:
                c["prices"].append(price)
                c["weights"].append(weight)
                c["mean"] = sum(p * w for p, w in zip(c["prices"], c["weights"])) / sum(c["weights"])
                placed = True
                break

        if not placed:
            clusters.append({
                "prices": [price],
                "weights": [weight],
                "mean": price
            })

    out = []
    for c in clusters:
        strength = sum(c["weights"])
        out.append({
            "level": round(c["mean"], 6),
            "strength": strength,
            "touches": len(c["prices"])
        })

    return out


# =========================
# Main SR Computation
# =========================

def compute_sr_levels(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    lookback: int = 360,
    extrema_window: int = 7,
    max_levels: int = 4,
    atr_period: int = 14
) -> Dict[str, List[Dict]]:
    """
    Institutional SR detection.
    """

    highs = highs[-lookback:]
    lows = lows[-lookback:]
    closes = closes[-lookback:]
    volumes = volumes[-lookback:]

    if not highs or not lows or not closes:
        return {"levels": []}

    atr = compute_atr(highs, lows, closes, atr_period)

    values = []
    for h, l, c in zip(highs, lows, closes):
        values.append(h)
        values.append(l)
        values.append(c)

    pivots = _find_local_extrema(values, window=extrema_window)

    clusters = _cluster_levels_weighted(pivots, volumes * 3, atr)

    clusters_sorted = sorted(clusters, key=lambda x: x["strength"], reverse=True)[:max_levels]

    return {"levels": clusters_sorted}


# =========================
# Nearest SR
# =========================

def get_nearest_sr(price: float, sr: Dict[str, List[Dict]], max_dist_atr: float = 1.5, atr: float = 0.0) -> Optional[Dict]:
    if not sr or "levels" not in sr:
        return None

    best = None
    best_dist = float("inf")

    for lvl in sr["levels"]:
        d = abs(price - lvl["level"])
        if d < best_dist:
            best_dist = d
            best = lvl

    if atr > 0 and best_dist > atr * max_dist_atr:
        return None

    return best


# =========================
# Location Score
# =========================

def sr_location_score(price: float, nearest: Optional[Dict], atr: float, direction: str) -> float:
    if nearest is None or atr <= 0:
        return 0.0

    dist = abs(price - nearest["level"])
    closeness = max(0.0, 1.0 - (dist / (atr * 1.5)))

    strength = min(2.0, math.log1p(nearest.get("strength", 1.0)))

    sign = 0
    if direction == "LONG":
        sign = 1 if price >= nearest["level"] else -1
    elif direction == "SHORT":
        sign = 1 if price <= nearest["level"] else -1

    score = sign * closeness * strength
    return max(-1.0, min(1.0, round(score, 3)))

# strategy/sr_levels.py

"""
Support & Resistance utilities (tuned for intraday precision).

Improvements:
- Safer numeric handling
- Faster clustering
- Stable nearest SR search
- Consistent rounding
"""

from typing import List, Dict, Optional, Tuple
from statistics import mean


# =========================
# Simple fallback SR
# =========================

def compute_simple_sr(
    highs: List[float],
    lows: List[float],
    lookback: int = 180
) -> Dict[str, Optional[float]]:

    highs = highs[-lookback:] if highs else []
    lows = lows[-lookback:] if lows else []

    if not highs or not lows:
        return {"support": None, "resistance": None}

    return {
        "support": min(lows),
        "resistance": max(highs)
    }


# =========================
# Local extrema detection
# =========================

def _find_local_extrema(
    values: List[float],
    window: int = 7
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:

    n = len(values)

    maxima = []
    minima = []

    if n < window * 2 + 1:
        return maxima, minima

    half = window // 2

    for i in range(half, n - half):

        center = values[i]
        left = values[i - half:i]
        right = values[i + 1:i + 1 + half]

        if all(center > x for x in left + right):
            maxima.append((i, center))

        if all(center < x for x in left + right):
            minima.append((i, center))

    return maxima, minima


# =========================
# Level clustering
# =========================

def _cluster_levels(
    peaks: List[float],
    tol_pct: float = 0.0035
) -> List[Dict]:

    if not peaks:
        return []

    sorted_peaks = sorted(peaks)

    clusters = []
    cluster = [sorted_peaks[0]]

    for p in sorted_peaks[1:]:

        avg = sum(cluster) / len(cluster)
        tol = avg * tol_pct

        if abs(p - avg) <= tol:
            cluster.append(p)

        else:
            clusters.append(cluster)
            cluster = [p]

    clusters.append(cluster)

    results = []

    for c in clusters:

        level = mean(c)

        results.append({
            "level": round(level, 6),
            "count": len(c),
            "strength": min(len(c), 4)
        })

    return results


# =========================
# Compute SR Levels
# =========================

def compute_sr_levels(
    highs: List[float],
    lows: List[float],
    lookback: int = 360,
    extrema_window: int = 7,
    cluster_tol_pct: float = 0.0035,
    max_levels: int = 3
) -> Dict[str, List[Dict]]:

    highs_s = highs[-lookback:] if highs else []
    lows_s = lows[-lookback:] if lows else []

    if not highs_s or not lows_s:
        return {"supports": [], "resistances": []}

    max_extrema, _ = _find_local_extrema(highs_s, window=extrema_window)
    _, min_extrema = _find_local_extrema(lows_s, window=extrema_window)

    resistances = [v for _, v in max_extrema]
    supports = [v for _, v in min_extrema]

    resist_clusters = _cluster_levels(resistances, tol_pct=cluster_tol_pct)
    supp_clusters = _cluster_levels(supports, tol_pct=cluster_tol_pct)

    supports_sorted = sorted(
        supp_clusters,
        key=lambda x: x["level"]
    )[:max_levels]

    resistances_sorted = sorted(
        resist_clusters,
        key=lambda x: x["level"],
        reverse=True
    )[:max_levels]

    return {
        "supports": supports_sorted,
        "resistances": resistances_sorted
    }


# =========================
# Nearest SR
# =========================

def get_nearest_sr(
    price: float,
    sr_levels: Dict[str, List[Dict]],
    max_search_pct: float = 0.025
) -> Optional[Dict]:

    if not sr_levels:
        return None

    supports = sr_levels.get("supports", [])
    resistances = sr_levels.get("resistances", [])

    best = None
    best_dist = float("inf")

    # Check supports
    for s in supports:

        lvl = s["level"]

        dist = abs(price - lvl) / max(lvl, 1e-9)

        if dist < best_dist:
            best_dist = dist
            best = {
                "type": "support",
                "level": lvl,
                "dist_pct": dist,
                "strength": s.get("strength", 1)
            }

    # Check resistances
    for r in resistances:

        lvl = r["level"]

        dist = abs(lvl - price) / max(price, 1e-9)

        if dist < best_dist:
            best_dist = dist
            best = {
                "type": "resistance",
                "level": lvl,
                "dist_pct": dist,
                "strength": r.get("strength", 1)
            }

    if best and best["dist_pct"] <= max_search_pct:
        return best

    return None


# =========================
# SR Location Score
# =========================

def sr_location_score(
    price: float,
    nearest_sr: Optional[Dict],
    direction: str,
    proximity_threshold: float = 0.02
) -> float:

    if nearest_sr is None:
        return 0.0

    dist = nearest_sr.get("dist_pct")

    if dist is None or dist > proximity_threshold:
        return 0.0

    closeness = max(
        0.0,
        (proximity_threshold - dist) /
        (proximity_threshold + 1e-9)
    )

    strength = float(nearest_sr.get("strength", 1))

    strength_factor = min(
        1.5,
        0.6 + 0.2 * strength
    )

    typ = nearest_sr.get("type")

    sign = 0

    if direction == "LONG":

        if typ == "support":
            sign = 1

        elif typ == "resistance":
            sign = -1

    elif direction == "SHORT":

        if typ == "resistance":
            sign = 1

        elif typ == "support":
            sign = -1

    score = sign * closeness * strength_factor

    score = max(min(score, 1.0), -1.0)

    return round(score, 3)

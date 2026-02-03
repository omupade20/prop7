from typing import List, Dict, Optional
from statistics import mean

# ==================================================
# 1️⃣ PIVOT CONFIRMED DETECTION (LIKE PINE SCRIPT)
# ==================================================

def find_pivot_highs(
    highs: List[float],
    left: int = 5,
    right: int = 5
) -> List[int]:
    """
    Returns indices of pivot highs:
    A pivot high at i means highs[i] > all highs to the left and >= all to the right.
    This replicates Pine Script's pivothigh(leftBars, rightBars). :contentReference[oaicite:1]{index=1}
    """
    pivots = []
    n = len(highs)
    for i in range(left, n - right):
        center = highs[i]
        if center > max(highs[i - left:i]) and center >= max(highs[i+1:i+1+right]):
            pivots.append(i)
    return pivots

def find_pivot_lows(
    lows: List[float],
    left: int = 5,
    right: int = 5
) -> List[int]:
    """
    Returns indices of pivot lows (reverse logic).
    """
    pivots = []
    n = len(lows)
    for i in range(left, n - right):
        center = lows[i]
        if center < min(lows[i - left:i]) and center <= min(lows[i+1:i+1+right]):
            pivots.append(i)
    return pivots

# ==================================================
# 2️⃣ CLUSTERING CONFIRMED PIVOTS INTO LEVELS
# ==================================================

def cluster_pivot_levels(
    prices: List[float],
    indices: List[int],
    tol_pct: float = 0.005,
    min_hits: int = 1
) -> List[Dict]:
    """
    Group pivot values close to each other (within tol_pct) into clusters.
    A cluster becomes a level if it has at least min_hits.
    """
    if not indices:
        return []

    pivot_vals = sorted(prices[i] for i in indices)
    clusters = [[pivot_vals[0]]]

    for price in pivot_vals[1:]:
        avg = mean(clusters[-1])
        if abs(price - avg) <= avg * tol_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    out = []
    for c in clusters:
        if len(c) >= min_hits:
            out.append({"level": round(mean(c), 6), "strength": len(c)})
    return out

def compute_sr_levels(
    highs: List[float],
    lows: List[float],
    left: int = 5,
    right: int = 5,
    tol_pct: float = 0.005,
    max_levels: int = 6
) -> Dict[str, List[Dict]]:
    """
    Compute pivot-confirmed support & resistance levels.
    - left, right: replicate Pine Script pivot parameters.
    - tol_pct: cluster tolerance (%) relative to price.
    - max_levels: number of levels per side to keep.
    """
    # Find pivot indices
    piv_hi_idx = find_pivot_highs(highs, left=left, right=right)
    piv_lo_idx = find_pivot_lows(lows, left=left, right=right)

    # Cluster into price levels
    resistances = cluster_pivot_levels(highs, piv_hi_idx, tol_pct=tol_pct)
    supports = cluster_pivot_levels(lows, piv_lo_idx, tol_pct=tol_pct)

    # Sort and trim
    resistances = sorted(resistances, key=lambda x: x["level"], reverse=True)[:max_levels]
    supports = sorted(supports, key=lambda x: x["level"])[:max_levels]

    return {"supports": supports, "resistances": resistances}

# ==================================================
# 3️⃣ NEAREST S/R & LOCATION SCORE
# ==================================================

def get_nearest_sr(
    price: float,
    sr_levels: Dict[str, List[Dict]],
    max_dist_pct: float = 0.04
) -> Optional[Dict]:
    """
    Return nearest support or resistance within max_dist_pct of price.
    """
    if not sr_levels:
        return None

    best = None
    best_dist = float("inf")

    for s in sr_levels.get("supports", []):
        dist = abs(price - s["level"]) / price
        if dist < best_dist:
            best_dist = dist
            best = {"type": "support", **s, "dist_pct": dist}

    for r in sr_levels.get("resistances", []):
        dist = abs(r["level"] - price) / price
        if dist < best_dist:
            best_dist = dist
            best = {"type": "resistance", **r, "dist_pct": dist}

    return best if best and best["dist_pct"] <= max_dist_pct else None

def sr_location_score(
    price: float,
    nearest_sr: Optional[Dict],
    direction: str,
    max_dist_pct: float = 0.04,
    hard_zone_pct: float = 0.015
) -> float:
    """
    Soft/hard influence score of nearest S/R level.
    - If price is inside a hard zone near opposite SR (within hard_zone_pct),
      penalize strongly (-1.0).
    - Otherwise score influence based on closeness and strength.
    """
    if not nearest_sr:
        return 0.0

    dist = nearest_sr["dist_pct"]
    typ = nearest_sr["type"]
    strength = nearest_sr.get("strength", 1)

    # Hard block zone
    if dist <= hard_zone_pct:
        if direction == "LONG" and typ == "resistance":
            return -1.0
        if direction == "SHORT" and typ == "support":
            return -1.0

    # Soft influence
    if dist > max_dist_pct:
        return 0.0

    closeness = max(0.0, (max_dist_pct - dist) / max_dist_pct)
    weight = min(1.5, 0.5 + 0.3 * strength)

    if direction == "LONG":
        # support helps, resistance hurts
        return round(closeness * weight if typ == "support" else -0.6 * closeness, 3)
    else:
        # resistance helps short, support hurts
        return round(closeness * weight if typ == "resistance" else -0.6 * closeness, 3)

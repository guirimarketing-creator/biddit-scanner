"""
Compute rental yield and a quality score for each property in the DB.
Only processes properties in the target Flemish provinces.
"""

from config import MIN_YIELD, INCLUDED_PROVINCES, EPC_RANK, MAJOR_CITIES, EXCLUDED_PROPERTY_TYPES
from database import get_all_active, update_yields
from rental_rates import get_rent_rate

# Building condition → estimated structural renovation cost (€).
RENOVATION_COSTS: dict[str, float] = {
    "goed": 0,
    "goed onderhouden": 0,
    "zeer goed": 0,
    "op te frissen": 20_000,
    "te renoveren": 70_000,
    "volledig te renoveren": 100_000,
    "grondige renovatie": 100_000,
    "af te breken": 150_000,
    "te slopen": 150_000,
    "nieuw": 0,
    "nieuwbouw": 0,
}

# EPC label → estimated energy renovation cost (€).
# Reflects Flemish EPC compliance requirements (2028: label C, 2035: label B).
# A "Goed" house with EPC F still needs ~€50-80k in energy work to rent legally.
EPC_RENOVATION_COSTS: dict[str, float] = {
    "A+": 0,
    "A":  0,
    "B":  0,
    "C":  0,
    "D":  10_000,   # Minor upgrades to meet 2028 deadline
    "E":  35_000,   # Insulation + heating upgrade
    "F":  65_000,   # Major energy renovation
    "G":  90_000,   # Complete energy overhaul
}


def estimate_renovation_cost(renovation_state: str, epc_score: str) -> float | None:
    structural = None
    if renovation_state:
        key = renovation_state.lower().strip()
        for pattern, cost in RENOVATION_COSTS.items():
            if pattern in key:
                structural = cost
                break

    energy = EPC_RENOVATION_COSTS.get((epc_score or "").upper().strip())

    if structural is None and energy is None:
        return None

    # When building needs full renovation, energy work is included — don't double-count.
    # When building is in good shape but EPC is bad, energy cost IS the renovation cost.
    structural = structural or 0
    energy = energy or 0
    if structural >= 70_000:
        # Full renovation already covers energy upgrade
        return structural
    return structural + energy


def compute_score(row: dict, gross_yield: float) -> float:
    """
    Higher = more interesting. Components:
      - Yield contribution (main driver)
      - EPC bonus (energy-efficient = lower running costs)
      - Major city bonus (liquidity, demand)
      - Property type penalty for land-only
    """
    score = gross_yield * 10  # Base: yield drives score

    epc = (row.get("epc_score") or "").upper().strip()
    epc_rank = EPC_RANK.get(epc, 5)  # Default to E-level (mediocre) if unknown
    if epc_rank <= 2:    # A+, A, B
        score += 15
    elif epc_rank == 3:  # C
        score += 8
    elif epc_rank >= 6:  # F, G
        score -= 10

    city = (row.get("city") or "").lower().strip()
    if city in MAJOR_CITIES:
        score += 10

    ptype = (row.get("property_type") or "").lower()
    if ptype == "land":
        score -= 20  # Land rarely generates rental income

    return round(score, 2)


def run_analyzer() -> dict:
    """
    Calculate estimated rental income and gross yield for all active properties
    in the target provinces. Updates DB in place.

    Returns summary stats dict.
    """
    rows = get_all_active(province_filter=INCLUDED_PROVINCES)
    stats = {
        "total_in_region": len(rows),
        "total_with_yield": 0,
        "total_interesting": 0,
    }

    for row in rows:
        if (row["property_type"] or "unknown") in EXCLUDED_PROPERTY_TYPES:
            continue

        size_m2 = row["size_m2"]
        purchase_price = row["current_bid"] or row["starting_price"]

        if not size_m2 or size_m2 <= 0 or not purchase_price or purchase_price <= 0:
            continue

        rate = get_rent_rate(row["city"], row["province"])
        monthly_rent = round(size_m2 * rate, 2)
        annual_rent = monthly_rent * 12
        gross_yield = round((annual_rent / purchase_price) * 100, 2)

        row_dict = dict(row)
        score = compute_score(row_dict, gross_yield)
        renovation_cost = estimate_renovation_cost(
            row["renovation_state"] or "", row["epc_score"] or ""
        )

        update_yields(row["biddit_id"], monthly_rent, gross_yield, score, renovation_cost)

        stats["total_with_yield"] += 1
        if gross_yield >= MIN_YIELD:
            stats["total_interesting"] += 1

    print(
        f"[analyzer] {stats['total_in_region']} properties in region, "
        f"{stats['total_with_yield']} with yield computed, "
        f"{stats['total_interesting']} >= {MIN_YIELD}%"
    )
    return stats


if __name__ == "__main__":
    from database import init_db
    init_db()
    run_analyzer()

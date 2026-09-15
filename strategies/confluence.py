from __future__ import annotations

from .models import EntryZone, FairValueGap, LiquidityPool, LiquiditySweep, OrderBlock, StructureEvent


DEFAULT_WEIGHTS = {
    "liquidity_identified": 2,
    "liquidity_sweep": 2,
    "bos_choch_mss": 2,
    "order_block": 2,
    "fair_value_gap": 1,
    "strong_displacement": 1,
    "session_confirmation": 1,
    "htf_alignment": 2,
}


def score_setup(
    direction: str,
    liquidity: LiquidityPool | None,
    sweep: LiquiditySweep | None,
    structure_event: StructureEvent | None,
    order_block: OrderBlock | None,
    fvg: FairValueGap | None,
    strong_displacement: bool = False,
    session_confirmation: bool = False,
    htf_alignment: bool = False,
    weights: dict[str, int] | None = None,
) -> tuple[int, int, dict[str, int]]:
    weights = weights or DEFAULT_WEIGHTS
    components = {
        "liquidity_identified": weights["liquidity_identified"] if liquidity else 0,
        "liquidity_sweep": weights["liquidity_sweep"] if sweep and sweep.direction == direction else 0,
        "bos_choch_mss": weights["bos_choch_mss"] if structure_event and structure_event.direction == direction else 0,
        "order_block": weights["order_block"] if order_block and order_block.direction == direction else 0,
        "fair_value_gap": weights["fair_value_gap"] if fvg and fvg.direction == direction else 0,
        "strong_displacement": weights["strong_displacement"] if strong_displacement else 0,
        "session_confirmation": weights["session_confirmation"] if session_confirmation else 0,
        "htf_alignment": weights["htf_alignment"] if htf_alignment else 0,
    }
    return sum(components.values()), sum(weights.values()), components


def calculate_entry_zone(
    direction: str,
    order_block: OrderBlock | None,
    fvg: FairValueGap | None,
    prefer_overlap: bool = True,
    fallback_to_ob: bool = True,
    fallback_to_fvg: bool = True,
    reject_if_no_overlap: bool = False,
) -> EntryZone | None:
    if order_block and order_block.direction != direction:
        order_block = None
    if fvg and fvg.direction != direction:
        fvg = None

    if order_block and fvg and prefer_overlap:
        low = max(order_block.low, fvg.low)
        high = min(order_block.high, fvg.high)
        if low <= high:
            return EntryZone(direction, low, high, ("order_block", "fair_value_gap"))
        if reject_if_no_overlap:
            return None

    if order_block and fallback_to_ob:
        return EntryZone(direction, order_block.low, order_block.high, ("order_block",))
    if fvg and fallback_to_fvg:
        return EntryZone(direction, fvg.low, fvg.high, ("fair_value_gap",))
    return None


def calculate_invalidation(
    direction: str,
    sweep: LiquiditySweep | None,
    order_block: OrderBlock | None,
    buffer_points: float = 50,
    method: str = "beyond_sweep_extreme",
) -> float | None:
    if direction == "bullish":
        candidates = []
        if sweep:
            candidates.append(sweep.sweep_extreme)
        if order_block:
            candidates.append(order_block.low)
        if not candidates:
            return None
        base = min(candidates) if method == "most_conservative" else candidates[0]
        return base - buffer_points

    candidates = []
    if sweep:
        candidates.append(sweep.sweep_extreme)
    if order_block:
        candidates.append(order_block.high)
    if not candidates:
        return None
    base = max(candidates) if method == "most_conservative" else candidates[0]
    return base + buffer_points

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SwingPoint:
    kind: str
    index: int
    timestamp: Any
    price: float
    confirmed_index: int
    confirmed_time: Any


@dataclass(frozen=True)
class StructureEvent:
    event_type: str
    direction: str
    broken_level: float
    break_index: int
    break_time: Any
    confirmation_index: int
    confirmation_time: Any
    prior_structure: str
    new_structure: str


@dataclass(frozen=True)
class LiquidityPool:
    kind: str
    source: str
    price_level: float
    formation_index: int
    formation_time: Any
    confirmed_index: int
    confirmed_time: Any
    touch_count: int = 1
    swept: bool = False


@dataclass(frozen=True)
class LiquiditySweep:
    direction: str
    liquidity_level: float
    pool_source: str
    sweep_extreme: float
    sweep_index: int
    sweep_time: Any
    confirmation_index: int
    confirmation_time: Any
    penetration_points: float
    rejection_close: float
    displacement_confirmed: bool


@dataclass(frozen=True)
class OrderBlock:
    direction: str
    low: float
    high: float
    start_index: int
    end_index: int
    formation_time: Any
    confirmed_index: int
    confirmed_time: Any
    caused_event_type: str | None = None
    after_sweep: bool = False
    touch_count: int = 0


@dataclass(frozen=True)
class FairValueGap:
    direction: str
    low: float
    high: float
    formation_index: int
    formation_time: Any
    size_points: float
    mitigated: bool = False
    mitigation_time: Any | None = None
    retest_count: int = 0
    associated_structure_event: str | None = None


@dataclass(frozen=True)
class EntryZone:
    direction: str
    low: float
    high: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SetupDecision:
    symbol: str
    timeframe: str
    timestamp: Any
    h4_bias: str
    h1_bias: str
    m15_structure: str
    liquidity: LiquidityPool | None
    sweep: LiquiditySweep | None
    structure_event: StructureEvent | None
    order_block: OrderBlock | None
    fvg: FairValueGap | None
    confluence_score: int
    max_score: int
    required_score: int
    entry_zone: EntryZone | None
    invalidation: float | None
    decision: str
    reason: str
    components: dict[str, int] = field(default_factory=dict)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BacktestOrderPlan:
    direction: str
    signal_index: int
    signal_time: Any
    entry: float
    stop_loss: float
    take_profits: tuple[float, ...]
    allocations: tuple[float, ...]
    risk_amount: float
    risk_per_unit: float
    setup_score: int
    model: str


@dataclass(frozen=True)
class BacktestTrade:
    direction: str
    signal_time: Any
    entry_time: Any
    exit_time: Any
    entry: float
    stop_loss: float
    take_profits: tuple[float, ...]
    allocations: tuple[float, ...]
    exit_reason: str
    pnl: float
    r_multiple: float
    risk_amount: float
    bars_held: int
    tp_hits: tuple[bool, ...]
    entry_model: str
    confluence_score: int
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BacktestResult:
    trades: list[BacktestTrade]
    metrics: dict[str, float]
    equity_curve: list[tuple[Any, float]]
    rejected_signals: list[dict[str, Any]]

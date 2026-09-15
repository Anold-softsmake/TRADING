from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoricalRiskManager:
    starting_equity: float = 10_000.0
    risk_per_setup_pct: float = 0.5
    max_daily_loss_pct: float = 2.0
    max_weekly_loss_pct: float = 5.0
    max_trades_day: int = 3
    max_consecutive_losses: int = 3
    equity: float = field(init=False)
    daily_pnl: dict[str, float] = field(default_factory=dict)
    weekly_pnl: dict[str, float] = field(default_factory=dict)
    daily_trades: dict[str, int] = field(default_factory=dict)
    consecutive_losses: int = 0

    def __post_init__(self) -> None:
        self.equity = self.starting_equity

    def can_open(self, timestamp: Any) -> tuple[bool, str]:
        day = _day_key(timestamp)
        week = _week_key(timestamp)
        if self.daily_trades.get(day, 0) >= self.max_trades_day:
            return False, "Maximum trades/day reached."
        if self.daily_pnl.get(day, 0.0) <= -self.starting_equity * self.max_daily_loss_pct / 100:
            return False, "Maximum daily loss reached."
        if self.weekly_pnl.get(week, 0.0) <= -self.starting_equity * self.max_weekly_loss_pct / 100:
            return False, "Maximum weekly loss reached."
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, "Maximum consecutive losses reached."
        return True, "PASS"

    def risk_amount(self) -> float:
        return self.equity * self.risk_per_setup_pct / 100

    def record_open(self, timestamp: Any) -> None:
        day = _day_key(timestamp)
        self.daily_trades[day] = self.daily_trades.get(day, 0) + 1

    def record_close(self, timestamp: Any, pnl: float) -> None:
        day = _day_key(timestamp)
        week = _week_key(timestamp)
        self.equity += pnl
        self.daily_pnl[day] = self.daily_pnl.get(day, 0.0) + pnl
        self.weekly_pnl[week] = self.weekly_pnl.get(week, 0.0) + pnl
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0


def _day_key(timestamp: Any) -> str:
    return timestamp.strftime("%Y-%m-%d") if hasattr(timestamp, "strftime") else str(timestamp)


def _week_key(timestamp: Any) -> str:
    if hasattr(timestamp, "strftime"):
        return f"{timestamp.isocalendar().year}-W{timestamp.isocalendar().week:02d}"
    return str(timestamp)

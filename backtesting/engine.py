from __future__ import annotations

from typing import Any

import pandas as pd

from risk.risk_manager import HistoricalRiskManager
from strategies.amin_xauusd_strategy import AminXauusdPhase1Strategy
from strategies.models import SetupDecision
from strategies.utils import validate_ohlc

from .metrics import calculate_metrics
from .models import BacktestOrderPlan, BacktestResult, BacktestTrade


class HistoricalBacktestEngine:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.strategy = AminXauusdPhase1Strategy(settings)
        risk_cfg = settings.get("risk", {})
        self.risk = HistoricalRiskManager(
            starting_equity=float(risk_cfg.get("starting_equity", 10_000)),
            risk_per_setup_pct=float(risk_cfg.get("risk_per_setup_pct", 0.5)),
            max_daily_loss_pct=float(risk_cfg.get("max_daily_loss_pct", 2)),
            max_weekly_loss_pct=float(risk_cfg.get("max_weekly_loss_pct", 5)),
            max_trades_day=int(risk_cfg.get("max_trades_day", 3)),
            max_consecutive_losses=int(risk_cfg.get("max_consecutive_losses", 3)),
        )

    def run(self, m15: pd.DataFrame, h1: pd.DataFrame | None = None, h4: pd.DataFrame | None = None) -> BacktestResult:
        df = validate_ohlc(m15)
        analysis = self.strategy.analyze(df, h1, h4)
        trades: list[BacktestTrade] = []
        rejected: list[dict[str, Any]] = []
        equity_curve: list[tuple[Any, float]] = [(df.at[0, "timestamp"], self.risk.equity)]
        index = 0

        while index < len(df):
            decision = analysis.decisions[index]
            if decision.decision != "TRADE_CANDIDATE":
                index += 1
                continue

            allowed, reason = self.risk.can_open(decision.timestamp)
            if not allowed:
                rejected.append({"timestamp": decision.timestamp, "reason": reason, "score": decision.confluence_score})
                index += 1
                continue

            plan = self._build_order_plan(decision, index)
            if plan is None:
                rejected.append({"timestamp": decision.timestamp, "reason": "Invalid order plan.", "score": decision.confluence_score})
                index += 1
                continue

            trade, exit_index = self._simulate_order(df, plan)
            if trade is None:
                rejected.append({"timestamp": decision.timestamp, "reason": "Entry zone not reached before expiry.", "score": decision.confluence_score})
                index += 1
                continue

            self.risk.record_open(trade.entry_time)
            self.risk.record_close(trade.exit_time, trade.pnl)
            trades.append(trade)
            equity_curve.append((trade.exit_time, self.risk.equity))
            index = max(exit_index + 1, index + 1)

        metrics = calculate_metrics(trades, float(self.settings.get("risk", {}).get("starting_equity", 10_000)))
        return BacktestResult(trades, metrics, equity_curve, rejected)

    def _build_order_plan(self, decision: SetupDecision, signal_index: int) -> BacktestOrderPlan | None:
        if decision.entry_zone is None or decision.invalidation is None:
            return None
        direction = _decision_direction(decision)
        entry = _entry_price(decision.entry_zone.low, decision.entry_zone.high, direction, self.settings.get("backtest", {}).get("entry_location", "zone_midpoint"))
        risk_per_unit = entry - decision.invalidation if direction == "bullish" else decision.invalidation - entry
        if risk_per_unit <= 0:
            return None
        risk_amount = self.risk.risk_amount()
        tp_multiples = tuple(float(x) for x in self.settings.get("backtest", {}).get("tp_r_multiples", [1, 2, 3]))
        allocations = tuple(float(x) for x in self.settings.get("backtest", {}).get("tp_allocations", [0.3, 0.3, 0.4]))
        if len(tp_multiples) != len(allocations) or round(sum(allocations), 6) != 1.0:
            return None
        take_profits = tuple(entry + risk_per_unit * multiple if direction == "bullish" else entry - risk_per_unit * multiple for multiple in tp_multiples)
        return BacktestOrderPlan(
            direction,
            signal_index,
            decision.timestamp,
            entry,
            decision.invalidation,
            take_profits,
            allocations,
            risk_amount,
            risk_per_unit,
            decision.confluence_score,
            self.settings.get("backtest", {}).get("entry_model", "single_entry"),
        )

    def _simulate_order(self, df: pd.DataFrame, plan: BacktestOrderPlan) -> tuple[BacktestTrade | None, int]:
        cfg = self.settings.get("backtest", {})
        max_wait = int(cfg.get("max_entry_wait_bars", 12))
        max_hold = int(cfg.get("max_hold_bars", 96))
        conservative = bool(cfg.get("conservative_same_candle", True))
        management = cfg.get("profit_management", "move_to_breakeven_after_tp1")
        entry_index = _find_entry_index(df, plan, max_wait)
        if entry_index is None:
            return None, plan.signal_index

        open_allocations = list(plan.allocations)
        tp_hits = [False for _ in plan.take_profits]
        pnl = 0.0
        stop = plan.stop_loss
        exit_reason = "time_exit"
        exit_index = min(len(df) - 1, entry_index + max_hold)
        notes: list[str] = []

        for index in range(entry_index, min(len(df), entry_index + max_hold + 1)):
            row = df.iloc[index]
            stop_hit = _stop_hit(row, plan.direction, stop)
            hit_tps = [tp_index for tp_index, tp in enumerate(plan.take_profits) if not tp_hits[tp_index] and _tp_hit(row, plan.direction, tp)]

            if conservative and stop_hit:
                pnl += -sum(open_allocations) * plan.risk_amount * _risk_units(plan.entry, stop, plan.risk_per_unit)
                exit_reason = "stop_loss"
                exit_index = index
                break

            for tp_index in hit_tps:
                tp_hits[tp_index] = True
                allocation = open_allocations[tp_index]
                open_allocations[tp_index] = 0.0
                pnl += allocation * plan.risk_amount * _tp_r_multiple(plan, tp_index)
                if tp_index == 0 and management == "move_to_breakeven_after_tp1":
                    stop = plan.entry
                    notes.append("SL moved to breakeven after TP1.")

            if not conservative and stop_hit:
                pnl += -sum(open_allocations) * plan.risk_amount * _risk_units(plan.entry, stop, plan.risk_per_unit)
                exit_reason = "stop_loss"
                exit_index = index
                break

            if all(tp_hits):
                exit_reason = "tp3"
                exit_index = index
                break

        else:
            row = df.iloc[exit_index]
            close = float(row["close"])
            pnl += _mark_to_market(plan, close, sum(open_allocations))

        trade = BacktestTrade(
            plan.direction,
            plan.signal_time,
            df.at[entry_index, "timestamp"],
            df.at[exit_index, "timestamp"],
            plan.entry,
            plan.stop_loss,
            plan.take_profits,
            plan.allocations,
            exit_reason,
            pnl,
            pnl / plan.risk_amount if plan.risk_amount else 0.0,
            plan.risk_amount,
            exit_index - entry_index,
            tuple(tp_hits),
            plan.model,
            plan.setup_score,
            notes,
        )
        return trade, exit_index


def _decision_direction(decision: SetupDecision) -> str:
    if decision.sweep:
        return decision.sweep.direction
    if decision.structure_event:
        return decision.structure_event.direction
    if decision.entry_zone:
        return decision.entry_zone.direction
    return "bullish"


def _entry_price(low: float, high: float, direction: str, location: str) -> float:
    if location == "zone_edge":
        return high if direction == "bullish" else low
    if location == "deep_zone":
        return low if direction == "bullish" else high
    return (low + high) / 2


def _find_entry_index(df: pd.DataFrame, plan: BacktestOrderPlan, max_wait: int) -> int | None:
    end = min(len(df), plan.signal_index + max_wait + 1)
    for index in range(plan.signal_index + 1, end):
        row = df.iloc[index]
        if float(row["low"]) <= plan.entry <= float(row["high"]):
            return index
    return None


def _stop_hit(row: pd.Series, direction: str, stop: float) -> bool:
    return float(row["low"]) <= stop if direction == "bullish" else float(row["high"]) >= stop


def _tp_hit(row: pd.Series, direction: str, tp: float) -> bool:
    return float(row["high"]) >= tp if direction == "bullish" else float(row["low"]) <= tp


def _tp_r_multiple(plan: BacktestOrderPlan, tp_index: int) -> float:
    if plan.direction == "bullish":
        return (plan.take_profits[tp_index] - plan.entry) / plan.risk_per_unit
    return (plan.entry - plan.take_profits[tp_index]) / plan.risk_per_unit


def _risk_units(entry: float, stop: float, initial_risk: float) -> float:
    return abs(entry - stop) / initial_risk


def _mark_to_market(plan: BacktestOrderPlan, close: float, open_allocation: float) -> float:
    if open_allocation <= 0:
        return 0.0
    r = (close - plan.entry) / plan.risk_per_unit if plan.direction == "bullish" else (plan.entry - close) / plan.risk_per_unit
    return open_allocation * plan.risk_amount * r

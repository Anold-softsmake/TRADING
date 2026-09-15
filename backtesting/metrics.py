from __future__ import annotations

from collections import defaultdict
from math import sqrt

import numpy as np

from .models import BacktestTrade


def calculate_metrics(trades: list[BacktestTrade], starting_equity: float) -> dict[str, float]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "average_r": 0.0,
            "max_drawdown": 0.0,
            "net_profit": 0.0,
        }

    pnls = np.array([trade.pnl for trade in trades], dtype=float)
    r_values = np.array([trade.r_multiple for trade in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(losses.sum()) if len(losses) else 0.0
    equity = starting_equity + np.cumsum(pnls)
    peaks = np.maximum.accumulate(np.insert(equity, 0, starting_equity))[1:]
    drawdowns = peaks - equity
    returns = pnls / starting_equity

    monthly = defaultdict(float)
    daily = defaultdict(float)
    for trade in trades:
        if hasattr(trade.exit_time, "strftime"):
            monthly[trade.exit_time.strftime("%Y-%m")] += trade.pnl
            daily[trade.exit_time.strftime("%Y-%m-%d")] += trade.pnl

    return {
        "total_trades": float(len(trades)),
        "win_rate": float(len(wins) / len(trades)),
        "loss_rate": float(len(losses) / len(trades)),
        "profit_factor": float(gross_profit / abs(gross_loss)) if gross_loss else 0.0,
        "expectancy": float(pnls.mean()),
        "average_r": float(r_values.mean()),
        "average_win": float(wins.mean()) if len(wins) else 0.0,
        "average_loss": float(losses.mean()) if len(losses) else 0.0,
        "max_drawdown": float(drawdowns.max()) if len(drawdowns) else 0.0,
        "max_consecutive_losses": float(_max_consecutive_losses(trades)),
        "sharpe_ratio": _ratio(returns, downside_only=False),
        "sortino_ratio": _ratio(returns, downside_only=True),
        "net_profit": float(pnls.sum()),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "average_trade_duration_bars": float(np.mean([trade.bars_held for trade in trades])),
        "tp1_hit_rate": _tp_hit_rate(trades, 0),
        "tp2_hit_rate": _tp_hit_rate(trades, 1),
        "tp3_hit_rate": _tp_hit_rate(trades, 2),
        "entry_2_frequency": float(sum(1 for trade in trades if trade.entry_model == "two_entry") / len(trades)),
        "entry_2_contribution": float(sum(trade.pnl for trade in trades if trade.entry_model == "two_entry")),
        "monthly_periods": float(len(monthly)),
        "daily_periods": float(len(daily)),
    }


def _max_consecutive_losses(trades: list[BacktestTrade]) -> int:
    max_streak = 0
    streak = 0
    for trade in trades:
        if trade.pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _tp_hit_rate(trades: list[BacktestTrade], index: int) -> float:
    eligible = [trade for trade in trades if len(trade.tp_hits) > index]
    if not eligible:
        return 0.0
    return float(sum(1 for trade in eligible if trade.tp_hits[index]) / len(eligible))


def _ratio(returns: np.ndarray, downside_only: bool) -> float:
    if len(returns) < 2:
        return 0.0
    sample = returns[returns < 0] if downside_only else returns
    if len(sample) < 2 or float(sample.std(ddof=1)) == 0.0:
        return 0.0
    return float(returns.mean() / sample.std(ddof=1) * sqrt(len(returns)))

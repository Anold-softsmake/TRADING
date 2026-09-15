from __future__ import annotations

import random

from .models import BacktestTrade


def bootstrap_equity_paths(
    trades: list[BacktestTrade],
    starting_equity: float,
    runs: int = 500,
    seed: int = 42,
) -> list[list[float]]:
    rng = random.Random(seed)
    pnls = [trade.pnl for trade in trades]
    paths: list[list[float]] = []
    if not pnls:
        return paths
    for _ in range(runs):
        equity = starting_equity
        path = [equity]
        for pnl in (rng.choice(pnls) for _ in pnls):
            equity += pnl
            path.append(equity)
        paths.append(path)
    return paths

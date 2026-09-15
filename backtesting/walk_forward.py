from __future__ import annotations

from typing import Any, Iterator

import pandas as pd

from .engine import HistoricalBacktestEngine
from .optimizer import _set_nested, grid_search


def rolling_windows(df: pd.DataFrame, train_bars: int, validation_bars: int, step_bars: int) -> Iterator[tuple[pd.DataFrame, pd.DataFrame]]:
    start = 0
    while start + train_bars + validation_bars <= len(df):
        train = df.iloc[start : start + train_bars].copy()
        validation = df.iloc[start + train_bars : start + train_bars + validation_bars].copy()
        yield train, validation
        start += step_bars


def walk_forward_optimize(
    df: pd.DataFrame,
    settings: dict[str, Any],
    parameter_grid: dict[str, list[Any]],
    train_bars: int,
    validation_bars: int,
    step_bars: int,
    objective: str = "profit_factor",
) -> dict[str, Any]:
    windows: list[dict[str, Any]] = []
    validation_metrics: list[dict[str, float]] = []
    for window_index, (train, validation) in enumerate(rolling_windows(df, train_bars, validation_bars, step_bars), start=1):
        ranked = grid_search(train, settings, parameter_grid, objective=objective)
        if not ranked:
            continue
        selected_settings = _apply(settings, ranked[0]["parameters"])
        validation_result = HistoricalBacktestEngine(selected_settings).run(validation)
        validation_metrics.append(validation_result.metrics)
        windows.append(
            {
                "window": window_index,
                "selected_parameters": ranked[0]["parameters"],
                "train_metrics": ranked[0]["metrics"],
                "validation_metrics": validation_result.metrics,
                "validation_rejected_signals": len(validation_result.rejected_signals),
            }
        )
    return {"windows": windows, "summary": _summarize_windows(validation_metrics, objective)}


def _apply(settings: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    from copy import deepcopy

    selected = deepcopy(settings)
    for key, value in parameters.items():
        _set_nested(selected, key, value)
    return selected


def _summarize_windows(metrics: list[dict[str, float]], objective: str) -> dict[str, float | str]:
    if not metrics:
        return {"status": "NO_WINDOWS"}
    objectives = [float(item.get(objective, 0.0)) for item in metrics]
    trades = [float(item.get("total_trades", 0.0)) for item in metrics]
    passing = sum(1 for value in objectives if value > 1.0) if objective == "profit_factor" else sum(1 for value in objectives if value > 0.0)
    return {
        "status": "WALK_FORWARD_COMPLETE",
        "windows": float(len(metrics)),
        "pass_rate": float(passing / len(metrics)),
        "average_objective": float(sum(objectives) / len(objectives)),
        "average_validation_trades": float(sum(trades) / len(trades)),
    }

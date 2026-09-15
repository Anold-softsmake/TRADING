from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from .engine import HistoricalBacktestEngine


def grid_search(
    m15: pd.DataFrame,
    base_settings: dict[str, Any],
    parameter_grid: dict[str, list[Any]],
    h1: pd.DataFrame | None = None,
    h4: pd.DataFrame | None = None,
    objective: str = "profit_factor",
) -> list[dict[str, Any]]:
    keys = list(parameter_grid.keys())
    results: list[dict[str, Any]] = []
    for values in product(*(parameter_grid[key] for key in keys)):
        settings = deepcopy(base_settings)
        for key, value in zip(keys, values):
            _set_nested(settings, key, value)
        result = HistoricalBacktestEngine(settings).run(m15, h1, h4)
        results.append(
            {
                "parameters": dict(zip(keys, values)),
                "metrics": result.metrics,
                "objective": float(result.metrics.get(objective, 0.0)),
                "rejected_signals": len(result.rejected_signals),
            }
        )
    return sorted(results, key=lambda item: item["objective"], reverse=True)


def default_phase3_grid() -> dict[str, list[Any]]:
    return {
        "confluence.minimum_score": [5, 7, 9],
        "sweep.require_displacement": [False, True],
        "entry_zone.reject_if_no_overlap": [False, True],
        "backtest.entry_location": ["zone_edge", "zone_midpoint", "deep_zone"],
        "backtest.profit_management": ["none", "move_to_breakeven_after_tp1"],
        "backtest.tp_r_multiples": [[2], [1, 2, 3]],
        "backtest.tp_allocations": [[1.0], [0.3, 0.3, 0.4]],
    }


def summarize_sensitivity(results: list[dict[str, Any]], objective: str = "profit_factor") -> dict[str, Any]:
    if not results:
        return {"status": "NO_RESULTS"}
    values = np.array([float(item["metrics"].get(objective, 0.0)) for item in results], dtype=float)
    mean = float(values.mean())
    std = float(values.std())
    best = float(values.max())
    worst = float(values.min())
    fragility = std / abs(mean) if mean else 0.0
    status = "ROBUST_CANDIDATE"
    if len(results) < 10:
        status = "INSUFFICIENT_VARIANTS"
    elif fragility > 1.0 or worst <= 0:
        status = "FRAGILE_OR_NO_EDGE"
    return {
        "status": status,
        "objective": objective,
        "variants": len(results),
        "mean": mean,
        "std": std,
        "best": best,
        "worst": worst,
        "fragility_ratio": float(fragility),
    }


def _set_nested(settings: dict[str, Any], dotted_key: str, value: Any) -> None:
    target = settings
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .engine import HistoricalBacktestEngine
from .models import BacktestResult
from .optimizer import _set_nested, grid_search
from .walk_forward import walk_forward_optimize


@dataclass(frozen=True)
class DataSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


@dataclass(frozen=True)
class OutOfSampleResult:
    selected_parameters: dict[str, Any]
    train_metrics: dict[str, float]
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float]
    robustness: dict[str, Any]
    train_result: BacktestResult
    validation_result: BacktestResult
    test_result: BacktestResult


def chronological_split(
    df: pd.DataFrame,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
) -> DataSplit:
    if not 0 < train_ratio < 1 or not 0 <= validation_ratio < 1 or train_ratio + validation_ratio >= 1:
        raise ValueError("Ratios must leave a non-empty test period.")
    train_end = int(len(df) * train_ratio)
    validation_end = int(len(df) * (train_ratio + validation_ratio))
    if train_end == 0 or validation_end <= train_end or validation_end >= len(df):
        raise ValueError("Not enough rows for train/validation/test split.")
    return DataSplit(
        df.iloc[:train_end].copy(),
        df.iloc[train_end:validation_end].copy(),
        df.iloc[validation_end:].copy(),
    )


def run_out_of_sample_validation(
    m15: pd.DataFrame,
    settings: dict[str, Any],
    parameter_grid: dict[str, list[Any]],
    objective: str = "profit_factor",
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
) -> OutOfSampleResult:
    split = chronological_split(m15, train_ratio, validation_ratio)
    train_ranked = grid_search(split.train, settings, parameter_grid, objective=objective)
    if not train_ranked:
        raise ValueError("Parameter grid produced no results.")

    selected_parameters = train_ranked[0]["parameters"]
    selected_settings = apply_parameters(settings, selected_parameters)
    train_result = HistoricalBacktestEngine(selected_settings).run(split.train)
    validation_result = HistoricalBacktestEngine(selected_settings).run(split.validation)
    test_result = HistoricalBacktestEngine(selected_settings).run(split.test)

    robustness = classify_robustness(
        train_result.metrics,
        validation_result.metrics,
        test_result.metrics,
        objective=objective,
    )
    return OutOfSampleResult(
        selected_parameters,
        train_result.metrics,
        validation_result.metrics,
        test_result.metrics,
        robustness,
        train_result,
        validation_result,
        test_result,
    )


def apply_parameters(settings: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    selected = deepcopy(settings)
    for key, value in parameters.items():
        _set_nested(selected, key, value)
    return selected


def classify_robustness(
    train_metrics: dict[str, float],
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
    objective: str = "profit_factor",
    min_test_trades: int = 30,
    max_objective_decay: float = 0.5,
) -> dict[str, Any]:
    train_objective = float(train_metrics.get(objective, 0.0))
    validation_objective = float(validation_metrics.get(objective, 0.0))
    test_objective = float(test_metrics.get(objective, 0.0))
    test_trades = int(test_metrics.get("total_trades", 0))
    decay = 0.0 if train_objective == 0 else (train_objective - test_objective) / abs(train_objective)
    reasons: list[str] = []

    if test_trades < min_test_trades:
        reasons.append("Insufficient test trades for statistical confidence.")
    if test_objective <= 1.0 and objective == "profit_factor":
        reasons.append("Out-of-sample profit factor is not above breakeven.")
    if validation_objective <= 0:
        reasons.append("Validation objective is non-positive.")
    if decay > max_objective_decay:
        reasons.append("Objective decayed too much from train to test.")

    status = "PASS_ROBUSTNESS_CHECKS" if not reasons else "FAIL_ROBUSTNESS_CHECKS"
    return {
        "status": status,
        "objective": objective,
        "train_objective": train_objective,
        "validation_objective": validation_objective,
        "test_objective": test_objective,
        "objective_decay": float(decay),
        "test_trades": float(test_trades),
        "reasons": reasons,
    }


def run_walk_forward_validation(
    m15: pd.DataFrame,
    settings: dict[str, Any],
    parameter_grid: dict[str, list[Any]],
    train_bars: int,
    validation_bars: int,
    step_bars: int,
    objective: str = "profit_factor",
) -> dict[str, Any]:
    return walk_forward_optimize(m15, settings, parameter_grid, train_bars, validation_bars, step_bars, objective)

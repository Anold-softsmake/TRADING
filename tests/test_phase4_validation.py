from __future__ import annotations

from backtesting.out_of_sample import (
    apply_parameters,
    chronological_split,
    classify_robustness,
    run_out_of_sample_validation,
    run_walk_forward_validation,
)
from tests.test_phase2_backtesting import backtest_settings, candles


def sample_data():
    rows = []
    base = 100.0
    for index in range(80):
        open_price = base + (index % 7)
        high = open_price + 2 + (index % 3)
        low = open_price - 2 - (index % 2)
        close = open_price + (1 if index % 4 else -1)
        rows.append((open_price, high, low, close))
    rows[10] = (105, 106, 98, 99)
    rows[11] = (99, 100, 95, 99)
    rows[12] = (99, 104, 94, 103)
    rows[13] = (103, 112, 102, 111)
    rows[14] = (111, 116, 108, 114)
    return candles(rows)


def test_chronological_split_preserves_order() -> None:
    df = sample_data()

    split = chronological_split(df, train_ratio=0.5, validation_ratio=0.25)

    assert len(split.train) == 40
    assert len(split.validation) == 20
    assert len(split.test) == 20
    assert split.train["timestamp"].max() < split.validation["timestamp"].min()
    assert split.validation["timestamp"].max() < split.test["timestamp"].min()


def test_apply_parameters_updates_nested_settings() -> None:
    settings = backtest_settings()

    updated = apply_parameters(settings, {"confluence.minimum_score": 3, "backtest.entry_location": "deep_zone"})

    assert updated["confluence"]["minimum_score"] == 3
    assert updated["backtest"]["entry_location"] == "deep_zone"
    assert settings["backtest"]["entry_location"] == "zone_midpoint"


def test_robustness_flags_insufficient_test_sample() -> None:
    robustness = classify_robustness(
        {"profit_factor": 2.0, "total_trades": 100},
        {"profit_factor": 1.5, "total_trades": 40},
        {"profit_factor": 0.9, "total_trades": 3},
    )

    assert robustness["status"] == "FAIL_ROBUSTNESS_CHECKS"
    assert robustness["reasons"]


def test_out_of_sample_validation_returns_all_splits() -> None:
    settings = backtest_settings()
    grid = {"confluence.minimum_score": [1, 3]}

    result = run_out_of_sample_validation(sample_data(), settings, grid, train_ratio=0.5, validation_ratio=0.25)

    assert result.selected_parameters
    assert "total_trades" in result.train_metrics
    assert "status" in result.robustness


def test_walk_forward_validation_summarizes_windows() -> None:
    settings = backtest_settings()
    grid = {"confluence.minimum_score": [1, 3]}

    result = run_walk_forward_validation(sample_data(), settings, grid, train_bars=30, validation_bars=15, step_bars=15)

    assert result["summary"]["status"] == "WALK_FORWARD_COMPLETE"
    assert result["windows"]

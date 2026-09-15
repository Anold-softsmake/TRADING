from __future__ import annotations

import pandas as pd

from backtesting.comparisons import compare_core_variants
from backtesting.optimizer import grid_search, summarize_sensitivity
from strategies.sessions import current_session, session_filter_pass
from tests.test_phase2_backtesting import backtest_settings, candles


def sample_data() -> pd.DataFrame:
    return candles(
        [
            (100, 101, 99, 100),
            (100, 102, 98, 101),
            (101, 103, 97, 102),
            (102, 102, 99, 100),
            (100, 101, 98, 99),
            (99, 100, 96, 99),
            (99, 102, 95, 101),
            (101, 108, 100, 107),
            (107, 109, 104, 108),
            (108, 108, 100, 103),
            (103, 115, 102, 113),
            (113, 118, 112, 117),
        ]
    )


def test_grid_search_returns_ranked_results() -> None:
    settings = backtest_settings()
    grid = {
        "confluence.minimum_score": [1, 10],
        "backtest.entry_location": ["zone_midpoint", "deep_zone"],
    }

    results = grid_search(sample_data(), settings, grid)

    assert len(results) == 4
    assert results == sorted(results, key=lambda item: item["objective"], reverse=True)
    assert "parameters" in results[0]


def test_sensitivity_summary_flags_result_set() -> None:
    results = [
        {"metrics": {"profit_factor": 2.0}},
        {"metrics": {"profit_factor": 1.8}},
        {"metrics": {"profit_factor": 2.2}},
    ]

    summary = summarize_sensitivity(results)

    assert summary["variants"] == 3
    assert summary["status"] in {"INSUFFICIENT_VARIANTS", "ROBUST_CANDIDATE", "FRAGILE_OR_NO_EDGE"}


def test_core_variant_comparisons_include_expected_labels() -> None:
    results = compare_core_variants(sample_data(), backtest_settings())

    assert "single_entry" in results
    assert "tp1_tp2_tp3" in results
    assert "ob_fvg_overlap_required" in results


def test_session_filter_uses_configurable_eat_windows() -> None:
    settings = {
        "sessions": {
            "enabled": True,
            "timezone_display": "Africa/Nairobi",
            "windows": [{"name": "london", "start": "10:00", "end": "19:00", "enabled": True}],
        }
    }
    timestamp = pd.Timestamp("2026-01-01 11:00")

    assert session_filter_pass(timestamp, settings)
    assert current_session(timestamp, settings) == "london"

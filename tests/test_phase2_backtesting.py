from __future__ import annotations

import pandas as pd

from backtesting.engine import HistoricalBacktestEngine
from backtesting.metrics import calculate_metrics
from backtesting.models import BacktestTrade


def candles(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01 00:00", periods=len(rows), freq="15min"),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
        }
    )


def backtest_settings() -> dict:
    return {
        "symbol": "XAUUSD",
        "timeframes": {"execution": "M15"},
        "swing": {"left_bars": 1, "right_bars": 1, "min_distance_points": 0, "use_wicks": True},
        "structure": {
            "min_break_points": 0,
            "break_requires_close": True,
            "use_body_close": True,
            "displacement_required_for_mss": False,
            "displacement_atr_multiple": 1.0,
        },
        "liquidity": {
            "equal_high_tolerance_points": 1,
            "equal_low_tolerance_points": 1,
            "min_touches": 2,
            "max_age_bars": 100,
            "require_unmitigated": False,
        },
        "sweep": {"min_penetration_points": 1, "max_confirmation_bars": 2, "require_close_back_inside": True, "require_displacement": False},
        "order_block": {
            "require_displacement": False,
            "require_structure_break": True,
            "prefer_after_sweep": False,
            "max_cluster_candles": 2,
            "max_touches": 20,
            "freshness_max_bars": 100,
            "use_body_only": False,
        },
        "fvg": {"min_size_points": 1, "require_displacement": False, "mitigation_mode": "wick_touch", "max_retests": 2},
        "confluence": {"minimum_score": 1},
        "entry_zone": {"require_ob_or_fvg": False, "prefer_ob_fvg_overlap": True, "fallback_to_ob": True, "fallback_to_fvg": True},
        "invalidation": {"buffer_points": 1, "method": "beyond_sweep_extreme"},
        "risk": {
            "starting_equity": 10000,
            "risk_per_setup_pct": 1,
            "max_daily_loss_pct": 5,
            "max_weekly_loss_pct": 10,
            "max_trades_day": 3,
            "max_consecutive_losses": 3,
        },
        "backtest": {
            "entry_model": "single_entry",
            "entry_location": "zone_midpoint",
            "max_entry_wait_bars": 12,
            "max_hold_bars": 20,
            "tp_r_multiples": [1, 2, 3],
            "tp_allocations": [0.3, 0.3, 0.4],
            "profit_management": "move_to_breakeven_after_tp1",
            "conservative_same_candle": True,
        },
    }


def test_metrics_calculate_core_values() -> None:
    trades = [
        BacktestTrade("bullish", "s", "e", "x", 100, 99, (101, 102, 103), (0.3, 0.3, 0.4), "tp3", 200, 2, 100, 4, (True, True, True), "single_entry", 8),
        BacktestTrade("bullish", "s", "e", "x", 100, 99, (101, 102, 103), (0.3, 0.3, 0.4), "stop_loss", -100, -1, 100, 2, (False, False, False), "single_entry", 8),
    ]

    metrics = calculate_metrics(trades, 10000)

    assert metrics["total_trades"] == 2
    assert metrics["win_rate"] == 0.5
    assert metrics["profit_factor"] == 2
    assert metrics["net_profit"] == 100


def test_backtester_runs_without_live_execution() -> None:
    df = candles(
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

    result = HistoricalBacktestEngine(backtest_settings()).run(df)

    assert isinstance(result.trades, list)
    assert "total_trades" in result.metrics
    assert result.equity_curve


def test_risk_limit_rejects_after_one_trade_per_day() -> None:
    settings = backtest_settings()
    settings["risk"]["max_trades_day"] = 1
    df = candles(
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
            (117, 118, 110, 111),
            (111, 116, 109, 115),
            (115, 119, 114, 118),
        ]
    )

    result = HistoricalBacktestEngine(settings).run(df)

    assert result.metrics["total_trades"] <= 1

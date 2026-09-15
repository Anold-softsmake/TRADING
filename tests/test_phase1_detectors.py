from __future__ import annotations

import pandas as pd

from strategies.amin_xauusd_strategy import AminXauusdPhase1Strategy
from strategies.fair_value_gaps import detect_fair_value_gaps
from strategies.liquidity import identify_liquidity_pools
from strategies.liquidity_sweep import detect_liquidity_sweeps
from strategies.market_structure import analyze_market_structure, detect_swings
from strategies.order_blocks import detect_order_blocks


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


def test_swings_are_confirmed_after_right_bars() -> None:
    df = candles(
        [
            (100, 101, 99, 100),
            (100, 103, 99, 102),
            (102, 106, 101, 105),
            (105, 104, 100, 101),
            (101, 102, 98, 99),
            (99, 100, 97, 98),
        ]
    )

    swings = detect_swings(df, left_bars=2, right_bars=2)

    assert any(swing.kind == "high" and swing.index == 2 and swing.confirmed_index == 4 for swing in swings)


def test_liquidity_sweep_requires_penetration_and_close_back_inside() -> None:
    df = candles(
        [
            (100, 101, 99, 100),
            (100, 102, 98, 101),
            (101, 103, 97, 102),
            (102, 102, 99, 100),
            (100, 101, 98, 99),
            (99, 100, 96, 99),
            (99, 102, 95, 101),
            (101, 105, 100, 104),
        ]
    )
    swings = detect_swings(df, left_bars=1, right_bars=1)
    pools = identify_liquidity_pools(df, swings, max_age_bars=100)

    sweeps = detect_liquidity_sweeps(
        df,
        pools,
        min_penetration_points=1,
        max_confirmation_bars=2,
        require_displacement=False,
    )

    assert any(sweep.direction == "bullish" and sweep.confirmation_index >= sweep.sweep_index for sweep in sweeps)


def test_fvg_detection_uses_three_candle_gap() -> None:
    df = candles(
        [
            (100, 101, 99, 100),
            (100, 106, 100, 105),
            (106, 109, 104, 108),
            (108, 110, 107, 109),
        ]
    )

    fvgs = detect_fair_value_gaps(df, min_size_points=2, require_displacement=False)

    assert any(fvg.direction == "bullish" and fvg.low == 101 and fvg.high == 104 for fvg in fvgs)


def test_order_block_before_bullish_structure_break() -> None:
    df = candles(
        [
            (100, 101, 99, 100),
            (100, 104, 99, 103),
            (103, 105, 101, 104),
            (104, 103, 98, 99),
            (99, 100, 97, 98),
            (98, 112, 98, 111),
        ]
    )
    swings = detect_swings(df, left_bars=1, right_bars=1)
    structure = analyze_market_structure(df, swings=swings, min_break_points=0, displacement_required_for_mss=False)

    blocks = detect_order_blocks(
        df,
        structure.events,
        require_displacement=False,
        max_cluster_candles=2,
        freshness_max_bars=100,
        max_touches=10,
    )

    assert any(block.direction == "bullish" and block.low <= 97 and block.high >= 100 for block in blocks)


def test_strategy_returns_structured_decision() -> None:
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
        ]
    )
    settings = {
        "symbol": "XAUUSD",
        "timeframes": {"execution": "M15"},
        "swing": {"left_bars": 1, "right_bars": 1, "min_distance_points": 0, "use_wicks": True},
        "structure": {
            "min_break_points": 0,
            "break_requires_close": True,
            "displacement_required_for_mss": False,
            "displacement_atr_multiple": 1.0,
        },
        "liquidity": {"equal_high_tolerance_points": 1, "equal_low_tolerance_points": 1, "min_touches": 2, "max_age_bars": 100},
        "sweep": {"min_penetration_points": 1, "max_confirmation_bars": 2, "require_close_back_inside": True, "require_displacement": False},
        "order_block": {"require_displacement": False, "require_structure_break": True, "max_cluster_candles": 2, "max_touches": 10, "freshness_max_bars": 100},
        "fvg": {"min_size_points": 1, "require_displacement": False, "max_retests": 2},
        "confluence": {"minimum_score": 1},
        "entry_zone": {"require_ob_or_fvg": False},
        "invalidation": {"buffer_points": 1, "method": "beyond_sweep_extreme"},
    }

    decision = AminXauusdPhase1Strategy(settings).latest_decision(df)

    assert decision.symbol == "XAUUSD"
    assert decision.decision in {"TRADE_CANDIDATE", "NO SETUP"}
    assert decision.max_score > 0

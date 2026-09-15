from __future__ import annotations

import pandas as pd

from .models import LiquidityPool, LiquiditySweep
from .utils import atr, validate_ohlc


def detect_liquidity_sweeps(
    candles: pd.DataFrame,
    pools: list[LiquidityPool],
    min_penetration_points: float = 30,
    max_confirmation_bars: int = 3,
    require_close_back_inside: bool = True,
    require_displacement: bool = True,
    displacement_atr_multiple: float = 1.2,
) -> list[LiquiditySweep]:
    df = validate_ohlc(candles)
    average_range = atr(df)
    sweeps: list[LiquiditySweep] = []

    for pool in pools:
        for index in range(pool.confirmed_index + 1, len(df)):
            row = df.iloc[index]
            if pool.kind == "sell_side":
                penetration = pool.price_level - float(row["low"])
                swept = penetration >= min_penetration_points
                close_inside = float(row["close"]) > pool.price_level
                direction = "bullish"
                extreme = float(row["low"])
            else:
                penetration = float(row["high"]) - pool.price_level
                swept = penetration >= min_penetration_points
                close_inside = float(row["close"]) < pool.price_level
                direction = "bearish"
                extreme = float(row["high"])

            if not swept:
                continue

            confirmation_index = _confirmation_index(
                df,
                index,
                pool,
                direction,
                max_confirmation_bars,
                close_inside,
                require_close_back_inside,
            )
            if confirmation_index is None:
                break

            displacement = _has_following_displacement(df, confirmation_index, direction, average_range, displacement_atr_multiple, max_confirmation_bars)
            if require_displacement and not displacement:
                break

            confirmation = df.iloc[confirmation_index]
            sweeps.append(
                LiquiditySweep(
                    direction,
                    pool.price_level,
                    pool.source,
                    extreme,
                    index,
                    row["timestamp"],
                    confirmation_index,
                    confirmation["timestamp"],
                    penetration,
                    float(confirmation["close"]),
                    displacement,
                )
            )
            break

    return sorted(sweeps, key=lambda sweep: sweep.confirmation_index)


def _confirmation_index(
    df: pd.DataFrame,
    start_index: int,
    pool: LiquidityPool,
    direction: str,
    max_confirmation_bars: int,
    current_close_inside: bool,
    require_close_back_inside: bool,
) -> int | None:
    if current_close_inside or not require_close_back_inside:
        return start_index
    end = min(len(df), start_index + max_confirmation_bars + 1)
    for index in range(start_index + 1, end):
        close = float(df.at[index, "close"])
        if direction == "bullish" and close > pool.price_level:
            return index
        if direction == "bearish" and close < pool.price_level:
            return index
    return None


def _has_following_displacement(
    df: pd.DataFrame,
    start_index: int,
    direction: str,
    average_range: pd.Series,
    multiple: float,
    max_bars: int,
) -> bool:
    end = min(len(df), start_index + max_bars + 1)
    for index in range(start_index, end):
        row = df.iloc[index]
        body = abs(float(row["close"]) - float(row["open"]))
        directional = float(row["close"]) > float(row["open"]) if direction == "bullish" else float(row["close"]) < float(row["open"])
        if directional and body >= float(average_range.iloc[index]) * multiple:
            return True
    return False

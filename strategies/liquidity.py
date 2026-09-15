from __future__ import annotations

import pandas as pd

from .models import LiquidityPool, SwingPoint
from .utils import validate_ohlc


def identify_liquidity_pools(
    candles: pd.DataFrame,
    swings: list[SwingPoint],
    equal_high_tolerance_points: float = 80,
    equal_low_tolerance_points: float = 80,
    min_touches: int = 2,
    max_age_bars: int = 500,
    require_unmitigated: bool = False,
) -> list[LiquidityPool]:
    df = validate_ohlc(candles)
    pools: list[LiquidityPool] = []

    for swing in swings:
        if len(df) - swing.confirmed_index > max_age_bars:
            continue
        kind = "buy_side" if swing.kind == "high" else "sell_side"
        source = "swing_high" if swing.kind == "high" else "swing_low"
        pools.append(
            LiquidityPool(
                kind,
                source,
                swing.price,
                swing.index,
                swing.timestamp,
                swing.confirmed_index,
                swing.confirmed_time,
                1,
                _is_swept(df, swing),
            )
        )

    pools.extend(_equal_level_pools(df, swings, "high", equal_high_tolerance_points, min_touches, max_age_bars))
    pools.extend(_equal_level_pools(df, swings, "low", equal_low_tolerance_points, min_touches, max_age_bars))
    pools.extend(_previous_day_pools(df))
    if require_unmitigated:
        pools = [pool for pool in pools if not pool.swept]
    return sorted(pools, key=lambda pool: pool.confirmed_index)


def known_pools(pools: list[LiquidityPool], decision_index: int, require_unswept: bool = False) -> list[LiquidityPool]:
    result = [pool for pool in pools if pool.confirmed_index <= decision_index]
    if require_unswept:
        result = [pool for pool in result if not pool.swept]
    return result


def _equal_level_pools(
    df: pd.DataFrame,
    swings: list[SwingPoint],
    swing_kind: str,
    tolerance: float,
    min_touches: int,
    max_age_bars: int,
) -> list[LiquidityPool]:
    selected = [s for s in swings if s.kind == swing_kind and len(df) - s.confirmed_index <= max_age_bars]
    pools: list[LiquidityPool] = []
    used: set[int] = set()

    for index, swing in enumerate(selected):
        if index in used:
            continue
        cluster = [swing]
        for other_index, other in enumerate(selected[index + 1 :], start=index + 1):
            if abs(other.price - swing.price) <= tolerance:
                cluster.append(other)
                used.add(other_index)
        if len(cluster) >= min_touches:
            price = sum(item.price for item in cluster) / len(cluster)
            confirmed = max(cluster, key=lambda item: item.confirmed_index)
            kind = "buy_side" if swing_kind == "high" else "sell_side"
            source = "equal_high" if swing_kind == "high" else "equal_low"
            pools.append(
                LiquidityPool(
                    kind,
                    source,
                    price,
                    cluster[0].index,
                    cluster[0].timestamp,
                    confirmed.confirmed_index,
                    confirmed.confirmed_time,
                    len(cluster),
                    False,
                )
            )
    return pools


def _previous_day_pools(df: pd.DataFrame) -> list[LiquidityPool]:
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        return []
    pools: list[LiquidityPool] = []
    work = df.copy()
    work["date"] = work["timestamp"].dt.date
    grouped = work.groupby("date", sort=True)
    previous = None
    for _, group in grouped:
        if previous is not None:
            confirmed_index = int(group.index.min())
            confirmed_time = df.at[confirmed_index, "timestamp"]
            high_index = int(previous["high"].idxmax())
            low_index = int(previous["low"].idxmin())
            pools.append(
                LiquidityPool("buy_side", "previous_day_high", float(previous["high"].max()), high_index, df.at[high_index, "timestamp"], confirmed_index, confirmed_time)
            )
            pools.append(
                LiquidityPool("sell_side", "previous_day_low", float(previous["low"].min()), low_index, df.at[low_index, "timestamp"], confirmed_index, confirmed_time)
            )
        previous = group
    return pools


def _is_swept(df: pd.DataFrame, swing: SwingPoint) -> bool:
    future = df.iloc[swing.confirmed_index + 1 :]
    if future.empty:
        return False
    if swing.kind == "high":
        return bool((future["high"] > swing.price).any())
    return bool((future["low"] < swing.price).any())

from __future__ import annotations

import pandas as pd

from .models import LiquiditySweep, OrderBlock, StructureEvent
from .utils import atr, is_bearish, is_bullish, validate_ohlc


def detect_order_blocks(
    candles: pd.DataFrame,
    structure_events: list[StructureEvent],
    sweeps: list[LiquiditySweep] | None = None,
    max_cluster_candles: int = 3,
    require_displacement: bool = True,
    displacement_atr_multiple: float = 1.2,
    require_structure_break: bool = True,
    prefer_after_sweep: bool = True,
    max_touches: int = 1,
    freshness_max_bars: int = 100,
    use_body_only: bool = False,
) -> list[OrderBlock]:
    df = validate_ohlc(candles)
    sweeps = sweeps or []
    average_range = atr(df)
    blocks: list[OrderBlock] = []

    events = structure_events if require_structure_break else _synthetic_displacement_events(df, average_range, displacement_atr_multiple)
    for event in events:
        direction = "bullish" if event.direction == "bullish" else "bearish"
        if require_displacement and not _event_has_displacement(df, event.break_index, direction, average_range, displacement_atr_multiple):
            continue

        cluster = _find_cluster_before_event(df, event.break_index, direction, max_cluster_candles)
        if not cluster:
            continue

        start, end = cluster[0], cluster[-1]
        zone = df.iloc[start : end + 1]
        if use_body_only:
            high = float(zone[["open", "close"]].max(axis=1).max())
            low = float(zone[["open", "close"]].min(axis=1).min())
        else:
            high = float(zone["high"].max())
            low = float(zone["low"].min())

        touches = _count_touches(df, event.break_index + 1, low, high)
        if touches > max_touches:
            continue
        if len(df) - event.confirmation_index > freshness_max_bars:
            continue

        after_sweep = any(s.confirmation_index <= event.break_index and s.direction == direction for s in sweeps)
        if prefer_after_sweep and sweeps and not after_sweep:
            continue
        blocks.append(
            OrderBlock(
                direction,
                low,
                high,
                start,
                end,
                df.at[end, "timestamp"],
                event.confirmation_index,
                event.confirmation_time,
                event.event_type,
                after_sweep,
                touches,
            )
        )

    return sorted(blocks, key=lambda block: block.confirmed_index)


def _find_cluster_before_event(df: pd.DataFrame, event_index: int, direction: str, max_cluster_candles: int) -> list[int]:
    wanted = is_bearish if direction == "bullish" else is_bullish
    cluster: list[int] = []
    for index in range(event_index - 1, max(-1, event_index - max_cluster_candles - 5), -1):
        if index < 0:
            break
        if wanted(df, index):
            cluster.insert(0, index)
            if len(cluster) >= max_cluster_candles:
                break
        elif cluster:
            break
    return cluster


def _event_has_displacement(df: pd.DataFrame, index: int, direction: str, average_range: pd.Series, multiple: float) -> bool:
    row = df.iloc[index]
    body = abs(float(row["close"]) - float(row["open"]))
    directional = float(row["close"]) > float(row["open"]) if direction == "bullish" else float(row["close"]) < float(row["open"])
    return directional and body >= float(average_range.iloc[index]) * multiple


def _count_touches(df: pd.DataFrame, start_index: int, low: float, high: float) -> int:
    touches = 0
    for index in range(start_index, len(df)):
        if float(df.at[index, "low"]) <= high and float(df.at[index, "high"]) >= low:
            touches += 1
    return touches


def _synthetic_displacement_events(df: pd.DataFrame, average_range: pd.Series, multiple: float) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    for index in range(1, len(df)):
        row = df.iloc[index]
        body = abs(float(row["close"]) - float(row["open"]))
        if body < float(average_range.iloc[index]) * multiple:
            continue
        direction = "bullish" if float(row["close"]) > float(row["open"]) else "bearish"
        events.append(StructureEvent("DISPLACEMENT", direction, float(row["close"]), index, row["timestamp"], index, row["timestamp"], "Neutral", "Neutral"))
    return events

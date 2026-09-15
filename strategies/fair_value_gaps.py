from __future__ import annotations

import pandas as pd

from .models import FairValueGap, StructureEvent
from .utils import atr, validate_ohlc


def detect_fair_value_gaps(
    candles: pd.DataFrame,
    structure_events: list[StructureEvent] | None = None,
    min_size_points: float = 30,
    require_displacement: bool = True,
    displacement_atr_multiple: float = 1.2,
    mitigation_mode: str = "wick_touch",
    max_retests: int = 2,
) -> list[FairValueGap]:
    df = validate_ohlc(candles)
    events = structure_events or []
    average_range = atr(df)
    fvgs: list[FairValueGap] = []

    for index in range(2, len(df)):
        candle_1 = df.iloc[index - 2]
        candle_2 = df.iloc[index - 1]
        candle_3 = df.iloc[index]
        direction = None
        low = high = 0.0

        if float(candle_1["high"]) < float(candle_3["low"]):
            direction = "bullish"
            low = float(candle_1["high"])
            high = float(candle_3["low"])
        elif float(candle_1["low"]) > float(candle_3["high"]):
            direction = "bearish"
            low = float(candle_3["high"])
            high = float(candle_1["low"])

        if not direction:
            continue

        size = high - low
        if size < min_size_points:
            continue
        if require_displacement and not _middle_candle_displaces(df, index - 1, direction, average_range, displacement_atr_multiple):
            continue

        retests, mitigation_time = _retests(df, index + 1, low, high, max_retests)
        associated = _associated_event(events, index, direction)
        fvgs.append(
            FairValueGap(
                direction,
                low,
                high,
                index,
                candle_3["timestamp"],
                size,
                mitigation_time is not None,
                mitigation_time,
                retests,
                associated,
            )
        )

    return sorted(fvgs, key=lambda fvg: fvg.formation_index)


def _middle_candle_displaces(df: pd.DataFrame, index: int, direction: str, average_range: pd.Series, multiple: float) -> bool:
    row = df.iloc[index]
    body = abs(float(row["close"]) - float(row["open"]))
    directional = float(row["close"]) > float(row["open"]) if direction == "bullish" else float(row["close"]) < float(row["open"])
    return directional and body >= float(average_range.iloc[index]) * multiple


def _retests(df: pd.DataFrame, start_index: int, low: float, high: float, max_retests: int) -> tuple[int, object | None]:
    retests = 0
    mitigation_time = None
    for index in range(start_index, len(df)):
        touched = float(df.at[index, "low"]) <= high and float(df.at[index, "high"]) >= low
        if touched:
            retests += 1
            mitigation_time = df.at[index, "timestamp"]
            if retests >= max_retests:
                break
    return retests, mitigation_time


def _associated_event(events: list[StructureEvent], index: int, direction: str) -> str | None:
    for event in reversed(events):
        if event.direction == direction and event.confirmation_index <= index:
            return event.event_type
    return None

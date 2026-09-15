from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .models import StructureEvent, SwingPoint
from .utils import atr, validate_ohlc


@dataclass(frozen=True)
class StructureState:
    bias: str
    labels: dict[int, str]
    swings: list[SwingPoint]
    events: list[StructureEvent]


def detect_swings(
    candles: pd.DataFrame,
    left_bars: int = 3,
    right_bars: int = 3,
    min_distance_points: float = 0,
    use_wicks: bool = True,
) -> list[SwingPoint]:
    df = validate_ohlc(candles)
    high_source = df["high"] if use_wicks else df[["open", "close"]].max(axis=1)
    low_source = df["low"] if use_wicks else df[["open", "close"]].min(axis=1)
    swings: list[SwingPoint] = []

    for index in range(left_bars, len(df) - right_bars):
        high = float(high_source.iloc[index])
        low = float(low_source.iloc[index])
        left_highs = high_source.iloc[index - left_bars : index]
        right_highs = high_source.iloc[index + 1 : index + right_bars + 1]
        left_lows = low_source.iloc[index - left_bars : index]
        right_lows = low_source.iloc[index + 1 : index + right_bars + 1]

        if high > float(left_highs.max()) and high > float(right_highs.max()):
            if _far_enough(swings, "high", high, min_distance_points):
                swings.append(
                    SwingPoint(
                        "high",
                        index,
                        df.at[index, "timestamp"],
                        high,
                        index + right_bars,
                        df.at[index + right_bars, "timestamp"],
                    )
                )

        if low < float(left_lows.min()) and low < float(right_lows.min()):
            if _far_enough(swings, "low", low, min_distance_points):
                swings.append(
                    SwingPoint(
                        "low",
                        index,
                        df.at[index, "timestamp"],
                        low,
                        index + right_bars,
                        df.at[index + right_bars, "timestamp"],
                    )
                )

    return sorted(swings, key=lambda swing: (swing.confirmed_index, swing.index))


def analyze_market_structure(
    candles: pd.DataFrame,
    swings: list[SwingPoint] | None = None,
    min_break_points: float = 0,
    break_requires_close: bool = True,
    use_body_close: bool = True,
    displacement_required_for_mss: bool = True,
    displacement_atr_multiple: float = 1.2,
) -> StructureState:
    df = validate_ohlc(candles)
    swings = swings or detect_swings(df)
    labels = label_swings(swings)
    events: list[StructureEvent] = []
    current_bias = "Neutral"
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    average_range = atr(df)

    for index, row in df.iterrows():
        known_swings = [s for s in swings if s.confirmed_index <= index]
        known_highs = [s for s in known_swings if s.kind == "high"]
        known_lows = [s for s in known_swings if s.kind == "low"]
        if known_highs:
            last_high = known_highs[-1]
        if known_lows:
            last_low = known_lows[-1]

        break_price_up = float(row["close"] if break_requires_close else row["high"])
        break_price_down = float(row["close"] if break_requires_close else row["low"])

        if last_high and break_price_up > last_high.price + min_break_points:
            prior = current_bias
            event_type = "BOS" if prior in ("Bullish", "Neutral") else "CHoCH"
            new_bias = "Bullish"
            if event_type == "CHoCH" and _has_displacement(df, index, "bullish", average_range, displacement_atr_multiple):
                event_type = "MSS" if displacement_required_for_mss else "CHoCH"
            events.append(_structure_event(event_type, "bullish", last_high.price, index, row["timestamp"], prior, new_bias))
            current_bias = new_bias

        if last_low and break_price_down < last_low.price - min_break_points:
            prior = current_bias
            event_type = "BOS" if prior in ("Bearish", "Neutral") else "CHoCH"
            new_bias = "Bearish"
            if event_type == "CHoCH" and _has_displacement(df, index, "bearish", average_range, displacement_atr_multiple):
                event_type = "MSS" if displacement_required_for_mss else "CHoCH"
            events.append(_structure_event(event_type, "bearish", last_low.price, index, row["timestamp"], prior, new_bias))
            current_bias = new_bias

    if labels:
        recent = list(labels.values())[-4:]
        if recent.count("HH") and recent.count("HL"):
            current_bias = "Bullish"
        if recent.count("LH") and recent.count("LL"):
            current_bias = "Bearish"

    return StructureState(current_bias, labels, swings, events)


def label_swings(swings: list[SwingPoint]) -> dict[int, str]:
    labels: dict[int, str] = {}
    previous_high: SwingPoint | None = None
    previous_low: SwingPoint | None = None
    for swing in sorted(swings, key=lambda s: s.confirmed_index):
        if swing.kind == "high":
            labels[swing.index] = "HH" if previous_high and swing.price > previous_high.price else "LH"
            previous_high = swing
        else:
            labels[swing.index] = "HL" if previous_low and swing.price > previous_low.price else "LL"
            previous_low = swing
    return labels


def _far_enough(swings: list[SwingPoint], kind: str, price: float, min_distance_points: float) -> bool:
    same_kind = [s for s in swings if s.kind == kind]
    if not same_kind or min_distance_points <= 0:
        return True
    return abs(price - same_kind[-1].price) >= min_distance_points


def _has_displacement(
    df: pd.DataFrame,
    index: int,
    direction: str,
    average_range: pd.Series,
    multiple: float,
) -> bool:
    row = df.iloc[index]
    body = abs(float(row["close"]) - float(row["open"]))
    directional = float(row["close"]) > float(row["open"]) if direction == "bullish" else float(row["close"]) < float(row["open"])
    return directional and body >= float(average_range.iloc[index]) * multiple


def _structure_event(
    event_type: str,
    direction: str,
    broken_level: float,
    index: int,
    timestamp: object,
    prior: str,
    new: str,
) -> StructureEvent:
    return StructureEvent(event_type, direction, broken_level, index, timestamp, index, timestamp, prior, new)

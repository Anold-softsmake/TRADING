from __future__ import annotations

from typing import Iterable, TypeVar

import pandas as pd


REQUIRED_OHLC = ("timestamp", "open", "high", "low", "close")


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_OHLC if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {', '.join(missing)}")
    result = df.copy()
    result = result.sort_values("timestamp").reset_index(drop=True)
    return result


def true_range(df: pd.DataFrame) -> pd.Series:
    previous_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).rolling(period, min_periods=1).mean()


def candle_body(df: pd.DataFrame, index: int) -> float:
    row = df.iloc[index]
    return abs(float(row["close"]) - float(row["open"]))


def is_bullish(df: pd.DataFrame, index: int) -> bool:
    row = df.iloc[index]
    return float(row["close"]) > float(row["open"])


def is_bearish(df: pd.DataFrame, index: int) -> bool:
    row = df.iloc[index]
    return float(row["close"]) < float(row["open"])


T = TypeVar("T")


def latest_known(items: Iterable[T], decision_index: int) -> T | None:
    known = [item for item in items if getattr(item, "confirmed_index", -1) <= decision_index]
    return known[-1] if known else None

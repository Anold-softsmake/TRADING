from __future__ import annotations


def first_take_profit(entry: float, stop_loss: float, direction: str, r_multiple: float = 1.0) -> float:
    risk = abs(entry - stop_loss)
    if risk <= 0:
        raise ValueError("Entry and stop loss must be separated by positive risk.")
    if direction == "bearish":
        return entry - risk * r_multiple
    return entry + risk * r_multiple

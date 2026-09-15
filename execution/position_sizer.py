from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolSpec:
    tick_size: float
    tick_value: float
    min_volume: float
    max_volume: float
    volume_step: float


def calculate_volume(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    spec: SymbolSpec,
) -> float:
    risk_amount = equity * risk_pct / 100
    price_risk = abs(entry_price - stop_loss)
    if price_risk <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0:
        raise ValueError("Entry, stop, tick size, and tick value must create positive risk.")
    loss_per_lot = price_risk / spec.tick_size * spec.tick_value
    raw_volume = risk_amount / loss_per_lot
    stepped = _floor_to_step(raw_volume, spec.volume_step)
    return min(max(stepped, spec.min_volume), spec.max_volume)


def combined_risk_amount(volumes: list[float], entries: list[float], stop_loss: float, spec: SymbolSpec) -> float:
    if len(volumes) != len(entries):
        raise ValueError("Volumes and entries must have the same length.")
    total = 0.0
    for volume, entry in zip(volumes, entries):
        total += abs(entry - stop_loss) / spec.tick_size * spec.tick_value * volume
    return total


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("Volume step must be positive.")
    steps = int(value / step)
    return round(steps * step, 8)

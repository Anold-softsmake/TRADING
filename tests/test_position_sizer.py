from __future__ import annotations

from execution.position_sizer import SymbolSpec, calculate_volume, combined_risk_amount


def test_calculate_volume_uses_tick_specs() -> None:
    spec = SymbolSpec(tick_size=0.01, tick_value=1.0, min_volume=0.01, max_volume=100, volume_step=0.01)

    volume = calculate_volume(10000, 1, 2000, 1999, spec)

    assert volume == 1.0


def test_combined_risk_amount_for_two_entries() -> None:
    spec = SymbolSpec(tick_size=0.01, tick_value=1.0, min_volume=0.01, max_volume=100, volume_step=0.01)

    risk = combined_risk_amount([0.5, 0.25], [2000, 1998], 1996, spec)

    assert risk == 250.0

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd

from .engine import HistoricalBacktestEngine


def compare_core_variants(
    m15: pd.DataFrame,
    settings: dict[str, Any],
    h1: pd.DataFrame | None = None,
    h4: pd.DataFrame | None = None,
) -> dict[str, dict[str, float]]:
    variants = {
        "single_entry": {"backtest.entry_model": "single_entry"},
        "two_entry": {"backtest.entry_model": "two_entry", "backtest.two_entry_enabled": True},
        "single_tp": {"backtest.tp_r_multiples": [2], "backtest.tp_allocations": [1.0]},
        "tp1_tp2_tp3": {"backtest.tp_r_multiples": [1, 2, 3], "backtest.tp_allocations": [0.3, 0.3, 0.4]},
        "sweep_displacement_required": {"sweep.require_displacement": True},
        "sweep_displacement_not_required": {"sweep.require_displacement": False},
        "ob_only_zone": {"entry_zone.fallback_to_ob": True, "entry_zone.fallback_to_fvg": False},
        "ob_or_fvg_zone": {"entry_zone.fallback_to_ob": True, "entry_zone.fallback_to_fvg": True},
        "ob_fvg_overlap_required": {"entry_zone.reject_if_no_overlap": True},
    }
    results: dict[str, dict[str, float]] = {}
    for name, overrides in variants.items():
        variant_settings = deepcopy(settings)
        for key, value in overrides.items():
            _set_nested(variant_settings, key, value)
        results[name] = HistoricalBacktestEngine(variant_settings).run(m15, h1, h4).metrics
    return results


def _set_nested(settings: dict[str, Any], dotted_key: str, value: Any) -> None:
    target = settings
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value

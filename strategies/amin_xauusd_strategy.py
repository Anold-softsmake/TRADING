from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yaml

from .confluence import calculate_entry_zone, calculate_invalidation, score_setup
from .fair_value_gaps import detect_fair_value_gaps
from .liquidity import identify_liquidity_pools
from .liquidity_sweep import detect_liquidity_sweeps
from .market_structure import analyze_market_structure, detect_swings
from .models import FairValueGap, LiquidityPool, LiquiditySweep, OrderBlock, SetupDecision, StructureEvent
from .order_blocks import detect_order_blocks
from .sessions import session_filter_pass
from .utils import validate_ohlc


@dataclass(frozen=True)
class Phase1Analysis:
    decisions: list[SetupDecision]
    swings: dict[str, Any]
    liquidity_pools: list[LiquidityPool]
    sweeps: list[LiquiditySweep]
    structure_events: list[StructureEvent]
    order_blocks: list[OrderBlock]
    fair_value_gaps: list[FairValueGap]


def load_settings(path: str = "config/settings.yaml") -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class AminXauusdPhase1Strategy:
    """Research-only detector for Amin FX-inspired public concepts."""

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.symbol = settings.get("symbol", "XAUUSD")

    def analyze(
        self,
        m15: pd.DataFrame,
        h1: pd.DataFrame | None = None,
        h4: pd.DataFrame | None = None,
        session_confirmation: bool | None = None,
    ) -> Phase1Analysis:
        m15 = validate_ohlc(m15)
        swing_cfg = self.settings.get("swing", {})
        structure_cfg = self.settings.get("structure", {})
        liquidity_cfg = self.settings.get("liquidity", {})
        sweep_cfg = self.settings.get("sweep", {})
        ob_cfg = self.settings.get("order_block", {})
        fvg_cfg = self.settings.get("fvg", {})

        swings = detect_swings(m15, **swing_cfg)
        structure = analyze_market_structure(m15, swings=swings, **structure_cfg)
        pools = identify_liquidity_pools(m15, swings, **liquidity_cfg)
        sweeps = detect_liquidity_sweeps(m15, pools, **sweep_cfg)
        order_blocks = detect_order_blocks(m15, structure.events, sweeps=sweeps, **ob_cfg)
        fvgs = detect_fair_value_gaps(m15, structure.events, **fvg_cfg)

        h1_bias = self._bias(h1) if h1 is not None else "Neutral"
        h4_bias = self._bias(h4) if h4 is not None else "Neutral"
        decisions = [
            self._decision_at(
                m15,
                index,
                h1_bias,
                h4_bias,
                structure.bias,
                pools,
                sweeps,
                structure.events,
                order_blocks,
                fvgs,
                session_confirmation,
            )
            for index in range(len(m15))
        ]

        return Phase1Analysis(
            decisions,
            {"M15": structure.swings, "H1_bias": h1_bias, "H4_bias": h4_bias, "labels": structure.labels},
            pools,
            sweeps,
            structure.events,
            order_blocks,
            fvgs,
        )

    def latest_decision(self, m15: pd.DataFrame, h1: pd.DataFrame | None = None, h4: pd.DataFrame | None = None) -> SetupDecision:
        analysis = self.analyze(m15, h1, h4)
        return analysis.decisions[-1]

    def explain(self, decision: SetupDecision) -> str:
        lines = [
            f"{decision.symbol}",
            "",
            f"Decision: {decision.decision}",
            "",
            f"H4 Bias: {decision.h4_bias}",
            f"H1 Bias: {decision.h1_bias}",
            f"M15 Structure: {decision.m15_structure}",
            f"Liquidity Sweep: {'Confirmed' if decision.sweep else 'Not confirmed'}",
            f"Structure Event: {decision.structure_event.event_type if decision.structure_event else 'None'}",
            f"Order Block: {'Valid' if decision.order_block else 'None'}",
            f"FVG: {'Valid' if decision.fvg else 'None'}",
            f"Score: {decision.confluence_score}/{decision.max_score}",
            f"Required: {decision.required_score}/{decision.max_score}",
        ]
        if decision.entry_zone:
            lines.append(f"Entry Zone: {decision.entry_zone.low:.2f}-{decision.entry_zone.high:.2f}")
        if decision.invalidation is not None:
            lines.append(f"Invalidation: {decision.invalidation:.2f}")
        lines.extend(["", f"Reason: {decision.reason}"])
        return "\n".join(lines)

    def _decision_at(
        self,
        df: pd.DataFrame,
        index: int,
        h1_bias: str,
        h4_bias: str,
        m15_structure: str,
        pools: list[LiquidityPool],
        sweeps: list[LiquiditySweep],
        events: list[StructureEvent],
        order_blocks: list[OrderBlock],
        fvgs: list[FairValueGap],
        session_confirmation: bool | None,
    ) -> SetupDecision:
        known_sweep = _latest([s for s in sweeps if s.confirmation_index <= index])
        direction = known_sweep.direction if known_sweep else _direction_from_bias(h1_bias, h4_bias, m15_structure)
        known_pool = _latest([p for p in pools if p.confirmed_index <= index and (not known_sweep or p.price_level == known_sweep.liquidity_level)])
        known_event = _latest([e for e in events if e.confirmation_index <= index and e.direction == direction])
        known_ob = _latest([ob for ob in order_blocks if ob.confirmed_index <= index and ob.direction == direction])
        known_fvg = _latest([fvg for fvg in fvgs if fvg.formation_index <= index and fvg.direction == direction])
        strong_displacement = bool(known_sweep and known_sweep.displacement_confirmed)
        htf_alignment = direction == "bullish" and h1_bias == h4_bias == "Bullish" or direction == "bearish" and h1_bias == h4_bias == "Bearish"

        session_pass = session_filter_pass(df.at[index, "timestamp"], self.settings) if session_confirmation is None else session_confirmation
        score, max_score, components = score_setup(
            direction,
            known_pool,
            known_sweep,
            known_event,
            known_ob,
            known_fvg,
            strong_displacement,
            session_pass,
            htf_alignment,
            self.settings.get("confluence", {}).get("weights"),
        )
        entry_cfg = self.settings.get("entry_zone", {})
        zone = calculate_entry_zone(
            direction,
            known_ob,
            known_fvg,
            entry_cfg.get("prefer_ob_fvg_overlap", True),
            entry_cfg.get("fallback_to_ob", True),
            entry_cfg.get("fallback_to_fvg", True),
            entry_cfg.get("reject_if_no_overlap", False),
        )
        invalidation_cfg = self.settings.get("invalidation", {})
        invalidation = calculate_invalidation(
            direction,
            known_sweep,
            known_ob,
            invalidation_cfg.get("buffer_points", 50),
            invalidation_cfg.get("method", "beyond_sweep_extreme"),
        )
        required = int(self.settings.get("confluence", {}).get("minimum_score", 7))
        has_required_zone = zone is not None or not entry_cfg.get("require_ob_or_fvg", True)
        decision = "TRADE_CANDIDATE" if score >= required and has_required_zone and invalidation is not None else "NO SETUP"
        reason = _reason(decision, score, required, has_required_zone, invalidation)

        return SetupDecision(
            self.symbol,
            self.settings.get("timeframes", {}).get("execution", "M15"),
            df.at[index, "timestamp"],
            h4_bias,
            h1_bias,
            m15_structure,
            known_pool,
            known_sweep,
            known_event,
            known_ob,
            known_fvg,
            score,
            max_score,
            required,
            zone,
            invalidation,
            decision,
            reason,
            components,
        )

    def _bias(self, candles: pd.DataFrame) -> str:
        swing_cfg = self.settings.get("swing", {})
        structure_cfg = self.settings.get("structure", {})
        swings = detect_swings(candles, **swing_cfg)
        return analyze_market_structure(candles, swings=swings, **structure_cfg).bias


def _latest(items: list[Any]) -> Any | None:
    return items[-1] if items else None


def _direction_from_bias(h1_bias: str, h4_bias: str, m15_structure: str) -> str:
    if h1_bias == h4_bias == "Bearish" or m15_structure == "Bearish":
        return "bearish"
    return "bullish"


def _reason(decision: str, score: int, required: int, has_required_zone: bool, invalidation: float | None) -> str:
    if decision == "TRADE_CANDIDATE":
        return "Required confluence, entry zone, and invalidation are present. Research candidate only; no trade execution."
    if score < required:
        return "Insufficient confirmation."
    if not has_required_zone:
        return "No valid Order Block/FVG entry zone."
    if invalidation is None:
        return "No structural invalidation level."
    return "No valid setup."

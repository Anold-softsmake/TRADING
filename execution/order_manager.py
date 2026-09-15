from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from risk.kill_switch import KillSwitch
from strategies.models import SetupDecision

from .mt5_connector import MT5Connector
from .position_sizer import calculate_volume
from .targets import first_take_profit


@dataclass(frozen=True)
class ExecutionValidation:
    passed: bool
    reason: str
    details: dict[str, Any]


class DemoOrderManager:
    def __init__(self, connector: MT5Connector, settings: dict[str, Any], kill_switch: KillSwitch | None = None):
        self.connector = connector
        self.settings = settings
        self.kill_switch = kill_switch or KillSwitch(settings.get("execution", {}).get("kill_switch_file", "config/KILL_SWITCH"))

    def validate_signal(self, decision: SetupDecision) -> ExecutionValidation:
        execution_cfg = self.settings.get("execution", {})
        mode = execution_cfg.get("mode", "DEMO")
        if mode != "DEMO":
            return ExecutionValidation(False, "Execution mode must be DEMO for Phase 5.", {"mode": mode})
        if self.kill_switch.active():
            return ExecutionValidation(False, "Kill switch is active.", {})
        if decision.decision != "TRADE_CANDIDATE":
            return ExecutionValidation(False, "Decision is not a trade candidate.", {"decision": decision.decision})
        if decision.entry_zone is None or decision.invalidation is None:
            return ExecutionValidation(False, "Entry zone or invalidation is missing.", {})

        spread = self.connector.spread_points()
        max_spread = float(execution_cfg.get("max_spread_points", 50))
        if spread > max_spread:
            return ExecutionValidation(False, "Spread filter failed.", {"spread_points": spread, "max_spread_points": max_spread})

        account = self.connector.account_info()
        spec = self.connector.symbol_spec()
        entry = (decision.entry_zone.low + decision.entry_zone.high) / 2
        risk_pct = float(self.settings.get("risk", {}).get("risk_per_setup_pct", 0.5))
        volume = calculate_volume(float(account.get("equity", account.get("balance", 0))), risk_pct, entry, decision.invalidation, spec)
        if volume < spec.min_volume:
            return ExecutionValidation(False, "Calculated volume is below minimum.", {"volume": volume, "min_volume": spec.min_volume})

        return ExecutionValidation(
            True,
            "PASS",
            {
                "spread_points": spread,
                "entry": entry,
                "stop_loss": decision.invalidation,
                "volume": volume,
                "equity": account.get("equity"),
            },
        )

    def build_market_order_request(self, decision: SetupDecision, validation: ExecutionValidation) -> dict[str, Any]:
        if not validation.passed:
            raise ValueError(f"Cannot build order from failed validation: {validation.reason}")
        direction = _direction(decision)
        tick = self.connector.tick()
        mt5 = self.connector.mt5
        price = float(tick["ask"]) if direction == "bullish" else float(tick["bid"])
        r_multiple = float(self.settings.get("backtest", {}).get("tp_r_multiples", [1])[0])
        tp = first_take_profit(price, float(decision.invalidation), direction, r_multiple)
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.connector.symbol,
            "volume": validation.details["volume"],
            "type": mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": decision.invalidation,
            "tp": tp,
            "deviation": int(self.settings.get("execution", {}).get("max_deviation_points", 20)),
            "comment": "amin-xauusd-demo",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

    def submit_demo_order(self, decision: SetupDecision) -> dict[str, Any]:
        validation = self.validate_signal(decision)
        if not validation.passed:
            return {"submitted": False, "reason": validation.reason, "details": validation.details}
        request = self.build_market_order_request(decision, validation)
        result = self.connector.send_order(request)
        return {"submitted": True, "request": request, "result": result}


def _direction(decision: SetupDecision) -> str:
    if decision.sweep:
        return decision.sweep.direction
    if decision.structure_event:
        return decision.structure_event.direction
    if decision.entry_zone:
        return decision.entry_zone.direction
    return "bullish"

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from execution.demo_bot import LiveTradingDisabled, _assert_demo_only, _risk_kwargs
from execution.mt5_connector import MT5Connector, MT5Credentials
from execution.order_manager import DemoOrderManager
from risk.kill_switch import KillSwitch
from risk.risk_manager import HistoricalRiskManager

from .alerts import TradingViewAlert, TradingViewAlertError, alert_to_decision, normalize_symbol, parse_alert, secrets_match

LOGGER = logging.getLogger("amin_xauusd.tradingview")


class TradingViewBridge:
    def __init__(self, settings: dict[str, Any], connector: MT5Connector | None = None):
        self.settings = settings
        self.kill_switch = KillSwitch(settings.get("execution", {}).get("kill_switch_file", "config/KILL_SWITCH"))
        self.risk = HistoricalRiskManager(**_risk_kwargs(settings))
        self.connector = connector
        self.orders = DemoOrderManager(connector, settings, self.kill_switch) if connector is not None else None
        self.signal_log = Path(settings.get("execution", {}).get("signal_log_file", "logs/demo_signals.jsonl"))
        self._seen: set[tuple[str, str, str]] = set()

    def handle_body(self, body: bytes | str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        _assert_demo_only(self.settings)
        alert = parse_alert(body, headers)
        expected = _webhook_secret(self.settings)
        if not secrets_match(alert.secret, expected):
            raise TradingViewAlertError("Webhook secret does not match.")
        allowed = {normalize_symbol(symbol) for symbol in self.settings.get("tradingview", {}).get("allowed_symbols", ["XAUUSD"])}
        if alert.symbol not in allowed:
            return _result("blocked", f"Symbol {alert.symbol} is not allowed.", {"symbol": alert.symbol})
        fingerprint = (alert.symbol, str(alert.time), alert.action)
        if fingerprint in self._seen:
            return _result("ignored", "Duplicate TradingView alert.", {"symbol": alert.symbol})
        self._seen.add(fingerprint)

        if self.kill_switch.active():
            return _result("blocked", "Kill switch is active.", {"symbol": alert.symbol})

        decision = alert_to_decision(alert, self.settings)
        allowed_risk, reason = self.risk.can_open(decision.timestamp)
        if not allowed_risk:
            return _log_and_return(self.signal_log, "blocked", reason, decision, alert)

        dry_run = bool(self.settings.get("execution", {}).get("dry_run", True))
        if dry_run or decision.decision != "TRADE_CANDIDATE":
            status = "dry_run" if decision.decision == "TRADE_CANDIDATE" else "blocked"
            message = "TradingView signal logged. No order sent." if status == "dry_run" else decision.reason
            return _log_and_return(self.signal_log, status, message, decision, alert)

        if self.orders is None:
            try:
                self._connect_mt5()
            except Exception as exc:
                LOGGER.exception("MT5 demo connection failed")
                return _log_and_return(self.signal_log, "blocked", f"MT5 demo connection failed: {exc}", decision, alert)
        assert self.orders is not None
        order = self.orders.submit_demo_order(decision)
        if order.get("submitted"):
            self.risk.record_open(decision.timestamp)
        status = "submitted" if order.get("submitted") else "blocked"
        return _log_and_return(self.signal_log, status, order.get("reason", "submitted"), decision, alert, extra={"order": order})

    def _connect_mt5(self) -> None:
        login = os.getenv("MT5_LOGIN")
        connector = MT5Connector(self.settings.get("symbol", "XAUUSD"))
        connector.connect(
            MT5Credentials(
                login=int(login) if login else None,
                password=os.getenv("MT5_PASSWORD"),
                server=os.getenv("MT5_SERVER"),
                path=os.getenv("MT5_PATH"),
            )
        )
        self.connector = connector
        self.orders = DemoOrderManager(connector, self.settings, self.kill_switch)


def _webhook_secret(settings: dict[str, Any]) -> str:
    env_name = settings.get("tradingview", {}).get("secret_env", "TRADINGVIEW_WEBHOOK_SECRET")
    return os.getenv(env_name) or str(settings.get("tradingview", {}).get("secret") or "")


def _log_and_return(
    path: Path,
    status: str,
    reason: str,
    decision: Any,
    alert: TradingViewAlert,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details = {
        "symbol": alert.symbol,
        "action": alert.action,
        "score": alert.score,
        "entry": alert.entry,
        "stop": alert.stop,
        "decision": decision.decision,
    }
    if extra:
        details.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"status": status, "reason": reason, **details}, default=str) + "\n")
    LOGGER.info("%s | %s | %s %s", status, reason, alert.action, alert.symbol)
    return _result(status, reason, details)


def _result(status: str, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reason": reason, "details": details}

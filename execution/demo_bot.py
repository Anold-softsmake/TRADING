from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from risk.kill_switch import KillSwitch
from risk.risk_manager import HistoricalRiskManager
from strategies.amin_xauusd_strategy import AminXauusdPhase1Strategy
from strategies.models import SetupDecision

from .mt5_connector import MT5ConnectionError, MT5Connector, MT5Credentials
from .order_manager import DemoOrderManager

LOGGER = logging.getLogger("amin_xauusd.demo")


class LiveTradingDisabled(RuntimeError):
    pass


class DemoTradingBot:
    """Closed-bar demo loop. Live execution is refused regardless of broker connection."""

    def __init__(
        self,
        settings: dict[str, Any],
        connector: MT5Connector | None = None,
        strategy: AminXauusdPhase1Strategy | None = None,
        kill_switch: KillSwitch | None = None,
    ):
        self.settings = settings
        self.connector = connector or MT5Connector(settings.get("symbol", "XAUUSD"))
        self.strategy = strategy or AminXauusdPhase1Strategy(settings)
        self.kill_switch = kill_switch or KillSwitch(settings.get("execution", {}).get("kill_switch_file", "config/KILL_SWITCH"))
        self.orders = DemoOrderManager(self.connector, settings, self.kill_switch)
        self._last_closed_bar: Any = None
        self.risk = HistoricalRiskManager(**_risk_kwargs(settings))
        self.signal_log = Path(settings.get("execution", {}).get("signal_log_file", "logs/demo_signals.jsonl"))

    def connect(self) -> None:
        _assert_demo_only(self.settings)
        self.connector.connect(_credentials_from_env())
        account = self.connector.account_info()
        equity = float(account.get("equity", account.get("balance", self.risk.equity)))
        self.risk.equity = equity
        self.risk.starting_equity = equity
        LOGGER.info("Connected to MT5 demo. equity=%s", equity)

    def shutdown(self) -> None:
        self.connector.shutdown()

    def evaluate_once(self, submit: bool | None = None) -> dict[str, Any]:
        _assert_demo_only(self.settings)
        if self.kill_switch.active():
            return _result("blocked", "Kill switch is active.", {})

        m15 = _closed_bars(self.connector.rates("M15", 500))
        h1 = _closed_bars(self.connector.rates("H1", 300))
        h4 = _closed_bars(self.connector.rates("H4", 200))
        if m15.empty:
            return _result("blocked", "No closed M15 bars available.", {})

        decision = self.strategy.latest_decision(m15, h1, h4)
        timestamp = decision.timestamp
        allowed, reason = self.risk.can_open(timestamp)
        if not allowed:
            payload = _decision_payload(decision, extra={"risk_reason": reason})
            self._log_signal(payload)
            return _result("blocked", reason, payload)

        open_positions = self.connector.open_positions()
        max_simultaneous = int(self.settings.get("risk", {}).get("max_simultaneous_setups", 1))
        if len(open_positions) >= max_simultaneous:
            payload = _decision_payload(decision, extra={"open_positions": len(open_positions)})
            self._log_signal(payload)
            return _result("blocked", "Maximum simultaneous setups reached.", payload)

        dry_run = self.settings.get("execution", {}).get("dry_run", True) if submit is None else not submit
        if dry_run:
            validation = self.orders.validate_signal(decision)
            payload = _decision_payload(decision, extra={"validation": {"passed": validation.passed, "reason": validation.reason, "details": validation.details}})
            self._log_signal(payload)
            status = "dry_run" if validation.passed else "blocked"
            return _result(status, validation.reason, payload)

        order = self.orders.submit_demo_order(decision)
        if order.get("submitted"):
            self.risk.record_open(timestamp)
        payload = _decision_payload(decision, extra={"order": _json_safe(order)})
        self._log_signal(payload)
        status = "submitted" if order.get("submitted") else "blocked"
        return _result(status, order.get("reason", "submitted"), payload)

    def run(self, once: bool = False, poll_seconds: int = 15) -> dict[str, Any] | None:
        _assert_demo_only(self.settings)
        self._configure_logging()
        self.connect()
        last_result: dict[str, Any] | None = None
        try:
            while True:
                m15 = _closed_bars(self.connector.rates("M15", 5))
                closed_bar = None if m15.empty else m15["timestamp"].iloc[-1]
                if closed_bar is not None and closed_bar != self._last_closed_bar:
                    last_result = self.evaluate_once()
                    self._last_closed_bar = closed_bar
                    LOGGER.info("%s | %s | %s", last_result["status"], last_result["reason"], last_result["details"].get("decision"))
                if once:
                    return last_result or self.evaluate_once()
                time.sleep(max(poll_seconds, 5))
        except KeyboardInterrupt:
            LOGGER.info("Demo bot stopped by user.")
            return last_result
        finally:
            self.shutdown()

    def _configure_logging(self) -> None:
        log_file = self.settings.get("execution", {}).get("log_file", "logs/execution.log")
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
        )

    def _log_signal(self, payload: dict[str, Any]) -> None:
        self.signal_log.parent.mkdir(parents=True, exist_ok=True)
        with self.signal_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")


def _assert_demo_only(settings: dict[str, Any]) -> None:
    execution = settings.get("execution", {})
    mode = str(execution.get("mode", "DEMO")).upper()
    if mode != "DEMO" or bool(execution.get("allow_live", False)):
        raise LiveTradingDisabled("Live trading is disabled. Keep execution.mode=DEMO and allow_live=false.")


def _credentials_from_env() -> MT5Credentials:
    login = os.getenv("MT5_LOGIN")
    return MT5Credentials(
        login=int(login) if login else None,
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER"),
        path=os.getenv("MT5_PATH"),
    )


def _closed_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or len(df) < 2:
        return df.copy() if df is not None else pd.DataFrame()
    return df.iloc[:-1].reset_index(drop=True)


def _risk_kwargs(settings: dict[str, Any]) -> dict[str, Any]:
    risk = settings.get("risk", {})
    return {
        "starting_equity": float(risk.get("starting_equity", 10_000)),
        "risk_per_setup_pct": float(risk.get("risk_per_setup_pct", 0.5)),
        "max_daily_loss_pct": float(risk.get("max_daily_loss_pct", 2)),
        "max_weekly_loss_pct": float(risk.get("max_weekly_loss_pct", 5)),
        "max_trades_day": int(risk.get("max_trades_day", 3)),
        "max_consecutive_losses": int(risk.get("max_consecutive_losses", 3)),
    }


def _decision_payload(decision: SetupDecision, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "symbol": decision.symbol,
        "timestamp": str(decision.timestamp),
        "decision": decision.decision,
        "reason": decision.reason,
        "score": decision.confluence_score,
        "required": decision.required_score,
        "entry_zone": None if decision.entry_zone is None else {"low": decision.entry_zone.low, "high": decision.entry_zone.high, "direction": decision.entry_zone.direction},
        "invalidation": decision.invalidation,
    }
    if extra:
        payload.update(extra)
    return payload


def _result(status: str, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reason": reason, "details": details}


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

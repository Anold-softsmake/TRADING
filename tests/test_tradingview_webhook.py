from __future__ import annotations

import json

import pytest

from execution.demo_bot import LiveTradingDisabled
from tradingview.alerts import TradingViewAlertError, parse_alert
from tradingview.bridge import TradingViewBridge


def tv_settings(tmp_path, secret: str = "change-me") -> dict:
    return {
        "symbol": "XAUUSD",
        "execution": {
            "mode": "DEMO",
            "allow_live": False,
            "dry_run": True,
            "kill_switch_file": str(tmp_path / "KILL_SWITCH"),
            "signal_log_file": str(tmp_path / "demo_signals.jsonl"),
        },
        "risk": {
            "starting_equity": 10000,
            "risk_per_setup_pct": 0.5,
            "max_daily_loss_pct": 2,
            "max_weekly_loss_pct": 5,
            "max_trades_day": 3,
            "max_consecutive_losses": 3,
        },
        "confluence": {"minimum_score": 7, "weights": {"liquidity_sweep": 2, "bos_choch_mss": 2}},
        "tradingview": {"secret": secret, "allowed_symbols": ["XAUUSD"], "require_min_score": True},
    }


def sample_alert(**overrides) -> str:
    payload = {
        "secret": "change-me",
        "symbol": "OANDA:XAUUSD",
        "timeframe": "15",
        "action": "buy",
        "price": 2400.5,
        "entry": 2400.2,
        "stop": 2392.0,
        "zone_low": 2399.0,
        "zone_high": 2401.0,
        "score": 9,
        "time": "2026-09-11T12:00:00",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_parse_maps_tradingview_ticker_to_xauusd() -> None:
    alert = parse_alert(sample_alert())
    assert alert.symbol == "XAUUSD"
    assert alert.action == "buy"
    assert alert.stop == 2392.0


def test_bridge_dry_run_logs_without_mt5(tmp_path) -> None:
    bridge = TradingViewBridge(tv_settings(tmp_path))
    result = bridge.handle_body(sample_alert())
    assert result["status"] == "dry_run"
    assert "No order sent" in result["reason"]
    logged = (tmp_path / "demo_signals.jsonl").read_text(encoding="utf-8")
    assert "buy" in logged


def test_bridge_rejects_bad_secret(tmp_path) -> None:
    bridge = TradingViewBridge(tv_settings(tmp_path))
    with pytest.raises(TradingViewAlertError):
        bridge.handle_body(sample_alert(secret="wrong"))


def test_bridge_blocks_low_score(tmp_path) -> None:
    bridge = TradingViewBridge(tv_settings(tmp_path))
    result = bridge.handle_body(sample_alert(score=3, time="2026-09-11T13:00:00"))
    assert result["status"] == "blocked"


def test_bridge_refuses_live_mode(tmp_path) -> None:
    settings = tv_settings(tmp_path)
    settings["execution"]["mode"] = "LIVE"
    bridge = TradingViewBridge(settings)
    with pytest.raises(LiveTradingDisabled):
        bridge.handle_body(sample_alert())


def test_bridge_blocks_when_demo_mt5_is_missing(tmp_path) -> None:
    settings = tv_settings(tmp_path)
    settings["execution"]["dry_run"] = False
    bridge = TradingViewBridge(settings)
    result = bridge.handle_body(sample_alert(time="2026-09-11T14:00:00"))
    assert result["status"] == "blocked"
    assert "MT5" in result["reason"]


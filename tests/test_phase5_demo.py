from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from execution.demo_bot import DemoTradingBot, LiveTradingDisabled, _assert_demo_only, _closed_bars
from execution.mt5_connector import MT5Connector
from execution.order_manager import DemoOrderManager
from execution.targets import first_take_profit
from risk.kill_switch import KillSwitch
from strategies.models import EntryZone, SetupDecision


class FakeMT5:
    TRADE_RETCODE_DONE = 10009
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    POSITION_TYPE_BUY = 0
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240

    def __init__(self, spread: float = 0.2, positions: list | None = None):
        self._spread = spread
        self._positions = positions or []
        self.sent = []

    def initialize(self, **kwargs):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (1, "ok")

    def symbol_select(self, symbol, enable):
        return True

    def account_info(self):
        return SimpleNamespace(_asdict=lambda: {"equity": 10000.0, "balance": 10000.0})

    def symbol_info(self, symbol):
        return SimpleNamespace(
            _asdict=lambda: {
                "trade_tick_size": 0.01,
                "trade_tick_value": 1.0,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
            },
            point=0.01,
        )

    def symbol_info_tick(self, symbol):
        return {"ask": 2000.10, "bid": 2000.10 - self._spread}

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        rows = []
        for index in range(count):
            rows.append(
                {
                    "time": 1_704_067_200 + index * 60 * 15,
                    "open": 2000 + index * 0.1,
                    "high": 2001 + index * 0.1,
                    "low": 1999 + index * 0.1,
                    "close": 2000.5 + index * 0.1,
                    "tick_volume": 100,
                    "spread": 20,
                    "real_volume": 0,
                }
            )
        return rows

    def positions_get(self, symbol=None, ticket=None):
        return self._positions

    def order_send(self, request):
        self.sent.append(request)
        return SimpleNamespace(_asdict=lambda: {"retcode": self.TRADE_RETCODE_DONE, "order": 1, "deal": 1})


def candidate() -> SetupDecision:
    return SetupDecision(
        "XAUUSD",
        "M15",
        pd.Timestamp("2026-01-01 12:00"),
        "Bullish",
        "Bullish",
        "Bullish",
        None,
        None,
        None,
        None,
        None,
        8,
        13,
        7,
        EntryZone("bullish", 1998, 2002, ("ob",)),
        1990,
        "TRADE_CANDIDATE",
        "test",
        {},
    )


def demo_settings(tmp_path, dry_run: bool = True) -> dict:
    return {
        "symbol": "XAUUSD",
        "timeframes": {"execution": "M15"},
        "execution": {
            "mode": "DEMO",
            "allow_live": False,
            "dry_run": dry_run,
            "max_spread_points": 50,
            "max_deviation_points": 20,
            "kill_switch_file": str(tmp_path / "KILL_SWITCH"),
            "log_file": str(tmp_path / "execution.log"),
            "signal_log_file": str(tmp_path / "demo_signals.jsonl"),
        },
        "risk": {
            "starting_equity": 10000,
            "risk_per_setup_pct": 0.5,
            "max_daily_loss_pct": 2,
            "max_weekly_loss_pct": 5,
            "max_simultaneous_setups": 1,
            "max_trades_day": 3,
            "max_consecutive_losses": 3,
        },
        "backtest": {"tp_r_multiples": [1, 2, 3]},
        "confluence": {"minimum_score": 7},
    }


def test_first_take_profit_is_one_r() -> None:
    assert first_take_profit(2000, 1990, "bullish", 1) == 2010
    assert first_take_profit(2000, 2010, "bearish", 1) == 1990


def test_closed_bars_drop_forming_candle() -> None:
    df = pd.DataFrame({"timestamp": [1, 2, 3], "close": [1, 2, 3]})
    closed = _closed_bars(df)
    assert list(closed["timestamp"]) == [1, 2]


def test_live_mode_is_refused() -> None:
    with pytest.raises(LiveTradingDisabled):
        _assert_demo_only({"execution": {"mode": "LIVE", "allow_live": False}})
    with pytest.raises(LiveTradingDisabled):
        _assert_demo_only({"execution": {"mode": "DEMO", "allow_live": True}})


def test_order_manager_uses_r_multiple_take_profit(tmp_path) -> None:
    mt5 = FakeMT5()
    connector = MT5Connector("XAUUSD", mt5_module=mt5)
    connector.connect()
    manager = DemoOrderManager(connector, demo_settings(tmp_path, dry_run=False))
    validation = manager.validate_signal(candidate())
    request = manager.build_market_order_request(candidate(), validation)
    assert request["sl"] == 1990
    assert request["tp"] == pytest.approx(2010.1, rel=0, abs=0.2)


def test_kill_switch_blocks_orders(tmp_path) -> None:
    path = tmp_path / "KILL_SWITCH"
    path.write_text("ON", encoding="utf-8")
    mt5 = FakeMT5()
    connector = MT5Connector("XAUUSD", mt5_module=mt5)
    connector.connect()
    manager = DemoOrderManager(connector, demo_settings(tmp_path), KillSwitch(str(path)))
    result = manager.submit_demo_order(candidate())
    assert result["submitted"] is False
    assert "Kill switch" in result["reason"]


def test_demo_bot_dry_run_does_not_send_orders(tmp_path) -> None:
    mt5 = FakeMT5()
    connector = MT5Connector("XAUUSD", mt5_module=mt5)
    connector.connected = True
    bot = DemoTradingBot(demo_settings(tmp_path, dry_run=True), connector=connector)
    bot.strategy.latest_decision = lambda *args, **kwargs: candidate()  # type: ignore[method-assign]
    result = bot.evaluate_once()
    assert result["status"] == "dry_run"
    assert mt5.sent == []


def test_demo_bot_blocks_when_position_already_open(tmp_path) -> None:
    mt5 = FakeMT5(positions=[{"ticket": 1}])
    connector = MT5Connector("XAUUSD", mt5_module=mt5)
    connector.connected = True
    bot = DemoTradingBot(demo_settings(tmp_path, dry_run=False), connector=connector)
    bot.strategy.latest_decision = lambda *args, **kwargs: candidate()  # type: ignore[method-assign]
    result = bot.evaluate_once()
    assert result["status"] == "blocked"
    assert "simultaneous" in result["reason"].lower()

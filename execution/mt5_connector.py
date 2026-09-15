from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .position_sizer import SymbolSpec


class MT5ConnectionError(RuntimeError):
    pass


class MT5OrderError(RuntimeError):
    pass


@dataclass(frozen=True)
class MT5Credentials:
    login: int | None = None
    password: str | None = None
    server: str | None = None
    path: str | None = None


class MT5Connector:
    def __init__(self, symbol: str = "XAUUSD", mt5_module: Any | None = None):
        self.symbol = symbol
        self.mt5 = mt5_module or self._import_mt5()
        self.connected = False

    def connect(self, credentials: MT5Credentials | None = None) -> None:
        credentials = credentials or MT5Credentials()
        kwargs = {}
        if credentials.path:
            kwargs["path"] = credentials.path
        if credentials.login is not None:
            kwargs["login"] = credentials.login
        if credentials.password:
            kwargs["password"] = credentials.password
        if credentials.server:
            kwargs["server"] = credentials.server

        if not self.mt5.initialize(**kwargs):
            raise MT5ConnectionError(f"MT5 initialize failed: {self.mt5.last_error()}")
        if not self.mt5.symbol_select(self.symbol, True):
            raise MT5ConnectionError(f"Symbol select failed for {self.symbol}: {self.mt5.last_error()}")
        self.connected = True

    def shutdown(self) -> None:
        if self.connected:
            self.mt5.shutdown()
            self.connected = False

    def account_info(self) -> dict[str, Any]:
        info = self.mt5.account_info()
        if info is None:
            raise MT5ConnectionError(f"Could not read account info: {self.mt5.last_error()}")
        return info._asdict() if hasattr(info, "_asdict") else dict(info)

    def symbol_spec(self) -> SymbolSpec:
        info = self.mt5.symbol_info(self.symbol)
        if info is None:
            raise MT5ConnectionError(f"Could not read symbol info for {self.symbol}: {self.mt5.last_error()}")
        data = info._asdict() if hasattr(info, "_asdict") else info
        return SymbolSpec(
            tick_size=float(_get(data, "trade_tick_size", "point")),
            tick_value=float(_get(data, "trade_tick_value")),
            min_volume=float(_get(data, "volume_min")),
            max_volume=float(_get(data, "volume_max")),
            volume_step=float(_get(data, "volume_step")),
        )

    def tick(self) -> dict[str, Any]:
        tick = self.mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise MT5ConnectionError(f"Could not read tick for {self.symbol}: {self.mt5.last_error()}")
        return tick._asdict() if hasattr(tick, "_asdict") else dict(tick)

    def spread_points(self) -> float:
        tick = self.tick()
        info = self.mt5.symbol_info(self.symbol)
        point = float(getattr(info, "point", 0.01))
        return (float(tick["ask"]) - float(tick["bid"])) / point

    def rates(self, timeframe: str, count: int, start_pos: int = 0) -> pd.DataFrame:
        mt5_timeframe = self._timeframe(timeframe)
        rates = self.mt5.copy_rates_from_pos(self.symbol, mt5_timeframe, start_pos, count)
        if rates is None:
            raise MT5ConnectionError(f"Could not read rates for {self.symbol} {timeframe}: {self.mt5.last_error()}")
        df = pd.DataFrame(rates)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "tick_volume", "spread"])
        df["timestamp"] = pd.to_datetime(df["time"], unit="s")
        return df.rename(columns={"tick_volume": "tick_volume"})[["timestamp", "open", "high", "low", "close", "tick_volume", "spread"]]

    def open_positions(self) -> list[dict[str, Any]]:
        positions = self.mt5.positions_get(symbol=self.symbol) or []
        result = []
        for position in positions:
            data = position._asdict() if hasattr(position, "_asdict") else dict(position)
            result.append(data)
        return result

    def send_order(self, request: dict[str, Any]) -> dict[str, Any]:
        result = self.mt5.order_send(request)
        if result is None:
            raise MT5OrderError(f"order_send returned None: {self.mt5.last_error()}")
        data = result._asdict() if hasattr(result, "_asdict") else dict(result)
        if data.get("retcode") != self.mt5.TRADE_RETCODE_DONE:
            raise MT5OrderError(f"Order rejected: {data}")
        return data

    def close_position(self, ticket: int, volume: float, deviation: int = 20) -> dict[str, Any]:
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5OrderError(f"No position found for ticket {ticket}")
        position = positions[0]
        tick = self.tick()
        is_buy = int(position.type) == self.mt5.POSITION_TYPE_BUY
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": self.symbol,
            "volume": volume,
            "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
            "price": tick["bid"] if is_buy else tick["ask"],
            "deviation": deviation,
            "comment": "amin-xauusd-demo-close",
        }
        return self.send_order(request)

    def _timeframe(self, timeframe: str) -> int:
        mapping = {
            "M5": self.mt5.TIMEFRAME_M5,
            "M15": self.mt5.TIMEFRAME_M15,
            "H1": self.mt5.TIMEFRAME_H1,
            "H4": self.mt5.TIMEFRAME_H4,
        }
        if timeframe not in mapping:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return mapping[timeframe]

    @staticmethod
    def _import_mt5() -> Any:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise MT5ConnectionError("MetaTrader5 package is not installed. Install it only when ready for MT5 demo mode.") from exc
        return mt5


def utc_now() -> datetime:
    return datetime.utcnow()


def _get(data: Any, *names: str) -> Any:
    for name in names:
        if isinstance(data, dict) and name in data:
            return data[name]
        if hasattr(data, name):
            return getattr(data, name)
    raise KeyError(f"None of these fields exist: {names}")

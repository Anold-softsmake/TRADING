from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

import pandas as pd

from strategies.models import EntryZone, SetupDecision


class TradingViewAlertError(ValueError):
    pass


@dataclass(frozen=True)
class TradingViewAlert:
    symbol: str
    action: str
    timeframe: str
    price: float
    entry: float
    stop: float
    zone_low: float
    zone_high: float
    score: int
    time: Any
    secret: str
    raw: dict[str, Any]


def parse_alert(body: bytes | str, headers: dict[str, str] | None = None) -> TradingViewAlert:
    payload = _decode_payload(body)
    headers = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    secret = str(payload.get("secret") or headers.get("x-webhook-secret") or "")
    action = _normalize_action(payload.get("action") or payload.get("side") or payload.get("order"))
    price = _float(payload.get("price") or payload.get("close"), "price")
    entry = _float(payload.get("entry") or price, "entry")
    stop = _optional_float(payload.get("stop") or payload.get("sl") or payload.get("invalidation"))
    if stop is None:
        raise TradingViewAlertError("Alert is missing stop/invalidation.")
    zone_low = _optional_float(payload.get("zone_low"))
    zone_high = _optional_float(payload.get("zone_high"))
    if zone_low is None or zone_high is None:
        width = abs(entry - stop) * 0.25
        zone_low = entry - width
        zone_high = entry + width
    timestamp = _timestamp(payload.get("time") or payload.get("timestamp") or payload.get("timenow"))
    return TradingViewAlert(
        symbol=normalize_symbol(str(payload.get("symbol") or payload.get("ticker") or "")),
        action=action,
        timeframe=str(payload.get("timeframe") or payload.get("interval") or "M15"),
        price=price,
        entry=entry,
        stop=stop,
        zone_low=min(zone_low, zone_high),
        zone_high=max(zone_low, zone_high),
        score=int(float(payload.get("score") or payload.get("confluence") or 0)),
        time=timestamp,
        secret=secret,
        raw=payload,
    )


def alert_to_decision(alert: TradingViewAlert, settings: dict[str, Any]) -> SetupDecision:
    direction = "bullish" if alert.action == "buy" else "bearish"
    required = int(settings.get("confluence", {}).get("minimum_score", 7))
    max_score = int(sum(settings.get("confluence", {}).get("weights", {}).values()) or 13)
    meets_score = alert.score >= required or not settings.get("tradingview", {}).get("require_min_score", True)
    decision = "TRADE_CANDIDATE" if meets_score else "NO SETUP"
    reason = "TradingView alert passed local risk mapping." if decision == "TRADE_CANDIDATE" else "TradingView score is below the configured minimum."
    return SetupDecision(
        settings.get("symbol", "XAUUSD"),
        alert.timeframe,
        alert.time,
        "Bullish" if direction == "bullish" else "Bearish",
        "Bullish" if direction == "bullish" else "Bearish",
        "Bullish" if direction == "bullish" else "Bearish",
        None,
        None,
        None,
        None,
        None,
        alert.score,
        max_score,
        required,
        EntryZone(direction, alert.zone_low, alert.zone_high, ("tradingview",)),
        alert.stop,
        decision,
        reason,
        {"tradingview": alert.score},
    )


def secrets_match(provided: str, expected: str) -> bool:
    if not expected or len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _decode_payload(body: bytes | str) -> dict[str, Any]:
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    text = text.strip()
    if not text:
        raise TradingViewAlertError("Empty TradingView webhook body.")
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        parsed = parse_qs(text, keep_blank_values=True)
        if "payload" in parsed:
            return json.loads(parsed["payload"][0])
        if len(parsed) > 1:
            return {key: values[0] for key, values in parsed.items()}
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise TradingViewAlertError("Webhook body is not valid JSON.") from None
    raise TradingViewAlertError("Webhook JSON must be an object.")


def _normalize_action(value: Any) -> str:
    action = str(value or "").strip().lower()
    if action in {"buy", "long", "bull", "bullish"}:
        return "buy"
    if action in {"sell", "short", "bear", "bearish"}:
        return "sell"
    raise TradingViewAlertError(f"Unsupported action: {value!r}")


def normalize_symbol(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", symbol).upper()
    if "XAU" in cleaned or cleaned in {"GOLD"}:
        return "XAUUSD"
    return cleaned


def _float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TradingViewAlertError(f"Alert field {name} must be numeric.") from exc


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _timestamp(value: Any) -> Any:
    if value in (None, ""):
        return pd.Timestamp.now(tz="UTC").tz_convert(None)
    try:
        return pd.to_datetime(value, utc=True).tz_convert(None)
    except (TypeError, ValueError):
        return datetime.utcnow()

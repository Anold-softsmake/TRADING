from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    enabled: bool = True


DEFAULT_WINDOWS = (
    SessionWindow("london", 10, 0, 19, 0, True),
    SessionWindow("new_york", 15, 0, 0, 0, True),
    SessionWindow("overlap", 15, 0, 19, 0, True),
)


def session_filter_pass(timestamp: Any, settings: dict[str, Any]) -> bool:
    session_cfg = settings.get("sessions", {})
    if not session_cfg.get("enabled", False):
        return True
    local_time = _to_display_timezone(timestamp, session_cfg.get("timezone_display", "Africa/Nairobi"))
    windows = _windows_from_config(session_cfg)
    return any(_in_window(local_time.hour, local_time.minute, window) for window in windows if window.enabled)


def current_session(timestamp: Any, settings: dict[str, Any]) -> str:
    session_cfg = settings.get("sessions", {})
    local_time = _to_display_timezone(timestamp, session_cfg.get("timezone_display", "Africa/Nairobi"))
    active = [window.name for window in _windows_from_config(session_cfg) if window.enabled and _in_window(local_time.hour, local_time.minute, window)]
    return "+".join(active) if active else "off_session"


def _to_display_timezone(timestamp: Any, timezone_name: str) -> Any:
    if not hasattr(timestamp, "tzinfo"):
        return timestamp
    zone = ZoneInfo(timezone_name)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=zone)
    return timestamp.astimezone(zone)


def _windows_from_config(session_cfg: dict[str, Any]) -> list[SessionWindow]:
    if "windows" in session_cfg:
        return [
            SessionWindow(
                item["name"],
                int(item["start"].split(":")[0]),
                int(item["start"].split(":")[1]),
                int(item["end"].split(":")[0]),
                int(item["end"].split(":")[1]),
                bool(item.get("enabled", True)),
            )
            for item in session_cfg["windows"]
        ]
    enabled = {
        "london": bool(session_cfg.get("london_enabled", True)),
        "new_york": bool(session_cfg.get("new_york_enabled", True)),
        "overlap": bool(session_cfg.get("overlap_enabled", True)),
    }
    return [SessionWindow(w.name, w.start_hour, w.start_minute, w.end_hour, w.end_minute, enabled.get(w.name, w.enabled)) for w in DEFAULT_WINDOWS]


def _in_window(hour: int, minute: int, window: SessionWindow) -> bool:
    now = hour * 60 + minute
    start = window.start_hour * 60 + window.start_minute
    end = window.end_hour * 60 + window.end_minute
    if start <= end:
        return start <= now < end
    return now >= start or now < end

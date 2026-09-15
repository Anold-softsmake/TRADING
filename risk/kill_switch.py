from __future__ import annotations

from pathlib import Path


class KillSwitch:
    def __init__(self, path: str = "config/KILL_SWITCH"):
        self.path = Path(path)

    def active(self) -> bool:
        if not self.path.exists():
            return False
        content = self.path.read_text(encoding="utf-8").strip().upper()
        return content in {"1", "ON", "TRUE", "ACTIVE", "STOP"}

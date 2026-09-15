from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .alerts import TradingViewAlertError
from .bridge import LiveTradingDisabled, TradingViewBridge

LOGGER = logging.getLogger("amin_xauusd.tradingview")
PINE_PATH = Path(__file__).with_name("amin_xauusd.pine")


def serve_tradingview_webhook(settings: dict[str, Any], bridge: TradingViewBridge | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tv_cfg = settings.get("tradingview", {})
    host = str(tv_cfg.get("host", "127.0.0.1"))
    port = int(tv_cfg.get("port", 8787))
    path = str(tv_cfg.get("path", "/webhook"))
    handler = _handler_class(bridge or TradingViewBridge(settings), path)
    server = ThreadingHTTPServer((host, port), handler)
    LOGGER.info("TradingView webhook listening on http://%s:%s%s", host, port, path)
    LOGGER.info("Pine script: %s", PINE_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("TradingView webhook stopped.")
    finally:
        server.server_close()


def _handler_class(bridge: TradingViewBridge, webhook_path: str):
    class TradingViewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - HTTP method name
            route = urlparse(self.path).path
            if route in {"/", "/health"}:
                self._send(200, {"status": "ok", "webhook": webhook_path, "pine": str(PINE_PATH)})
                return
            self._send(404, {"status": "error", "reason": "Not found."})

        def do_POST(self) -> None:  # noqa: N802 - HTTP method name
            route = urlparse(self.path).path
            if route != webhook_path:
                self._send(404, {"status": "error", "reason": "Not found."})
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length > 0 else b""
            headers = {key: value for key, value in self.headers.items()}
            try:
                result = bridge.handle_body(body, headers)
                self._send(200, result)
            except TradingViewAlertError as exc:
                self._send(400, {"status": "error", "reason": str(exc)})
            except LiveTradingDisabled as exc:
                self._send(403, {"status": "error", "reason": str(exc)})
            except Exception as exc:  # noqa: BLE001 - convert unexpected execution failures to HTTP
                LOGGER.exception("TradingView webhook failed")
                self._send(500, {"status": "error", "reason": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return TradingViewHandler

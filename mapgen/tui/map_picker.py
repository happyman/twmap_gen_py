"""Lightweight HTTP server that receives map-picker results from the browser.

The picker page at ``dev.happyman.idv.tw`` POSTs/GETs back the selected
region; this module spins up a one-shot server, opens the browser, and
blocks until the callback arrives (or times out / cancelled).
"""

from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ..settings import picker_timeout, picker_url

_server: HTTPServer | None = None
_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    """Handles the callback from the picker page."""

    server_result: dict | None = None
    server_event: threading.Event

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/" and parsed.query:
            params = parse_qs(parsed.query)
            self.__class__.server_result = {
                "x": _first(params, "x"),
                "y": _first(params, "y"),
                "shiftx": _first(params, "shiftx"),
                "shifty": _first(params, "shifty"),
                "ph": _first(params, "ph"),
                "datum": _first(params, "datum"),
                "title": _first(params, "title"),
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>OK, you may close this tab.</h2>"
                b"<p>Return to the TUI.</p></body></html>"
            )
            self.__class__.server_event.set()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress noisy request logs


def pick() -> dict | None:
    """Open the picker in a browser and wait for the callback.

    Returns a dict with keys ``x, y, shiftx, shifty, ph, datum, title``
    or *None* on timeout / user cancellation.
    """
    global _server  # noqa: PLW0603
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    with _lock:
        _server = server
    port = server.server_address[1]
    _Handler.server_event = threading.Event()

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    webbrowser.open(f"{picker_url()}{port}")

    _Handler.server_event.wait(timeout=picker_timeout())
    with _lock:
        _server = None
    server.shutdown()
    return _Handler.server_result


def stop() -> None:
    """Shut down the picker server if running (called on TUI exit)."""
    with _lock:
        srv = _server
    if srv is not None:
        srv.shutdown()


def _first(params: dict, key: str) -> str:
    vals = params.get(key, [""])
    return vals[0] if vals else ""

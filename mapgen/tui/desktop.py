"""Desktop wrapper: the same Textual app in a native window.

Serves the ``mapgen-tui`` app locally with ``textual-serve`` and opens it in a
``pywebview`` window. Because it is literally the same Textual app, the desktop
look is identical to the terminal one on Linux/macOS — this module just gives
Windows users a windowed entry point.

Run with ``python -m mapgen.tui.desktop`` or the ``mapgen-desktop`` script.
"""

from __future__ import annotations

import shlex
import socket
import sys
import threading
import time

from textual_serve.server import Server

SERVER_READY_POLL = 0.05
SERVER_READY_TIMEOUT = 15.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _server_command(argv: list[str] | None = None) -> str:
    """Shell command that launches the Textual app as a subprocess."""
    extra = f" {shlex.join(argv)}" if argv else ""
    return f'"{sys.executable}" -m mapgen.tui.app{extra}'


def _wait_until_ready(host: str, port: int) -> None:
    deadline = time.monotonic() + SERVER_READY_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(SERVER_READY_POLL)
    raise RuntimeError("textual-serve server did not become ready")


def main(argv: list[str] | None = None) -> int:
    import webview  # noqa: PLC0415  (only needed for the desktop entry point)

    args = list(argv) if argv is not None else sys.argv[1:]
    host = "127.0.0.1"
    port = _free_port()
    server = Server(command=_server_command(args), host=host, port=port)

    thread = threading.Thread(target=server.serve, name="textual-serve", daemon=True)
    thread.start()
    try:
        _wait_until_ready(host, port)
        webview.create_window(
            "Taiwan Map Generator",
            server.public_url,
            width=1100,
            height=800,
            min_size=(800, 600),
        )
        webview.start()
    finally:
        server.request_exit()
        thread.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import socket
import socketserver
import threading
from collections.abc import Callable

DEFAULT_EMERGENCY_HOST = "127.0.0.1"
DEFAULT_EMERGENCY_PORT = 8765


class _EmergencyTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[socketserver.BaseRequestHandler],
        on_rtl: Callable[[], str],
    ) -> None:
        super().__init__(server_address, handler_class)
        self.on_rtl = on_rtl


class _EmergencyRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        command = self.request.recv(1024).decode("utf-8", errors="replace").strip().upper()
        server = self.server
        if not isinstance(server, _EmergencyTCPServer):
            self.request.sendall(b"ERROR unsupported server\n")
            return

        if command == "RTL":
            response = server.on_rtl()
            self.request.sendall(f"OK {response}\n".encode("utf-8"))
            return

        self.request.sendall(b"ERROR unknown command\n")


class EmergencyCommandServer:
    """Tiny localhost command server used by external emergency scripts."""

    def __init__(
        self,
        on_rtl: Callable[[], str],
        host: str = DEFAULT_EMERGENCY_HOST,
        port: int = DEFAULT_EMERGENCY_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self._on_rtl = on_rtl
        self._server: _EmergencyTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._server = _EmergencyTCPServer(
            (self.host, self.port),
            _EmergencyRequestHandler,
            self._on_rtl,
        )
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None


def request_rtl_via_local_server(
    host: str = DEFAULT_EMERGENCY_HOST,
    port: int = DEFAULT_EMERGENCY_PORT,
    timeout_s: float = 1.0,
) -> str | None:
    """Ask a running mission process to send RTL, or return None if unavailable."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)
            sock.sendall(b"RTL\n")
            return sock.recv(1024).decode("utf-8", errors="replace").strip()
    except OSError:
        return None


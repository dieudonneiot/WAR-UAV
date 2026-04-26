"""Local browser dashboard for live flight control.

Usage:
    python scripts/web_dashboard.py
"""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from uav.control.emergency import (
    DEFAULT_EMERGENCY_HOST,
    DEFAULT_EMERGENCY_PORT,
    request_command_via_local_server,
    request_status_via_local_server,
)

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TEKNOFEST Flight Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f5f2;
      --panel: #ffffff;
      --ink: #202421;
      --muted: #667065;
      --line: #d7ddd2;
      --green: #2f7d4d;
      --green-dark: #205c38;
      --red: #a63b32;
      --amber: #996b1f;
      --shadow: 0 10px 26px rgba(31, 37, 30, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", system-ui, sans-serif;
    }

    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfa;
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .connection {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
      white-space: nowrap;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--amber);
    }

    .dot.online { background: var(--green); }
    .dot.offline { background: var(--red); }

    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(300px, 0.9fr) minmax(420px, 1.1fr);
      gap: 20px;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .status {
      padding: 20px;
    }

    .section-title {
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .metric {
      min-height: 72px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfa;
    }

    .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    .value {
      margin-top: 8px;
      font-size: 20px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }

    .actions {
      padding: 20px;
    }

    .button-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    button {
      min-height: 54px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }

    button:hover { border-color: var(--green); }
    button:disabled { cursor: wait; opacity: 0.6; }

    .primary {
      background: var(--green);
      border-color: var(--green);
      color: #ffffff;
    }

    .danger {
      background: var(--red);
      border-color: var(--red);
      color: #ffffff;
    }

    .mode-row {
      display: flex;
      gap: 10px;
      margin-top: 16px;
    }

    input {
      min-width: 0;
      flex: 1;
      height: 44px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 12px;
      color: var(--ink);
      font: inherit;
      text-transform: uppercase;
    }

    .mode-row button { min-height: 44px; padding: 0 18px; }

    .log {
      grid-column: 1 / -1;
      padding: 16px 20px;
      min-height: 130px;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      color: #303630;
      font: 13px Consolas, "SFMono-Regular", monospace;
    }

    @media (max-width: 840px) {
      header {
        height: auto;
        padding: 16px;
        align-items: flex-start;
        flex-direction: column;
      }

      main {
        grid-template-columns: 1fr;
        margin: 16px auto;
      }

      .button-grid,
      .metrics {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>TEKNOFEST Flight Dashboard</h1>
    <div class="connection"><span id="dot" class="dot"></span><span id="connection">checking</span></div>
  </header>
  <main>
    <section class="status">
      <h2 class="section-title">Status</h2>
      <div class="metrics">
        <div class="metric"><div class="label">Phase</div><div id="phase" class="value">--</div></div>
        <div class="metric"><div class="label">Mode</div><div id="mode" class="value">--</div></div>
        <div class="metric"><div class="label">Altitude</div><div id="alt" class="value">--</div></div>
        <div class="metric"><div class="label">Waypoint</div><div id="wp_dist" class="value">--</div></div>
        <div class="metric"><div class="label">Latitude</div><div id="lat" class="value">--</div></div>
        <div class="metric"><div class="label">Longitude</div><div id="lon" class="value">--</div></div>
      </div>
    </section>
    <section class="actions">
      <h2 class="section-title">Controls</h2>
      <div class="button-grid">
        <button class="primary" data-command="MODE TAKEOFF">TAKEOFF</button>
        <button data-command="MODE GUIDED">GUIDED</button>
        <button data-command="LOITER">LOITER</button>
        <button class="danger" data-command="RTL">RTL</button>
      </div>
      <div class="mode-row">
        <input id="modeInput" aria-label="Mode" value="AUTO">
        <button id="modeButton">MODE</button>
      </div>
    </section>
    <section class="log">
      <h2 class="section-title">Event Log</h2>
      <pre id="log"></pre>
    </section>
  </main>
  <script>
    const fields = ["phase", "mode", "lat", "lon", "alt", "wp_dist"];
    const logEl = document.getElementById("log");
    const dotEl = document.getElementById("dot");
    const connectionEl = document.getElementById("connection");

    function addLog(message) {
      const stamp = new Date().toLocaleTimeString();
      logEl.textContent = `[${stamp}] ${message}\\n` + logEl.textContent;
    }

    function setConnection(ok) {
      dotEl.className = `dot ${ok ? "online" : "offline"}`;
      connectionEl.textContent = ok ? "mission server online" : "mission server offline";
    }

    async function refreshStatus() {
      try {
        const response = await fetch("/api/status");
        const data = await response.json();
        setConnection(data.ok);
        for (const key of fields) {
          document.getElementById(key).textContent = data.fields[key] || "--";
        }
      } catch (error) {
        setConnection(false);
      }
    }

    async function sendCommand(command) {
      document.querySelectorAll("button").forEach((button) => button.disabled = true);
      try {
        const response = await fetch("/api/command", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({command})
        });
        const data = await response.json();
        addLog(data.response || data.error || "No response");
        await refreshStatus();
      } catch (error) {
        addLog(String(error));
      } finally {
        document.querySelectorAll("button").forEach((button) => button.disabled = false);
      }
    }

    document.querySelectorAll("[data-command]").forEach((button) => {
      button.addEventListener("click", () => sendCommand(button.dataset.command));
    });

    document.getElementById("modeButton").addEventListener("click", () => {
      const mode = document.getElementById("modeInput").value.trim().toUpperCase();
      if (mode) sendCommand(`MODE ${mode}`);
    });

    refreshStatus();
    setInterval(refreshStatus, 1000);
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local flight-control web dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard port.")
    parser.add_argument("--command-host", default=DEFAULT_EMERGENCY_HOST,
                        help=f"Running mission command host (default: {DEFAULT_EMERGENCY_HOST})")
    parser.add_argument("--command-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Running mission command port (default: {DEFAULT_EMERGENCY_PORT})")
    args = parser.parse_args()

    handler = make_handler(args.command_host, args.command_port)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Flight dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def make_handler(command_host: str, command_port: int) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/":
                self._send_html(DASHBOARD_HTML)
            elif self.path == "/api/status":
                response = request_status_via_local_server(command_host, command_port, timeout_s=0.4)
                if response is None:
                    self._send_json({"ok": False, "fields": {}, "response": None})
                    return
                status = strip_ok(response)
                self._send_json({"ok": True, "fields": parse_status(status), "response": status})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path != "/api/command":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            command = str(payload.get("command", "")).strip().upper()
            if command not in {"RTL", "LOITER", "MODE TAKEOFF", "MODE GUIDED"} and not command.startswith("MODE "):
                self._send_json({"ok": False, "error": "Unsupported command"}, HTTPStatus.BAD_REQUEST)
                return

            response = request_command_via_local_server(
                command,
                command_host,
                command_port,
                timeout_s=1.0,
            )
            if response is None:
                self._send_json({"ok": False, "error": "Mission command server offline"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._send_json({"ok": response.startswith("OK "), "response": strip_ok(response)})

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, body: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return DashboardHandler


def strip_ok(response: str) -> str:
    return response[3:] if response.startswith("OK ") else response


def parse_status(status: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in status.split():
        key, separator, value = item.partition("=")
        if separator:
            fields[key] = value
    return fields


if __name__ == "__main__":
    main()


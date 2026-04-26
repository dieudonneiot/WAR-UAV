"""Local browser dashboard for live flight control and mission management.

Usage:
    python scripts/web_dashboard.py
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from uav.control.emergency import (
    DEFAULT_EMERGENCY_HOST,
    DEFAULT_EMERGENCY_PORT,
    request_command_via_local_server,
    request_status_via_local_server,
)

SCRIPTS_DIR = Path(__file__).parent

ALLOWED_SCRIPTS: frozenset[str] = frozenset({
    "run_square_mission.py",
    "run_square_simulation.py",
    "run_visual_simulation.py",
    "run_vision_pipeline.py",
})


class ProcessManager:
    """Manages a single child process: launch, capture output, stop."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._logs: collections.deque[dict[str, Any]] = collections.deque(maxlen=500)

    def launch(self, script: str, extra_args: list[str]) -> dict[str, Any]:
        if script not in ALLOWED_SCRIPTS:
            return {"ok": False, "error": f"Unknown script: {script!r}"}
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"ok": False, "error": "A process is already running — stop it first."}
            cmd = [sys.executable, "-u", str(SCRIPTS_DIR / script)] + extra_args
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            self._proc = proc
            self._add_log(f"[dashboard] Started pid={proc.pid}: {' '.join(cmd)}")
            threading.Thread(target=self._read_output, args=(proc,), daemon=True).start()
        return {"ok": True}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return {"ok": False, "error": "No process is running"}
            self._proc.terminate()
            self._add_log("[dashboard] SIGTERM sent — process stopping…")
        return {"ok": True}

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is None:
                return {"running": False, "pid": None, "returncode": None}
            rc = self._proc.poll()
            return {"running": rc is None, "pid": self._proc.pid, "returncode": rc}

    def logs_since(self, since: float) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._logs if e["ts"] > since]

    def _add_log(self, line: str) -> None:
        self._logs.append({"ts": time.time(), "line": line})

    def _read_output(self, proc: subprocess.Popen[str]) -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._add_log(line.rstrip())
        except Exception:
            pass
        self._add_log(f"[dashboard] Process exited (code {proc.wait()})")


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TEKNOFEST Mission Control</title>
  <style>
    :root {
      --bg:#f4f5f2; --panel:#ffffff; --ink:#202421; --muted:#667065; --line:#d7ddd2;
      --green:#2f7d4d; --green-d:#205c38; --red:#a63b32; --amber:#996b1f;
      --blue:#1a5fb4; --blue-d:#1245a0;
      --shadow:0 10px 26px rgba(31,37,30,.08);
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{min-height:100vh;background:var(--bg);color:var(--ink);
         font-family:"Segoe UI",system-ui,sans-serif;font-size:14px;line-height:1.4;}
    /* header */
    header{height:54px;display:flex;align-items:center;gap:12px;padding:0 22px;
           border-bottom:1px solid var(--line);background:#fbfcfa;}
    header h1{font-size:17px;font-weight:700;flex:1;}
    .badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;
           color:var(--muted);white-space:nowrap;}
    .proc-badge{padding:3px 10px;border-radius:20px;border:1px solid var(--line);background:#f8f9f7;}
    .proc-badge.running{color:var(--green);border-color:#a8d5b8;background:#f0faf4;}
    .dot{width:8px;height:8px;border-radius:50%;background:var(--amber);flex-shrink:0;}
    .dot.on{background:var(--green);} .dot.off{background:var(--red);}
    /* layout */
    main{width:min(1300px,calc(100vw - 32px));margin:16px auto;display:grid;
         grid-template-columns:minmax(210px,1fr) minmax(210px,1fr) minmax(290px,1.4fr);gap:14px;}
    .s-status{grid-column:1;} .s-controls{grid-column:2;} .s-launch{grid-column:3;}
    .s-proclog,.s-evtlog{grid-column:1/-1;}
    section{background:var(--panel);border:1px solid var(--line);border-radius:8px;
            box-shadow:var(--shadow);padding:14px 16px;}
    .sec-title{font-size:11px;font-weight:700;text-transform:uppercase;
               letter-spacing:.05em;color:var(--muted);margin-bottom:12px;}
    /* metrics */
    .metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;}
    .metric{padding:9px 10px;border:1px solid var(--line);border-radius:6px;background:#fbfcfa;}
    .label{font-size:10px;font-weight:700;text-transform:uppercase;color:var(--muted);}
    .value{margin-top:5px;font-size:17px;font-weight:700;overflow-wrap:anywhere;}
    /* buttons */
    button{border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);
           cursor:pointer;font:inherit;font-weight:600;font-size:13px;height:38px;padding:0 12px;}
    button:hover:not(:disabled){border-color:#888;}
    button:disabled{opacity:.5;cursor:not-allowed;}
    .btn-g{background:var(--green);border-color:var(--green);color:#fff;}
    .btn-g:hover:not(:disabled){background:var(--green-d);}
    .btn-r{background:var(--red);border-color:var(--red);color:#fff;}
    .btn-b{background:var(--blue);border-color:var(--blue);color:#fff;}
    .btn-b:hover:not(:disabled){background:var(--blue-d);}
    /* controls */
    .btn-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;}
    .btn-grid button{min-height:42px;}
    .mode-row{display:flex;gap:8px;margin-top:10px;}
    input,select{border:1px solid var(--line);border-radius:6px;padding:0 9px;
                 font:inherit;font-size:13px;color:var(--ink);background:#fff;height:34px;}
    input:focus,select:focus{outline:none;border-color:var(--blue);}
    .mode-row input{flex:1;min-width:0;text-transform:uppercase;}
    .mode-row button{height:34px;}
    /* launch tabs */
    .tab-bar{display:flex;gap:2px;margin-bottom:12px;
             border-bottom:1px solid var(--line);}
    .tab-bar button{border:none;border-bottom:2px solid transparent;border-radius:0;
                    background:transparent;color:var(--muted);height:32px;
                    padding:0 10px;font-size:12px;}
    .tab-bar button.active{color:var(--blue);border-bottom-color:var(--blue);}
    .tab-bar button:hover:not(.active):not(:disabled){color:var(--ink);}
    .tab-content{display:none;} .tab-content.active{display:block;}
    /* form fields */
    .fields{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:8px;}
    .field{display:flex;flex-direction:column;gap:4px;}
    .field label{font-size:10px;font-weight:700;text-transform:uppercase;color:var(--muted);}
    .field input,.field select{width:100%;}
    .field-wide{grid-column:1/-1;}
    .check-row{display:flex;align-items:center;gap:6px;font-size:12px;margin-top:2px;color:var(--muted);}
    .check-row input[type="checkbox"]{width:14px;height:14px;margin:0;}
    .launch-actions{display:flex;gap:8px;margin-top:10px;}
    .launch-actions button{flex:1;}
    /* log panels */
    .log-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;}
    .log-header .sec-title{margin:0;}
    .log-header button{height:24px;padding:0 9px;font-size:11px;}
    .log-box{max-height:300px;overflow-y:auto;background:#f8f9f7;
             border:1px solid var(--line);border-radius:6px;padding:9px 11px;}
    pre{white-space:pre-wrap;word-break:break-all;
        font:12px Consolas,"SFMono-Regular",monospace;line-height:1.5;color:#303630;}
    @media(max-width:860px){
      main{grid-template-columns:1fr;}
      .s-status,.s-controls,.s-launch,.s-proclog,.s-evtlog{grid-column:1;}
    }
  </style>
</head>
<body>
<header>
  <h1>TEKNOFEST Mission Control</h1>
  <div id="proc-badge" class="badge proc-badge">
    <span class="dot" id="proc-dot"></span>
    <span id="proc-text">idle</span>
  </div>
  <div class="badge">
    <span class="dot" id="conn-dot"></span>
    <span id="conn-text">checking…</span>
  </div>
</header>

<main>
  <!-- Telemetry -->
  <section class="s-status">
    <p class="sec-title">Telemetry</p>
    <div class="metrics">
      <div class="metric"><div class="label">Phase</div><div id="phase" class="value">--</div></div>
      <div class="metric"><div class="label">Mode</div><div id="mode" class="value">--</div></div>
      <div class="metric"><div class="label">Altitude</div><div id="alt" class="value">--</div></div>
      <div class="metric"><div class="label">WP Dist</div><div id="wp_dist" class="value">--</div></div>
      <div class="metric"><div class="label">Latitude</div><div id="lat" class="value">--</div></div>
      <div class="metric"><div class="label">Longitude</div><div id="lon" class="value">--</div></div>
    </div>
  </section>

  <!-- Flight Controls -->
  <section class="s-controls">
    <p class="sec-title">Flight Controls</p>
    <div class="btn-grid">
      <button class="btn-g" data-command="MODE TAKEOFF">TAKEOFF</button>
      <button data-command="MODE GUIDED">GUIDED</button>
      <button data-command="LOITER">LOITER</button>
      <button class="btn-r" data-command="RTL">RTL</button>
    </div>
    <div class="mode-row">
      <input id="modeInput" value="AUTO" aria-label="Flight mode">
      <button id="modeBtn">SET MODE</button>
    </div>
  </section>

  <!-- Launch Panel -->
  <section class="s-launch">
    <p class="sec-title">Launch Script</p>
    <div class="tab-bar">
      <button class="tab active" data-tab="mavlink">MAVLink Mission</button>
      <button class="tab" data-tab="sim">Simulation</button>
      <button class="tab" data-tab="vision">Vision</button>
    </div>

    <!-- MAVLink Mission -->
    <div class="tab-content active" id="tab-mavlink">
      <div class="fields">
        <div class="field">
          <label>Shape</label>
          <select id="m-shape">
            <option value="square">Square</option>
            <option value="triangle">Triangle</option>
            <option value="circle">Circle</option>
            <option value="line">Line</option>
          </select>
        </div>
        <div class="field">
          <label>Control</label>
          <select id="m-control">
            <option value="guided">Guided</option>
            <option value="auto">Auto</option>
          </select>
        </div>
        <div class="field">
          <label>Size (m)</label>
          <input type="number" id="m-size" value="500" min="50" max="5000">
        </div>
        <div class="field">
          <label>Alt (m)</label>
          <input type="number" id="m-alt" value="50" min="10" max="500">
        </div>
        <div class="field field-wide">
          <label>MAVLink Connection</label>
          <input type="text" id="m-conn" value="udpin:0.0.0.0:14550">
        </div>
      </div>
      <div class="launch-actions">
        <button class="btn-b" id="launch-mavlink">LAUNCH</button>
        <button class="btn-r stop-btn">STOP</button>
      </div>
    </div>

    <!-- Simulation -->
    <div class="tab-content" id="tab-sim">
      <div class="fields">
        <div class="field">
          <label>Side (m)</label>
          <input type="number" id="s-side" value="500" min="50" max="5000">
        </div>
        <div class="field">
          <label>Alt (m)</label>
          <input type="number" id="s-alt" value="50" min="10" max="500">
        </div>
        <div class="field">
          <label>Speed (m/s)</label>
          <input type="number" id="s-speed" value="20" min="1" max="100">
        </div>
        <div class="field">
          <label>Frame delay (ms)</label>
          <input type="number" id="s-delay" value="50" min="10" max="500">
        </div>
      </div>
      <label class="check-row">
        <input type="checkbox" id="s-headless"> Save PNG only (headless)
      </label>
      <div class="launch-actions">
        <button class="btn-b" id="launch-sim">LAUNCH SIM</button>
        <button class="btn-r stop-btn">STOP</button>
      </div>
    </div>

    <!-- Vision Pipeline -->
    <div class="tab-content" id="tab-vision">
      <div class="fields">
        <div class="field">
          <label>Source</label>
          <input type="text" id="v-source" value="0" placeholder="0=webcam or path">
        </div>
        <div class="field">
          <label>Model</label>
          <input type="text" id="v-model" value="yolov8n.pt">
        </div>
        <div class="field">
          <label>Confidence</label>
          <input type="number" id="v-conf" value="0.25" min="0.05" max="0.99" step="0.05">
        </div>
        <div class="field">
          <label>Lock time (s)</label>
          <input type="number" id="v-lock" value="4" min="1" max="30">
        </div>
      </div>
      <label class="check-row">
        <input type="checkbox" id="v-headless"> Save PNG only (headless)
      </label>
      <div class="launch-actions">
        <button class="btn-b" id="launch-vision">LAUNCH VISION</button>
        <button class="btn-r stop-btn">STOP</button>
      </div>
    </div>
  </section>

  <!-- Process Output -->
  <section class="s-proclog">
    <div class="log-header">
      <p class="sec-title">Process Output</p>
      <button id="clear-proc">Clear</button>
    </div>
    <div class="log-box" id="proc-box">
      <pre id="proclog">Waiting for a process to start…</pre>
    </div>
  </section>

  <!-- Command Log -->
  <section class="s-evtlog">
    <div class="log-header">
      <p class="sec-title">Command Log</p>
      <button id="clear-evt">Clear</button>
    </div>
    <div class="log-box" id="evt-box">
      <pre id="evtlog"></pre>
    </div>
  </section>
</main>

<script>
  // Telemetry
  const TEL = ["phase","mode","lat","lon","alt","wp_dist"];
  const connDot   = document.getElementById("conn-dot");
  const connText  = document.getElementById("conn-text");
  const procBadge = document.getElementById("proc-badge");
  const procDot   = document.getElementById("proc-dot");
  const procText  = document.getElementById("proc-text");

  function setConn(ok) {
    connDot.className    = "dot " + (ok ? "on" : "off");
    connText.textContent = ok ? "mission server online" : "mission server offline";
  }

  function setProcStatus(s) {
    if (s.running) {
      procBadge.className  = "badge proc-badge running";
      procDot.className    = "dot on";
      procText.textContent = "running  pid=" + s.pid;
    } else {
      procBadge.className  = "badge proc-badge";
      procDot.className    = "dot off";
      procText.textContent = s.returncode === null ? "idle" : "exited  code=" + s.returncode;
    }
  }

  async function refreshTel() {
    try {
      const d = await (await fetch("/api/status")).json();
      setConn(d.ok);
      TEL.forEach(k => {
        document.getElementById(k).textContent = (d.fields && d.fields[k]) || "--";
      });
    } catch { setConn(false); }
  }

  async function refreshProcStatus() {
    try {
      const d = await (await fetch("/api/process/status")).json();
      setProcStatus(d);
    } catch {}
  }

  // Flight commands
  const evtLog = document.getElementById("evtlog");

  function addEvt(msg) {
    const t = new Date().toLocaleTimeString();
    evtLog.textContent = "[" + t + "] " + msg + "\\n" + evtLog.textContent;
  }

  async function sendCmd(cmd) {
    document.querySelectorAll("[data-command],#modeBtn").forEach(b => b.disabled = true);
    try {
      const d = await (await fetch("/api/command", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({command: cmd})
      })).json();
      addEvt(d.response || d.error || "no response");
      refreshTel();
    } catch(e) { addEvt(String(e)); }
    finally {
      document.querySelectorAll("[data-command],#modeBtn").forEach(b => b.disabled = false);
    }
  }

  document.querySelectorAll("[data-command]").forEach(b =>
    b.addEventListener("click", () => sendCmd(b.dataset.command))
  );
  document.getElementById("modeBtn").addEventListener("click", () => {
    const m = document.getElementById("modeInput").value.trim().toUpperCase();
    if (m) sendCmd("MODE " + m);
  });

  // Tab switching
  document.querySelectorAll(".tab").forEach(btn =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    })
  );

  // Process management
  async function stopProc() {
    try {
      const d = await (await fetch("/api/process/stop", {method: "POST"})).json();
      addEvt(d.ok ? "Stop signal sent." : "Stop failed: " + d.error);
    } catch(e) { addEvt(String(e)); }
  }

  async function launch(script, args) {
    try {
      const d = await (await fetch("/api/process/launch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({script, args})
      })).json();
      addEvt(d.ok ? "Launched " + script : "Launch failed: " + d.error);
    } catch(e) { addEvt(String(e)); }
  }

  document.querySelectorAll(".stop-btn").forEach(b => b.addEventListener("click", stopProc));

  document.getElementById("launch-mavlink").addEventListener("click", () =>
    launch("run_square_mission.py", [
      "--shape",        document.getElementById("m-shape").value,
      "--control-mode", document.getElementById("m-control").value,
      "--size-m",       document.getElementById("m-size").value,
      "--alt-m",        document.getElementById("m-alt").value,
      "--connection",   document.getElementById("m-conn").value,
    ])
  );

  document.getElementById("launch-sim").addEventListener("click", () => {
    const args = [
      "--side-m",    document.getElementById("s-side").value,
      "--alt-m",     document.getElementById("s-alt").value,
      "--speed-mps", document.getElementById("s-speed").value,
      "--delay-ms",  document.getElementById("s-delay").value,
    ];
    if (document.getElementById("s-headless").checked) args.push("--headless");
    launch("run_square_simulation.py", args);
  });

  document.getElementById("launch-vision").addEventListener("click", () => {
    const args = [
      "--source",          document.getElementById("v-source").value,
      "--model",           document.getElementById("v-model").value,
      "--confidence",      document.getElementById("v-conf").value,
      "--lock-duration-s", document.getElementById("v-lock").value,
    ];
    if (document.getElementById("v-headless").checked) args.push("--headless");
    launch("run_vision_pipeline.py", args);
  });

  // Process log polling
  const procLog = document.getElementById("proclog");
  const procBox = document.getElementById("proc-box");
  let lastTs = 0;
  let firstEntry = true;

  function atBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 50; }

  async function refreshProcLog() {
    try {
      const d = await (await fetch("/api/process/logs?since=" + lastTs)).json();
      if (!d.entries || d.entries.length === 0) return;
      if (firstEntry) { procLog.textContent = ""; firstEntry = false; }
      const wasBottom = atBottom(procBox);
      d.entries.forEach(e => {
        if (e.ts > lastTs) lastTs = e.ts;
        procLog.textContent += e.line + "\\n";
      });
      if (wasBottom) procBox.scrollTop = procBox.scrollHeight;
    } catch {}
  }

  document.getElementById("clear-proc").addEventListener("click", () => {
    procLog.textContent = ""; firstEntry = true;
  });
  document.getElementById("clear-evt").addEventListener("click", () => {
    evtLog.textContent = "";
  });

  // Start polling
  refreshTel();
  refreshProcLog();
  refreshProcStatus();
  setInterval(refreshTel,        1000);
  setInterval(refreshProcLog,     500);
  setInterval(refreshProcStatus, 1000);
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Mission Control web dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host.")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard port.")
    parser.add_argument("--command-host", default=DEFAULT_EMERGENCY_HOST,
                        help=f"Running mission command host (default: {DEFAULT_EMERGENCY_HOST})")
    parser.add_argument("--command-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Running mission command port (default: {DEFAULT_EMERGENCY_PORT})")
    args = parser.parse_args()

    proc_mgr = ProcessManager()
    handler = make_handler(args.command_host, args.command_port, proc_mgr)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Mission Control dashboard -> http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def make_handler(
    command_host: str, command_port: int, proc_mgr: ProcessManager
) -> type[BaseHTTPRequestHandler]:
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
            elif self.path.startswith("/api/process/logs"):
                qs = parse_qs(urlparse(self.path).query)
                since = float(qs.get("since", ["0"])[0])
                self._send_json({"ok": True, "entries": proc_mgr.logs_since(since)})
            elif self.path == "/api/process/status":
                self._send_json({"ok": True, **proc_mgr.status()})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path == "/api/command":
                payload = self._read_json()
                command = str(payload.get("command", "")).strip().upper()
                if (command not in {"RTL", "LOITER", "MODE TAKEOFF", "MODE GUIDED"}
                        and not command.startswith("MODE ")):
                    self._send_json({"ok": False, "error": "Unsupported command"}, HTTPStatus.BAD_REQUEST)
                    return
                response = request_command_via_local_server(
                    command, command_host, command_port, timeout_s=1.0,
                )
                if response is None:
                    self._send_json(
                        {"ok": False, "error": "Mission command server offline"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                self._send_json({"ok": response.startswith("OK "), "response": strip_ok(response)})

            elif self.path == "/api/process/launch":
                payload = self._read_json()
                script = str(payload.get("script", ""))
                raw_args = payload.get("args", [])
                if not isinstance(raw_args, list):
                    self._send_json({"ok": False, "error": "args must be a list"}, HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(proc_mgr.launch(script, [str(a) for a in raw_args]))

            elif self.path == "/api/process/stop":
                self._send_json(proc_mgr.stop())

            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

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

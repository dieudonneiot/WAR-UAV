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
PROJECT_ROOT = SCRIPTS_DIR.parent

ALLOWED_SCRIPTS: frozenset[str] = frozenset({
    "run_square_mission.py",
    "run_square_simulation.py",
    "run_visual_simulation.py",
    "run_vision_pipeline.py",
    "run_air_defense_simulation.py",
    "generate_air_defense_figures.py",
    "run_gazebo_air_defense.py",
    "run_gazebo_setup.py",
    "run_sitl_wsl.py",
    "run_wsl_cmd.py",
    "run_simulation_test.py",
    "telemetry.py",
    "emergency_rtl.py",
    "loiter.py",
    "check_env.py",
})

_ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "RTL", "LOITER", "MODE TAKEOFF", "MODE GUIDED", "ARM", "DISARM",
})


class ProcessManager:
    """Manages a single child process: launch, capture output, stop."""

    def __init__(
        self,
        shared_logs: collections.deque | None = None,
        log_prefix: str = "",
    ) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._prefix = log_prefix
        self._logs: collections.deque[dict[str, Any]] = (
            shared_logs if shared_logs is not None else collections.deque(maxlen=1000)
        )

    def launch(self, script: str, extra_args: list[str]) -> dict[str, Any]:
        if script not in ALLOWED_SCRIPTS:
            return {"ok": False, "error": f"Unknown script: {script!r}"}
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._add_log("[dashboard] Auto-stopping running process…")
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2.0)
                self._add_log("[dashboard] Previous process stopped.")
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
        self._logs.append({"ts": time.time(), "line": self._prefix + line})

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
      --bg:#f0f2ee; --panel:#ffffff; --ink:#1e201d; --muted:#5e6a5c; --line:#d4dace;
      --green:#2a7a47; --green-d:#1d5c33; --red:#b03530; --red-d:#872820;
      --amber:#8f6218; --blue:#1450a8; --blue-d:#0f3d82;
      --purple:#5e35b1; --teal:#0d7377;
      --shadow:0 8px 24px rgba(20,30,20,.07);
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{min-height:100vh;background:var(--bg);color:var(--ink);
         font-family:"Segoe UI",system-ui,sans-serif;font-size:14px;line-height:1.45;}

    /* ── header ──────────────────────────────────────────────────────────── */
    header{height:52px;display:flex;align-items:center;gap:10px;padding:0 18px;
           border-bottom:1px solid var(--line);background:#f8faf6;flex-wrap:wrap;}
    header h1{font-size:15px;font-weight:700;flex:1;white-space:nowrap;letter-spacing:.01em;}
    .badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;
           color:var(--muted);white-space:nowrap;}
    .proc-badge{padding:3px 10px;border-radius:20px;border:1px solid var(--line);background:#f5f7f3;}
    .proc-badge.running{color:var(--green);border-color:#9fd0b2;background:#edf8f2;}
    .dot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex-shrink:0;}
    .dot.on{background:var(--green);} .dot.off{background:var(--red);}
    #hdr-rtl{height:28px;padding:0 14px;font-size:11px;font-weight:700;letter-spacing:.03em;}

    /* ── layout ──────────────────────────────────────────────────────────── */
    main{width:min(1440px,calc(100vw - 24px));margin:14px auto;
         display:grid;
         grid-template-columns:minmax(195px,1fr) minmax(195px,1fr) minmax(310px,1.6fr);
         gap:12px;}
    .s-status{grid-column:1;} .s-controls{grid-column:2;} .s-launch{grid-column:3;}
    .s-proclog,.s-evtlog,.s-preview{grid-column:1/-1;}
    section{background:var(--panel);border:1px solid var(--line);border-radius:9px;
            box-shadow:var(--shadow);padding:13px 15px;}
    .sec-title{font-size:10.5px;font-weight:700;text-transform:uppercase;
               letter-spacing:.06em;color:var(--muted);margin-bottom:10px;}

    /* ── metrics ─────────────────────────────────────────────────────────── */
    .metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;}
    .metric{padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:#f9fbf8;}
    .m-label{font-size:9.5px;font-weight:700;text-transform:uppercase;color:var(--muted);}
    .m-value{margin-top:3px;font-size:15px;font-weight:700;overflow-wrap:anywhere;}
    .m-value.armed{color:var(--green);}
    .m-value.disarmed{color:var(--red);}

    /* ── buttons ─────────────────────────────────────────────────────────── */
    button{border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);
           cursor:pointer;font:inherit;font-weight:600;font-size:13px;
           height:34px;padding:0 12px;transition:filter .12s;}
    button:hover:not(:disabled){filter:brightness(.91);}
    button:active:not(:disabled){filter:brightness(.83);}
    button:disabled{opacity:.38;cursor:not-allowed;}
    .btn-g{background:var(--green);border-color:var(--green);color:#fff;}
    .btn-r{background:var(--red);border-color:var(--red);color:#fff;}
    .btn-b{background:var(--blue);border-color:var(--blue);color:#fff;}
    .btn-a{background:var(--amber);border-color:var(--amber);color:#fff;}
    .btn-p{background:var(--purple);border-color:var(--purple);color:#fff;}
    .btn-t{background:var(--teal);border-color:var(--teal);color:#fff;}

    /* ── controls ────────────────────────────────────────────────────────── */
    .btn-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;}
    .btn-grid button{min-height:36px;}
    input,select{border:1px solid var(--line);border-radius:6px;padding:0 8px;
                 font:inherit;font-size:13px;color:var(--ink);background:#fff;height:30px;}
    input:focus,select:focus{outline:none;border-color:var(--blue);}
    .mode-row{display:flex;gap:6px;margin-top:8px;}
    .mode-row input{flex:1;min-width:0;text-transform:uppercase;}
    .mode-row button{height:30px;}

    /* ── launch panel tabs ───────────────────────────────────────────────── */
    .tab-bar{display:flex;gap:1px;margin-bottom:10px;
             border-bottom:2px solid var(--line);flex-wrap:wrap;}
    .tab-bar button{border:none;border-bottom:2px solid transparent;
                    margin-bottom:-2px;border-radius:0;
                    background:transparent;color:var(--muted);
                    height:28px;padding:0 9px;font-size:11px;font-weight:600;}
    .tab-bar button.active{color:var(--blue);border-bottom-color:var(--blue);}
    .tab-bar button:hover:not(.active){color:var(--ink);filter:none;}
    .tab-content{display:none;} .tab-content.active{display:block;}

    /* ── form fields ─────────────────────────────────────────────────────── */
    .fields{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-bottom:7px;}
    .field{display:flex;flex-direction:column;gap:3px;}
    .field label{font-size:9.5px;font-weight:700;text-transform:uppercase;color:var(--muted);}
    .field input,.field select{width:100%;}
    .field-wide{grid-column:1/-1;}
    .check-row{display:flex;align-items:center;gap:6px;font-size:11.5px;
               color:var(--muted);margin-top:2px;}
    .check-row input[type="checkbox"]{width:13px;height:13px;margin:0;cursor:pointer;}
    .launch-actions{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;}
    .launch-actions button{flex:1;min-width:70px;}

    /* ── sub-sections ────────────────────────────────────────────────────── */
    .subsec{border:1px solid var(--line);border-radius:7px;padding:10px;margin-bottom:8px;}
    .subsec:last-child{margin-bottom:0;}
    .subsec-title{font-size:10px;font-weight:700;text-transform:uppercase;
                  letter-spacing:.05em;color:var(--muted);margin-bottom:7px;}

    /* ── log panels ──────────────────────────────────────────────────────── */
    .log-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px;}
    .log-header .sec-title{margin:0;}
    .log-header button{height:22px;padding:0 9px;font-size:11px;}
    .log-box{max-height:270px;overflow-y:auto;background:#f7f9f6;
             border:1px solid var(--line);border-radius:6px;padding:8px 11px;}
    pre{white-space:pre-wrap;word-break:break-all;
        font:12px Consolas,"SFMono-Regular",monospace;line-height:1.55;color:#2a2e29;}

    /* ── image preview ───────────────────────────────────────────────────── */
    .img-wrap{text-align:center;background:#f0f2ee;border-radius:6px;
              border:1px solid var(--line);padding:8px;min-height:50px;}
    .img-wrap img{max-width:100%;max-height:360px;border-radius:5px;
                  display:block;margin:0 auto;}
    .img-placeholder{color:var(--muted);font-size:12px;padding:16px;}

    /* ── direct-cmd strip ────────────────────────────────────────────────── */
    .dstrip{margin-top:9px;padding-top:9px;border-top:1px solid var(--line);}
    .dstrip-row{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px;}
    .dstrip-row button{flex:1;min-width:70px;height:28px;font-size:11px;}

    @media(max-width:860px){
      main{grid-template-columns:1fr;}
      .s-status,.s-controls,.s-launch,.s-proclog,.s-evtlog,.s-preview{grid-column:1;}
    }
  </style>
</head>
<body>
<header>
  <h1>&#9992; TEKNOFEST Mission Control</h1>
  <div id="proc-badge" class="badge proc-badge">
    <span class="dot" id="proc-dot"></span>
    <span id="proc-text">idle</span>
  </div>
  <div id="hdr-sitl-badge" class="badge proc-badge" style="display:none;">
    <span class="dot on" id="hdr-sitl-dot"></span>
    <span id="hdr-sitl-text">SITL</span>
  </div>
  <div class="badge">
    <span class="dot" id="conn-dot"></span>
    <span id="conn-text">checking&#8230;</span>
  </div>
  <button class="btn-r" id="hdr-rtl" title="Emergency Return-to-Launch">&#9888; EMERGENCY RTL</button>
</header>

<main>
  <!-- ── Telemetry ──────────────────────────────────────────────────────── -->
  <section class="s-status">
    <p class="sec-title">Telemetry</p>
    <div class="metrics">
      <div class="metric"><div class="m-label">Phase</div><div id="phase" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Mode</div><div id="mode" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Armed</div><div id="armed" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Altitude (m)</div><div id="alt" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">WP Dist (m)</div><div id="wp_dist" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Gnd Speed</div><div id="groundspeed" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Latitude</div><div id="lat" class="m-value">--</div></div>
      <div class="metric"><div class="m-label">Longitude</div><div id="lon" class="m-value">--</div></div>
    </div>
    <button class="btn-t" id="btn-tel-quick"
            style="width:100%;margin-top:9px;height:28px;font-size:11px;">
      &#9654; Stream Telemetry
    </button>
  </section>

  <!-- ── Flight Controls ───────────────────────────────────────────────── -->
  <section class="s-controls">
    <p class="sec-title">Flight Controls</p>
    <div class="btn-grid">
      <button class="btn-g" data-command="MODE TAKEOFF">TAKEOFF</button>
      <button data-command="MODE GUIDED">GUIDED</button>
      <button data-command="LOITER">LOITER</button>
      <button class="btn-r" data-command="RTL">RTL</button>
      <button class="btn-a" data-command="ARM">ARM</button>
      <button data-command="DISARM">DISARM</button>
    </div>
    <div class="mode-row">
      <input id="modeInput" value="AUTO" aria-label="Flight mode">
      <button id="modeBtn">SET MODE</button>
    </div>

    <div class="dstrip">
      <p class="subsec-title" style="margin-bottom:5px;">Direct Script Commands</p>
      <div class="field" style="margin-bottom:6px;">
        <label>Connection</label>
        <input type="text" id="direct-conn" value="udpin:0.0.0.0:14550">
      </div>
      <label class="check-row" style="margin-bottom:6px;">
        <input type="checkbox" id="direct-mode"> Direct MAVLink (bypass cmd server)
      </label>
      <div class="dstrip-row">
        <button id="btn-rtl-direct" class="btn-r" title="Run emergency_rtl.py directly">&#8629; RTL</button>
        <button id="btn-loiter-direct" title="Run loiter.py directly">&#8635; Loiter</button>
        <button id="btn-checkenv" class="btn-t" title="Run check_env.py">&#10003; Env</button>
      </div>
    </div>
  </section>

  <!-- ── Launch Panel ──────────────────────────────────────────────────── -->
  <section class="s-launch">
    <p class="sec-title">Launch Scripts</p>
    <div class="tab-bar">
      <button class="tab active" data-tab="mission">Mission</button>
      <button class="tab" data-tab="sim">Simulation</button>
      <button class="tab" data-tab="vision">Vision</button>
      <button class="tab" data-tab="airdefense">Air Defense</button>
      <button class="tab" data-tab="gazebo">Gazebo SITL</button>
      <button class="tab" data-tab="wsl">WSL Console</button>
      <button class="tab" data-tab="utils">Utilities</button>
    </div>

    <!-- MAVLink Mission -->
    <div class="tab-content active" id="tab-mission">
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
          <label>Control Mode</label>
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
        <div class="field">
          <label>Accept Radius (m)</label>
          <input type="number" id="m-accept" value="65" min="10" max="300">
        </div>
        <div class="field">
          <label>Monitor (s, 0=&#8734;)</label>
          <input type="number" id="m-monitor" value="300" min="0" max="3600">
        </div>
        <div class="field field-wide">
          <label>MAVLink Connection</label>
          <input type="text" id="m-conn" value="udpin:0.0.0.0:14550">
        </div>
      </div>
      <div class="launch-actions">
        <button class="btn-b" id="launch-mavlink">&#9654; LAUNCH MISSION</button>
        <button class="btn-r stop-btn">&#9632; STOP</button>
      </div>
    </div>

    <!-- Simulations -->
    <div class="tab-content" id="tab-sim">

      <div class="subsec">
        <p class="subsec-title">Square Mission Simulation</p>
        <div class="fields">
          <div class="field"><label>Side (m)</label>
            <input type="number" id="s-side" value="500" min="50" max="5000"></div>
          <div class="field"><label>Alt (m)</label>
            <input type="number" id="s-alt" value="50" min="10" max="500"></div>
          <div class="field"><label>Speed (m/s)</label>
            <input type="number" id="s-speed" value="20" min="1" max="100"></div>
          <div class="field"><label>Frame Delay (ms)</label>
            <input type="number" id="s-delay" value="50" min="10" max="500"></div>
        </div>
        <label class="check-row"><input type="checkbox" id="s-headless"> Save PNG (headless)</label>
        <div class="launch-actions">
          <button class="btn-b" id="launch-sim">&#9654; LAUNCH</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
      </div>

      <div class="subsec">
        <p class="subsec-title">Visual Target-Lock Simulation</p>
        <div class="fields">
          <div class="field"><label>Frame Delay (ms)</label>
            <input type="number" id="vs-delay" value="600" min="50" max="3000"></div>
          <div class="field" style="justify-content:flex-end;">
            <label class="check-row" style="margin:0;">
              <input type="checkbox" id="vs-headless"> Save PNG
            </label>
          </div>
        </div>
        <div class="launch-actions">
          <button class="btn-b" id="launch-visual">&#9654; LAUNCH</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
      </div>

      <div class="subsec">
        <p class="subsec-title">Simulation Test (Synthetic Detection)</p>
        <p style="font-size:11px;color:var(--muted);margin-bottom:7px;">
          Runs hardcoded synthetic detection steps. No parameters required.
        </p>
        <div class="launch-actions">
          <button class="btn-b" id="launch-simtest">&#9654; RUN TEST</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
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
          <label>IoU Threshold</label>
          <input type="number" id="v-iou" value="0.45" min="0.1" max="0.99" step="0.05">
        </div>
        <div class="field">
          <label>Image Size (0=auto)</label>
          <input type="number" id="v-imgsz" value="0" min="0" max="1920" step="32">
        </div>
        <div class="field">
          <label>Lock Time (s)</label>
          <input type="number" id="v-lock" value="4" min="1" max="30">
        </div>
        <div class="field">
          <label>Smoothing (0&#8211;1)</label>
          <input type="number" id="v-smooth" value="0.65" min="0" max="1" step="0.05">
        </div>
        <div class="field">
          <label>Max Frames (0=&#8734;)</label>
          <input type="number" id="v-maxframes" value="0" min="0" max="100000">
        </div>
      </div>
      <label class="check-row"><input type="checkbox" id="v-headless"> Save PNG (headless)</label>
      <div class="launch-actions">
        <button class="btn-b" id="launch-vision">&#9654; LAUNCH VISION</button>
        <button class="btn-r stop-btn">&#9632; STOP</button>
      </div>
    </div>

    <!-- Air Defense Avoidance -->
    <div class="tab-content" id="tab-airdefense">
      <div class="fields">
        <div class="field"><label>Side (m)</label>
          <input type="number" id="ad-side" value="500" min="100" max="5000"></div>
        <div class="field"><label>Zone Radius (m)</label>
          <input type="number" id="ad-radius" value="100" min="20" max="1000"></div>
        <div class="field"><label>Safety Buffer (m)</label>
          <input type="number" id="ad-buffer" value="75" min="10" max="500"></div>
        <div class="field"><label>Zone Activates (s)</label>
          <input type="number" id="ad-activate" value="30" min="5" max="300"></div>
        <div class="field"><label>Alt (m)</label>
          <input type="number" id="ad-alt" value="50" min="10" max="500"></div>
        <div class="field"><label>Speed (m/s)</label>
          <input type="number" id="ad-speed" value="20" min="1" max="100"></div>
        <div class="field"><label>Frame Delay (ms)</label>
          <input type="number" id="ad-delay" value="40" min="10" max="500"></div>
        <div class="field"><label>Figures Output Dir</label>
          <input type="text" id="ad-outdir" value="logs/figures"></div>
      </div>
      <label class="check-row"><input type="checkbox" id="ad-headless"> Save PNG (headless)</label>
      <div class="launch-actions" style="margin-top:9px;">
        <button class="btn-b" id="launch-adsim" style="flex:2">&#9654; RUN ANIMATION</button>
        <button class="btn-p" id="launch-adfigs" style="flex:2">&#128202; GEN FIGURES</button>
        <button class="btn-r stop-btn" style="flex:1">&#9632; STOP</button>
      </div>
      <p style="font-size:11px;color:var(--muted);margin-top:7px;">
        Figures saved to output dir for CDR report. Use <strong>headless</strong> to generate a
        preview PNG shown below.
      </p>
    </div>

    <!-- Gazebo SITL -->
    <div class="tab-content" id="tab-gazebo">

      <div class="subsec">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
          <span class="subsec-title" style="margin:0;">Step 1 &#8212; SITL + Gazebo (WSL2)</span>
          <div id="sitl-badge" class="badge proc-badge" style="font-size:10.5px;">
            <span class="dot off" id="sitl-dot"></span>
            <span id="sitl-text">idle</span>
          </div>
        </div>
        <p style="font-size:11px;color:var(--muted);margin-bottom:7px;">
          Starts Gazebo + ArduPlane SITL inside WSL2. Gazebo GUI appears via WSLg.
        </p>
        <div class="fields" style="margin-bottom:6px;">
          <div class="field"><label>WSL Distro (optional)</label>
            <input type="text" id="gz-distro" value="" placeholder="leave blank for default"></div>
          <div class="field" style="justify-content:flex-end;">
            <label class="check-row" style="margin:0;">
              <input type="checkbox" id="gz-headlessgz"> Headless (no GUI)
            </label>
          </div>
        </div>
        <div style="display:flex;gap:7px;">
          <button class="btn-g" id="btn-launch-sitl" style="flex:1;">&#9654; LAUNCH SITL</button>
          <button class="btn-r" id="btn-stop-sitl" style="flex:0 0 88px;">&#9632; STOP SITL</button>
        </div>
      </div>

      <div class="subsec">
        <p class="subsec-title">Step 2 &#8212; Air Defense Mission</p>
        <div class="fields">
          <div class="field field-wide"><label>MAVLink Connection</label>
            <input type="text" id="gz-conn" value="udpin:0.0.0.0:14550"></div>
          <div class="field"><label>Side (m)</label>
            <input type="number" id="gz-side" value="500" min="100" max="5000"></div>
          <div class="field"><label>Alt (m)</label>
            <input type="number" id="gz-alt" value="50" min="10" max="500"></div>
          <div class="field"><label>Zone Radius (m)</label>
            <input type="number" id="gz-radius" value="100" min="20" max="1000"></div>
          <div class="field"><label>Safety Buffer (m)</label>
            <input type="number" id="gz-buffer" value="75" min="10" max="500"></div>
          <div class="field"><label>Zone Activates (s)</label>
            <input type="number" id="gz-activate" value="30" min="5" max="300"></div>
        </div>
        <label class="check-row" style="margin-bottom:4px;">
          <input type="checkbox" id="gz-noviz"> Skip Gazebo zone visualisation
        </label>
        <div class="launch-actions" style="margin-top:7px;">
          <button class="btn-b" id="launch-gazebo" style="flex:1;">&#9654; LAUNCH MISSION</button>
          <button class="btn-r stop-btn" style="flex:0 0 72px;">&#9632; STOP</button>
        </div>
      </div>

      <div style="padding:9px;background:#18202e;border-radius:7px;font-size:11px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;">
          <strong style="color:#8ab4f8;">First-time WSL2 setup (~15 min)</strong>
          <button id="btn-gz-setup"
                  style="height:24px;padding:0 10px;font-size:11px;
                         background:#253560;border:1px solid #4a6aaa;
                         color:#8ab4f8;border-radius:5px;cursor:pointer;font-weight:600;">
            RUN SETUP
          </button>
        </div>
        <code style="color:#80cbc4;">setup_gazebo_wsl.sh</code>
        &#8212; Gazebo Harmonic + ardupilot_gazebo + ArduPilot SITL
      </div>
    </div>

    <!-- WSL Console -->
    <div class="tab-content" id="tab-wsl">
      <div class="fields" style="margin-bottom:7px;">
        <div class="field field-wide">
          <label>WSL Distro (optional)</label>
          <input type="text" id="wsl-distro" value="" placeholder="leave blank for default distro">
        </div>
      </div>
      <p class="sec-title" style="margin-bottom:6px;">Quick Commands</p>
      <div id="wsl-quick-grid"
           style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:9px;">
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px;">
        <input type="text" id="wsl-cmd-input" placeholder="bash command to run in WSL2&#8230;" style="flex:1;">
        <button class="btn-b" id="btn-wsl-run" style="flex:0 0 52px;">RUN</button>
        <button class="btn-r" id="btn-wsl-stop" style="flex:0 0 52px;">STOP</button>
      </div>
      <p style="font-size:11px;color:var(--muted);">
        Runs via <code>bash -ic</code> so <code>~/.bashrc</code> is sourced automatically.
        Output appears in Process Output below.
      </p>
    </div>

    <!-- Utilities -->
    <div class="tab-content" id="tab-utils">

      <div class="subsec">
        <p class="subsec-title">Live Telemetry Stream</p>
        <div class="fields">
          <div class="field field-wide"><label>Connection</label>
            <input type="text" id="tel-conn" value="udpin:0.0.0.0:14550"></div>
          <div class="field"><label>Interval (s)</label>
            <input type="number" id="tel-interval" value="1.0" min="0.1" max="10" step="0.1"></div>
          <div class="field"><label>Count (0=&#8734;)</label>
            <input type="number" id="tel-count" value="0" min="0" max="10000"></div>
        </div>
        <label class="check-row" style="margin-bottom:7px;">
          <input type="checkbox" id="tel-direct"> Direct MAVLink (bypass cmd server)
        </label>
        <div class="launch-actions">
          <button class="btn-t" id="launch-telemetry">&#9654; STREAM TELEMETRY</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
      </div>

      <div class="subsec">
        <p class="subsec-title">Emergency / Direct Flight Commands</p>
        <div class="fields">
          <div class="field field-wide"><label>Connection</label>
            <input type="text" id="em-conn" value="udpin:0.0.0.0:14550"></div>
        </div>
        <label class="check-row" style="margin-bottom:7px;">
          <input type="checkbox" id="em-direct"> Direct MAVLink
        </label>
        <div class="launch-actions">
          <button class="btn-r" id="launch-em-rtl">&#9888; EMERGENCY RTL</button>
          <button id="launch-em-loiter">&#8635; LOITER</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
      </div>

      <div class="subsec">
        <p class="subsec-title">Environment Check</p>
        <p style="font-size:11px;color:var(--muted);margin-bottom:7px;">
          Prints installed package versions: pymavlink, opencv, ultralytics, etc.
        </p>
        <div class="launch-actions">
          <button class="btn-t" id="launch-checkenv">&#10003; CHECK ENVIRONMENT</button>
          <button class="btn-r stop-btn">&#9632; STOP</button>
        </div>
      </div>

    </div>
  </section>

  <!-- ── Process Output ────────────────────────────────────────────────── -->
  <section class="s-proclog">
    <div class="log-header">
      <p class="sec-title">Process Output</p>
      <div style="display:flex;align-items:center;gap:8px;">
        <span id="proc-running-label" style="font-size:11px;color:var(--muted);"></span>
        <button id="clear-proc">Clear</button>
      </div>
    </div>
    <div class="log-box" id="proc-box">
      <pre id="proclog">Waiting for a process to start&#8230;</pre>
    </div>
  </section>

  <!-- ── Image Preview ─────────────────────────────────────────────────── -->
  <section class="s-preview" id="preview-section" style="display:none;">
    <div class="log-header">
      <p class="sec-title">Output Preview</p>
      <div style="display:flex;align-items:center;gap:8px;">
        <span id="preview-label" style="font-size:11px;color:var(--muted);"></span>
        <button id="btn-preview-refresh">&#8635; Refresh</button>
        <button id="btn-preview-close">&#10005; Close</button>
      </div>
    </div>
    <div class="img-wrap" id="img-wrap">
      <p class="img-placeholder">No preview yet.</p>
    </div>
  </section>

  <!-- ── Command Log ───────────────────────────────────────────────────── -->
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
  // ── Telemetry polling ────────────────────────────────────────────────────
  const TEL_FIELDS = ["phase","mode","armed","lat","lon","alt","groundspeed","wp_dist"];
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
      TEL_FIELDS.forEach(k => {
        const el = document.getElementById(k);
        if (!el) return;
        const v = (d.fields && d.fields[k]) || "--";
        el.textContent = v;
        if (k === "armed") {
          const on = (v === "1" || v.toLowerCase() === "armed");
          el.className = "m-value" + (on ? " armed" : " disarmed");
        }
      });
    } catch { setConn(false); }
  }

  // ── Flight commands ──────────────────────────────────────────────────────
  const evtLog = document.getElementById("evtlog");

  function addEvt(msg) {
    const t = new Date().toLocaleTimeString();
    evtLog.textContent = "[" + t + "]  " + msg + "\\n" + evtLog.textContent;
  }

  async function sendCmd(cmd) {
    document.querySelectorAll("[data-command],#modeBtn").forEach(b => b.disabled = true);
    addEvt("CMD: " + cmd);
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
  document.getElementById("hdr-rtl").addEventListener("click", () => sendCmd("RTL"));

  // ── Tab switching ────────────────────────────────────────────────────────
  document.querySelectorAll(".tab").forEach(btn =>
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    })
  );

  // ── Process launch/stop ──────────────────────────────────────────────────
  let _headlessOut = "";

  async function stopProc() {
    try {
      const d = await (await fetch("/api/process/stop", {method: "POST"})).json();
      addEvt(d.ok ? "Stop signal sent." : "Stop failed: " + d.error);
    } catch(e) { addEvt(String(e)); }
  }

  async function launch(script, args, btn, headlessOut) {
    const orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; btn.textContent = "Launching…"; }
    if (headlessOut) _headlessOut = headlessOut;
    addEvt("→ " + script);
    try {
      const d = await (await fetch("/api/process/launch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({script, args})
      })).json();
      addEvt(d.ok ? "✓ Started: " + script : "✗ " + d.error);
    } catch(e) { addEvt("✗ " + String(e)); }
    finally { if (btn) { btn.disabled = false; btn.textContent = orig; } }
  }

  document.querySelectorAll(".stop-btn").forEach(b => b.addEventListener("click", stopProc));

  // MAVLink Mission
  document.getElementById("launch-mavlink").addEventListener("click", function() {
    launch("run_square_mission.py", [
      "--shape",             document.getElementById("m-shape").value,
      "--control-mode",      document.getElementById("m-control").value,
      "--size-m",            document.getElementById("m-size").value,
      "--alt-m",             document.getElementById("m-alt").value,
      "--acceptance-radius", document.getElementById("m-accept").value,
      "--auto-monitor-s",    document.getElementById("m-monitor").value,
      "--connection",        document.getElementById("m-conn").value,
    ], this);
  });

  // Square Simulation
  document.getElementById("launch-sim").addEventListener("click", function() {
    const hl = document.getElementById("s-headless").checked;
    const out = "logs/square_mission_preview.png";
    const args = [
      "--side-m",    document.getElementById("s-side").value,
      "--alt-m",     document.getElementById("s-alt").value,
      "--speed-mps", document.getElementById("s-speed").value,
      "--delay-ms",  document.getElementById("s-delay").value,
    ];
    if (hl) { args.push("--headless", "--output", out); }
    launch("run_square_simulation.py", args, this, hl ? out : "");
  });

  // Visual Simulation
  document.getElementById("launch-visual").addEventListener("click", function() {
    const hl = document.getElementById("vs-headless").checked;
    const out = "logs/visual_simulation_preview.png";
    const args = ["--delay-ms", document.getElementById("vs-delay").value];
    if (hl) { args.push("--headless", "--output", out); }
    launch("run_visual_simulation.py", args, this, hl ? out : "");
  });

  // Simulation Test
  document.getElementById("launch-simtest").addEventListener("click", function() {
    launch("run_simulation_test.py", [], this);
  });

  // Vision Pipeline
  document.getElementById("launch-vision").addEventListener("click", function() {
    const hl = document.getElementById("v-headless").checked;
    const out = "logs/vision_pipeline_preview.png";
    const args = [
      "--source",          document.getElementById("v-source").value,
      "--model",           document.getElementById("v-model").value,
      "--confidence",      document.getElementById("v-conf").value,
      "--iou",             document.getElementById("v-iou").value,
      "--lock-duration-s", document.getElementById("v-lock").value,
      "--smoothing",       document.getElementById("v-smooth").value,
    ];
    const imgsz = parseInt(document.getElementById("v-imgsz").value);
    if (imgsz > 0) args.push("--imgsz", String(imgsz));
    const maxf = parseInt(document.getElementById("v-maxframes").value);
    if (maxf > 0) args.push("--max-frames", String(maxf));
    if (hl) { args.push("--headless", "--output", out); }
    launch("run_vision_pipeline.py", args, this, hl ? out : "");
  });

  // Air Defense helpers
  function adArgs() {
    return [
      "--side-m",      document.getElementById("ad-side").value,
      "--zone-radius", document.getElementById("ad-radius").value,
      "--zone-buffer", document.getElementById("ad-buffer").value,
      "--activate-at", document.getElementById("ad-activate").value,
      "--alt-m",       document.getElementById("ad-alt").value,
      "--speed-mps",   document.getElementById("ad-speed").value,
    ];
  }

  document.getElementById("launch-adsim").addEventListener("click", function() {
    const hl = document.getElementById("ad-headless").checked;
    const out = "logs/air_defense_preview.png";
    const args = [...adArgs(), "--delay-ms", document.getElementById("ad-delay").value];
    if (hl) { args.push("--headless", "--output", out); }
    launch("run_air_defense_simulation.py", args, this, hl ? out : "");
  });

  document.getElementById("launch-adfigs").addEventListener("click", function() {
    launch("generate_air_defense_figures.py",
      [...adArgs(), "--out-dir", document.getElementById("ad-outdir").value],
      this);
  });

  // Gazebo Mission
  document.getElementById("launch-gazebo").addEventListener("click", function() {
    const args = [
      "--connection",  document.getElementById("gz-conn").value,
      "--side-m",      document.getElementById("gz-side").value,
      "--alt-m",       document.getElementById("gz-alt").value,
      "--zone-radius", document.getElementById("gz-radius").value,
      "--zone-buffer", document.getElementById("gz-buffer").value,
      "--activate-at", document.getElementById("gz-activate").value,
    ];
    const distro = document.getElementById("gz-distro").value.trim();
    if (distro) args.push("--wsl-distro", distro);
    if (document.getElementById("gz-noviz").checked) args.push("--no-viz");
    launch("run_gazebo_air_defense.py", args, this);
  });

  // Utilities — Telemetry
  document.getElementById("launch-telemetry").addEventListener("click", function() {
    const args = [
      "--connection", document.getElementById("tel-conn").value,
      "--interval-s", document.getElementById("tel-interval").value,
      "--count",      document.getElementById("tel-count").value,
    ];
    if (document.getElementById("tel-direct").checked) args.push("--direct");
    launch("telemetry.py", args, this);
  });

  // Utilities — Emergency RTL script
  document.getElementById("launch-em-rtl").addEventListener("click", function() {
    const args = ["--connection", document.getElementById("em-conn").value];
    if (document.getElementById("em-direct").checked) args.push("--direct");
    launch("emergency_rtl.py", args, this);
  });

  // Utilities — Loiter script
  document.getElementById("launch-em-loiter").addEventListener("click", function() {
    const args = ["--connection", document.getElementById("em-conn").value];
    if (document.getElementById("em-direct").checked) args.push("--direct");
    launch("loiter.py", args, this);
  });

  // Utilities — Check Env
  document.getElementById("launch-checkenv").addEventListener("click", function() {
    launch("check_env.py", [], this);
  });

  // Flight Controls panel — direct script shortcuts
  document.getElementById("btn-rtl-direct").addEventListener("click", function() {
    const conn = document.getElementById("direct-conn").value;
    const direct = document.getElementById("direct-mode").checked;
    const args = ["--connection", conn];
    if (direct) args.push("--direct");
    launch("emergency_rtl.py", args, this);
  });

  document.getElementById("btn-loiter-direct").addEventListener("click", function() {
    const conn = document.getElementById("direct-conn").value;
    const direct = document.getElementById("direct-mode").checked;
    const args = ["--connection", conn];
    if (direct) args.push("--direct");
    launch("loiter.py", args, this);
  });

  document.getElementById("btn-checkenv").addEventListener("click", function() {
    launch("check_env.py", [], this);
  });

  // Telemetry quick-launch from status panel
  document.getElementById("btn-tel-quick").addEventListener("click", function() {
    const conn = document.getElementById("direct-conn").value || "udpin:0.0.0.0:14550";
    launch("telemetry.py", ["--connection", conn, "--interval-s", "1.0"], this);
  });

  // ── SITL process (independent process manager) ───────────────────────────
  async function launchSitl(script, args, btn) {
    const orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; btn.textContent = "Launching…"; }
    addEvt("→ [SITL] " + script);
    try {
      const d = await (await fetch("/api/sitl/launch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({script, args})
      })).json();
      addEvt(d.ok ? "✓ [SITL] Started." : "✗ [SITL] " + d.error);
    } catch(e) { addEvt("✗ [SITL] " + String(e)); }
    finally { if (btn) { btn.disabled = false; btn.textContent = orig; } }
  }

  async function stopSitl() {
    try {
      const d = await (await fetch("/api/sitl/stop", {method: "POST"})).json();
      addEvt(d.ok ? "[SITL] Stop signal sent." : "[SITL] Stop: " + d.error);
    } catch(e) { addEvt(String(e)); }
  }

  const sitlBadge    = document.getElementById("sitl-badge");
  const sitlDot      = document.getElementById("sitl-dot");
  const sitlText     = document.getElementById("sitl-text");
  const hdrSitlBadge = document.getElementById("hdr-sitl-badge");
  const hdrSitlText  = document.getElementById("hdr-sitl-text");

  function setSitlStatus(s) {
    if (s.running) {
      sitlBadge.className     = "badge proc-badge running";
      sitlDot.className       = "dot on";
      sitlText.textContent    = "SITL pid=" + s.pid;
      hdrSitlBadge.style.display = "";
      hdrSitlBadge.className  = "badge proc-badge running";
      hdrSitlText.textContent = "SITL pid=" + s.pid;
    } else {
      sitlBadge.className     = "badge proc-badge";
      sitlDot.className       = "dot off";
      sitlText.textContent    = s.returncode === null ? "idle" : "exited  code=" + s.returncode;
      hdrSitlBadge.style.display = s.returncode !== null ? "" : "none";
      hdrSitlBadge.className  = "badge proc-badge";
      hdrSitlText.textContent = s.returncode !== null ? "SITL exited " + s.returncode : "";
    }
  }

  async function refreshSitlStatus() {
    try { const d = await (await fetch("/api/sitl/status")).json(); setSitlStatus(d); } catch {}
  }

  document.getElementById("btn-launch-sitl").addEventListener("click", function() {
    const args = [];
    const distro = document.getElementById("gz-distro").value.trim();
    if (distro) args.push("--distro", distro);
    if (document.getElementById("gz-headlessgz").checked) args.push("--headless");
    launchSitl("run_sitl_wsl.py", args, this);
  });

  document.getElementById("btn-stop-sitl").addEventListener("click", stopSitl);

  document.getElementById("btn-gz-setup").addEventListener("click", function() {
    const btn = this;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = "Running…";
    addEvt("→ setup_gazebo_wsl.sh (~15 min) — watch Process Output");
    const distro = document.getElementById("gz-distro").value.trim();
    fetch("/api/process/launch", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({script: "run_gazebo_setup.py", args: distro ? [distro] : []})
    }).then(r => r.json()).then(d =>
      addEvt(d.ok ? "✓ Setup started." : "✗ " + d.error)
    ).catch(e => addEvt("✗ " + String(e)))
      .finally(() => { btn.disabled = false; btn.textContent = orig; });
  });

  setInterval(refreshSitlStatus, 1000);
  refreshSitlStatus();

  // ── WSL Console ──────────────────────────────────────────────────────────
  const WSL_QUICK = [
    ["CHECK SITL",  "which sim_vehicle.py 2>&1 || echo NOT FOUND"],
    ["GZ VERSION",  "gz sim --version 2>&1"],
    ["LIST MODELS", "ls ~/ardupilot_gazebo/models/ 2>&1"],
    ["GZ TOPICS",   "gz topic -l 2>/dev/null | head -20"],
    ["FIX PATH",    "export PATH=\\"$PATH:$HOME/ardupilot/Tools/autotest\\" && echo PATH OK && which sim_vehicle.py 2>&1"],
    ["FULL STATUS", "echo === sim_vehicle === ; which sim_vehicle.py 2>&1 ; echo === gz === ; gz sim --version 2>&1 ; echo === models === ; ls ~/ardupilot_gazebo/models/ 2>&1 | head -10"],
  ];

  (function() {
    const grid = document.getElementById("wsl-quick-grid");
    WSL_QUICK.forEach(([label, cmd], i) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      btn.style.fontSize = "11px";
      btn.style.height = "30px";
      if (i === WSL_QUICK.length - 1) btn.classList.add("btn-b");
      btn.addEventListener("click", function() { wslRun(cmd, this); });
      grid.appendChild(btn);
    });
  })();

  async function wslRun(cmd, btn) {
    const orig = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; }
    const distro = document.getElementById("wsl-distro").value.trim();
    addEvt("[WSL] " + cmd.substring(0, 72) + (cmd.length > 72 ? "…" : ""));
    try {
      const d = await (await fetch("/api/wsl/run", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cmd, distro})
      })).json();
      addEvt(d.ok ? "✓ [WSL] Running…" : "✗ [WSL] " + d.error);
    } catch(e) { addEvt("✗ [WSL] " + String(e)); }
    finally { if (btn) { btn.disabled = false; if (orig) btn.textContent = orig; } }
  }

  document.getElementById("btn-wsl-run").addEventListener("click", function() {
    const cmd = document.getElementById("wsl-cmd-input").value.trim();
    if (cmd) wslRun(cmd, this);
  });

  document.getElementById("wsl-cmd-input").addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      const cmd = this.value.trim();
      if (cmd) wslRun(cmd, document.getElementById("btn-wsl-run"));
    }
  });

  document.getElementById("btn-wsl-stop").addEventListener("click", async function() {
    try {
      const d = await (await fetch("/api/wsl/stop", {method: "POST"})).json();
      addEvt(d.ok ? "[WSL] Stopped." : "[WSL] Stop: " + d.error);
    } catch(e) { addEvt(String(e)); }
  });

  // ── Image Preview ────────────────────────────────────────────────────────
  const previewSection = document.getElementById("preview-section");
  const imgWrap        = document.getElementById("img-wrap");
  const previewLabel   = document.getElementById("preview-label");

  function showPreview(path) {
    const url = "/api/image?path=" + encodeURIComponent(path) + "&t=" + Date.now();
    previewSection.style.display = "";
    previewLabel.textContent = path;
    imgWrap.innerHTML = '<img src="' + url + '" alt="preview" '
      + 'onerror="this.parentNode.innerHTML=\'<p class=\\\\\"img-placeholder\\\\\">Image not found.</p>\'">';
  }

  document.getElementById("btn-preview-refresh").addEventListener("click", () => {
    if (_headlessOut) showPreview(_headlessOut);
  });
  document.getElementById("btn-preview-close").addEventListener("click", () => {
    previewSection.style.display = "none";
    _headlessOut = "";
  });

  // ── Process log polling ──────────────────────────────────────────────────
  const procLog = document.getElementById("proclog");
  const procBox = document.getElementById("proc-box");
  let lastTs = 0, firstEntry = true, prevRunning = false;

  function atBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 60; }

  async function refreshProcLog() {
    try {
      const d = await (await fetch("/api/process/logs?since=" + lastTs)).json();
      if (!d.entries || d.entries.length === 0) return;
      if (firstEntry) { procLog.textContent = ""; firstEntry = false; }
      const snap = atBottom(procBox);
      d.entries.forEach(e => {
        if (e.ts > lastTs) lastTs = e.ts;
        procLog.textContent += e.line + "\\n";
      });
      if (snap) procBox.scrollTop = procBox.scrollHeight;
    } catch {}
  }

  async function watchStatus() {
    try {
      const d = await (await fetch("/api/process/status")).json();
      setProcStatus(d);
      if (_headlessOut && prevRunning && !d.running && d.returncode === 0) {
        showPreview(_headlessOut);
      }
      prevRunning = d.running;
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
  watchStatus();
  setInterval(refreshTel,     1000);
  setInterval(refreshProcLog,  500);
  setInterval(watchStatus,    1000);
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

    shared_logs: collections.deque = collections.deque(maxlen=1000)
    proc_mgr = ProcessManager(shared_logs, log_prefix="")
    sitl_mgr = ProcessManager(shared_logs, log_prefix="[SITL] ")
    wsl_mgr  = ProcessManager(shared_logs, log_prefix="[WSL] ")
    handler = make_handler(args.command_host, args.command_port, proc_mgr, sitl_mgr, wsl_mgr)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Mission Control dashboard -> http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def make_handler(
    command_host: str, command_port: int,
    proc_mgr: ProcessManager, sitl_mgr: ProcessManager, wsl_mgr: ProcessManager,
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/":
                self._send_html(DASHBOARD_HTML)

            elif parsed.path == "/api/status":
                response = request_status_via_local_server(command_host, command_port, timeout_s=0.4)
                if response is None:
                    self._send_json({"ok": False, "fields": {}, "response": None})
                    return
                status = strip_ok(response)
                self._send_json({"ok": True, "fields": parse_status(status), "response": status})

            elif parsed.path == "/api/process/logs":
                qs = parse_qs(parsed.query)
                since = float(qs.get("since", ["0"])[0])
                self._send_json({"ok": True, "entries": proc_mgr.logs_since(since)})

            elif parsed.path == "/api/process/status":
                self._send_json({"ok": True, **proc_mgr.status()})

            elif parsed.path == "/api/sitl/status":
                self._send_json({"ok": True, **sitl_mgr.status()})

            elif parsed.path == "/api/wsl/status":
                self._send_json({"ok": True, **wsl_mgr.status()})

            elif parsed.path == "/api/image":
                qs = parse_qs(parsed.query)
                rel = qs.get("path", [""])[0]
                if not rel:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                try:
                    abs_path = (PROJECT_ROOT / rel).resolve()
                    abs_path.relative_to(PROJECT_ROOT.resolve())
                except (ValueError, Exception):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                if not abs_path.exists() or abs_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                data = abs_path.read_bytes()
                ct = "image/png" if abs_path.suffix.lower() == ".png" else "image/jpeg"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path == "/api/command":
                payload = self._read_json()
                command = str(payload.get("command", "")).strip().upper()
                if (command not in _ALLOWED_COMMANDS and not command.startswith("MODE ")):
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

            elif self.path == "/api/sitl/launch":
                payload = self._read_json()
                script = str(payload.get("script", ""))
                raw_args = payload.get("args", [])
                if not isinstance(raw_args, list):
                    self._send_json({"ok": False, "error": "args must be a list"}, HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(sitl_mgr.launch(script, [str(a) for a in raw_args]))

            elif self.path == "/api/sitl/stop":
                self._send_json(sitl_mgr.stop())

            elif self.path == "/api/wsl/run":
                payload = self._read_json()
                cmd = str(payload.get("cmd", "")).strip()
                if not cmd:
                    self._send_json({"ok": False, "error": "cmd is required"}, HTTPStatus.BAD_REQUEST)
                    return
                distro = str(payload.get("distro", "")).strip()
                args = ["--cmd", cmd]
                if distro:
                    args += ["--distro", distro]
                self._send_json(wsl_mgr.launch("run_wsl_cmd.py", args))

            elif self.path == "/api/wsl/stop":
                self._send_json(wsl_mgr.stop())

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

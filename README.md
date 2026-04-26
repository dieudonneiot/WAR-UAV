# TEKNOFEST 2026 UAV Software Workspace

Python-first combat UAV software stack covering:

- Mission logic and autonomy
- Computer vision and QR reading
- MAVLink communication with the autopilot
- GCS-facing telemetry utilities
- ArduPilot SITL and Gazebo simulation

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [First-Time Setup](#first-time-setup)
   - [WSL2 — ArduPilot SITL](#wsl2--ardupilot-sitl)
   - [Windows — Python environment](#windows--python-environment)
3. [Running the SITL Simulation](#running-the-sitl-simulation)
4. [Known Issues and Bugs](#known-issues-and-bugs)
5. [Flight Control](#flight-control)
6. [Simulation Tiers](#simulation-tiers)
7. [Script Reference](#script-reference)
8. [Project Layout](#project-layout)
9. [Configuration](#configuration)

---

## Prerequisites

### Windows side

| Tool | Version | Notes |
| ---- | ------- | ----- |
| Python | 3.10 – 3.12 | [python.org](https://www.python.org/downloads/) |
| Git | any | For cloning this repo |
| WSL2 | Ubuntu 22.04 | Required to run ArduPilot SITL |

### WSL2 side (Ubuntu)

| Tool | Installed by | Notes |
| ---- | ------------ | ----- |
| Git | `apt` | Clone ArduPilot |
| Python 3 | `apt` / ArduPilot installer | Build deps |
| ArduPilot build deps | `install-prereqs-ubuntu.sh` | ~5 min, done once |
| `sim_vehicle.py` | ArduPilot repo | SITL launcher |
| MAVProxy | ArduPilot installer | Console + map GUI |

> **WSL2 GUI support:** MAVProxy opens a map window.
> On Windows 11 this works out of the box (WSLg).
> On Windows 10 you need an X server such as VcXsrv or MobaXterm.

---

## First-Time Setup

### WSL2 — ArduPilot SITL

Open a **WSL2 / Ubuntu** terminal and run these commands **once**:

```bash
# 1. Clone ArduPilot with all submodules
git clone --recurse-submodules git@github.com:ArduPilot/ardupilot.git
cd ardupilot

# 2. Install all build dependencies (~5 minutes)
Tools/environment_install/install-prereqs-ubuntu.sh -y

# 3. Reload your shell profile so new PATH entries take effect
. ~/.profile
```

> The first time you launch SITL it compiles ArduPlane from source — this takes
> **~10 minutes**. Every subsequent launch is instant.

---

### Windows — Python environment

Open a **PowerShell** or **Windows terminal** in this repo's folder:

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1

# 3. Install the project and all dependencies in editable mode
pip install -e .

# 4. Verify everything is installed correctly
python scripts/check_env.py
```

Expected output from `check_env.py`:

```text
numpy        OK
cv2          OK
ultralytics  OK
pymavlink    OK
mavsdk       OK
yaml         OK
dotenv       OK
rich         OK
```

---

## Running the SITL Simulation

You need **two terminals open at the same time**: one in WSL2, one in Windows PowerShell.

### Step 1 — Start ArduPlane SITL (WSL2 terminal)

```bash
cd ardupilot
sim_vehicle.py -v ArduPlane --console --map
```

Flag breakdown:

| Flag | Meaning |
| ---- | ------- |
| `-v ArduPlane` | Simulate a fixed-wing aircraft |
| `--console` | Opens the MAVProxy text console |
| `--map` | Opens the MAVProxy map window |

`sim_vehicle.py`/MAVProxy normally exposes a UDP MAVLink stream to Windows on
port `14550`. The Python mission listens for that stream with
`udpin:0.0.0.0:14550`.

> Do not point the Python script at `tcp:127.0.0.1:5762`. In this SITL setup,
> `5762` is ArduPlane's raw `SERIAL1` TCP port. It accepts a TCP connection, so
> the ArduPlane terminal prints `New connection on SERIAL1`, but it does not
> provide the MAVLink heartbeat the mission script is waiting for.

### Step 2 — Wait until SITL is fully ready

**Do not launch the Python script until you see both of these signals:**

1. In the **MAVProxy console window**:

   ```text
   AP: ArduPilot Ready
   pre-arm good
   ```

2. In the **MAVProxy status bar** (top of the console):

   ```text
   GPS: OK6(10)
   ```

> If the script connects while SITL is still booting (showing
> `Waiting for internal clock bits to be set (current=0x00)`),
> `wait_heartbeat()` will block indefinitely because the autopilot
> has not started sending heartbeats yet.

### Step 3 — Run the square waypoint mission (Windows PowerShell)

```powershell
# Make sure the venv is active
.\.venv\Scripts\Activate.ps1

# Fly the default 500 m square at 50 m AGL
python scripts/run_square_mission.py
```

The script will print its progress:

```text
Connecting to udpin:0.0.0.0:14550 …
Connected.
Disabling hand-launch safety (TKOFF_THR_MINACC=0) …
Disabling pre-arm checks (ARMING_CHECK=0) …
Taking off to 50 m …
  alt=...
  ...
```

### Optional — Custom mission parameters

```powershell
python scripts/run_square_mission.py `
    --connection udpin:0.0.0.0:14550 `
    --shape triangle `
    --size-m 300 `
    --alt-m 80 `
    --acceptance-radius 50
```

| Argument | Default | Description |
| -------- | ------- | ----------- |
| `--connection` | `udpin:0.0.0.0:14550` | MAVLink connection string |
| `--shape` | `square` | Mission shape: `square`, `triangle`, `line`, or `circle` |
| `--size-m` | `500` | Mission size in metres; circle uses this as diameter |
| `--side-m` | `500` | Deprecated alias for `--size-m` |
| `--alt-m` | `50` | Cruise altitude in metres AGL |
| `--acceptance-radius` | `65` | Waypoint reached threshold in metres |

---

## Known Issues and Bugs

### Plane does not move / stays on the ground

**Root cause:** `climb_to()` in [src/uav/autonomy/navigator.py](src/uav/autonomy/navigator.py)
applies an RC throttle override (channel 3) while the aircraft is in **FBWA** mode.
A fixed-wing aircraft requires **forward airspeed** to generate lift — spinning the
motor from a standstill on the ground never produces altitude. The altitude loop
prints `alt=0.0 m` forever.

**Fix needed:** Replace the manual throttle-override takeoff with ArduPlane's
dedicated `TAKEOFF` flight mode, which handles the full takeoff sequence
(acceleration + rotation + climb) automatically:

```python
# Instead of FBWA + rc_override, do:
client.set_mode("TAKEOFF")
client.arm()
# Then wait until alt >= target_alt_m via get_position()
```

### Script hangs at "Connecting…" with no output

The SITL is still booting. Wait until the MAVProxy status bar shows `GPS: OK`
before running the script. See [Step 2](#step-2--wait-until-sitl-is-fully-ready).

### Mode `FBWA` / `GUIDED` not found in mode mapping

This happens when `connect()` reads the mode map before the autopilot has finished
initialising. Add a short `time.sleep(2)` after `client.connect()` before any
`set_mode()` call, or use `master.wait_heartbeat(timeout=30)`.

### `ARMING_CHECK` param set is silently ignored

In SITL the parameter may revert if the vehicle is still in its boot sequence.
Set `ARMING_CHECK=0` via the MAVProxy console first as a sanity check:

```text
MAVProxy> param set ARMING_CHECK 0
```

---

## Flight Control

See [docs/flight_control.md](docs/flight_control.md) for the control reference:
MAVProxy commands, Python control helpers, useful ArduPlane modes, telemetry,
and the implementation roadmap.

---

## Simulation Tiers

Use the quickest tier that covers what you are testing:

### Tier 1 — Repo-native visual simulation (no external tools)

Exercises the complete vision → tracking → engagement → mission-phase loop
using synthetic detections. No ArduPilot, no Gazebo needed.

```powershell
python scripts/run_visual_simulation.py
```

Headless (saves a PNG instead of opening a window):

```powershell
python scripts/run_visual_simulation.py --headless
```

Animated square mission path:

```powershell
python scripts/run_square_simulation.py --side-m 500 --alt-m 50 --speed-mps 25
```

### Tier 2 — Real camera / video with YOLO detections

Same dashboard as Tier 1 but with live Ultralytics detections instead of
synthetic ones. Useful for tuning the vision stack before SITL is set up.

```powershell
# Webcam
python scripts/run_vision_pipeline.py --source 0 --model yolov8n.pt

# Pre-recorded video
python scripts/run_vision_pipeline.py --source data/sample.mp4 --model yolov8n.pt

# Full tuning flags
python scripts/run_vision_pipeline.py `
    --source data/sample.mp4 `
    --model yolov8n.pt `
    --confidence 0.35 `
    --iou 0.5 `
    --imgsz 960 `
    --min-box-area 80 `
    --smoothing 0.7 `
    --max-missed-frames 3
```

Detection / tracking tuning flags:

| Flag | Effect |
| ---- | ------ |
| `--confidence` | Raise to reduce false positives |
| `--iou` | Adjust YOLO non-maximum suppression |
| `--imgsz` | Increase for small/distant targets (GPU cost rises) |
| `--min-box-area` | Ignore tiny noisy detections |
| `--smoothing` | Reduce jitter in the tracked target bounding box |
| `--max-missed-frames` | Keep a track alive through brief detection gaps |
| `--lock-duration-s` | Seconds of continuous lock before engagement fires |

### Tier 3 — Full ArduPilot SITL (real MAVLink)

The full stack: ArduPlane flight-controller physics + MAVProxy console and map +
this repo as the mission computer. Described fully in
[Running the SITL Simulation](#running-the-sitl-simulation).

```text
WSL2           → sim_vehicle.py (ArduPlane SITL)
               → MAVProxy (console + map)
Windows        → run_square_mission.py (mission computer)
```

---

## Script Reference

| Script | Purpose |
| ------ | ------- |
| `scripts/check_env.py` | Verify all Python dependencies are installed |
| `scripts/run_visual_simulation.py` | Repo-native visual sim (Tier 1) |
| `scripts/run_square_simulation.py` | Animated square mission path (Tier 1) |
| `scripts/run_vision_pipeline.py` | YOLO + tracking + engagement dashboard (Tier 2) |
| `scripts/run_square_mission.py` | Real MAVLink mission to ArduPilot SITL (Tier 3) |
| `scripts/run_simulation_test.py` | Automated vision simulation test |

---

## Project Layout

```text
TEKNOFEST2026/
├── config/
│   └── mission.example.yaml       # Mission and camera parameters
├── data/                          # Raw data and sample videos
├── docs/
│   └── simulation.md              # Extended simulation workflow notes
├── models/                        # YOLO model weights (.pt files)
├── scripts/                       # Launcher and validation scripts
├── src/uav/
│   ├── autonomy/                  # Mission phases, engagement, navigation
│   │   ├── engagement.py          # Target-lock state machine
│   │   ├── mission_manager.py     # Phase transitions
│   │   └── navigator.py          # Waypoint guidance, square layout
│   ├── common/                    # Shared settings and data models
│   ├── gcs/                       # Telemetry bridge for GCS tools
│   ├── mavlink/
│   │   └── client.py             # MavlinkClient: connect, arm, set_mode, fly_to
│   ├── simulation/
│   │   ├── mission_scenario.py   # Waypoint mission physics simulation
│   │   ├── vision_scenario.py    # Synthetic detection scenarios
│   │   └── visualizer.py        # Dashboard rendering
│   └── vision/
│       ├── detector.py           # YOLO detection wrapper
│       └── tracker.py            # Multi-object tracking
├── tests/                         # Pytest smoke tests
├── .env.example                   # Environment variable template
├── pyproject.toml                 # Dependencies and build config
└── WSL commands (in order).txt   # Quick SITL command reference
```

---

## Configuration

### Environment variables — `.env`

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

```bash
UAV_SERIAL_PORT=COM6      # unused in SITL (TCP replaces serial)
UAV_BAUDRATE=57600
UAV_SYS_ID=1
UAV_COMP_ID=1
MISSION_NAME=combat_uav
ENABLE_SIMULATION=true
LOG_LEVEL=INFO
```

### Mission parameters — `config/mission.example.yaml`

```yaml
mission:
  name: combat_uav
  home_altitude_m: 0.0
  lock_duration_s: 4.0       # seconds of continuous target lock to trigger engagement
  telemetry_rate_hz: 2.0

vision:
  detector_model: models/yolov8n.pt
  camera_fov_deg: 100
  image_width: 1920
  image_height: 1200

navigation:
  geofence_margin_m: 50
  safe_altitude_m: 60
```

### Smoke tests

```powershell
pytest
```

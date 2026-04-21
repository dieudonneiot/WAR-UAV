# TEKNOFEST 2026 UAV Software Workspace

This repository is organized for a Python-first combat UAV software stack:

- mission logic and autonomy
- computer vision and QR reading
- MAVLink communication with the autopilot
- GCS-facing telemetry utilities
- simulation and SITL helpers

## Quick Start

1. Create and activate the virtual environment:
   - PowerShell: `.\.venv\Scripts\Activate.ps1`
2. Install the project in editable mode:
   - `pip install -e .`
3. Run the environment check:
   - `python scripts/check_env.py`
4. Run the smoke tests:
   - `pytest`
5. Run the visual simulation:
   - `python scripts/run_visual_simulation.py`
6. Run the YOLO vision pipeline on a camera or video:
   - `python scripts/run_vision_pipeline.py --source 0 --model yolov8n.pt`

## Project Layout

- `src/uav/autonomy`: mission phases, geofence logic, guidance placeholders
- `src/uav/vision`: detection, tracking, and QR-reading helpers
- `src/uav/mavlink`: MAVLink communication wrappers
- `src/uav/gcs`: telemetry bridge utilities for operator tools
- `src/uav/simulation`: SITL integration points
- `src/uav/common`: shared settings and data models
- `config`: mission and environment configuration
- `scripts`: setup and validation scripts
- `tests`: starter tests

## Simulation

Start with the repo-native visual simulation when you want to see the
vision-to-mission loop without external simulator setup:

```powershell
python scripts/run_visual_simulation.py
```

For details on the Gazebo/ArduPilot SITL direction, see `docs/simulation.md`.

To run the same dashboard with real frames and Ultralytics detections:

```powershell
python scripts/run_vision_pipeline.py --source 0 --model yolov8n.pt
```

Use a video file instead of a webcam by passing its path:

```powershell
python scripts/run_vision_pipeline.py --source data/sample.mp4 --model yolov8n.pt
```

Useful tuning flags:

```powershell
python scripts/run_vision_pipeline.py --source data/sample.mp4 --model yolov8n.pt --confidence 0.35 --iou 0.5 --imgsz 960 --min-box-area 80 --smoothing 0.7 --max-missed-frames 3
```

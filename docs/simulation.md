# Simulation Workflow

The project now supports two simulation tracks.

## 1. Repo-native visual simulation

Use this first when you want to see the mission logic without installing Gazebo,
ArduPilot, MAVProxy, or a real camera.

```powershell
.\.venv\Scripts\python.exe scripts\run_visual_simulation.py
```

Press `q` or `Esc` to close the window.

For machines without GUI support, save a preview image:

```powershell
.\.venv\Scripts\python.exe scripts\run_visual_simulation.py --headless
```

This visual simulation exercises the same flow that the real UAV code will use:

1. detections
2. target tracking
3. engagement state
4. mission phase transition

That makes it useful while the real Gazebo/SITL setup is still being prepared.

## 2. Full Gazebo/ArduPilot SITL

Before moving to full SITL, run real camera or video frames through the same
dashboard:

```powershell
.\.venv\Scripts\python.exe scripts\run_vision_pipeline.py --source 0 --model yolov8n.pt
```

For a saved video:

```powershell
.\.venv\Scripts\python.exe scripts\run_vision_pipeline.py --source data/sample.mp4 --model yolov8n.pt
```

This replaces synthetic detections with real Ultralytics detections while keeping
the same tracker, engagement controller, and visual dashboard.

The screenshot target is a full stack:

- Gazebo Sim for world and aircraft visualization
- ArduPilot SITL for flight-controller behavior
- MAVProxy or QGroundControl for map/operator view
- this repo as the mission-computer process

That stack is usually easiest on Ubuntu or WSL2 with GUI support. The repo-native
simulation should stay useful even after SITL is working because it gives quick,
deterministic checks for the vision-to-mission logic.

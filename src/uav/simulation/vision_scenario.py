from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from uav.autonomy.engagement import EngagementConfig, EngagementController, EngagementState
from uav.autonomy.mission_manager import MissionManager
from uav.vision.detector import Detection
from uav.vision.tracker import TargetTracker, TrackState


@dataclass(frozen=True, slots=True)
class SyntheticDetectionStep:
    dt_s: float
    detections: list[Detection]


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    time_s: float
    track: TrackState | None
    engagement: EngagementState
    camera_frame: Any | None = None


def run_vision_simulation(
    steps: list[SyntheticDetectionStep],
    image_width: int = 1920,
    image_height: int = 1200,
    lock_duration_s: float = 4.0,
) -> list[SimulationEvent]:
    manager = MissionManager(mission_name="vision_simulation")
    tracker = TargetTracker()
    engagement = EngagementController(
        EngagementConfig(
            image_width=image_width,
            image_height=image_height,
            lock_duration_s=lock_duration_s,
        )
    )

    time_s = 0.0
    events: list[SimulationEvent] = []
    for step in steps:
        time_s += step.dt_s
        track = tracker.update(step.detections)
        state = engagement.update(manager, track, step.dt_s)
        events.append(SimulationEvent(time_s=time_s, track=track, engagement=state))

    return events

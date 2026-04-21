from __future__ import annotations

from uav.simulation.vision_scenario import SyntheticDetectionStep, run_vision_simulation
from uav.vision.detector import Detection


def test_vision_simulation_reaches_lock_phase() -> None:
    steps = [
        SyntheticDetectionStep(dt_s=1.0, detections=[]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at_center()]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at_center()]),
    ]

    events = run_vision_simulation(steps, lock_duration_s=2.0)

    assert [event.engagement.phase for event in events] == ["search", "track", "lock"]
    assert events[-1].track is not None
    assert events[-1].track.target_id == 1


def _target_at_center() -> Detection:
    return Detection(
        class_id=0,
        label="uav",
        confidence=0.9,
        x_min=920,
        y_min=575,
        x_max=1000,
        y_max=625,
        track_id=1,
    )

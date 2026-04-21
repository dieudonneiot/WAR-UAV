from __future__ import annotations

from rich.console import Console
from rich.table import Table

from uav.simulation.vision_scenario import SyntheticDetectionStep, run_vision_simulation
from uav.vision.detector import Detection


def main() -> None:
    steps = [
        SyntheticDetectionStep(dt_s=1.0, detections=[]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at(700, 520, track_id=1)]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at(930, 590, track_id=1)]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at(950, 600, track_id=1)]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at(965, 610, track_id=1)]),
        SyntheticDetectionStep(dt_s=1.0, detections=[_target_at(960, 600, track_id=1)]),
    ]

    events = run_vision_simulation(steps)
    table = Table(title="Vision Simulation")
    table.add_column("t")
    table.add_column("phase")
    table.add_column("target")
    table.add_column("lock")
    table.add_column("err_x")
    table.add_column("err_y")

    for event in events:
        target_id = "-" if event.track is None else str(event.track.target_id)
        error_x = _format_optional(event.engagement.center_error_x_px)
        error_y = _format_optional(event.engagement.center_error_y_px)
        table.add_row(
            f"{event.time_s:.1f}s",
            event.engagement.phase,
            target_id,
            f"{event.engagement.lock_progress_s:.1f}s",
            error_x,
            error_y,
        )

    Console().print(table)


def _target_at(center_x: float, center_y: float, track_id: int) -> Detection:
    width = 80
    height = 50
    return Detection(
        class_id=0,
        label="uav",
        confidence=0.9,
        x_min=center_x - width / 2,
        y_min=center_y - height / 2,
        x_max=center_x + width / 2,
        y_max=center_y + height / 2,
        track_id=track_id,
    )


def _format_optional(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}px"


if __name__ == "__main__":
    main()

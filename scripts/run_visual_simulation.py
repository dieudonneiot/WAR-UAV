from __future__ import annotations

import argparse

import cv2
from rich.console import Console

from uav.simulation.vision_scenario import SyntheticDetectionStep, run_vision_simulation
from uav.simulation.visualizer import SimulationVisualizer
from uav.vision.detector import Detection


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a visual UAV target-lock simulation.")
    parser.add_argument("--headless", action="store_true", help="Save a preview image instead of opening a GUI.")
    parser.add_argument(
        "--output",
        default="logs/visual_simulation_preview.png",
        help="Preview image path used with --headless.",
    )
    parser.add_argument("--delay-ms", type=int, default=600, help="Delay between GUI frames.")
    args = parser.parse_args()

    events = run_vision_simulation(_scenario_steps())
    visualizer = SimulationVisualizer()

    if args.headless:
        output_path = visualizer.save_preview(events[-1], args.output)
        Console().print(f"[green]Saved visual simulation preview:[/green] {output_path}")
        return

    for event in events:
        cv2.imshow("TEKNOFEST UAV Simulation", visualizer.render(event))
        key = cv2.waitKey(args.delay_ms) & 0xFF
        if key in {27, ord("q")}:
            break

    cv2.destroyAllWindows()


def _scenario_steps() -> list[SyntheticDetectionStep]:
    return [
        SyntheticDetectionStep(dt_s=0.8, detections=[]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(640, 500, track_id=1)]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(780, 540, track_id=1)]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(900, 580, track_id=1)]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(940, 590, track_id=1)]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(960, 600, track_id=1)]),
        SyntheticDetectionStep(dt_s=0.8, detections=[_target_at(965, 604, track_id=1)]),
    ]


def _target_at(center_x: float, center_y: float, track_id: int) -> Detection:
    width = 96
    height = 56
    return Detection(
        class_id=0,
        label="uav",
        confidence=0.91,
        x_min=center_x - width / 2,
        y_min=center_y - height / 2,
        x_max=center_x + width / 2,
        y_max=center_y + height / 2,
        track_id=track_id,
    )


if __name__ == "__main__":
    main()

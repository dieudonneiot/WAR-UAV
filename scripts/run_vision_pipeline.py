from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from rich.console import Console

from uav.autonomy.engagement import EngagementConfig, EngagementController
from uav.autonomy.mission_manager import MissionManager
from uav.simulation.vision_scenario import SimulationEvent
from uav.simulation.visualizer import SimulationVisualizer, VisualizerConfig
from uav.vision.detector import TargetDetector
from uav.vision.frame_source import OpenCVFrameSource
from uav.vision.tracker import TargetTracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run YOLO detection through the UAV vision loop.")
    parser.add_argument("--source", default="0", help="Camera index, video path, or image stream source.")
    parser.add_argument("--model", default="yolov8n.pt", help="Ultralytics model path or model name.")
    parser.add_argument("--confidence", type=float, default=0.25, help="Detection confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.45, help="Ultralytics NMS IoU threshold.")
    parser.add_argument("--imgsz", type=int, default=0, help="YOLO inference image size. 0 uses model default.")
    parser.add_argument("--min-box-area", type=float, default=0.0, help="Ignore smaller boxes in pixels.")
    parser.add_argument(
        "--max-missed-frames",
        type=int,
        default=3,
        help="Keep the last target visible for this many missed frames.",
    )
    parser.add_argument("--smoothing", type=float, default=0.65, help="Track smoothing factor from 0 to 1.")
    parser.add_argument("--lock-duration-s", type=float, default=4.0, help="Seconds required to lock.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after this many frames. 0 means no limit.")
    parser.add_argument("--headless", action="store_true", help="Save the last frame instead of opening a GUI.")
    parser.add_argument(
        "--output",
        default="logs/vision_pipeline_preview.png",
        help="Preview image path used with --headless.",
    )
    args = parser.parse_args()

    console = Console()
    detector = TargetDetector(
        model_path=args.model,
        confidence_threshold=args.confidence,
        iou_threshold=args.iou,
        image_size=None if args.imgsz <= 0 else args.imgsz,
        min_box_area_px=args.min_box_area,
    )
    tracker = TargetTracker(
        min_confidence=args.confidence,
        max_missed_frames=args.max_missed_frames,
        smoothing_alpha=args.smoothing,
    )
    manager = MissionManager(mission_name="vision_pipeline")

    last_dashboard = None
    engagement = None
    visualizer = None

    with OpenCVFrameSource(_parse_source(args.source)) as source:
        for frame_count, sample in enumerate(source, start=1):
            frame_height, frame_width = sample.frame.shape[:2]
            if engagement is None:
                engagement = EngagementController(
                    EngagementConfig(
                        image_width=frame_width,
                        image_height=frame_height,
                        lock_duration_s=args.lock_duration_s,
                    )
                )
                visualizer = SimulationVisualizer(
                    VisualizerConfig(image_width=frame_width, image_height=frame_height)
                )

            detections = detector.predict(sample.frame)
            track = tracker.update(detections)
            state = engagement.update(manager, track, sample.dt_s)
            event = SimulationEvent(
                time_s=sample.time_s,
                track=track,
                engagement=state,
                camera_frame=sample.frame,
            )
            last_dashboard = visualizer.render(event)

            if not args.headless:
                cv2.imshow("TEKNOFEST UAV Vision Pipeline", last_dashboard)
                key = cv2.waitKey(1) & 0xFF
                if key in {27, ord("q")}:
                    break

            if args.max_frames and frame_count >= args.max_frames:
                break

    cv2.destroyAllWindows()

    if args.headless and last_dashboard is not None:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), last_dashboard)
        console.print(f"[green]Saved vision pipeline preview:[/green] {output_path}")


def _parse_source(source: str) -> int | str:
    if source.isdigit():
        return int(source)
    return source


if __name__ == "__main__":
    main()

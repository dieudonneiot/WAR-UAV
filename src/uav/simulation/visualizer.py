from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from uav.simulation.vision_scenario import SimulationEvent


@dataclass(frozen=True, slots=True)
class VisualizerConfig:
    canvas_width: int = 1280
    canvas_height: int = 720
    image_width: int = 1920
    image_height: int = 1200


class SimulationVisualizer:
    def __init__(self, config: VisualizerConfig | None = None) -> None:
        self.config = config or VisualizerConfig()

    def render(self, event: SimulationEvent) -> np.ndarray:
        canvas = np.full(
            (self.config.canvas_height, self.config.canvas_width, 3),
            (32, 35, 38),
            dtype=np.uint8,
        )
        camera_rect = (24, 48, 800, 520)
        map_rect = (848, 48, 408, 520)
        telemetry_rect = (24, 592, 1232, 104)

        self._draw_panel(canvas, camera_rect, "Camera")
        self._draw_panel(canvas, map_rect, "Map")
        self._draw_panel(canvas, telemetry_rect, "Telemetry")
        self._draw_camera(canvas, camera_rect, event)
        self._draw_map(canvas, map_rect, event)
        self._draw_telemetry(canvas, telemetry_rect, event)
        return canvas

    def save_preview(self, event: SimulationEvent, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), self.render(event))
        return path

    def _draw_panel(self, canvas: np.ndarray, rect: tuple[int, int, int, int], title: str) -> None:
        x, y, width, height = rect
        cv2.rectangle(canvas, (x, y), (x + width, y + height), (20, 22, 24), -1)
        cv2.rectangle(canvas, (x, y), (x + width, y + height), (84, 92, 100), 1)
        cv2.putText(
            canvas,
            title,
            (x + 12, y + 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (220, 226, 232),
            2,
            cv2.LINE_AA,
        )

    def _draw_camera(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        event: SimulationEvent,
    ) -> None:
        x, y, width, height = rect
        view_x, view_y = x + 12, y + 40
        view_w, view_h = width - 24, height - 52
        horizon_y = view_y + int(view_h * 0.46)

        cv2.rectangle(canvas, (view_x, view_y), (view_x + view_w, horizon_y), (165, 190, 210), -1)
        cv2.rectangle(
            canvas,
            (view_x, horizon_y),
            (view_x + view_w, view_y + view_h),
            (62, 92, 64),
            -1,
        )
        cv2.line(canvas, (view_x, horizon_y), (view_x + view_w, horizon_y), (235, 235, 235), 2)

        center = (view_x + view_w // 2, view_y + view_h // 2)
        cv2.drawMarker(canvas, center, (240, 240, 240), cv2.MARKER_CROSS, 28, 1)

        if event.track is not None:
            target_center = self._camera_to_view(
                event.track.center_x,
                event.track.center_y,
                view_x,
                view_y,
                view_w,
                view_h,
            )
            box_w = max(28, int(event.track.width / self.config.image_width * view_w))
            box_h = max(20, int(event.track.height / self.config.image_height * view_h))
            color = (50, 220, 80) if event.engagement.lock_active else (40, 180, 255)
            top_left = (target_center[0] - box_w // 2, target_center[1] - box_h // 2)
            bottom_right = (target_center[0] + box_w // 2, target_center[1] + box_h // 2)
            cv2.rectangle(canvas, top_left, bottom_right, color, 2)
            cv2.line(canvas, center, target_center, color, 1)
            cv2.putText(
                canvas,
                f"{event.track.label} {event.track.confidence:.2f}",
                (top_left[0], max(view_y + 20, top_left[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )

    def _draw_map(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        event: SimulationEvent,
    ) -> None:
        x, y, width, height = rect
        view_x, view_y = x + 12, y + 40
        view_w, view_h = width - 24, height - 52
        cv2.rectangle(canvas, (view_x, view_y), (view_x + view_w, view_y + view_h), (70, 82, 72), -1)

        grid_color = (110, 130, 76)
        for grid_x in range(view_x, view_x + view_w, 48):
            cv2.line(canvas, (grid_x, view_y), (grid_x, view_y + view_h), grid_color, 1)
        for grid_y in range(view_y, view_y + view_h, 48):
            cv2.line(canvas, (view_x, grid_y), (view_x + view_w, grid_y), grid_color, 1)

        road_x = view_x + int(view_w * 0.54)
        cv2.line(canvas, (road_x, view_y), (road_x + 22, view_y + view_h), (72, 74, 78), 26)
        cv2.line(canvas, (road_x, view_y), (road_x + 22, view_y + view_h), (190, 190, 95), 2)

        ownship = (view_x + view_w // 2, view_y + int(view_h * 0.65))
        self._draw_aircraft(canvas, ownship, (255, 170, 60))

        if event.track is not None:
            offset_x = int((event.track.center_x - self.config.image_width / 2) * 0.09)
            offset_y = int((event.track.center_y - self.config.image_height / 2) * 0.09)
            target = (ownship[0] + offset_x, ownship[1] + offset_y - 120)
            cv2.circle(canvas, target, 8, (40, 180, 255), -1)
            cv2.line(canvas, ownship, target, (40, 180, 255), 1)

    def _draw_telemetry(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        event: SimulationEvent,
    ) -> None:
        x, y, _, _ = rect
        target_id = "-" if event.track is None else str(event.track.target_id)
        color = (50, 220, 80) if event.engagement.lock_active else (40, 180, 255)
        lines = [
            f"t={event.time_s:.1f}s",
            f"phase={event.engagement.phase}",
            f"target={target_id}",
            f"lock={event.engagement.lock_progress_s:.1f}s",
            f"err_x={self._format_px(event.engagement.center_error_x_px)}",
            f"err_y={self._format_px(event.engagement.center_error_y_px)}",
        ]
        cv2.putText(
            canvas,
            "  ".join(lines),
            (x + 16, y + 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            color,
            2,
            cv2.LINE_AA,
        )

    def _camera_to_view(
        self,
        center_x: float,
        center_y: float,
        view_x: int,
        view_y: int,
        view_w: int,
        view_h: int,
    ) -> tuple[int, int]:
        return (
            view_x + int(center_x / self.config.image_width * view_w),
            view_y + int(center_y / self.config.image_height * view_h),
        )

    def _draw_aircraft(self, canvas: np.ndarray, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        cx, cy = center
        points = np.array(
            [
                [cx, cy - 22],
                [cx - 16, cy + 18],
                [cx, cy + 8],
                [cx + 16, cy + 18],
            ],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(canvas, points, color)
        cv2.polylines(canvas, [points], isClosed=True, color=(245, 245, 245), thickness=1)

    def _format_px(self, value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:.0f}px"

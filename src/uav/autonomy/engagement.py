from __future__ import annotations

from dataclasses import dataclass

from uav.autonomy.mission_manager import MissionManager
from uav.vision.tracker import TrackState


@dataclass(frozen=True, slots=True)
class EngagementConfig:
    image_width: int
    image_height: int
    lock_duration_s: float
    center_tolerance_ratio: float = 0.12


@dataclass(frozen=True, slots=True)
class EngagementState:
    phase: str
    lock_progress_s: float
    target_id: int | None
    center_error_x_px: float | None
    center_error_y_px: float | None

    @property
    def lock_active(self) -> bool:
        return self.phase == "lock"


class EngagementController:
    def __init__(self, config: EngagementConfig) -> None:
        self.config = config
        self._lock_progress_s = 0.0

    def update(
        self,
        manager: MissionManager,
        track: TrackState | None,
        dt_s: float,
    ) -> EngagementState:
        if track is None:
            self._lock_progress_s = 0.0
            manager.transition_to("search")
            return EngagementState(
                phase=manager.current_phase,
                lock_progress_s=0.0,
                target_id=None,
                center_error_x_px=None,
                center_error_y_px=None,
            )

        center_error_x_px, center_error_y_px = self._center_error_px(track)
        if self._is_centered(center_error_x_px, center_error_y_px):
            self._lock_progress_s += dt_s
        else:
            self._lock_progress_s = 0.0

        next_phase = (
            "lock"
            if self._lock_progress_s >= self.config.lock_duration_s
            else "track"
        )
        manager.transition_to(next_phase)
        return EngagementState(
            phase=manager.current_phase,
            lock_progress_s=self._lock_progress_s,
            target_id=track.target_id,
            center_error_x_px=center_error_x_px,
            center_error_y_px=center_error_y_px,
        )

    def _center_error_px(self, track: TrackState) -> tuple[float, float]:
        return (
            track.center_x - self.config.image_width / 2,
            track.center_y - self.config.image_height / 2,
        )

    def _is_centered(self, center_error_x_px: float, center_error_y_px: float) -> bool:
        tolerance_x = self.config.image_width * self.config.center_tolerance_ratio
        tolerance_y = self.config.image_height * self.config.center_tolerance_ratio
        return abs(center_error_x_px) <= tolerance_x and abs(center_error_y_px) <= tolerance_y

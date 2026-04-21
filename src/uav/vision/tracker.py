from __future__ import annotations

from dataclasses import dataclass

from uav.vision.detector import Detection


@dataclass(slots=True)
class TrackState:
    target_id: int
    center_x: float
    center_y: float
    confidence: float
    class_id: int
    label: str
    width: float
    height: float


class TargetTracker:
    def __init__(self, min_confidence: float = 0.25) -> None:
        self.min_confidence = min_confidence
        self._last_target_id: int | None = None
        self._next_target_id = 1

    def update(self, detections: list[Detection]) -> TrackState | None:
        candidates = [
            detection
            for detection in detections
            if detection.confidence >= self.min_confidence
        ]
        if not candidates:
            return None

        best_detection = max(candidates, key=lambda detection: detection.confidence)
        target_id = self._resolve_target_id(best_detection)
        self._last_target_id = target_id

        return TrackState(
            target_id=target_id,
            center_x=best_detection.center_x,
            center_y=best_detection.center_y,
            confidence=best_detection.confidence,
            class_id=best_detection.class_id,
            label=best_detection.label,
            width=best_detection.width,
            height=best_detection.height,
        )

    def _resolve_target_id(self, detection: Detection) -> int:
        if detection.track_id is not None:
            return detection.track_id
        if self._last_target_id is not None:
            return self._last_target_id

        target_id = self._next_target_id
        self._next_target_id += 1
        return target_id

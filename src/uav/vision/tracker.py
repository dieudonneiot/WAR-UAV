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
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 0.0
    y_max: float = 0.0
    age: int = 1
    missed_frames: int = 0
    is_confirmed: bool = True


class TargetTracker:
    def __init__(
        self,
        min_confidence: float = 0.25,
        max_missed_frames: int = 3,
        smoothing_alpha: float = 0.65,
        min_iou: float = 0.10,
    ) -> None:
        self.min_confidence = min_confidence
        self.max_missed_frames = max_missed_frames
        self.smoothing_alpha = smoothing_alpha
        self.min_iou = min_iou
        self._active_track: TrackState | None = None
        self._next_target_id = 1

    def update(self, detections: list[Detection]) -> TrackState | None:
        candidates = [
            detection
            for detection in detections
            if detection.confidence >= self.min_confidence
        ]
        if not candidates:
            return self._mark_missed()

        best_detection = self._select_detection(candidates)
        target_id = self._resolve_target_id(best_detection)
        track = self._track_from_detection(best_detection, target_id)
        self._active_track = track
        return track

    def reset(self) -> None:
        self._active_track = None

    def _select_detection(self, detections: list[Detection]) -> Detection:
        active_track = self._active_track
        if active_track is not None:
            same_id = [
                detection
                for detection in detections
                if detection.track_id is not None and detection.track_id == active_track.target_id
            ]
            if same_id:
                return max(same_id, key=self._score_detection)

            overlapping = [
                detection
                for detection in detections
                if _iou(active_track, detection) >= self.min_iou
            ]
            if overlapping:
                return max(overlapping, key=lambda detection: _iou(active_track, detection))

        return max(detections, key=self._score_detection)

    def _track_from_detection(self, detection: Detection, target_id: int) -> TrackState:
        previous = self._active_track
        if previous is None or previous.target_id != target_id:
            return TrackState(
                target_id=target_id,
                center_x=detection.center_x,
                center_y=detection.center_y,
                confidence=detection.confidence,
                class_id=detection.class_id,
                label=detection.label,
                width=detection.width,
                height=detection.height,
                x_min=detection.x_min,
                y_min=detection.y_min,
                x_max=detection.x_max,
                y_max=detection.y_max,
            )

        alpha = self.smoothing_alpha
        return TrackState(
            target_id=target_id,
            center_x=_smooth(previous.center_x, detection.center_x, alpha),
            center_y=_smooth(previous.center_y, detection.center_y, alpha),
            confidence=detection.confidence,
            class_id=detection.class_id,
            label=detection.label,
            width=_smooth(previous.width, detection.width, alpha),
            height=_smooth(previous.height, detection.height, alpha),
            x_min=_smooth(previous.x_min, detection.x_min, alpha),
            y_min=_smooth(previous.y_min, detection.y_min, alpha),
            x_max=_smooth(previous.x_max, detection.x_max, alpha),
            y_max=_smooth(previous.y_max, detection.y_max, alpha),
            age=previous.age + 1,
        )

    def _mark_missed(self) -> TrackState | None:
        if self._active_track is None:
            return None
        if self._active_track.missed_frames >= self.max_missed_frames:
            self.reset()
            return None

        previous = self._active_track
        missed_track = TrackState(
            target_id=previous.target_id,
            center_x=previous.center_x,
            center_y=previous.center_y,
            confidence=previous.confidence * 0.75,
            class_id=previous.class_id,
            label=previous.label,
            width=previous.width,
            height=previous.height,
            x_min=previous.x_min,
            y_min=previous.y_min,
            x_max=previous.x_max,
            y_max=previous.y_max,
            age=previous.age,
            missed_frames=previous.missed_frames + 1,
            is_confirmed=False,
        )
        self._active_track = missed_track
        return missed_track

    def _score_detection(self, detection: Detection) -> float:
        area_score = min(detection.area / 20_000, 1.0)
        return detection.confidence * 0.8 + area_score * 0.2

    def _resolve_target_id(self, detection: Detection) -> int:
        if detection.track_id is not None:
            return detection.track_id
        if self._active_track is not None:
            return self._active_track.target_id

        target_id = self._next_target_id
        self._next_target_id += 1
        return target_id


def _smooth(previous: float, current: float, alpha: float) -> float:
    return previous * (1 - alpha) + current * alpha


def _iou(track: TrackState, detection: Detection) -> float:
    x_min = max(track.x_min, detection.x_min)
    y_min = max(track.y_min, detection.y_min)
    x_max = min(track.x_max, detection.x_max)
    y_max = min(track.y_max, detection.y_max)
    intersection_width = max(0.0, x_max - x_min)
    intersection_height = max(0.0, y_max - y_min)
    intersection = intersection_width * intersection_height
    union = track.width * track.height + detection.area - intersection
    if union <= 0:
        return 0.0
    return intersection / union

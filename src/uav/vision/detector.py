from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ultralytics import YOLO


@dataclass(frozen=True, slots=True)
class Detection:
    class_id: int
    label: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    track_id: int | None = None

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min


class TargetDetector:
    def __init__(
        self,
        model_path: str | Path,
        confidence_threshold: float = 0.25,
        target_class_ids: set[int] | None = None,
    ) -> None:
        self.model = YOLO(str(model_path))
        self.confidence_threshold = confidence_threshold
        self.target_class_ids = target_class_ids

    def predict(self, frame: Any) -> list[Detection]:
        results = self.model(frame, verbose=False)
        detections: list[Detection] = []
        for result in results:
            detections.extend(self._detections_from_result(result))
        return detections

    def _detections_from_result(self, result: Any) -> list[Detection]:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        xyxy_rows = _rows(getattr(boxes, "xyxy", []))
        confidences = _values(getattr(boxes, "conf", []))
        class_ids = _values(getattr(boxes, "cls", []))
        track_ids = _optional_values(getattr(boxes, "id", None), len(xyxy_rows))
        names = getattr(result, "names", None) or getattr(self.model, "names", {})

        detections: list[Detection] = []
        for xyxy, confidence, class_id, track_id in zip(
            xyxy_rows, confidences, class_ids, track_ids, strict=False
        ):
            confidence_float = float(confidence)
            class_id_int = int(class_id)
            if confidence_float < self.confidence_threshold:
                continue
            if self.target_class_ids is not None and class_id_int not in self.target_class_ids:
                continue

            x_min, y_min, x_max, y_max = [float(value) for value in xyxy[:4]]
            detections.append(
                Detection(
                    class_id=class_id_int,
                    label=_label_for(names, class_id_int),
                    confidence=confidence_float,
                    x_min=x_min,
                    y_min=y_min,
                    x_max=x_max,
                    y_max=y_max,
                    track_id=None if track_id is None else int(track_id),
                )
            )

        return detections


def _to_builtin(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _rows(value: Any) -> list[list[float]]:
    built = _to_builtin(value)
    if built is None:
        return []
    return built


def _values(value: Any) -> list[float]:
    built = _to_builtin(value)
    if built is None:
        return []
    return built


def _optional_values(value: Any, count: int) -> list[int | None]:
    built = _to_builtin(value)
    if built is None:
        return [None] * count
    return built


def _label_for(names: Any, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, list) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)

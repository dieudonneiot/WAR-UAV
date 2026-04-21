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

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        if self.height <= 0:
            return 0.0
        return self.width / self.height


class TargetDetector:
    def __init__(
        self,
        model_path: str | Path,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        image_size: int | None = None,
        target_class_ids: set[int] | None = None,
        min_box_area_px: float = 0.0,
        max_box_area_ratio: float = 1.0,
        min_aspect_ratio: float = 0.05,
        max_aspect_ratio: float = 20.0,
    ) -> None:
        self.model = YOLO(str(model_path))
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.image_size = image_size
        self.target_class_ids = target_class_ids
        self.min_box_area_px = min_box_area_px
        self.max_box_area_ratio = max_box_area_ratio
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio

    def predict(self, frame: Any) -> list[Detection]:
        options: dict[str, Any] = {
            "verbose": False,
            "conf": self.confidence_threshold,
            "iou": self.iou_threshold,
        }
        if self.image_size is not None:
            options["imgsz"] = self.image_size
        if self.target_class_ids is not None:
            options["classes"] = sorted(self.target_class_ids)

        results = self.model(frame, **options)
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
        frame_area = _frame_area(result)

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
            detection = Detection(
                class_id=class_id_int,
                label=_label_for(names, class_id_int),
                confidence=confidence_float,
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
                track_id=None if track_id is None else int(track_id),
            )
            if not self._passes_geometry_filters(detection, frame_area):
                continue

            detections.append(detection)

        return sorted(detections, key=lambda detection: detection.confidence, reverse=True)

    def _passes_geometry_filters(self, detection: Detection, frame_area: float | None) -> bool:
        if detection.width <= 0 or detection.height <= 0:
            return False
        if detection.area < self.min_box_area_px:
            return False
        if frame_area is not None and detection.area / frame_area > self.max_box_area_ratio:
            return False
        return self.min_aspect_ratio <= detection.aspect_ratio <= self.max_aspect_ratio


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


def _frame_area(result: Any) -> float | None:
    shape = getattr(result, "orig_shape", None)
    if shape is None or len(shape) < 2:
        return None
    height, width = shape[:2]
    return float(height * width)


def _label_for(names: Any, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, list) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)

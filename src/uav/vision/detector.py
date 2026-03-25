from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO


class TargetDetector:
    def __init__(self, model_path: str | Path) -> None:
        self.model = YOLO(str(model_path))

    def predict(self, frame) -> list:
        results = self.model(frame, verbose=False)
        return results


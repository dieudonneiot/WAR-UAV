from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class FrameSample:
    frame: np.ndarray
    time_s: float
    dt_s: float


class OpenCVFrameSource:
    def __init__(self, source: int | str | Path, fallback_dt_s: float = 1 / 30) -> None:
        self.source = source
        self.fallback_dt_s = fallback_dt_s
        self._capture: cv2.VideoCapture | None = None
        self._last_time_s = 0.0

    def __enter__(self) -> OpenCVFrameSource:
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[FrameSample]:
        if self._capture is None:
            self.open()

        while True:
            sample = self.read()
            if sample is None:
                break
            yield sample

    def open(self) -> None:
        capture = cv2.VideoCapture(str(self.source) if isinstance(self.source, Path) else self.source)
        if not capture.isOpened():
            raise RuntimeError(f"Could not open frame source: {self.source}")

        self._capture = capture
        self._last_time_s = 0.0

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def read(self) -> FrameSample | None:
        if self._capture is None:
            raise RuntimeError("Frame source is not open")

        ok, frame = self._capture.read()
        if not ok:
            return None

        time_s = self._frame_time_s()
        dt_s = max(time_s - self._last_time_s, self.fallback_dt_s)
        self._last_time_s = time_s
        return FrameSample(frame=frame, time_s=time_s, dt_s=dt_s)

    def _frame_time_s(self) -> float:
        if self._capture is None:
            return 0.0

        time_ms = self._capture.get(cv2.CAP_PROP_POS_MSEC)
        if time_ms > 0:
            return time_ms / 1000
        return self._last_time_s + self.fallback_dt_s

from __future__ import annotations

import cv2


class QRReader:
    def __init__(self) -> None:
        self._detector = cv2.QRCodeDetector()

    def decode(self, frame) -> str | None:
        value, _, _ = self._detector.detectAndDecode(frame)
        return value or None


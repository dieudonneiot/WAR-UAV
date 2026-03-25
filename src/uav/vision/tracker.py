from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrackState:
    target_id: int
    center_x: float
    center_y: float
    confidence: float


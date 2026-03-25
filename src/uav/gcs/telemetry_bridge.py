from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class TelemetrySample:
    latitude: float
    longitude: float
    altitude_m: float
    heading_deg: float
    lock_active: bool

    def to_payload(self) -> dict:
        return asdict(self)


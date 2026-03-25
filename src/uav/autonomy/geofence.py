from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Geofence:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.min_lat <= latitude <= self.max_lat and self.min_lon <= longitude <= self.max_lon


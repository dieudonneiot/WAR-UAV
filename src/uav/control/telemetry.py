from __future__ import annotations

import time
from dataclasses import dataclass, replace
from threading import Lock


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    phase: str = "standby"
    mode: str = "--"
    lat_e7: int | None = None
    lon_e7: int | None = None
    relative_alt_m: float | None = None
    wp_dist_m: float | None = None
    updated_at_s: float = 0.0


class TelemetryState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = TelemetrySnapshot(updated_at_s=time.monotonic())

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            return replace(self._snapshot)

    def update_phase(self, phase: str) -> None:
        self._update(phase=phase)

    def update_mode(self, mode: str) -> None:
        self._update(mode=mode.upper())

    def update_position(self, lat_e7: int, lon_e7: int, relative_alt_m: float) -> None:
        self._update(lat_e7=lat_e7, lon_e7=lon_e7, relative_alt_m=relative_alt_m)

    def update_wp_dist(self, wp_dist_m: float | None) -> None:
        self._update(wp_dist_m=wp_dist_m)

    def status_line(self) -> str:
        return format_status_line(self.snapshot())

    def _update(self, **changes: object) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, updated_at_s=time.monotonic(), **changes)


def format_status_line(snapshot: TelemetrySnapshot, now_s: float | None = None) -> str:
    now_s = time.monotonic() if now_s is None else now_s
    age_s = max(0.0, now_s - snapshot.updated_at_s)
    lat = _format_e7(snapshot.lat_e7)
    lon = _format_e7(snapshot.lon_e7)
    alt = _format_float(snapshot.relative_alt_m, "m")
    wp_dist = _format_float(snapshot.wp_dist_m, "m")
    return (
        f"phase={snapshot.phase} mode={snapshot.mode} lat={lat} lon={lon} "
        f"alt={alt} wp_dist={wp_dist} age={age_s:.1f}s"
    )


def _format_e7(value: int | None) -> str:
    return "--" if value is None else f"{value / 10_000_000:.7f}"


def _format_float(value: float | None, unit: str) -> str:
    return "--" if value is None else f"{value:.1f}{unit}"


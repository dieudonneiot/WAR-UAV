from __future__ import annotations

from uav.control.telemetry import TelemetrySnapshot, TelemetryState, format_status_line


def test_format_status_line_handles_unknown_values() -> None:
    snapshot = TelemetrySnapshot(phase="standby", mode="--", updated_at_s=10.0)

    line = format_status_line(snapshot, now_s=12.5)

    assert line == "phase=standby mode=-- lat=-- lon=-- alt=-- wp_dist=-- age=2.5s"


def test_telemetry_state_updates_status_values() -> None:
    telemetry = TelemetryState()

    telemetry.update_phase("navigate")
    telemetry.update_mode("guided")
    telemetry.update_position(353_630_000, 1_491_650_000, 50.25)
    telemetry.update_wp_dist(123.4)
    snapshot = telemetry.snapshot()

    assert snapshot.phase == "navigate"
    assert snapshot.mode == "GUIDED"
    assert snapshot.lat_e7 == 353_630_000
    assert snapshot.lon_e7 == 1_491_650_000
    assert snapshot.relative_alt_m == 50.25
    assert snapshot.wp_dist_m == 123.4
    assert "phase=navigate mode=GUIDED" in telemetry.status_line()


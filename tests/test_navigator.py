from __future__ import annotations

from uav.autonomy.navigator import (
    WaypointNavigator,
    compute_circle_waypoints,
    compute_line_waypoints,
    compute_mission_waypoints,
    compute_square_waypoints,
    compute_triangle_waypoints,
)


class FakeMavlinkClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.altitudes = iter([0.0, 12.5, 50.0])

    def set_mode(self, mode_name: str) -> None:
        self.calls.append(("set_mode", mode_name))

    def arm(self) -> None:
        self.calls.append(("arm", None))

    def get_position(self) -> tuple[int, int, float]:
        return 0, 0, next(self.altitudes)


def test_climb_to_uses_arduplane_takeoff_mode() -> None:
    client = FakeMavlinkClient()
    navigator = WaypointNavigator(client)

    navigator.climb_to(50.0)

    assert client.calls == [("set_mode", "TAKEOFF"), ("arm", None)]


def test_waypoint_shapes_return_expected_counts_and_home_endpoint() -> None:
    home = (100_000_000, 200_000_000)

    assert len(compute_square_waypoints(*home, side_m=500.0)) == 4
    assert len(compute_triangle_waypoints(*home, side_m=500.0)) == 3
    assert len(compute_line_waypoints(*home, side_m=500.0)) == 2

    assert compute_square_waypoints(*home, side_m=500.0)[-1] == home
    assert compute_triangle_waypoints(*home, side_m=500.0)[-1] == home
    assert compute_line_waypoints(*home, side_m=500.0)[-1] == home


def test_circle_waypoints_close_the_route_at_home() -> None:
    home = (100_000_000, 200_000_000)

    waypoints = compute_circle_waypoints(*home, radius_m=250.0, points=8)

    assert len(waypoints) == 9
    assert waypoints[-1] == home
    assert len(set(waypoints[:-1])) == 8


def test_compute_mission_waypoints_rejects_unknown_shape() -> None:
    try:
        compute_mission_waypoints("spiral", 100_000_000, 200_000_000)
    except ValueError as exc:
        assert "Unknown mission shape" in str(exc)
    else:
        raise AssertionError("Expected unknown mission shape to raise ValueError.")

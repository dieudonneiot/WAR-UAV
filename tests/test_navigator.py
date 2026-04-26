from __future__ import annotations

from uav.autonomy.navigator import WaypointNavigator


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


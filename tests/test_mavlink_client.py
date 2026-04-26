from __future__ import annotations

from uav.mavlink.client import MavlinkClient


def test_return_to_launch_uses_rtl_mode() -> None:
    client = MavlinkClient("udpin:0.0.0.0:14550")
    modes: list[str] = []
    client.set_mode = modes.append  # type: ignore[method-assign]

    client.return_to_launch()

    assert modes == ["RTL"]


def test_loiter_uses_loiter_mode() -> None:
    client = MavlinkClient("udpin:0.0.0.0:14550")
    modes: list[str] = []
    client.set_mode = modes.append  # type: ignore[method-assign]

    client.loiter()

    assert modes == ["LOITER"]

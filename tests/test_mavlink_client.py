from __future__ import annotations

from pymavlink import mavutil

from uav.mavlink.client import MavlinkClient, build_auto_mission_items


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


def test_build_auto_mission_items_adds_takeoff_waypoints_and_rtl() -> None:
    items = build_auto_mission_items(
        353_630_000,
        1_491_650_000,
        [(353_631_000, 1_491_650_000), (353_631_000, 1_491_651_000)],
        alt_m=50.0,
        acceptance_radius_m=65.0,
    )

    assert [item.command for item in items] == [
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
        mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
    ]
    assert items[0].current == 1
    assert items[1].param2 == 65.0
    assert items[-1].frame == mavutil.mavlink.MAV_FRAME_MISSION


def test_upload_auto_mission_sends_requested_items() -> None:
    client = MavlinkClient("udpin:0.0.0.0:14550")
    fake_master = FakeMissionMaster(requested_sequences=[0, 1, 2])
    client.master = fake_master

    count = client.upload_auto_mission(
        353_630_000,
        1_491_650_000,
        [(353_631_000, 1_491_650_000)],
        alt_m=50.0,
    )

    assert count == 3
    assert fake_master.mav.cleared
    assert fake_master.mav.mission_count == 3
    assert [item["seq"] for item in fake_master.mav.items] == [0, 1, 2]
    assert fake_master.mav.current_seq == 0


class FakeMissionRequest:
    def __init__(self, seq: int) -> None:
        self.seq = seq


class FakeMissionAck:
    type = mavutil.mavlink.MAV_MISSION_ACCEPTED


class FakeMissionMav:
    def __init__(self) -> None:
        self.cleared = False
        self.mission_count: int | None = None
        self.items: list[dict[str, int]] = []
        self.current_seq: int | None = None

    def mission_clear_all_send(self, *args: object) -> None:
        self.cleared = True

    def mission_count_send(self, *args: object) -> None:
        self.mission_count = int(args[2])

    def mission_item_int_send(self, *args: object) -> None:
        self.items.append({"seq": int(args[2]), "command": int(args[4])})

    def mission_set_current_send(self, *args: object) -> None:
        self.current_seq = int(args[2])


class FakeMissionMaster:
    target_system = 1
    target_component = 1

    def __init__(self, requested_sequences: list[int]) -> None:
        self.mav = FakeMissionMav()
        self._requests = [FakeMissionRequest(seq) for seq in requested_sequences]

    def recv_match(self, type: object, blocking: bool, timeout: float) -> object | None:
        if type == "MISSION_ACK":
            return FakeMissionAck()
        if self._requests:
            return self._requests.pop(0)
        return None

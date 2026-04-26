from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from pymavlink import mavutil


@dataclass(frozen=True, slots=True)
class MissionItemInt:
    frame: int
    command: int
    current: int
    autocontinue: int
    param1: float
    param2: float
    param3: float
    param4: float
    x: int
    y: int
    z: float


class MavlinkClient:
    def __init__(self, connection_string: str, baudrate: int = 57600) -> None:
        self.connection_string = connection_string
        self.baudrate = baudrate
        self.master = None
        self._modes: dict[str, int] = {}
        self._send_lock = Lock()

    def connect(self, timeout_s: float = 30.0) -> None:
        self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baudrate)
        heartbeat = self.master.wait_heartbeat(timeout=timeout_s)
        if heartbeat is None:
            raise TimeoutError(
                f"No MAVLink heartbeat received from {self.connection_string} "
                f"within {timeout_s:.0f}s. Wait until SITL reports GPS OK, then retry."
            )
        self._modes = self._wait_for_mode_mapping(timeout_s=timeout_s)

    # --- vehicle control ---

    def arm(self, arm: bool = True) -> None:
        with self._send_lock:
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                1 if arm else 0, 0, 0, 0, 0, 0, 0,
            )

    def set_mode(self, mode_name: str) -> None:
        mode_name = mode_name.upper()
        if mode_name not in self._modes:
            self._modes = self._wait_for_mode_mapping(timeout_s=5.0)
        if mode_name not in self._modes:
            available = ", ".join(sorted(self._modes)) or "none"
            raise ValueError(f"Mode {mode_name!r} is not available. Known modes: {available}")

        with self._send_lock:
            self.master.mav.set_mode_send(
                self.master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                self._modes[mode_name],
            )

    def return_to_launch(self) -> None:
        """Command the vehicle to return to its launch point."""
        self.set_mode("RTL")

    def loiter(self) -> None:
        """Command the vehicle to circle near its current position."""
        self.set_mode("LOITER")

    def upload_auto_mission(
        self,
        home_lat_e7: int,
        home_lon_e7: int,
        waypoints: list[tuple[int, int]],
        alt_m: float,
        acceptance_radius_m: float = 0.0,
        timeout_s: float = 30.0,
    ) -> int:
        """Upload TAKEOFF + waypoints + RTL as an AUTO mission."""
        items = build_auto_mission_items(
            home_lat_e7,
            home_lon_e7,
            waypoints,
            alt_m,
            acceptance_radius_m=acceptance_radius_m,
        )
        self._clear_mission()
        self._send_mission_count(len(items))

        deadline = time.monotonic() + timeout_s
        sent: set[int] = set()
        while len(sent) < len(items) and time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=["MISSION_REQUEST_INT", "MISSION_REQUEST"],
                blocking=True,
                timeout=0.5,
            )
            if msg is None:
                continue
            seq = int(msg.seq)
            if seq < 0 or seq >= len(items):
                continue
            self._send_mission_item_int(seq, items[seq])
            sent.add(seq)

        if len(sent) < len(items):
            missing = sorted(set(range(len(items))) - sent)
            raise TimeoutError(f"Mission upload timed out; missing item requests: {missing}")

        ack_timeout = max(0.1, deadline - time.monotonic())
        ack = self.master.recv_match(type="MISSION_ACK", blocking=True, timeout=ack_timeout)
        if ack is None:
            raise TimeoutError("Mission upload timed out waiting for MISSION_ACK.")
        if int(ack.type) != mavutil.mavlink.MAV_MISSION_ACCEPTED:
            raise RuntimeError(f"Mission upload rejected with MAV_MISSION_RESULT {ack.type}.")

        self._set_current_mission_item(0)
        return len(items)

    def rc_override(self, throttle: int = 0) -> None:
        """Override RC channel 3 (throttle). Pass 0 to release all overrides."""
        with self._send_lock:
            self.master.mav.rc_channels_override_send(
                self.master.target_system, self.master.target_component,
                0, 0, throttle, 0, 0, 0, 0, 0,
            )

    def reposition(self, lat_e7: int, lon_e7: int, alt_m: float) -> None:
        """Command the vehicle to fly to a GPS location (GUIDED mode)."""
        with self._send_lock:
            self.master.mav.command_int_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_DO_REPOSITION,
                2, 0, -1, 0, 0, 0,
                lat_e7, lon_e7, alt_m,
            )

    def disable_hand_launch(self) -> None:
        with self._send_lock:
            self.master.mav.param_set_send(
                self.master.target_system, self.master.target_component,
                b'TKOFF_THR_MINACC', 0.0,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )

    def disable_arming_checks(self) -> None:
        """Disable all pre-arm checks — required in SITL where there is no RC input."""
        with self._send_lock:
            self.master.mav.param_set_send(
                self.master.target_system, self.master.target_component,
                b'ARMING_CHECK', 0.0,
                mavutil.mavlink.MAV_PARAM_TYPE_INT32,
            )

    def _clear_mission(self) -> None:
        with self._send_lock:
            try:
                self.master.mav.mission_clear_all_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                )
            except TypeError:
                self.master.mav.mission_clear_all_send(
                    self.master.target_system,
                    self.master.target_component,
                )

    def _send_mission_count(self, count: int) -> None:
        with self._send_lock:
            try:
                self.master.mav.mission_count_send(
                    self.master.target_system,
                    self.master.target_component,
                    count,
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                )
            except TypeError:
                self.master.mav.mission_count_send(
                    self.master.target_system,
                    self.master.target_component,
                    count,
                )

    def _send_mission_item_int(self, seq: int, item: MissionItemInt) -> None:
        with self._send_lock:
            try:
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                    item.frame,
                    item.command,
                    item.current,
                    item.autocontinue,
                    item.param1,
                    item.param2,
                    item.param3,
                    item.param4,
                    item.x,
                    item.y,
                    item.z,
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                )
            except TypeError:
                self.master.mav.mission_item_int_send(
                    self.master.target_system,
                    self.master.target_component,
                    seq,
                    item.frame,
                    item.command,
                    item.current,
                    item.autocontinue,
                    item.param1,
                    item.param2,
                    item.param3,
                    item.param4,
                    item.x,
                    item.y,
                    item.z,
                )

    def _set_current_mission_item(self, seq: int) -> None:
        with self._send_lock:
            self.master.mav.mission_set_current_send(
                self.master.target_system,
                self.master.target_component,
                seq,
            )

    # --- telemetry reads ---

    def get_position(self) -> tuple[int, int, float]:
        """Returns (lat_e7, lon_e7, relative_alt_m) from the latest GLOBAL_POSITION_INT."""
        msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True)
        return msg.lat, msg.lon, msg.relative_alt / 1000.0

    def get_nav_status(self, timeout: float = 0.5) -> float | None:
        """Returns distance-to-waypoint in metres, or None on timeout."""
        msg = self.master.recv_match(type='NAV_CONTROLLER_OUTPUT', blocking=True, timeout=timeout)
        return float(msg.wp_dist) if msg else None

    def _wait_for_mode_mapping(self, timeout_s: float) -> dict[str, int]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            modes = self.master.mode_mapping() or {}
            if modes:
                return {name.upper(): number for name, number in modes.items()}
            time.sleep(0.25)
        return {}


def build_auto_mission_items(
    home_lat_e7: int,
    home_lon_e7: int,
    waypoints: list[tuple[int, int]],
    alt_m: float,
    acceptance_radius_m: float = 0.0,
) -> list[MissionItemInt]:
    """Build an ArduPlane AUTO mission: take off, fly waypoints, then RTL."""
    mission_items = [
        MissionItemInt(
            frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            command=mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            current=1,
            autocontinue=1,
            param1=0.0,
            param2=0.0,
            param3=0.0,
            param4=0.0,
            x=home_lat_e7,
            y=home_lon_e7,
            z=alt_m,
        )
    ]

    for lat_e7, lon_e7 in waypoints:
        mission_items.append(
            MissionItemInt(
                frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                command=mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                current=0,
                autocontinue=1,
                param1=0.0,
                param2=acceptance_radius_m,
                param3=0.0,
                param4=0.0,
                x=lat_e7,
                y=lon_e7,
                z=alt_m,
            )
        )

    mission_items.append(
        MissionItemInt(
            frame=mavutil.mavlink.MAV_FRAME_MISSION,
            command=mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            current=0,
            autocontinue=1,
            param1=0.0,
            param2=0.0,
            param3=0.0,
            param4=0.0,
            x=0,
            y=0,
            z=0.0,
        )
    )
    return mission_items

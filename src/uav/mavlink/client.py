from __future__ import annotations

from pymavlink import mavutil


class MavlinkClient:
    def __init__(self, connection_string: str, baudrate: int = 57600) -> None:
        self.connection_string = connection_string
        self.baudrate = baudrate
        self.master = None
        self._modes: dict[str, int] = {}

    def connect(self) -> None:
        self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baudrate)
        self.master.wait_heartbeat()
        self._modes = self.master.mode_mapping()

    # --- vehicle control ---

    def arm(self, arm: bool = True) -> None:
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1 if arm else 0, 0, 0, 0, 0, 0, 0,
        )

    def set_mode(self, mode_name: str) -> None:
        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            self._modes[mode_name],
        )

    def rc_override(self, throttle: int = 0) -> None:
        """Override RC channel 3 (throttle). Pass 0 to release all overrides."""
        self.master.mav.rc_channels_override_send(
            self.master.target_system, self.master.target_component,
            0, 0, throttle, 0, 0, 0, 0, 0,
        )

    def reposition(self, lat_e7: int, lon_e7: int, alt_m: float) -> None:
        """Command the vehicle to fly to a GPS location (GUIDED mode)."""
        self.master.mav.command_int_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION,
            2, 0, -1, 0, 0, 0,
            lat_e7, lon_e7, alt_m,
        )

    def disable_hand_launch(self) -> None:
        self.master.mav.param_set_send(
            self.master.target_system, self.master.target_component,
            b'TKOFF_THR_MINACC', 0.0,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )

    def disable_arming_checks(self) -> None:
        """Disable all pre-arm checks — required in SITL where there is no RC input."""
        self.master.mav.param_set_send(
            self.master.target_system, self.master.target_component,
            b'ARMING_CHECK', 0.0,
            mavutil.mavlink.MAV_PARAM_TYPE_INT32,
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


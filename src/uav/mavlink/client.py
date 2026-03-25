from __future__ import annotations

from pymavlink import mavutil


class MavlinkClient:
    def __init__(self, connection_string: str, baudrate: int = 57600) -> None:
        self.connection_string = connection_string
        self.baudrate = baudrate
        self.master = None

    def connect(self) -> None:
        self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baudrate)
        self.master.wait_heartbeat()


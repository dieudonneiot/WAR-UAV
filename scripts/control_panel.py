"""Interactive terminal flight-control panel.

Usage:
    python scripts/control_panel.py
    python scripts/control_panel.py --direct
"""
from __future__ import annotations

import argparse

from uav.control.emergency import (
    DEFAULT_EMERGENCY_HOST,
    DEFAULT_EMERGENCY_PORT,
    request_loiter_via_local_server,
    request_mode_via_local_server,
    request_rtl_via_local_server,
    request_status_via_local_server,
)
from uav.control.telemetry import TelemetryState
from uav.mavlink.client import MavlinkClient

MODE_ALIASES = {
    "auto": "AUTO",
    "fbwa": "FBWA",
    "guided": "GUIDED",
    "manual": "MANUAL",
    "takeoff": "TAKEOFF",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive flight-control panel.")
    parser.add_argument("--connection", default="udpin:0.0.0.0:14550",
                        help="MAVLink connection string (default: udpin:0.0.0.0:14550)")
    parser.add_argument("--command-host", default=DEFAULT_EMERGENCY_HOST,
                        help=f"Running mission command host (default: {DEFAULT_EMERGENCY_HOST})")
    parser.add_argument("--command-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Running mission command port (default: {DEFAULT_EMERGENCY_PORT})")
    parser.add_argument("--direct", action="store_true",
                        help="Skip the running mission command server and use MAVLink directly.")
    args = parser.parse_args()

    panel = ControlPanel(args)
    panel.run()


class ControlPanel:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.client: MavlinkClient | None = None

    def run(self) -> None:
        print("TEKNOFEST flight control panel")
        print("Commands: status/s, rtl/r, loiter/l, mode <name>, auto, guided, fbwa, takeoff, help, quit/q")
        self.print_status()

        while True:
            try:
                command = input("flight> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nPanel closed.")
                return

            if not command:
                continue
            if command.lower() in {"q", "quit", "exit"}:
                print("Panel closed.")
                return
            self.handle(command)

    def handle(self, command: str) -> None:
        words = command.split()
        action = words[0].lower()

        if action in {"h", "help", "?"}:
            self.print_help()
        elif action in {"s", "status"}:
            self.print_status()
        elif action in {"r", "rtl"}:
            self.send_rtl()
        elif action in {"l", "loiter"}:
            self.send_loiter()
        elif action == "mode" and len(words) >= 2:
            self.send_mode(words[1])
        elif action in MODE_ALIASES:
            self.send_mode(MODE_ALIASES[action])
        else:
            print(f"Unknown command: {command}")

    def print_help(self) -> None:
        print("status/s        print latest telemetry")
        print("rtl/r           return to launch and stop mission route")
        print("loiter/l        circle near current position and stop mission route")
        print("mode <name>     set any ArduPlane mode, for example mode AUTO")
        print("auto/guided/fbwa/takeoff are shortcuts for mode <name>")
        print("quit/q          close this panel")

    def print_status(self) -> None:
        response = self._local_request("STATUS", request_status_via_local_server)
        if response is not None:
            print(_strip_ok(response))
            return

        client = self._direct_client()
        telemetry = TelemetryState()
        telemetry.update_phase("direct")
        lat_e7, lon_e7, alt_m = client.get_position()
        telemetry.update_position(lat_e7, lon_e7, alt_m)
        print(telemetry.status_line())

    def send_rtl(self) -> None:
        response = self._local_request("RTL", request_rtl_via_local_server)
        if response is not None:
            print(response)
            return
        self._direct_client().return_to_launch()
        print("RTL command sent directly.")

    def send_loiter(self) -> None:
        response = self._local_request("LOITER", request_loiter_via_local_server)
        if response is not None:
            print(response)
            return
        self._direct_client().loiter()
        print("LOITER command sent directly.")

    def send_mode(self, mode_name: str) -> None:
        mode_name = mode_name.upper()
        response = self._local_request(
            f"MODE {mode_name}",
            lambda host, port: request_mode_via_local_server(mode_name, host, port),
        )
        if response is not None:
            print(response)
            return
        self._direct_client().set_mode(mode_name)
        print(f"{mode_name} command sent directly.")

    def _local_request(self, command: str, sender) -> str | None:
        if self.args.direct:
            return None
        response = sender(self.args.command_host, self.args.command_port)
        if response is None and self.client is None:
            print(f"No running mission server for {command}; using direct MAVLink.")
        return response

    def _direct_client(self) -> MavlinkClient:
        if self.client is None:
            self.client = MavlinkClient(self.args.connection)
            print(f"Connecting to {self.args.connection} ...")
            self.client.connect()
            print("Connected.")
        return self.client


def _strip_ok(response: str) -> str:
    return response[3:] if response.startswith("OK ") else response


if __name__ == "__main__":
    main()

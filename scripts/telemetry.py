"""Print live aircraft telemetry.

Usage:
    python scripts/telemetry.py
    python scripts/telemetry.py --direct
"""
from __future__ import annotations

import argparse
import time

from uav.control.emergency import (
    DEFAULT_EMERGENCY_HOST,
    DEFAULT_EMERGENCY_PORT,
    request_status_via_local_server,
)
from uav.control.telemetry import TelemetryState
from uav.mavlink.client import MavlinkClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Print live flight telemetry.")
    parser.add_argument("--connection", default="udpin:0.0.0.0:14550",
                        help="MAVLink connection string (default: udpin:0.0.0.0:14550)")
    parser.add_argument("--command-host", default=DEFAULT_EMERGENCY_HOST,
                        help=f"Running mission command host (default: {DEFAULT_EMERGENCY_HOST})")
    parser.add_argument("--command-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Running mission command port (default: {DEFAULT_EMERGENCY_PORT})")
    parser.add_argument("--interval-s", type=float, default=1.0,
                        help="Seconds between telemetry lines (default: 1)")
    parser.add_argument("--count", type=int, default=0,
                        help="Number of lines to print; 0 means forever (default: 0)")
    parser.add_argument("--direct", action="store_true",
                        help="Skip the running mission command server and use MAVLink directly.")
    args = parser.parse_args()

    if not args.direct and _print_local_telemetry(args):
        return

    _print_direct_mavlink_telemetry(args)


def _print_local_telemetry(args: argparse.Namespace) -> bool:
    printed = 0
    while args.count <= 0 or printed < args.count:
        response = request_status_via_local_server(args.command_host, args.command_port)
        if response is None:
            if printed == 0:
                print("No running mission telemetry server found. Falling back to direct MAVLink.")
                return False
            print("Running mission telemetry server stopped.")
            return True
        print(_strip_ok(response))
        printed += 1
        time.sleep(args.interval_s)
    return True


def _print_direct_mavlink_telemetry(args: argparse.Namespace) -> None:
    client = MavlinkClient(args.connection)
    telemetry = TelemetryState()
    telemetry.update_phase("direct")

    print(f"Connecting to {args.connection} ...")
    client.connect()
    print("Connected. Press Ctrl+C to stop.")

    printed = 0
    try:
        while args.count <= 0 or printed < args.count:
            lat_e7, lon_e7, alt_m = client.get_position()
            telemetry.update_position(lat_e7, lon_e7, alt_m)
            print(telemetry.status_line())
            printed += 1
            time.sleep(args.interval_s)
    except KeyboardInterrupt:
        print("\nTelemetry stopped.")


def _strip_ok(response: str) -> str:
    return response[3:] if response.startswith("OK ") else response


if __name__ == "__main__":
    main()


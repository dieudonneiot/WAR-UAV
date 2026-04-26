"""Send an immediate Return-to-Launch command over MAVLink.

Usage:
    python scripts/emergency_rtl.py
    python scripts/emergency_rtl.py --direct --connection udpin:0.0.0.0:14551
"""
from __future__ import annotations

import argparse
import time

from uav.control.emergency import (
    DEFAULT_EMERGENCY_HOST,
    DEFAULT_EMERGENCY_PORT,
    request_rtl_via_local_server,
)
from uav.mavlink.client import MavlinkClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Send an emergency RTL command via MAVLink.")
    parser.add_argument("--connection", default="udpin:0.0.0.0:14550",
                        help="MAVLink connection string (default: udpin:0.0.0.0:14550)")
    parser.add_argument("--command-host", default=DEFAULT_EMERGENCY_HOST,
                        help=f"Running mission command host (default: {DEFAULT_EMERGENCY_HOST})")
    parser.add_argument("--command-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Running mission command port (default: {DEFAULT_EMERGENCY_PORT})")
    parser.add_argument("--direct", action="store_true",
                        help="Skip the running mission command server and use MAVLink directly.")
    args = parser.parse_args()

    if not args.direct:
        response = request_rtl_via_local_server(args.command_host, args.command_port)
        if response is not None:
            print(f"Running mission accepted emergency command: {response}")
            return
        print("No running mission emergency server found. Falling back to direct MAVLink.")

    client = MavlinkClient(args.connection)
    print(f"Connecting to {args.connection} ...")
    client.connect()
    print("Connected. Sending RTL ...")
    client.return_to_launch()
    time.sleep(2)
    print("RTL command sent.")


if __name__ == "__main__":
    main()

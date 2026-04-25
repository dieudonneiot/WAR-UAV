"""Live square waypoint mission via MAVLink (ArduPilot SITL or real hardware).

Usage:
    python scripts/run_square_mission.py
    python scripts/run_square_mission.py --connection tcp:127.0.0.1:5762 --side-m 500 --alt-m 50
"""
from __future__ import annotations

import argparse
import time

from uav.autonomy.mission_manager import MissionManager
from uav.autonomy.navigator import WaypointNavigator, compute_square_waypoints
from uav.mavlink.client import MavlinkClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fly a square waypoint mission via MAVLink.")
    parser.add_argument("--connection", default="tcp:127.0.0.1:5762",
                        help="MAVLink connection string (default: tcp:127.0.0.1:5762)")
    parser.add_argument("--side-m", type=float, default=500.0,
                        help="Square side length in metres (default: 500)")
    parser.add_argument("--alt-m", type=float, default=50.0,
                        help="Cruise altitude in metres AGL (default: 50)")
    parser.add_argument("--acceptance-radius", type=float, default=65.0,
                        help="Waypoint acceptance radius in metres (default: 65)")
    args = parser.parse_args()

    manager = MissionManager(mission_name="square_mission")
    client = MavlinkClient(args.connection)
    nav = WaypointNavigator(client, acceptance_radius_m=args.acceptance_radius)

    print(f"Connecting to {args.connection} …")
    client.connect()
    print("Connected.")

    print("Disabling hand-launch safety (TKOFF_THR_MINACC=0) …")
    client.disable_hand_launch()
    print("Disabling pre-arm checks (ARMING_CHECK=0) …")
    client.disable_arming_checks()
    time.sleep(1)

    print("Switching to FBWA …")
    client.set_mode("FBWA")
    time.sleep(1)

    print("Arming motors …")
    client.arm()
    time.sleep(1)

    manager.transition_to("takeoff")
    print(f"Climbing to {args.alt_m:.0f} m …")
    nav.climb_to(args.alt_m)

    print("Downloading home GPS position …")
    home_lat_e7, home_lon_e7, _ = client.get_position()
    waypoints = compute_square_waypoints(home_lat_e7, home_lon_e7, args.side_m)
    print(f"Square waypoints (1e-7 deg): {waypoints}")

    print("Switching to GUIDED …")
    client.set_mode("GUIDED")

    manager.transition_to("navigate")
    for i, (lat, lon) in enumerate(waypoints):
        print(f"\nFlying to WP{i + 1} …")
        nav.fly_to(lat, lon, args.alt_m)
        nav.wait_until_reached()

    print("\nMission complete. Switching to RTL …")
    manager.transition_to("rtl")
    client.set_mode("RTL")

    time.sleep(3)  # keep script alive long enough for the RTL command to be processed
    print(f"Done. Phase history: {manager.completed_phases} → {manager.current_phase}")


if __name__ == "__main__":
    main()

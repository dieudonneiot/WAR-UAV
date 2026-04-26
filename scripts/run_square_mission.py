"""Live waypoint mission via MAVLink (ArduPilot SITL or real hardware).

Usage:
    python scripts/run_square_mission.py
    python scripts/run_square_mission.py --shape triangle --size-m 500 --alt-m 50
"""
from __future__ import annotations

import argparse
import threading
import time

from uav.autonomy.mission_manager import MissionManager
from uav.autonomy.navigator import WaypointNavigator, compute_mission_waypoints
from uav.control.emergency import DEFAULT_EMERGENCY_PORT, EmergencyCommandServer
from uav.mavlink.client import MavlinkClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fly a shaped waypoint mission via MAVLink.")
    parser.add_argument("--connection", default="udpin:0.0.0.0:14550",
                        help="MAVLink connection string (default: udpin:0.0.0.0:14550)")
    parser.add_argument("--shape", choices=["square", "triangle", "line", "circle"], default="square",
                        help="Mission shape to fly (default: square)")
    parser.add_argument("--size-m", type=float, default=500.0,
                        help="Mission size in metres; circle uses this as diameter (default: 500)")
    parser.add_argument("--side-m", type=float, default=500.0,
                        help="Deprecated alias for --size-m.")
    parser.add_argument("--alt-m", type=float, default=50.0,
                        help="Cruise altitude in metres AGL (default: 50)")
    parser.add_argument("--acceptance-radius", type=float, default=65.0,
                        help="Waypoint acceptance radius in metres (default: 65)")
    parser.add_argument("--emergency-port", type=int, default=DEFAULT_EMERGENCY_PORT,
                        help=f"Local emergency command port (default: {DEFAULT_EMERGENCY_PORT})")
    args = parser.parse_args()

    size_m = args.size_m if args.size_m != 500.0 or args.side_m == 500.0 else args.side_m
    external_command_requested = threading.Event()
    requested_command = "RTL"
    command_lock = threading.Lock()

    manager = MissionManager(mission_name=f"{args.shape}_mission")
    client = MavlinkClient(args.connection)
    nav = WaypointNavigator(client, acceptance_radius_m=args.acceptance_radius)

    def request_emergency_rtl() -> str:
        nonlocal requested_command
        with command_lock:
            requested_command = "RTL"
        external_command_requested.set()
        client.return_to_launch()
        return "RTL requested by running mission"

    def request_loiter() -> str:
        nonlocal requested_command
        with command_lock:
            requested_command = "LOITER"
        external_command_requested.set()
        client.loiter()
        return "LOITER requested by running mission"

    def get_requested_command() -> str:
        with command_lock:
            return requested_command

    print(f"Connecting to {args.connection} …")
    client.connect()
    print("Connected.")

    emergency_server = EmergencyCommandServer(
        request_emergency_rtl,
        on_loiter=request_loiter,
        port=args.emergency_port,
    )
    try:
        emergency_server.start()
        print(f"Emergency RTL server listening on 127.0.0.1:{emergency_server.port}.")
    except OSError as exc:
        print(f"Warning: emergency RTL server disabled ({exc}). Ctrl+C still works.")

    try:
        print("Disabling hand-launch safety (TKOFF_THR_MINACC=0) …")
        client.disable_hand_launch()
        print("Disabling pre-arm checks (ARMING_CHECK=0) …")
        client.disable_arming_checks()
        time.sleep(1)

        manager.transition_to("takeoff")
        print(f"Taking off to {args.alt_m:.0f} m …")
        takeoff_complete = nav.climb_to(args.alt_m, should_stop=external_command_requested.is_set)
        if not takeoff_complete:
            print(f"\n{get_requested_command()} requested during takeoff.")

        if takeoff_complete and not external_command_requested.is_set():
            print("Downloading home GPS position …")
            home_lat_e7, home_lon_e7, _ = client.get_position()
            waypoints = compute_mission_waypoints(args.shape, home_lat_e7, home_lon_e7, size_m)
            print(f"{args.shape.title()} waypoints (1e-7 deg): {waypoints}")

        if takeoff_complete and not external_command_requested.is_set():
            print("Switching to GUIDED …")
            client.set_mode("GUIDED")

            manager.transition_to("navigate")
            for i, (lat, lon) in enumerate(waypoints):
                if external_command_requested.is_set():
                    break
                print(f"\nFlying to WP{i + 1} …")
                nav.fly_to(lat, lon, args.alt_m)
                reached = nav.wait_until_reached(should_stop=external_command_requested.is_set)
                if not reached:
                    break

        if external_command_requested.is_set():
            command = get_requested_command()
            print(f"\n{command} requested. Mission navigation stopped.")
            manager.transition_to(command.lower())
        else:
            print("\nMission complete. Switching to RTL …")
            manager.transition_to("rtl")
            client.return_to_launch()
    except KeyboardInterrupt:
        print("\nEmergency interrupt received. Switching to RTL …")
        external_command_requested.set()
        manager.transition_to("rtl")
        client.return_to_launch()
    finally:
        emergency_server.stop()

    time.sleep(3)  # keep script alive long enough for the RTL command to be processed
    print(f"Done. Phase history: {manager.completed_phases} → {manager.current_phase}")


if __name__ == "__main__":
    main()

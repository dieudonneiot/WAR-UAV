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
from uav.control.telemetry import TelemetryState
from uav.mavlink.client import MavlinkClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fly a shaped waypoint mission via MAVLink.")
    parser.add_argument("--connection", default="udpin:0.0.0.0:14550",
                        help="MAVLink connection string (default: udpin:0.0.0.0:14550)")
    parser.add_argument("--shape", choices=["square", "triangle", "line", "circle"], default="square",
                        help="Mission shape to fly (default: square)")
    parser.add_argument("--control-mode", choices=["guided", "auto"], default="guided",
                        help="Fly by GUIDED reposition commands or uploaded AUTO mission.")
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
    parser.add_argument("--auto-monitor-s", type=float, default=300.0,
                        help="Seconds to monitor AUTO missions; 0 means forever (default: 300).")
    args = parser.parse_args()

    size_m = args.size_m if args.size_m != 500.0 or args.side_m == 500.0 else args.side_m
    external_command_requested = threading.Event()
    requested_command = "RTL"
    command_lock = threading.Lock()

    manager = MissionManager(mission_name=f"{args.shape}_mission")
    client = MavlinkClient(args.connection)
    nav = WaypointNavigator(client, acceptance_radius_m=args.acceptance_radius)
    telemetry = TelemetryState()

    def transition_to(phase: str) -> None:
        manager.transition_to(phase)
        telemetry.update_phase(phase)

    def request_emergency_rtl() -> str:
        nonlocal requested_command
        with command_lock:
            requested_command = "RTL"
        external_command_requested.set()
        telemetry.update_mode("RTL")
        client.return_to_launch()
        return "RTL requested by running mission"

    def request_loiter() -> str:
        nonlocal requested_command
        with command_lock:
            requested_command = "LOITER"
        external_command_requested.set()
        telemetry.update_mode("LOITER")
        client.loiter()
        return "LOITER requested by running mission"

    def request_mode(mode_name: str) -> str:
        nonlocal requested_command
        mode_name = mode_name.upper()
        with command_lock:
            requested_command = mode_name
        external_command_requested.set()
        telemetry.update_mode(mode_name)
        client.set_mode(mode_name)
        return f"{mode_name} requested by running mission"

    def get_requested_command() -> str:
        with command_lock:
            return requested_command

    print(f"Connecting to {args.connection} …")
    client.connect()
    print("Connected.")

    emergency_server = EmergencyCommandServer(
        request_emergency_rtl,
        on_loiter=request_loiter,
        on_status=telemetry.status_line,
        on_mode=request_mode,
        port=args.emergency_port,
    )
    try:
        emergency_server.start()
        print(f"Flight command server listening on 127.0.0.1:{emergency_server.port}.")
    except OSError as exc:
        print(f"Warning: emergency RTL server disabled ({exc}). Ctrl+C still works.")

    try:
        print("Disabling hand-launch safety (TKOFF_THR_MINACC=0) …")
        client.disable_hand_launch()
        print("Disabling pre-arm checks (ARMING_CHECK=0) …")
        client.disable_arming_checks()
        time.sleep(1)

        if args.control_mode == "auto":
            print("Downloading home GPS position …")
            home_lat_e7, home_lon_e7, home_alt_m = client.get_position()
            telemetry.update_position(home_lat_e7, home_lon_e7, home_alt_m)
            waypoints = compute_mission_waypoints(args.shape, home_lat_e7, home_lon_e7, size_m)
            print(f"{args.shape.title()} waypoints (1e-7 deg): {waypoints}")

            print("Uploading AUTO mission …")
            item_count = client.upload_auto_mission(
                home_lat_e7,
                home_lon_e7,
                waypoints,
                args.alt_m,
                acceptance_radius_m=args.acceptance_radius,
            )
            print(f"Uploaded {item_count} mission items.")

            transition_to("auto")
            telemetry.update_mode("AUTO")
            print("Switching to AUTO and arming …")
            client.set_mode("AUTO")
            client.arm()

            print("Monitoring AUTO mission …")
            auto_start_s = time.monotonic()
            while not external_command_requested.is_set():
                lat_e7, lon_e7, alt_m = client.get_position()
                telemetry.update_position(lat_e7, lon_e7, alt_m)
                dist = client.get_nav_status(timeout=0.2)
                telemetry.update_wp_dist(dist)
                if dist is not None:
                    print(f"  alt={alt_m:.1f} m wp_dist={dist:.0f} m")
                if args.auto_monitor_s > 0 and time.monotonic() - auto_start_s >= args.auto_monitor_s:
                    print("AUTO monitor time elapsed; leaving uploaded mission active.")
                    break
        else:
            transition_to("takeoff")
            print(f"Taking off to {args.alt_m:.0f} m …")
            telemetry.update_mode("TAKEOFF")
            takeoff_complete = nav.climb_to(
                args.alt_m,
                should_stop=external_command_requested.is_set,
                on_position=telemetry.update_position,
            )
            if not takeoff_complete:
                print(f"\n{get_requested_command()} requested during takeoff.")

            if takeoff_complete and not external_command_requested.is_set():
                print("Downloading home GPS position …")
                home_lat_e7, home_lon_e7, home_alt_m = client.get_position()
                telemetry.update_position(home_lat_e7, home_lon_e7, home_alt_m)
                waypoints = compute_mission_waypoints(args.shape, home_lat_e7, home_lon_e7, size_m)
                print(f"{args.shape.title()} waypoints (1e-7 deg): {waypoints}")

            if takeoff_complete and not external_command_requested.is_set():
                print("Switching to GUIDED …")
                telemetry.update_mode("GUIDED")
                client.set_mode("GUIDED")

                transition_to("navigate")
                for i, (lat, lon) in enumerate(waypoints):
                    if external_command_requested.is_set():
                        break
                    print(f"\nFlying to WP{i + 1} …")
                    nav.fly_to(lat, lon, args.alt_m)
                    reached = nav.wait_until_reached(
                        should_stop=external_command_requested.is_set,
                        on_nav_status=telemetry.update_wp_dist,
                    )
                    if not reached:
                        break

            if not external_command_requested.is_set():
                print("\nMission complete. Switching to RTL …")
                transition_to("rtl")
                telemetry.update_mode("RTL")
                client.return_to_launch()

        if external_command_requested.is_set():
            command = get_requested_command()
            print(f"\n{command} requested. Mission navigation stopped.")
            transition_to(command.lower())
        elif args.control_mode == "auto":
            transition_to("auto_complete")
    except KeyboardInterrupt:
        print("\nEmergency interrupt received. Switching to RTL …")
        external_command_requested.set()
        transition_to("rtl")
        telemetry.update_mode("RTL")
        client.return_to_launch()
    finally:
        emergency_server.stop()

    time.sleep(3)  # keep script alive long enough for the RTL command to be processed
    print(f"Done. Phase history: {manager.completed_phases} → {manager.current_phase}")


if __name__ == "__main__":
    main()

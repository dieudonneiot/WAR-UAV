"""Live ArduPlane air-defense avoidance mission via SITL + Gazebo.

Connects to ArduPlane SITL (running in WSL2), uploads a waypoint mission,
waits for the air defense zone to activate, replans the route with
BypassPlanner, re-uploads the safe mission, and draws the restricted zone
as a red cylinder in the live Gazebo world.

Usage — SITL already running (most common):
    python scripts/run_gazebo_air_defense.py

Usage — let Python start SITL+Gazebo automatically:
    python scripts/run_gazebo_air_defense.py --auto-launch

Options:
    --connection        MAVLink connection string  (default: udpin:0.0.0.0:14550)
    --side-m            Mission square side in metres  (default: 500)
    --alt-m             Cruise altitude in metres  (default: 50)
    --zone-radius       Hard zone radius in metres  (default: 100)
    --zone-buffer       Safety buffer in metres  (default: 75)
    --activate-at       Seconds after takeoff when zone activates  (default: 30)
    --auto-launch       Start SITL+Gazebo via WSL2 automatically
    --no-viz            Skip Gazebo zone visualisation
    --headless-gz       Headless Gazebo (no GUI) when --auto-launch is used
"""
from __future__ import annotations

import argparse
import math
import sys
import time
import threading

from rich.console import Console

from uav.autonomy.air_defense import BypassPlanner, RestrictedZone, RouteChecker
from uav.autonomy.navigator import meters_to_e7
from uav.mavlink.client import MavlinkClient, build_auto_mission_items
from uav.simulation.gazebo_zone_visualizer import GazeboZoneVisualizer
from uav.simulation.sitl_bridge import SitlBridge

console = Console()

# ArduPilot SITL default home (Canberra) — must match sitl_launch.sh
HOME_LAT_E7 =  int(-35.363262 * 1e7)
HOME_LON_E7 =  int(149.165237 * 1e7)
HOME_ALT_M  = 0.0   # relative altitude


def _gps_waypoints(
    side_m: float, alt_m: float
) -> list[tuple[int, int]]:
    """Convert local-metre square waypoints to GPS 1e-7 integer pairs."""
    local = [
        (0.0,    side_m),
        (side_m, side_m),
        (side_m, 0.0),
    ]
    wps = []
    for east_m, north_m in local:
        lat = HOME_LAT_E7 + meters_to_e7(north_m)
        lon = HOME_LON_E7 + meters_to_e7(east_m)
        wps.append((lat, lon))
    return wps


def _arm_and_takeoff(client: MavlinkClient, alt_m: float) -> None:
    console.print("[yellow]Disabling arming checks (SITL)…[/yellow]")
    client.disable_arming_checks()
    time.sleep(0.5)
    console.print("[yellow]Setting TAKEOFF mode…[/yellow]")
    client.set_mode("TAKEOFF")
    time.sleep(0.5)
    console.print("[yellow]Arming…[/yellow]")
    client.arm(True)
    console.print(f"[green]Armed. Climbing to {alt_m:.0f} m…[/green]")

    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        _, _, rel_alt = client.get_position()
        console.print(f"  alt = {rel_alt:.1f} m", end="\r")
        if rel_alt >= alt_m * 0.92:
            console.print(f"\n[green]Reached {rel_alt:.1f} m.[/green]")
            return
        time.sleep(0.5)
    raise TimeoutError(f"Did not reach {alt_m:.0f} m within 120 s.")


def _upload_mission(
    client: MavlinkClient,
    waypoints: list[tuple[int, int]],
    alt_m: float,
) -> None:
    n = client.upload_auto_mission(
        HOME_LAT_E7, HOME_LON_E7,
        waypoints, alt_m,
        acceptance_radius_m=60.0,
    )
    console.print(f"[cyan]Mission uploaded: {n} items.[/cyan]")
    client.set_mode("AUTO")


def _monitor_zone_activation(
    client: MavlinkClient,
    zone: RestrictedZone,
    activate_at_s: float,
    viz: GazeboZoneVisualizer | None,
    result: dict,
) -> None:
    """Background thread: waits, activates zone, draws it in Gazebo."""
    console.print(f"[dim]Zone activates in {activate_at_s:.0f} s…[/dim]")
    time.sleep(activate_at_s)

    console.print(f"\n[bold red]⚠  AIR DEFENSE ZONE ACTIVE — {zone.label}[/bold red]")
    console.print(f"   center=({zone.center_x:.0f}, {zone.center_y:.0f}) m  "
                  f"R={zone.radius_m:.0f}+{zone.buffer_m:.0f} m buffer")

    if viz is not None:
        ok = viz.show_zone(zone)
        if ok:
            console.print("[cyan]Zone drawn in Gazebo.[/cyan]")
        else:
            console.print("[yellow]Gazebo viz failed (is Gazebo running?)[/yellow]")

    result["active"] = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection",  default="udpin:0.0.0.0:14550")
    parser.add_argument("--side-m",      type=float, default=500.0)
    parser.add_argument("--alt-m",       type=float, default=50.0)
    parser.add_argument("--zone-radius", type=float, default=100.0)
    parser.add_argument("--zone-buffer", type=float, default=75.0)
    parser.add_argument("--activate-at", type=float, default=30.0)
    parser.add_argument("--auto-launch", action="store_true")
    parser.add_argument("--no-viz",      action="store_true")
    parser.add_argument("--headless-gz", action="store_true")
    parser.add_argument("--wsl-distro",  default="")
    args = parser.parse_args()

    # ── SITL bridge ───────────────────────────────────────────────────────
    bridge: SitlBridge | None = None
    connection = args.connection

    if args.auto_launch:
        bridge = SitlBridge(
            wsl_distro=args.wsl_distro,
            headless_gazebo=args.headless_gz,
        )
        console.print("[bold cyan]Launching SITL + Gazebo in WSL2…[/bold cyan]")
        try:
            connection = bridge.launch(timeout_s=90.0)
        except Exception as exc:
            console.print(f"[bold red]SITL launch failed: {exc}[/bold red]")
            sys.exit(1)
    else:
        console.print(
            "[dim]Assuming SITL is already running.  "
            "Start it with:  bash scripts/sitl_launch.sh[/dim]"
        )

    # ── Gazebo zone visualizer ────────────────────────────────────────────
    viz: GazeboZoneVisualizer | None = None
    if not args.no_viz:
        viz = GazeboZoneVisualizer(
            world_name="air_defense",
            wsl_distro=args.wsl_distro,
        )

    # ── MAVLink connection ────────────────────────────────────────────────
    client = MavlinkClient(connection)
    console.print(f"[cyan]Connecting to {connection}…[/cyan]")
    client.connect(timeout_s=60.0)
    console.print("[green]Connected.[/green]")

    # ── Mission geometry ──────────────────────────────────────────────────
    zone = RestrictedZone(
        center_x=args.side_m * 0.5,
        center_y=args.side_m,
        radius_m=args.zone_radius,
        buffer_m=args.zone_buffer,
        label="AD-1",
    )

    original_wps_gps = _gps_waypoints(args.side_m, args.alt_m)
    original_wps_local: list[tuple[float, float]] = [
        (0.0,          args.side_m),
        (args.side_m,  args.side_m),
        (args.side_m,  0.0),
    ]

    # ── Takeoff and initial mission ───────────────────────────────────────
    try:
        _arm_and_takeoff(client, args.alt_m)
        _upload_mission(client, original_wps_gps, args.alt_m)
        console.print("[green]Mission started — AUTO mode.[/green]")
    except Exception as exc:
        console.print(f"[red]Takeoff/mission failed: {exc}[/red]")
        if bridge:
            bridge.stop()
        sys.exit(1)

    # ── Start zone-activation timer in background ─────────────────────────
    zone_state: dict = {"active": False}
    timer = threading.Thread(
        target=_monitor_zone_activation,
        args=(client, zone, args.activate_at, viz, zone_state),
        daemon=True,
    )
    timer.start()

    # ── Main loop: monitor + replan ───────────────────────────────────────
    replanned = False
    console.print("[dim]Monitoring mission…[/dim]")

    try:
        while True:
            lat, lon, alt = client.get_position()

            # Local metres from home (east, north)
            pos_east  = (lon - HOME_LON_E7) / 1e7 * 111_320
            pos_north = (lat - HOME_LAT_E7) / 1e7 * 111_320

            if zone_state["active"] and not replanned:
                console.print("\n[bold yellow]Route check triggered…[/bold yellow]")

                remaining_local: list[tuple[float, float]] = [
                    (pos_east, pos_north),
                ] + original_wps_local

                if not RouteChecker.route_is_safe(remaining_local, [zone]):
                    console.print("[bold red]Intersection detected — replanning.[/bold red]")

                    safe_local = BypassPlanner.plan(remaining_local, [zone])
                    console.print(f"[cyan]Bypass has {len(safe_local)} waypoints.[/cyan]")

                    # Convert safe local waypoints to GPS
                    safe_gps = [
                        (
                            HOME_LAT_E7 + meters_to_e7(north),
                            HOME_LON_E7 + meters_to_e7(east),
                        )
                        for east, north in safe_local[1:]  # skip current pos
                    ]

                    _upload_mission(client, safe_gps, args.alt_m)
                    replanned = True
                    console.print("[bold green]Safe mission uploaded.[/bold green]")

                    # Draw bypass waypoints in Gazebo
                    if viz is not None:
                        viz.update_bypass_path(
                            [(wp[0], wp[1]) for wp in safe_local],
                            alt_m=args.alt_m,
                        )
                        console.print("[cyan]Bypass route drawn in Gazebo.[/cyan]")
                else:
                    console.print("[green]Route already safe — no replan needed.[/green]")
                    replanned = True

            dist = client.get_nav_status(timeout=0.5)
            status = (
                f"  alt={alt:.1f}m  "
                f"pos=({pos_east:.0f},{pos_north:.0f})m  "
                f"wp_dist={dist:.0f}m" if dist else f"  alt={alt:.1f}m"
            )
            console.print(status, end="\r")
            time.sleep(0.5)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — sending RTL.[/yellow]")
        client.return_to_launch()
    finally:
        if viz is not None:
            viz.clear_all()
        if bridge is not None:
            bridge.stop()

    console.print("[green]Done.[/green]")


if __name__ == "__main__":
    main()

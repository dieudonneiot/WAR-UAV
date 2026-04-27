"""Animated air-defense avoidance simulation (no hardware required).

Usage:
    python scripts/run_air_defense_simulation.py
    python scripts/run_air_defense_simulation.py --headless
    python scripts/run_air_defense_simulation.py --side-m 600 --zone-radius 120
"""
from __future__ import annotations

import argparse

import cv2
import numpy as np
from rich.console import Console

from uav.autonomy.air_defense import BypassPlanner, RestrictedZone, RouteChecker
from uav.simulation.air_defense_simulation import AirDefenseStep, run_air_defense_simulation
from uav.simulation.mission_scenario import MissionStep
from uav.simulation.mission_visualizer import MissionVisualizer

_PHASE_COLOR = {
    "normal":           (40,  180, 255),
    "threat_detected":  (40,  40,  255),
    "replanning":       (0,   140, 255),
    "avoidance":        (0,   220, 180),
    "resume":           (60,  220, 80),
}


def _to_mission_step(s: AirDefenseStep) -> MissionStep:
    """Adapt AirDefenseStep to the plain MissionStep the visualizer expects."""
    return MissionStep(
        time_s=s.time_s,
        phase=s.phase,
        aircraft_x=s.aircraft_x,
        aircraft_y=s.aircraft_y,
        alt_m=s.alt_m,
        current_wp=s.current_wp,
        wp_dist_m=s.wp_dist_m,
        waypoints=s.active_waypoints,
    )


def _overlay_hud(canvas: np.ndarray, step: AirDefenseStep) -> None:
    col = _PHASE_COLOR.get(step.phase, (220, 220, 220))
    h, w = canvas.shape[:2]
    lines = [
        f"t = {step.time_s:.1f} s",
        f"phase: {step.phase.upper()}",
        f"zone dist: {step.min_zone_dist_m:.0f} m",
        f"replanned: {'YES' if step.replanned else 'NO'}",
        f"zones active: {len(step.zones)}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(canvas, line, (w - 310, 80 + i * 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, col, 2, cv2.LINE_AA)


def main() -> None:
    parser = argparse.ArgumentParser(description="Air-defense avoidance animation.")
    parser.add_argument("--side-m",        type=float, default=500.0)
    parser.add_argument("--alt-m",         type=float, default=50.0)
    parser.add_argument("--speed-mps",     type=float, default=20.0)
    parser.add_argument("--zone-radius",   type=float, default=100.0, help="Hard zone radius in metres.")
    parser.add_argument("--zone-buffer",   type=float, default=75.0,  help="Safety buffer in metres.")
    parser.add_argument("--activate-at",   type=float, default=30.0,  help="Seconds before zone activates.")
    parser.add_argument("--delay-ms",      type=int,   default=40)
    parser.add_argument("--headless",      action="store_true")
    parser.add_argument("--output",        default="logs/air_defense_preview.png")
    args = parser.parse_args()

    console = Console()
    console.print("[bold cyan]Air Defense Avoidance Simulation[/bold cyan]")

    zone = RestrictedZone(
        center_x=args.side_m * 0.5,
        center_y=args.side_m,
        radius_m=args.zone_radius,
        buffer_m=args.zone_buffer,
        label="AD-1",
    )

    steps = run_air_defense_simulation(
        side_m=args.side_m,
        cruise_alt_m=args.alt_m,
        cruise_speed_mps=args.speed_mps,
        zone_activation_time_s=args.activate_at,
        zone=zone,
    )

    console.print(f"  {len(steps)} frames  |  {steps[-1].time_s:.1f} s total")
    phases = {s.phase for s in steps}
    console.print(f"  phases seen: {sorted(phases)}")

    viz = MissionVisualizer()

    # Precompute bypass route for drawing
    bypass_wps = [list(s.active_waypoints) for s in steps if s.replanned]
    bypass_route = bypass_wps[0] if bypass_wps else []

    if args.headless:
        last = steps[-1]
        trail = [(s.aircraft_x, s.aircraft_y) for s in steps]
        ms = _to_mission_step(last)
        canvas = viz.render_air_defense(ms, trail, list(last.zones), bypass_route)
        _overlay_hud(canvas, last)
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(args.output, canvas)
        console.print(f"[green]Saved:[/green] {args.output}")
        return

    console.print("Press [bold]Q[/bold] or [bold]ESC[/bold] to quit.")
    trail: list[tuple[float, float]] = []
    for step in steps:
        trail.append((step.aircraft_x, step.aircraft_y))
        ms = _to_mission_step(step)
        canvas = viz.render_air_defense(ms, trail, list(step.zones), bypass_route)
        _overlay_hud(canvas, step)
        cv2.imshow("TEKNOFEST — Air Defense Avoidance", canvas)
        key = cv2.waitKey(args.delay_ms) & 0xFF
        if key in {27, ord("q")}:
            break

    cv2.destroyAllWindows()
    console.print("[green]Done.[/green]")


if __name__ == "__main__":
    main()

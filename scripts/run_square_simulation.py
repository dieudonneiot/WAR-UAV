"""Animated visual simulation of the square waypoint mission (no hardware required).

Usage:
    python scripts/run_square_simulation.py                # interactive window
    python scripts/run_square_simulation.py --headless     # save preview PNG
    python scripts/run_square_simulation.py --side-m 300 --speed-mps 15 --delay-ms 30
"""
from __future__ import annotations

import argparse

import cv2
from rich.console import Console

from uav.simulation.mission_scenario import run_square_mission_simulation
from uav.simulation.mission_visualizer import MissionVisualizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualise a square waypoint mission simulation.")
    parser.add_argument("--side-m",    type=float, default=500.0, help="Square side length in metres.")
    parser.add_argument("--alt-m",     type=float, default=50.0,  help="Cruise altitude in metres.")
    parser.add_argument("--speed-mps", type=float, default=20.0,  help="Cruise speed in m/s.")
    parser.add_argument("--delay-ms",  type=int,   default=50,    help="Milliseconds between frames.")
    parser.add_argument("--headless",  action="store_true",       help="Save a preview PNG instead of opening a window.")
    parser.add_argument("--output",    default="logs/square_mission_preview.png",
                        help="Output path used with --headless.")
    args = parser.parse_args()

    console = Console()
    console.print(
        f"[bold cyan]Square Mission Simulation[/bold cyan]  "
        f"side={args.side_m:.0f}m  alt={args.alt_m:.0f}m  speed={args.speed_mps:.0f}m/s"
    )

    steps = run_square_mission_simulation(
        side_m=args.side_m,
        cruise_alt_m=args.alt_m,
        cruise_speed_mps=args.speed_mps,
    )
    console.print(f"Simulation has [green]{len(steps)}[/green] frames "
                  f"({steps[-1].time_s:.1f} s total)")

    visualizer = MissionVisualizer()

    if args.headless:
        trail = [(s.aircraft_x, s.aircraft_y) for s in steps]
        path = visualizer.save_preview(steps[-1], args.output)
        console.print(f"[green]Saved preview:[/green] {path}")
        return

    console.print("Press [bold]Q[/bold] or [bold]ESC[/bold] to quit.")
    trail: list[tuple[float, float]] = []
    for step in steps:
        trail.append((step.aircraft_x, step.aircraft_y))
        frame = visualizer.render(step, trail)
        cv2.imshow("TEKNOFEST Square Mission", frame)
        key = cv2.waitKey(args.delay_ms) & 0xFF
        if key in {27, ord("q")}:
            break

    cv2.destroyAllWindows()
    console.print("[green]Simulation complete.[/green]")


if __name__ == "__main__":
    main()

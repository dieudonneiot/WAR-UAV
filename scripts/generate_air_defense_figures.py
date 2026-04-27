"""Generate CDR report figures for the Air Defense Avoidance section.

Produces five publication-quality matplotlib figures saved under logs/figures/:
  fig1_mission_map.png       — top-down map: original route, zone, buffer, bypass
  fig2_zone_distance.png     — distance-to-zone vs time (never drops below 0)
  fig3_state_timeline.png    — mission phase timeline
  fig4_astar_costmap.png     — A* grid cost map with planned path
  fig5_path_comparison.png   — original vs avoidance path length bar chart

Usage:
    python scripts/generate_air_defense_figures.py
    python scripts/generate_air_defense_figures.py --side-m 600 --zone-radius 120
    python scripts/generate_air_defense_figures.py --out-dir reports/figures
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from uav.autonomy.air_defense import (
    BypassPlanner, RestrictedZone, _arc_waypoints, _BYPASS_CLEARANCE_M,
    _tangent_points, astar_grid,
)
from uav.simulation.air_defense_simulation import run_air_defense_simulation


# ── Style ─────────────────────────────────────────────────────────────────────

PLT_STYLE = {
    "figure.facecolor":  "#1c1e20",
    "axes.facecolor":    "#23272b",
    "axes.edgecolor":    "#4a5260",
    "axes.labelcolor":   "#d0d4da",
    "axes.titlecolor":   "#e8eaed",
    "xtick.color":       "#8a92a0",
    "ytick.color":       "#8a92a0",
    "grid.color":        "#2e3540",
    "grid.linewidth":    0.8,
    "text.color":        "#d0d4da",
    "legend.facecolor":  "#1c2028",
    "legend.edgecolor":  "#3a4050",
    "legend.fontsize":   9,
    "font.size":         10,
    "axes.titlesize":    12,
    "axes.labelsize":    10,
    "lines.linewidth":   2.0,
}

PHASE_COLORS = {
    "normal":           "#4ab3f4",
    "threat_detected":  "#f44336",
    "replanning":       "#ff9800",
    "avoidance":        "#00e5cc",
    "resume":           "#66bb6a",
}


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved  {path}")


# ── Figure 1: top-down mission map ────────────────────────────────────────────

def fig1_mission_map(
    side_m: float,
    zone: RestrictedZone,
    out: Path,
) -> None:
    original_wps = [
        (0.0,    side_m),
        (side_m, side_m),
        (side_m, 0.0),
        (0.0,    0.0),
    ]
    home = (0.0, 0.0)
    full_original = [home] + original_wps

    remaining = [home] + original_wps
    safe = BypassPlanner.plan(remaining, [zone])
    bypass_route = safe

    with plt.rc_context(PLT_STYLE):
        fig, ax = plt.subplots(figsize=(7, 7))

        # Safety buffer ring
        buf_circle = plt.Circle(
            (zone.center_x, zone.center_y), zone.effective_radius,
            color="#1a3a6a", alpha=0.35, zorder=2,
        )
        ax.add_patch(buf_circle)
        buf_edge = plt.Circle(
            (zone.center_x, zone.center_y), zone.effective_radius,
            fill=False, edgecolor="#4488dd", linewidth=1.2,
            linestyle="--", zorder=3,
        )
        ax.add_patch(buf_edge)

        # Hard exclusion zone
        hard_circle = plt.Circle(
            (zone.center_x, zone.center_y), zone.radius_m,
            color="#6a0a0a", alpha=0.55, zorder=4,
        )
        ax.add_patch(hard_circle)
        hard_edge = plt.Circle(
            (zone.center_x, zone.center_y), zone.radius_m,
            fill=False, edgecolor="#ff3333", linewidth=2.0, zorder=5,
        )
        ax.add_patch(hard_edge)

        # Zone labels
        ax.text(zone.center_x, zone.center_y + zone.radius_m * 0.35,
                zone.label, color="#ff6666", fontsize=9, ha="center", fontweight="bold", zorder=6)
        ax.text(zone.center_x, zone.center_y - zone.radius_m - 14,
                f"R = {zone.radius_m:.0f} m", color="#ff6666", fontsize=8, ha="center", zorder=6)
        ax.text(zone.center_x, zone.center_y + zone.effective_radius + 12,
                f"buffer = +{zone.buffer_m:.0f} m", color="#6699cc", fontsize=8,
                ha="center", zorder=6)

        # Original route (dashed gray)
        ox = [p[0] for p in full_original]
        oy = [p[1] for p in full_original]
        ax.plot(ox, oy, color="#888888", linewidth=1.4, linestyle="--",
                label="Original route", zorder=7, alpha=0.7)

        # Bypass route (cyan)
        bx = [p[0] for p in bypass_route]
        by = [p[1] for p in bypass_route]
        ax.plot(bx, by, color="#00e5cc", linewidth=2.2, label="Replanned route", zorder=8)
        ax.annotate("", xy=(bx[2], by[2]), xytext=(bx[1], by[1]),
                    arrowprops=dict(arrowstyle="->", color="#00e5cc", lw=1.8), zorder=9)

        # Waypoint markers (original)
        wp_labels = ["WP1", "WP2", "WP3", "WP4"]
        for i, (wx, wy) in enumerate(original_wps):
            ax.scatter(wx, wy, s=70, color="#888888", zorder=10, alpha=0.6)
            ax.annotate(wp_labels[i], (wx, wy), textcoords="offset points",
                        xytext=(8, 6), fontsize=8, color="#aaaaaa")

        # Home
        ax.scatter(0, 0, s=120, color="#ffc030", marker="*", zorder=11, label="HOME")
        ax.annotate("HOME", (0, 0), textcoords="offset points",
                    xytext=(8, -14), fontsize=9, color="#ffc030", fontweight="bold")

        # Tangent-point bypass markers
        if len(bypass_route) > 2:
            for i, (bpx, bpy) in enumerate(bypass_route[1:-1], 1):
                ax.scatter(bpx, bpy, s=60, color="#00e5cc", marker="D", zorder=12)
                ax.annotate(f"T{i}", (bpx, bpy), textcoords="offset points",
                            xytext=(6, 6), fontsize=8, color="#00e5cc")

        margin = side_m * 0.18
        ax.set_xlim(-margin, side_m + margin)
        ax.set_ylim(-margin, side_m + margin)
        ax.set_aspect("equal")
        ax.set_xlabel("East  (m)")
        ax.set_ylabel("North  (m)")
        ax.set_title("Fig. 1 — Air Defense Avoidance: Mission Map")
        ax.xaxis.set_major_locator(ticker.MultipleLocator(100))
        ax.yaxis.set_major_locator(ticker.MultipleLocator(100))
        ax.grid(True, zorder=0)
        ax.legend(loc="lower right")

        _save(fig, out)


# ── Figure 2: distance-to-zone vs time ───────────────────────────────────────

def fig2_zone_distance(
    steps,
    zone: RestrictedZone,
    out: Path,
) -> None:
    times = [s.time_s for s in steps]
    dists = [s.min_zone_dist_m for s in steps]
    phases = [s.phase for s in steps]

    # Find zone-activation time
    act_t = next((s.time_s for s in steps if s.zones), None)
    replan_t = next((s.time_s for s in steps if s.phase == "replanning"), None)

    with plt.rc_context(PLT_STYLE):
        fig, ax = plt.subplots(figsize=(9, 4))

        # Color segments by phase
        prev_i = 0
        for i in range(1, len(times)):
            if phases[i] != phases[prev_i] or i == len(times) - 1:
                color = PHASE_COLORS.get(phases[prev_i], "#888888")
                ax.plot(times[prev_i:i+1], dists[prev_i:i+1], color=color, linewidth=2)
                prev_i = i

        # Safety floor
        ax.axhline(0, color="#ff3333", linewidth=1.0, linestyle="--",
                   label="Zone boundary (0 m)")

        # Vertical markers
        if act_t is not None:
            ax.axvline(act_t, color="#ff9800", linewidth=1.2, linestyle=":",
                       label=f"Zone activated  t={act_t:.0f}s")
        if replan_t is not None:
            ax.axvline(replan_t, color="#00e5cc", linewidth=1.2, linestyle=":",
                       label=f"Replan triggered  t={replan_t:.0f}s")

        # Phase legend patches
        patches = [mpatches.Patch(color=c, label=p) for p, c in PHASE_COLORS.items()]
        first_legend = ax.legend(handles=patches, loc="upper right", fontsize=8)
        ax.add_artist(first_legend)
        ax.legend(loc="upper left", fontsize=8)

        ax.set_xlabel("Time  (s)")
        ax.set_ylabel("Distance to zone boundary  (m)")
        ax.set_title("Fig. 2 — Distance to Restricted Zone Over Time")
        ax.grid(True)
        ax.set_ylim(bottom=-20)

        _save(fig, out)


# ── Figure 3: mission state timeline ─────────────────────────────────────────

def fig3_state_timeline(steps, out: Path) -> None:
    phase_order = ["normal", "threat_detected", "replanning", "avoidance", "resume"]
    phase_idx = {p: i for i, p in enumerate(phase_order)}

    times = [s.time_s for s in steps]
    indices = [phase_idx.get(s.phase, 0) for s in steps]

    with plt.rc_context(PLT_STYLE):
        fig, ax = plt.subplots(figsize=(9, 3.5))

        # Colored horizontal band per segment
        prev_i = 0
        for i in range(1, len(times)):
            if indices[i] != indices[prev_i] or i == len(times) - 1:
                color = PHASE_COLORS.get(steps[prev_i].phase, "#888888")
                ax.fill_between(
                    times[prev_i:i+1],
                    [indices[prev_i]] * (i - prev_i + 1),
                    [indices[prev_i] + 0.85] * (i - prev_i + 1),
                    color=color, alpha=0.85,
                )
                prev_i = i

        ax.set_yticks(range(len(phase_order)))
        ax.set_yticklabels([p.replace("_", " ").upper() for p in phase_order])
        ax.set_xlabel("Time  (s)")
        ax.set_title("Fig. 3 — Mission State Timeline")
        ax.grid(True, axis="x")
        ax.set_ylim(-0.2, len(phase_order) - 0.1)

        _save(fig, out)


# ── Figure 4: A* cost grid ────────────────────────────────────────────────────

def fig4_astar_costmap(
    side_m: float,
    zone: RestrictedZone,
    out: Path,
) -> None:
    home = (0.0, 0.0)
    goal = (side_m, 0.0)
    bounds = (-80.0, side_m + 80.0, -80.0, side_m + 80.0)

    path, grid = astar_grid(
        home, goal, [zone],
        grid_resolution_m=18.0,
        world_bounds=bounds,
    )

    min_x, max_x, min_y, max_y = bounds
    grid_arr = np.array(grid, dtype=float)  # rows × cols

    with plt.rc_context(PLT_STYLE):
        fig, ax = plt.subplots(figsize=(7, 7))

        # Cost map (imshow, origin=lower)
        ax.imshow(
            grid_arr,
            extent=[min_x, max_x, min_y, max_y],
            origin="lower",
            cmap="RdYlGn_r",
            alpha=0.65,
            vmin=0, vmax=1,
            aspect="equal",
            zorder=1,
        )

        # Zone overlay
        circ = plt.Circle(
            (zone.center_x, zone.center_y), zone.radius_m,
            fill=False, edgecolor="#ff4444", linewidth=2, zorder=4,
        )
        ax.add_patch(circ)
        buf = plt.Circle(
            (zone.center_x, zone.center_y), zone.effective_radius,
            fill=False, edgecolor="#4488dd", linewidth=1, linestyle="--", zorder=4,
        )
        ax.add_patch(buf)

        # A* path
        if path:
            px = [p[0] for p in path]
            py = [p[1] for p in path]
            ax.plot(px, py, color="#00e5cc", linewidth=2.4, label="A* path", zorder=5)
            ax.scatter(px[0], py[0], s=120, color="#ffc030", marker="*", zorder=6, label="Start")
            ax.scatter(px[-1], py[-1], s=80, color="#66bb6a", marker="D", zorder=6, label="Goal")

        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)
        ax.set_xlabel("East  (m)")
        ax.set_ylabel("North  (m)")
        ax.set_title("Fig. 4 — A* Grid Cost Map and Planned Path")
        ax.grid(False)
        ax.legend(loc="lower right")

        # Legend for cost map
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable
        sm = ScalarMappable(cmap="RdYlGn_r", norm=Normalize(0, 1))
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
        cbar.set_label("Cell cost  (0=free, 1=blocked)")
        cbar.ax.yaxis.label.set_color("#d0d4da")
        cbar.ax.tick_params(colors="#8a92a0")

        _save(fig, out)


# ── Figure 5: path length comparison ─────────────────────────────────────────

def fig5_path_comparison(
    side_m: float,
    zone: RestrictedZone,
    out: Path,
) -> None:
    home = (0.0, 0.0)
    original_wps = [
        (0.0,    side_m),
        (side_m, side_m),
        (side_m, 0.0),
        (0.0,    0.0),
    ]

    def route_length(wps: list[tuple[float, float]]) -> float:
        total = 0.0
        for i in range(len(wps) - 1):
            total += math.hypot(wps[i+1][0]-wps[i][0], wps[i+1][1]-wps[i][1])
        return total

    full_original = [home] + original_wps
    orig_len = route_length(full_original)

    bypass = BypassPlanner.plan([home] + original_wps, [zone])
    bypass_len = route_length(bypass)
    extra = bypass_len - orig_len
    overhead_pct = 100.0 * extra / orig_len

    with plt.rc_context(PLT_STYLE):
        fig, ax = plt.subplots(figsize=(6, 4.5))

        labels = ["Original\nroute", "Avoidance\nroute"]
        values = [orig_len, bypass_len]
        colors = ["#4ab3f4", "#00e5cc"]
        bars = ax.bar(labels, values, color=colors, width=0.45, zorder=3)

        # Value labels on bars
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val + orig_len * 0.01,
                f"{val:.0f} m",
                ha="center", va="bottom", fontweight="bold", fontsize=10,
            )

        # Extra-distance annotation
        ax.annotate(
            f"+ {extra:.0f} m  ({overhead_pct:.1f}% overhead)",
            xy=(1, bypass_len),
            xytext=(0.5, bypass_len + orig_len * 0.06),
            ha="center", fontsize=9, color="#ff9800",
            arrowprops=dict(arrowstyle="->", color="#ff9800"),
        )

        ax.set_ylabel("Total route length  (m)")
        ax.set_title("Fig. 5 — Original vs Avoidance Route Length")
        ax.grid(True, axis="y", zorder=0)
        ax.set_ylim(0, bypass_len * 1.18)

        _save(fig, out)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate air-defense CDR figures.")
    parser.add_argument("--side-m",       type=float, default=500.0)
    parser.add_argument("--zone-radius",  type=float, default=100.0)
    parser.add_argument("--zone-buffer",  type=float, default=75.0)
    parser.add_argument("--activate-at",  type=float, default=30.0)
    parser.add_argument("--out-dir",      default="logs/figures")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    print(f"Generating figures → {out_dir}/")

    zone = RestrictedZone(
        center_x=args.side_m * 0.5,
        center_y=args.side_m,
        radius_m=args.zone_radius,
        buffer_m=args.zone_buffer,
        label="AD-1",
    )

    steps = run_air_defense_simulation(
        side_m=args.side_m,
        zone_activation_time_s=args.activate_at,
        zone=zone,
    )

    fig1_mission_map(args.side_m, zone, out_dir / "fig1_mission_map.png")
    fig2_zone_distance(steps, zone, out_dir / "fig2_zone_distance.png")
    fig3_state_timeline(steps, out_dir / "fig3_state_timeline.png")
    fig4_astar_costmap(args.side_m, zone, out_dir / "fig4_astar_costmap.png")
    fig5_path_comparison(args.side_m, zone, out_dir / "fig5_path_comparison.png")

    print("Done.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MissionStep:
    time_s: float
    phase: str
    aircraft_x: float                          # metres east of home
    aircraft_y: float                          # metres north of home
    alt_m: float
    current_wp: int                            # -1=takeoff, 0-3=navigating to that WP
    wp_dist_m: float
    waypoints: tuple[tuple[float, float], ...]  # (x_east, y_north) in metres from home


def run_square_mission_simulation(
    side_m: float = 500.0,
    cruise_alt_m: float = 50.0,
    cruise_speed_mps: float = 20.0,
    climb_rate_mps: float = 5.0,
    dt_s: float = 0.5,
) -> list[MissionStep]:
    """Produce a time-stepped simulation of the square waypoint mission.

    Waypoint layout (metres from home, x=east, y=north):
        WP1 (0, side)  →  WP2 (side, side)  →  WP3 (side, 0)  →  WP4 (0, 0)
    """
    wps: tuple[tuple[float, float], ...] = (
        (0.0,    side_m),   # WP1 – north
        (side_m, side_m),   # WP2 – northeast
        (side_m, 0.0),      # WP3 – east
        (0.0,    0.0),      # WP4 – home (RTL start)
    )

    steps: list[MissionStep] = []
    time_s = 0.0

    # ── Phase 1: Takeoff ──────────────────────────────────────────────────────
    climb_dur = cruise_alt_m / climb_rate_mps
    t = 0.0
    while t <= climb_dur:
        steps.append(MissionStep(
            time_s=time_s + t,
            phase="takeoff",
            aircraft_x=0.0,
            aircraft_y=0.0,
            alt_m=min(t * climb_rate_mps, cruise_alt_m),
            current_wp=-1,
            wp_dist_m=0.0,
            waypoints=wps,
        ))
        t += dt_s
    time_s += climb_dur

    # ── Phase 2: Navigate each leg ────────────────────────────────────────────
    pos_x, pos_y = 0.0, 0.0
    for wp_idx, (wp_x, wp_y) in enumerate(wps):
        leg = math.hypot(wp_x - pos_x, wp_y - pos_y)
        if leg < 1.0:
            continue
        leg_dur = leg / cruise_speed_mps
        phase = "rtl" if wp_idx == 3 else f"nav_wp{wp_idx + 1}"
        t = 0.0
        while t <= leg_dur:
            frac = min(t / leg_dur, 1.0)
            cx = pos_x + frac * (wp_x - pos_x)
            cy = pos_y + frac * (wp_y - pos_y)
            # Descend on the RTL leg so the aircraft lands at home
            alt = cruise_alt_m * (1.0 - frac) if phase == "rtl" else cruise_alt_m
            steps.append(MissionStep(
                time_s=time_s + t,
                phase=phase,
                aircraft_x=cx,
                aircraft_y=cy,
                alt_m=max(0.0, alt),
                current_wp=wp_idx,
                wp_dist_m=math.hypot(wp_x - cx, wp_y - cy),
                waypoints=wps,
            ))
            t += dt_s
        time_s += leg_dur
        pos_x, pos_y = wp_x, wp_y

    return steps

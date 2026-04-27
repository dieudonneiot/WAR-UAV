from __future__ import annotations

import math
from dataclasses import dataclass

from uav.autonomy.air_defense import BypassPlanner, RestrictedZone, RouteChecker


@dataclass(frozen=True, slots=True)
class AirDefenseStep:
    time_s: float
    phase: str  # normal | threat_detected | replanning | avoidance | resume
    aircraft_x: float
    aircraft_y: float
    alt_m: float
    current_wp: int
    wp_dist_m: float
    original_waypoints: tuple[tuple[float, float], ...]
    active_waypoints: tuple[tuple[float, float], ...]
    zones: tuple[RestrictedZone, ...]
    min_zone_dist_m: float
    replanned: bool


def run_air_defense_simulation(
    side_m: float = 500.0,
    cruise_alt_m: float = 50.0,
    cruise_speed_mps: float = 20.0,
    climb_rate_mps: float = 5.0,
    dt_s: float = 0.5,
    zone_activation_time_s: float = 30.0,
    zone: RestrictedZone | None = None,
) -> list[AirDefenseStep]:
    """Kinematic simulation with mid-flight restricted zone activation and bypass.

    Phases emitted per step:
      normal          — routine navigation, no threat
      threat_detected — zone just activated and route intersection found
      replanning      — planner is computing bypass (one frame)
      avoidance       — flying the bypass route
      resume          — returning toward original mission after bypass
    """
    if zone is None:
        zone = RestrictedZone(
            center_x=side_m * 0.5,
            center_y=side_m,
            radius_m=100.0,
            buffer_m=75.0,
            label="AD-1",
        )

    original_wps: tuple[tuple[float, float], ...] = (
        (0.0,    side_m),   # WP1 – north
        (side_m, side_m),   # WP2 – northeast
        (side_m, 0.0),      # WP3 – east
        (0.0,    0.0),      # WP4 – home / RTL
    )

    steps: list[AirDefenseStep] = []
    zones: tuple[RestrictedZone, ...] = ()
    active_wps: list[tuple[float, float]] = list(original_wps)
    replanned = False

    def min_dist(x: float, y: float) -> float:
        return RouteChecker.min_distance_to_zones(x, y, zones)

    def emit(t: float, phase: str, x: float, y: float,
             alt: float, wp_idx: int, wp_dist: float) -> None:
        steps.append(AirDefenseStep(
            time_s=t,
            phase=phase,
            aircraft_x=x,
            aircraft_y=y,
            alt_m=max(0.0, alt),
            current_wp=wp_idx,
            wp_dist_m=wp_dist,
            original_waypoints=original_wps,
            active_waypoints=tuple(active_wps),
            zones=zones,
            min_zone_dist_m=min_dist(x, y),
            replanned=replanned,
        ))

    # ── Takeoff ───────────────────────────────────────────────────────────────
    climb_dur = cruise_alt_m / climb_rate_mps
    now = 0.0
    while now <= climb_dur:
        emit(now, "normal", 0.0, 0.0, now * climb_rate_mps, -1, 0.0)
        now += dt_s
    now = climb_dur

    # ── Cruise: advance along active_wps one time-step at a time ─────────────
    pos_x, pos_y = 0.0, 0.0
    wp_idx = 0

    while wp_idx < len(active_wps):
        wp_x, wp_y = active_wps[wp_idx]
        leg = math.hypot(wp_x - pos_x, wp_y - pos_y)
        if leg < 1.0:
            pos_x, pos_y = wp_x, wp_y
            wp_idx += 1
            continue

        leg_dur = leg / cruise_speed_mps
        is_last = wp_idx == len(active_wps) - 1
        t_leg = 0.0
        replan_triggered = False

        while t_leg <= leg_dur:
            frac = min(t_leg / leg_dur, 1.0)
            cx = pos_x + frac * (wp_x - pos_x)
            cy = pos_y + frac * (wp_y - pos_y)
            alt = cruise_alt_m * (1.0 - frac) if is_last else cruise_alt_m

            # Activate zone on schedule
            if now >= zone_activation_time_s and not zones:
                zones = (zone,)

            # Replan exactly once when the remaining route becomes unsafe
            if zones and not replanned:
                remaining = [(cx, cy)] + active_wps[wp_idx:]
                if not RouteChecker.route_is_safe(remaining, zones):
                    emit(now, "threat_detected", cx, cy, alt, wp_idx,
                         math.hypot(wp_x - cx, wp_y - cy))
                    emit(now, "replanning", cx, cy, alt, wp_idx,
                         math.hypot(wp_x - cx, wp_y - cy))
                    safe = BypassPlanner.plan(remaining, zones)
                    active_wps = active_wps[:wp_idx] + safe
                    replanned = True
                    pos_x, pos_y = cx, cy
                    replan_triggered = True
                    break

            phase = _label(replanned, is_last)
            emit(now, phase, cx, cy, alt, wp_idx, math.hypot(wp_x - cx, wp_y - cy))
            t_leg += dt_s
            now += dt_s

        if replan_triggered:
            continue

        pos_x, pos_y = wp_x, wp_y
        wp_idx += 1

    return steps


def _label(replanned: bool, is_last: bool) -> str:
    if not replanned:
        return "normal"
    return "resume" if is_last else "avoidance"

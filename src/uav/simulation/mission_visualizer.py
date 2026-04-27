from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

from uav.simulation.mission_scenario import MissionStep

if TYPE_CHECKING:
    from uav.autonomy.air_defense import RestrictedZone


class MissionVisualizer:
    """Renders a top-down tactical map of the square waypoint mission."""

    def __init__(self, canvas_width: int = 1280, canvas_height: int = 720) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

    # ── public API ────────────────────────────────────────────────────────────

    def render(
        self,
        step: MissionStep,
        trail: list[tuple[float, float]] | None = None,
    ) -> np.ndarray:
        margin = 24
        gap = 20
        top_y = 48
        tel_h = 84
        tel_y = self.canvas_height - tel_h - margin
        panel_h = tel_y - top_y - gap
        avail_w = self.canvas_width - margin * 2 - gap
        map_w = int(avail_w * 0.70)
        status_w = avail_w - map_w

        canvas = np.full((self.canvas_height, self.canvas_width, 3), (32, 35, 38), dtype=np.uint8)

        map_rect = (margin, top_y, map_w, panel_h)
        status_rect = (margin + map_w + gap, top_y, status_w, panel_h)
        tel_rect = (margin, tel_y, self.canvas_width - margin * 2, tel_h)

        self._draw_panel(canvas, map_rect, "Mission Map")
        self._draw_panel(canvas, status_rect, "Status")
        self._draw_panel(canvas, tel_rect, "Telemetry")

        self._draw_map(canvas, map_rect, step, trail or [])
        self._draw_status(canvas, status_rect, step)
        self._draw_telemetry(canvas, tel_rect, step)
        return canvas

    def render_air_defense(
        self,
        step: MissionStep,
        trail: list[tuple[float, float]] | None = None,
        zones: list[RestrictedZone] | None = None,
        bypass_route: list[tuple[float, float]] | None = None,
    ) -> np.ndarray:
        """Like render() but overlays restricted zones and the replanned route."""
        canvas = self.render(step, trail)
        if not zones:
            return canvas

        margin = 24
        gap = 20
        top_y = 48
        tel_h = 84
        tel_y = self.canvas_height - tel_h - margin
        panel_h = tel_y - top_y - gap
        avail_w = self.canvas_width - margin * 2 - gap
        map_w = int(avail_w * 0.70)
        vx = margin + 12
        vy = top_y + 40
        vw = map_w - 24
        vh = panel_h - 52

        bounds = self._map_bounds(step)

        def s2s(wx: float, wy: float) -> tuple[int, int]:
            return self._world_to_screen(wx, wy, vx, vy, vw, vh, bounds)

        self._draw_restricted_zones(canvas, zones, s2s)

        if bypass_route and len(bypass_route) > 1:
            for i in range(len(bypass_route) - 1):
                cv2.line(canvas, s2s(*bypass_route[i]), s2s(*bypass_route[i + 1]),
                         (0, 255, 220), 2, cv2.LINE_AA)

        return canvas

    def _draw_restricted_zones(
        self,
        canvas: np.ndarray,
        zones: list[RestrictedZone],
        s2s,
    ) -> None:
        for zone in zones:
            cx, cy = zone.center_x, zone.center_y
            # Approximate pixel radius by projecting one point on the boundary
            edge = s2s(cx + zone.radius_m, cy)
            center_px = s2s(cx, cy)
            r_hard_px = abs(edge[0] - center_px[0])

            edge_eff = s2s(cx + zone.effective_radius, cy)
            r_eff_px = abs(edge_eff[0] - center_px[0])

            # Filled soft zone (effective radius)
            overlay = canvas.copy()
            cv2.circle(overlay, center_px, r_eff_px, (0, 30, 180), -1)
            cv2.addWeighted(overlay, 0.25, canvas, 0.75, 0, canvas)

            # Hard zone fill
            overlay2 = canvas.copy()
            cv2.circle(overlay2, center_px, r_hard_px, (0, 0, 200), -1)
            cv2.addWeighted(overlay2, 0.35, canvas, 0.65, 0, canvas)

            # Borders
            cv2.circle(canvas, center_px, r_hard_px, (80, 80, 255), 2)
            cv2.circle(canvas, center_px, r_eff_px,  (0, 180, 255), 1)

            # Dashes on buffer ring
            import math
            for deg in range(0, 360, 18):
                rad = math.radians(deg)
                px = int(center_px[0] + r_eff_px * math.cos(rad))
                py = int(center_px[1] + r_eff_px * math.sin(rad))
                cv2.circle(canvas, (px, py), 2, (0, 180, 255), -1)

            # Label
            cv2.putText(canvas, zone.label,
                        (center_px[0] - 20, center_px[1] - r_eff_px - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 160, 255), 2, cv2.LINE_AA)
            cv2.putText(canvas, f"R={zone.radius_m:.0f}+{zone.buffer_m:.0f}m buf",
                        (center_px[0] - 36, center_px[1] + r_eff_px + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 255), 1, cv2.LINE_AA)

    def save_preview(self, step: MissionStep, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), self.render(step))
        return path

    # ── internal helpers ──────────────────────────────────────────────────────

    def _draw_panel(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        title: str,
    ) -> None:
        x, y, w, h = rect
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (20, 22, 24), -1)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (84, 92, 100), 1)
        cv2.putText(canvas, title, (x + 12, y + 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 226, 232), 2, cv2.LINE_AA)

    def _world_to_screen(
        self,
        wx: float, wy: float,
        vx: int, vy: int, vw: int, vh: int,
        bounds: tuple[float, float, float, float],
    ) -> tuple[int, int]:
        min_x, max_x, min_y, max_y = bounds
        sx = vx + int((wx - min_x) / (max_x - min_x) * vw)
        sy = vy + vh - int((wy - min_y) / (max_y - min_y) * vh)  # flip y
        return (sx, sy)

    def _map_bounds(self, step: MissionStep, margin: float = 100.0) -> tuple[float, float, float, float]:
        xs = [0.0] + [w[0] for w in step.waypoints]
        ys = [0.0] + [w[1] for w in step.waypoints]
        return (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)

    def _draw_map(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        step: MissionStep,
        trail: list[tuple[float, float]],
    ) -> None:
        x, y, w, h = rect
        vx, vy, vw, vh = x + 12, y + 40, w - 24, h - 52
        bounds = self._map_bounds(step)

        def s2s(wx: float, wy: float) -> tuple[int, int]:
            return self._world_to_screen(wx, wy, vx, vy, vw, vh, bounds)

        # Background
        cv2.rectangle(canvas, (vx, vy), (vx + vw, vy + vh), (52, 64, 52), -1)

        # Grid every 100 m
        min_x, max_x, min_y, max_y = bounds
        gstep = 100.0
        gx = min_x
        while gx <= max_x:
            p1, p2 = s2s(gx, min_y), s2s(gx, max_y)
            cv2.line(canvas, p1, p2, (74, 94, 74), 1)
            gx += gstep
        gy = min_y
        while gy <= max_y:
            p1, p2 = s2s(min_x, gy), s2s(max_x, gy)
            cv2.line(canvas, p1, p2, (74, 94, 74), 1)
            gy += gstep

        # Route lines: home → WP1 → WP2 → WP3 → WP4(home)
        route = [(0.0, 0.0)] + list(step.waypoints)
        for i in range(len(route) - 1):
            p1, p2 = s2s(*route[i]), s2s(*route[i + 1])
            if i < step.current_wp:
                color, thick = (60, 220, 80), 2    # completed – green
            elif i == step.current_wp:
                color, thick = (240, 220, 40), 3   # active – yellow
            else:
                color, thick = (110, 110, 110), 1  # future – gray
            cv2.line(canvas, p1, p2, color, thick)

        # Trail (aircraft history)
        for i in range(len(trail) - 1):
            cv2.line(canvas, s2s(*trail[i]), s2s(*trail[i + 1]), (200, 120, 60), 1)

        # Waypoint markers — support any number of waypoints (bypass may add extras)
        last_idx = len(step.waypoints) - 1
        for i, wp in enumerate(step.waypoints):
            if i == last_idx and wp == (0.0, 0.0):
                continue  # RTL home overlaps HOME marker; skip
            sp = s2s(*wp)
            if i < step.current_wp:
                col = (60, 220, 80)
            elif i == step.current_wp:
                col = (240, 220, 40)
            else:
                col = (180, 180, 180)
            label = f"WP{i + 1}"
            cv2.circle(canvas, sp, 9, col, -1)
            cv2.circle(canvas, sp, 9, (245, 245, 245), 1)
            cv2.putText(canvas, label, (sp[0] + 12, sp[1] + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2, cv2.LINE_AA)

        # Home marker
        home = s2s(0.0, 0.0)
        cv2.circle(canvas, home, 11, (255, 200, 60), -1)
        cv2.circle(canvas, home, 11, (245, 245, 245), 1)
        cv2.putText(canvas, "HOME", (home[0] + 13, home[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 60), 2, cv2.LINE_AA)

        # Aircraft symbol
        ac = s2s(step.aircraft_x, step.aircraft_y)
        self._draw_aircraft(canvas, ac)

        # Scale bar (100 m)
        x_range = bounds[1] - bounds[0]
        bar_px = int(100.0 / x_range * vw)
        bx, by = vx + 16, vy + vh - 18
        cv2.line(canvas, (bx, by), (bx + bar_px, by), (220, 220, 220), 2)
        cv2.line(canvas, (bx, by - 4), (bx, by + 4), (220, 220, 220), 1)
        cv2.line(canvas, (bx + bar_px, by - 4), (bx + bar_px, by + 4), (220, 220, 220), 1)
        cv2.putText(canvas, "100 m", (bx, by - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)

        # North arrow
        na = (vx + vw - 28, vy + 44)
        cv2.arrowedLine(canvas, (na[0], na[1] + 22), (na[0], na[1] - 22),
                        (220, 220, 220), 2, tipLength=0.4)
        cv2.putText(canvas, "N", (na[0] - 6, na[1] - 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 2, cv2.LINE_AA)

    def _draw_status(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        step: MissionStep,
    ) -> None:
        x, y, w, h = rect
        vx, vy = x + 14, y + 40

        # Altitude bar
        max_alt = max(60.0, step.alt_m + 10.0)
        bar_x, bar_y = vx + 16, vy + 16
        bar_h, bar_w = min(h - 80, 200), 26
        cv2.rectangle(canvas, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (55, 55, 65), -1)
        cv2.rectangle(canvas, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (110, 110, 120), 1)
        fill_h = int(bar_h * min(1.0, step.alt_m / max_alt))
        if fill_h > 0:
            fill_col = (60, 220, 80) if step.alt_m >= 45.0 else (240, 180, 40)
            cv2.rectangle(canvas,
                          (bar_x, bar_y + bar_h - fill_h),
                          (bar_x + bar_w, bar_y + bar_h),
                          fill_col, -1)
        cv2.putText(canvas, "ALT", (bar_x, bar_y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"{step.alt_m:.0f}m", (bar_x - 2, bar_y + bar_h + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 220), 1, cv2.LINE_AA)

        # Phase & waypoint info block
        col = _phase_color(step.phase)
        tx = bar_x + bar_w + 16
        cv2.putText(canvas, "PHASE", (tx, vy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(canvas, step.phase.upper().replace("_", " "), (tx, vy + 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, col, 2, cv2.LINE_AA)

        wp_label = "—" if step.current_wp < 0 else f"WP{step.current_wp + 1}"
        cv2.putText(canvas, "TARGET", (tx, vy + 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(canvas, wp_label, (tx, vy + 106),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 200, 80), 2, cv2.LINE_AA)

        cv2.putText(canvas, "DIST", (tx, vy + 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (160, 160, 160), 1, cv2.LINE_AA)
        dist_str = "—" if step.current_wp < 0 else f"{step.wp_dist_m:.0f} m"
        cv2.putText(canvas, dist_str, (tx, vy + 164),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (220, 220, 220), 2, cv2.LINE_AA)

    def _draw_telemetry(
        self,
        canvas: np.ndarray,
        rect: tuple[int, int, int, int],
        step: MissionStep,
    ) -> None:
        x, y, _, _ = rect
        col = _phase_color(step.phase)
        fields = [
            f"t={step.time_s:.1f}s",
            f"phase={step.phase}",
            f"alt={step.alt_m:.1f}m",
            f"wp_dist={step.wp_dist_m:.0f}m",
            f"pos=({step.aircraft_x:.0f},{step.aircraft_y:.0f})m",
        ]
        cv2.putText(canvas, "  ".join(fields), (x + 16, y + 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.68, col, 2, cv2.LINE_AA)

    def _draw_aircraft(self, canvas: np.ndarray, center: tuple[int, int]) -> None:
        cx, cy = center
        pts = np.array(
            [[cx, cy - 18], [cx - 12, cy + 14], [cx, cy + 6], [cx + 12, cy + 14]],
            dtype=np.int32,
        )
        cv2.fillConvexPoly(canvas, pts, (255, 170, 60))
        cv2.polylines(canvas, [pts], isClosed=True, color=(245, 245, 245), thickness=1)


def _phase_color(phase: str) -> tuple[int, int, int]:
    if phase == "takeoff":
        return (240, 180, 40)
    if phase.startswith("nav"):
        return (40, 180, 255)
    if phase == "rtl":
        return (60, 220, 80)
    return (220, 220, 220)

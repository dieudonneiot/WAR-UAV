from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


# ── Restricted Zone ───────────────────────────────────────────────────────────

@dataclass(slots=True)
class RestrictedZone:
    """Circular no-fly zone broadcast by the air defense system."""

    center_x: float   # metres east of home
    center_y: float   # metres north of home
    radius_m: float   # hard exclusion radius
    buffer_m: float = 75.0
    label: str = "AD-1"

    @property
    def effective_radius(self) -> float:
        return self.radius_m + self.buffer_m

    def contains(self, x: float, y: float) -> bool:
        return math.hypot(x - self.center_x, y - self.center_y) < self.effective_radius

    def distance_to_boundary(self, x: float, y: float) -> float:
        """Signed distance: positive = outside, negative = inside."""
        return math.hypot(x - self.center_x, y - self.center_y) - self.effective_radius

    def distance_to_point(self, x: float, y: float) -> float:
        """Distance from point to nearest point on the effective boundary (0 if inside)."""
        return max(0.0, self.distance_to_boundary(x, y))


# ── Route Checker ─────────────────────────────────────────────────────────────

class RouteChecker:

    @staticmethod
    def segment_intersects_circle(
        ax: float, ay: float,
        bx: float, by: float,
        cx: float, cy: float,
        r: float,
    ) -> bool:
        dx, dy = bx - ax, by - ay
        fx, fy = ax - cx, ay - cy
        a = dx * dx + dy * dy
        if a < 1e-12:
            return math.hypot(fx, fy) < r
        b = 2.0 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - r * r
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return False
        sq = math.sqrt(disc)
        t1 = (-b - sq) / (2.0 * a)
        t2 = (-b + sq) / (2.0 * a)
        return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0) or (t1 < 0.0 < t2)

    @staticmethod
    def segment_intersects_zone(
        a: tuple[float, float],
        b: tuple[float, float],
        zone: RestrictedZone,
    ) -> bool:
        return RouteChecker.segment_intersects_circle(
            a[0], a[1], b[0], b[1],
            zone.center_x, zone.center_y, zone.effective_radius,
        )

    @staticmethod
    def route_is_safe(
        waypoints: Sequence[tuple[float, float]],
        zones: Sequence[RestrictedZone],
    ) -> bool:
        for i in range(len(waypoints) - 1):
            for zone in zones:
                if RouteChecker.segment_intersects_zone(waypoints[i], waypoints[i + 1], zone):
                    return False
        return True

    @staticmethod
    def min_distance_to_zones(
        x: float, y: float,
        zones: Sequence[RestrictedZone],
    ) -> float:
        if not zones:
            return float("inf")
        return min(z.distance_to_point(x, y) for z in zones)


# ── Tangent helpers ───────────────────────────────────────────────────────────

def _tangent_points(
    px: float, py: float,
    cx: float, cy: float,
    r: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Tangent points on circle(cx,cy,r) from external point (px,py).

    Returns (t0, t1) where t0 is to the left and t1 to the right of the
    direction P→C.  Returns None if P is inside the circle.

    Derivation: right-angle triangle at tangent point T gives:
        cos(φ) = r/d  where d = |PC|
    Tangent point: T = C - r·(cos(α ∓ φ), sin(α ∓ φ))
    where α = atan2(cy-py, cx-px).
    """
    d = math.hypot(cx - px, cy - py)
    if d <= r + 1e-6:
        return None
    alpha = math.atan2(cy - py, cx - px)
    phi = math.acos(min(1.0, r / d))
    t0 = (cx - r * math.cos(alpha - phi), cy - r * math.sin(alpha - phi))
    t1 = (cx - r * math.cos(alpha + phi), cy - r * math.sin(alpha + phi))
    return t0, t1


_BYPASS_CLEARANCE_M = 20.0  # extra gap beyond effective_radius so the arc stays safely outside


def _path_length(pts: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return total


def _arc_waypoints(
    cx: float, cy: float, r: float,
    ta: tuple[float, float],
    tb: tuple[float, float],
    n: int = 5,
) -> list[tuple[float, float]]:
    """N interior points on the shorter arc from *ta* to *tb* on circle(cx,cy,r).

    The tangent-to-tangent chord cuts through the circle, so we interpolate
    along the arc instead.  All returned points lie on the circle boundary.
    """
    theta_a = math.atan2(ta[1] - cy, ta[0] - cx)
    theta_b = math.atan2(tb[1] - cy, tb[0] - cx)
    # Normalize difference to (−π, π] so we always take the shorter arc
    diff = (theta_b - theta_a + math.pi) % (2 * math.pi) - math.pi
    return [
        (cx + r * math.cos(theta_a + diff * k / (n + 1)),
         cy + r * math.sin(theta_a + diff * k / (n + 1)))
        for k in range(1, n + 1)
    ]


# ── Bypass Planner ────────────────────────────────────────────────────────────

class BypassPlanner:
    """Visibility-graph tangent bypass for circular restricted zones.

    Algorithm per blocking segment:
      1. Inflate the effective radius by _BYPASS_CLEARANCE_M to guarantee
         the path stays safely outside the zone boundary.
      2. Compute the two tangent lines from each endpoint to the inflated
         circle and pick the shorter left/right bypass pair.
      3. Insert arc-interpolated waypoints between the tangent points so the
         path follows the circle arc instead of the chord (which would dip
         back inside).

    Multiple or overlapping zones are resolved by iterating until the full
    route is safe (MAX_ITERATIONS guard).
    """

    MAX_ITERATIONS = 8

    @staticmethod
    def plan(
        waypoints: Sequence[tuple[float, float]],
        zones: Sequence[RestrictedZone],
    ) -> list[tuple[float, float]]:
        if not zones or RouteChecker.route_is_safe(waypoints, zones):
            return list(waypoints)

        route = list(waypoints)
        for _ in range(BypassPlanner.MAX_ITERATIONS):
            route = BypassPlanner._single_pass(route, zones)
            if RouteChecker.route_is_safe(route, zones):
                break
        return route

    @staticmethod
    def _single_pass(
        waypoints: list[tuple[float, float]],
        zones: Sequence[RestrictedZone],
    ) -> list[tuple[float, float]]:
        result: list[tuple[float, float]] = [waypoints[0]]

        for i in range(len(waypoints) - 1):
            seg_a = waypoints[i]
            seg_b = waypoints[i + 1]

            blocking: RestrictedZone | None = None
            for zone in zones:
                if RouteChecker.segment_intersects_zone(seg_a, seg_b, zone):
                    blocking = zone
                    break

            if blocking is None:
                result.append(seg_b)
                continue

            # Use inflated radius so arc stays outside the zone boundary
            bypass_r = blocking.effective_radius + _BYPASS_CLEARANCE_M

            tps_a = _tangent_points(
                seg_a[0], seg_a[1],
                blocking.center_x, blocking.center_y, bypass_r,
            )
            tps_b = _tangent_points(
                seg_b[0], seg_b[1],
                blocking.center_x, blocking.center_y, bypass_r,
            )

            if tps_a is None or tps_b is None:
                result.append(seg_b)
                continue

            dx, dy = seg_b[0] - seg_a[0], seg_b[1] - seg_a[1]

            def left_of(pt: tuple[float, float]) -> float:
                return (pt[0] - seg_a[0]) * (-dy) + (pt[1] - seg_a[1]) * dx

            ta_left  = tps_a[0] if left_of(tps_a[0]) >= left_of(tps_a[1]) else tps_a[1]
            ta_right = tps_a[1] if left_of(tps_a[0]) >= left_of(tps_a[1]) else tps_a[0]
            tb_left  = tps_b[0] if left_of(tps_b[0]) >= left_of(tps_b[1]) else tps_b[1]
            tb_right = tps_b[1] if left_of(tps_b[0]) >= left_of(tps_b[1]) else tps_b[0]

            cx, cy = blocking.center_x, blocking.center_y
            arc_l = _arc_waypoints(cx, cy, bypass_r, ta_left, tb_left)
            arc_r = _arc_waypoints(cx, cy, bypass_r, ta_right, tb_right)

            bypass_l = [seg_a, ta_left]  + arc_l + [tb_left,  seg_b]
            bypass_r = [seg_a, ta_right] + arc_r + [tb_right, seg_b]

            bypass = bypass_l if _path_length(bypass_l) <= _path_length(bypass_r) else bypass_r
            result.extend(bypass[1:])

        return result


# ── A* grid planner (for report figure only) ──────────────────────────────────

def astar_grid(
    start: tuple[float, float],
    goal: tuple[float, float],
    zones: Sequence[RestrictedZone],
    grid_resolution_m: float = 20.0,
    world_bounds: tuple[float, float, float, float] = (-100.0, 700.0, -100.0, 700.0),
) -> tuple[list[tuple[float, float]], list[list[int]]]:
    """A* on a 2-D grid.  Returns (path_in_metres, cost_grid).

    cost_grid cells: 0 = free, 1 = blocked (inside any effective radius).
    path_in_metres is a list of (x, y) world coordinates.
    """
    min_x, max_x, min_y, max_y = world_bounds
    res = grid_resolution_m
    cols = max(1, int((max_x - min_x) / res))
    rows = max(1, int((max_y - min_y) / res))

    def world_to_cell(wx: float, wy: float) -> tuple[int, int]:
        c = int((wx - min_x) / res)
        r = int((wy - min_y) / res)
        return (max(0, min(cols - 1, c)), max(0, min(rows - 1, r)))

    def cell_to_world(c: int, r: int) -> tuple[float, float]:
        return (min_x + (c + 0.5) * res, min_y + (r + 0.5) * res)

    # Build cost grid
    grid: list[list[int]] = []
    for r in range(rows):
        row: list[int] = []
        for c in range(cols):
            wx, wy = cell_to_world(c, r)
            blocked = any(z.contains(wx, wy) for z in zones)
            row.append(1 if blocked else 0)
        grid.append(row)

    sc, sr = world_to_cell(*start)
    gc, gr = world_to_cell(*goal)

    import heapq
    open_heap: list[tuple[float, int, int]] = []
    heapq.heappush(open_heap, (0.0, sc, sr))
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sc, sr): None}
    g_score: dict[tuple[int, int], float] = {(sc, sr): 0.0}

    def h(c: int, r: int) -> float:
        return math.hypot(c - gc, r - gr)

    directions = [
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
    ]

    found = False
    while open_heap:
        _, cc, cr = heapq.heappop(open_heap)
        if (cc, cr) == (gc, gr):
            found = True
            break
        for dc, dr in directions:
            nc, nr = cc + dc, cr + dr
            if not (0 <= nc < cols and 0 <= nr < rows):
                continue
            if grid[nr][nc] == 1:
                continue
            step_cost = math.hypot(dc, dr)
            new_g = g_score[(cc, cr)] + step_cost
            if new_g < g_score.get((nc, nr), float("inf")):
                g_score[(nc, nr)] = new_g
                came_from[(nc, nr)] = (cc, cr)
                heapq.heappush(open_heap, (new_g + h(nc, nr), nc, nr))

    path_cells: list[tuple[int, int]] = []
    if found:
        cur: tuple[int, int] | None = (gc, gr)
        while cur is not None:
            path_cells.append(cur)
            cur = came_from[cur]
        path_cells.reverse()

    path_world = [cell_to_world(c, r) for c, r in path_cells]
    return path_world, grid

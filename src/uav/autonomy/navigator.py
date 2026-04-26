from __future__ import annotations

import math
import time

from uav.mavlink.client import MavlinkClient

# 1 degree latitude ≈ 111 320 m; longitude varies with cos(lat) but we accept
# this planar approximation for short-range (<5 km) square patterns.
_METERS_PER_DEG = 111_320
_E7 = 10_000_000


def meters_to_e7(meters: float) -> int:
    """Convert a distance in metres to integer 1e-7 degree units."""
    return int(meters / _METERS_PER_DEG * _E7)


def compute_square_waypoints(
    home_lat_e7: int,
    home_lon_e7: int,
    side_m: float = 500.0,
) -> list[tuple[int, int]]:
    """Return four GPS waypoints forming a square of *side_m* metres.

    The square is laid out north-then-east of *home*:
        WP1 – north, WP2 – northeast, WP3 – east, WP4 – home (RTL start point).
    Coordinates are in 1e-7 degree integer format as used by MAVLink command_int.
    """
    off = meters_to_e7(side_m)
    return [
        (home_lat_e7 + off, home_lon_e7),           # WP1 – north
        (home_lat_e7 + off, home_lon_e7 + off),     # WP2 – northeast
        (home_lat_e7,       home_lon_e7 + off),     # WP3 – east
        (home_lat_e7,       home_lon_e7),            # WP4 – home
    ]


def compute_triangle_waypoints(
    home_lat_e7: int,
    home_lon_e7: int,
    side_m: float = 500.0,
) -> list[tuple[int, int]]:
    """Return three waypoints forming a simple triangle north/east of home."""
    off = meters_to_e7(side_m)
    half = meters_to_e7(side_m / 2.0)
    return [
        (home_lat_e7 + off, home_lon_e7),           # WP1 - north
        (home_lat_e7 + half, home_lon_e7 + off),    # WP2 - northeast
        (home_lat_e7,       home_lon_e7),           # WP3 - home
    ]


def compute_line_waypoints(
    home_lat_e7: int,
    home_lon_e7: int,
    side_m: float = 500.0,
) -> list[tuple[int, int]]:
    """Return an out-and-back line mission north of home."""
    off = meters_to_e7(side_m)
    return [
        (home_lat_e7 + off, home_lon_e7),           # WP1 - outbound
        (home_lat_e7,       home_lon_e7),           # WP2 - home
    ]


def compute_circle_waypoints(
    home_lat_e7: int,
    home_lon_e7: int,
    radius_m: float = 250.0,
    points: int = 8,
) -> list[tuple[int, int]]:
    """Approximate a circle around home with evenly spaced waypoints."""
    if points < 3:
        raise ValueError("Circle missions require at least 3 points.")

    radius_e7 = meters_to_e7(radius_m)
    waypoints: list[tuple[int, int]] = []
    for i in range(points):
        theta = 2.0 * math.pi * i / points
        north = int(round(math.cos(theta) * radius_e7))
        east = int(round(math.sin(theta) * radius_e7))
        waypoints.append((home_lat_e7 + north, home_lon_e7 + east))
    waypoints.append((home_lat_e7, home_lon_e7))
    return waypoints


def compute_mission_waypoints(
    shape: str,
    home_lat_e7: int,
    home_lon_e7: int,
    size_m: float = 500.0,
) -> list[tuple[int, int]]:
    """Return waypoints for a named mission shape."""
    shape = shape.lower()
    if shape == "square":
        return compute_square_waypoints(home_lat_e7, home_lon_e7, size_m)
    if shape == "triangle":
        return compute_triangle_waypoints(home_lat_e7, home_lon_e7, size_m)
    if shape == "line":
        return compute_line_waypoints(home_lat_e7, home_lon_e7, size_m)
    if shape == "circle":
        return compute_circle_waypoints(home_lat_e7, home_lon_e7, radius_m=size_m / 2.0)
    raise ValueError(f"Unknown mission shape {shape!r}.")


class WaypointNavigator:
    def __init__(self, client: MavlinkClient, acceptance_radius_m: float = 65.0) -> None:
        self.client = client
        self.acceptance_radius_m = acceptance_radius_m

    def fly_to(self, lat_e7: int, lon_e7: int, alt_m: float) -> None:
        self.client.reposition(lat_e7, lon_e7, alt_m)

    def wait_until_reached(self) -> None:
        """Block until NAV_CONTROLLER_OUTPUT.wp_dist drops below acceptance_radius_m."""
        while True:
            dist = self.client.get_nav_status()
            if dist is not None:
                print(f"  wp_dist={dist:.0f} m")
                if dist < self.acceptance_radius_m:
                    print("  Waypoint reached.")
                    break

    def climb_to(self, target_alt_m: float, timeout_s: float = 120.0) -> None:
        """Use ArduPlane TAKEOFF mode until relative altitude reaches *target_alt_m*."""
        self.client.set_mode("TAKEOFF")
        time.sleep(1)
        self.client.arm()

        deadline = time.monotonic() + timeout_s
        while True:
            _, _, alt = self.client.get_position()
            print(f"  alt={alt:.1f} m")
            if alt >= target_alt_m:
                print(f"  Reached {alt:.1f} m.")
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"TAKEOFF did not reach {target_alt_m:.1f} m within {timeout_s:.0f}s "
                    f"(last altitude {alt:.1f} m)."
                )

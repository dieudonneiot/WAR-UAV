from __future__ import annotations

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

    def climb_to(self, target_alt_m: float, throttle: int = 1800) -> None:
        """Apply RC throttle override until relative altitude reaches *target_alt_m*."""
        while True:
            self.client.rc_override(throttle)
            _, _, alt = self.client.get_position()
            print(f"  alt={alt:.1f} m")
            if alt >= target_alt_m:
                print(f"  Reached {alt:.1f} m.")
                self.client.rc_override(0)
                break

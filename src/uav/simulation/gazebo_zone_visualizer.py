from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field

from uav.autonomy.air_defense import RestrictedZone

# Cylinder height (m) — tall enough to be visible from any flight altitude
_COLUMN_HEIGHT = 400.0


@dataclass
class GazeboZoneVisualizer:
    """Draws RestrictedZone circles as 3-D cylinders in a running Gazebo world.

    Coordinate mapping (Gazebo ENU == our local ENU from home):
        Gazebo X  =  zone.center_x  (east  metres from home)
        Gazebo Y  =  zone.center_y  (north metres from home)
        Gazebo Z  =  _COLUMN_HEIGHT / 2  (cylinder midpoint)

    Requires:
        • Gazebo Harmonic running in WSL2 with world name matching *world_name*
        • `gz` CLI available in WSL2 PATH
    """

    world_name: str = "air_defense"
    wsl_distro: str = ""
    _active: set[str] = field(default_factory=set, init=False, repr=False)

    # ── public API ─────────────────────────────────────────────────────────

    def show_zone(self, zone: RestrictedZone) -> bool:
        """Spawn hard-zone and buffer-ring cylinders in Gazebo."""
        ok = True
        ok &= self._spawn(
            name=f"zone_{zone.label}_hard",
            x=zone.center_x,
            y=zone.center_y,
            radius=zone.radius_m,
            height=_COLUMN_HEIGHT,
            r=0.9, g=0.05, b=0.05, alpha=0.45,
        )
        ok &= self._spawn(
            name=f"zone_{zone.label}_buffer",
            x=zone.center_x,
            y=zone.center_y,
            radius=zone.effective_radius,
            height=8.0,          # flat ring at ground level
            r=0.1, g=0.4, b=0.9, alpha=0.35,
        )
        if ok:
            self._active.add(zone.label)
        return ok

    def hide_zone(self, zone: RestrictedZone) -> bool:
        ok  = self._remove(f"zone_{zone.label}_hard")
        ok &= self._remove(f"zone_{zone.label}_buffer")
        self._active.discard(zone.label)
        return ok

    def clear_all(self) -> None:
        for label in list(self._active):
            self._remove(f"zone_{label}_hard")
            self._remove(f"zone_{label}_buffer")
        self._active.clear()

    def update_bypass_path(
        self,
        waypoints: list[tuple[float, float]],
        alt_m: float = 50.0,
        name: str = "bypass_path",
    ) -> bool:
        """Draw the replanned bypass route as a series of thin marker cylinders."""
        self._remove_prefix(f"{name}_seg")
        ok = True
        for i, (wx, wy) in enumerate(waypoints):
            ok &= self._spawn(
                name=f"{name}_seg{i}",
                x=wx, y=wy,
                radius=3.0,
                height=alt_m * 2,
                r=0.0, g=0.9, b=0.8, alpha=0.70,
            )
        return ok

    # ── internal helpers ──────────────────────────────────────────────────

    def _spawn(
        self,
        name: str,
        x: float, y: float,
        radius: float, height: float,
        r: float, g: float, b: float, alpha: float,
    ) -> bool:
        self._remove(name)   # clean up stale model with the same name if any
        z = height / 2.0
        sdf = self._cylinder_sdf(name, x, y, z, radius, height, r, g, b, alpha)
        return self._gz_service_create(sdf)

    def _remove(self, name: str) -> bool:
        req = f'name: "{name}" type: MODEL'
        result = self._wsl_run(
            "gz", "service",
            "-s", f"/world/{self.world_name}/remove",
            "--reqtype", "gz.msgs.Entity",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "1000",
            "--req", req,
        )
        return result.returncode == 0

    def _remove_prefix(self, prefix: str) -> None:
        # Try to remove up to 20 segments
        for i in range(20):
            self._remove(f"{prefix}{i}")

    def _gz_service_create(self, sdf: str) -> bool:
        # Escape double-quotes inside the SDF string for proto text format
        escaped = sdf.replace('"', '\\"').replace("\n", "")
        req = f'sdf: "{escaped}"'
        result = self._wsl_run(
            "gz", "service",
            "-s", f"/world/{self.world_name}/create",
            "--reqtype", "gz.msgs.EntityFactory",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "2000",
            "--req", req,
        )
        return result.returncode == 0

    def _wsl_run(self, *cmd: str, timeout: float = 5.0) -> subprocess.CompletedProcess:
        base = ["wsl"]
        if self.wsl_distro:
            base += ["-d", self.wsl_distro]
        # Use interactive bash so WSL2 PATH and env vars are loaded
        full_cmd = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        return subprocess.run(
            base + ["--", "bash", "-ic", full_cmd],
            capture_output=True, text=True, timeout=timeout,
        )

    # ── SDF generators ────────────────────────────────────────────────────

    @staticmethod
    def _cylinder_sdf(
        name: str, x: float, y: float, z: float,
        radius: float, height: float,
        r: float, g: float, b: float, alpha: float,
    ) -> str:
        transparency = max(0.0, min(1.0, 1.0 - alpha))
        return (
            f'<sdf version="1.9">'
            f'<model name="{name}">'
            f'<static>true</static>'
            f'<link name="link">'
            f'<visual name="visual">'
            f'<transparency>{transparency:.2f}</transparency>'
            f'<geometry>'
            f'<cylinder><radius>{radius:.3f}</radius><length>{height:.3f}</length></cylinder>'
            f'</geometry>'
            f'<material>'
            f'<ambient>{r:.2f} {g:.2f} {b:.2f} {alpha:.2f}</ambient>'
            f'<diffuse>{r:.2f} {g:.2f} {b:.2f} {alpha:.2f}</diffuse>'
            f'<specular>0.1 0.1 0.1 1</specular>'
            f'</material>'
            f'</visual>'
            f'</link>'
            f'<pose>{x:.3f} {y:.3f} {z:.3f} 0 0 0</pose>'
            f'</model>'
            f'</sdf>'
        )

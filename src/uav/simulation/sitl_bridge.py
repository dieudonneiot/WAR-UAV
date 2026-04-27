from __future__ import annotations

import subprocess
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
_SITL_LAUNCH  = _SCRIPTS_DIR / "sitl_launch.sh"


class SitlBridge:
    """Manages ArduPlane SITL + Gazebo running in WSL2.

    Typical usage:
        bridge = SitlBridge()
        conn_str = bridge.launch()          # starts SITL+Gazebo in WSL2
        client = MavlinkClient(conn_str)
        client.connect()
        ...
        bridge.stop()

    If SITL is already running (e.g., started manually via sitl_launch.sh),
    construct with launch_sitl=False and pass the connection string directly:
        bridge = SitlBridge(launch_sitl=False)
        conn_str = bridge.connection_string  # "udpin:0.0.0.0:14550"
    """

    SITL_HOME     = "-35.363262,149.165237,584,353"
    GAZEBO_WORLD  = "air_defense"

    def __init__(
        self,
        mavlink_port: int = 14550,
        wsl_distro: str = "",
        launch_sitl: bool = True,
        headless_gazebo: bool = False,
    ) -> None:
        self.mavlink_port      = mavlink_port
        self.wsl_distro        = wsl_distro
        self.launch_sitl       = launch_sitl
        self.headless_gazebo   = headless_gazebo
        self._proc: subprocess.Popen | None = None

    @property
    def connection_string(self) -> str:
        return f"udpin:0.0.0.0:{self.mavlink_port}"

    def launch(self, timeout_s: float = 60.0) -> str:
        """Start SITL + Gazebo in WSL2.  Returns the MAVLink connection string."""
        if not self.launch_sitl:
            return self.connection_string

        cmd = self._wsl_cmd([
            "bash", str(self._wsl_path(_SITL_LAUNCH)),
            "--port", str(self.mavlink_port),
        ])
        if self.headless_gazebo:
            cmd.append("--headless")

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output until we see "SITL + Gazebo running" or timeout
        deadline = time.monotonic() + timeout_s
        for line in self._proc.stdout:  # type: ignore[union-attr]
            print(f"[sitl] {line.rstrip()}")
            if "SITL + Gazebo running" in line or "MAVLink port" in line:
                break
            if time.monotonic() > deadline:
                self.stop()
                raise TimeoutError("SITL did not start within timeout.")

        return self.connection_string

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def _wsl_cmd(self, inner: list[str]) -> list[str]:
        base = ["wsl"]
        if self.wsl_distro:
            base += ["-d", self.wsl_distro]
        base.append("--")
        return base + inner

    @staticmethod
    def _wsl_path(windows_path: Path) -> str:
        """Convert Windows path to WSL2 /mnt/... path."""
        p = str(windows_path).replace("\\", "/")
        if len(p) > 1 and p[1] == ":":
            drive = p[0].lower()
            return f"/mnt/{drive}/{p[3:]}"
        return p

    # ── convenience: get Windows host IP as seen from WSL2 ────────────────
    @staticmethod
    def windows_host_ip(wsl_distro: str = "") -> str:
        cmd = ["wsl"]
        if wsl_distro:
            cmd += ["-d", wsl_distro]
        cmd += ["--", "bash", "-c",
                "ip route show default 2>/dev/null | awk '{print $3; exit}'"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        return result.stdout.strip() or "127.0.0.1"

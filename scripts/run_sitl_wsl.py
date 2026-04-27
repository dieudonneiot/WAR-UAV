"""Launch Gazebo + ArduPlane SITL in WSL2 and stream output.

Usage:
    python scripts/run_sitl_wsl.py
    python scripts/run_sitl_wsl.py --headless
    python scripts/run_sitl_wsl.py --distro Ubuntu-22.04
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_SITL_SH = _SCRIPTS_DIR / "sitl_launch.sh"


def _wsl_path(p: Path) -> str:
    s = str(p).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        return f"/mnt/{s[0].lower()}/{s[3:]}"
    return s


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Gazebo + SITL in WSL2.")
    parser.add_argument("--distro", default="", help="WSL2 distro name")
    parser.add_argument("--headless", action="store_true", help="Headless Gazebo (no GUI)")
    args = parser.parse_args()

    cmd = ["wsl"]
    if args.distro:
        cmd += ["-d", args.distro]
    sh_args = ["bash", _wsl_path(_SITL_SH)]
    if args.headless:
        sh_args.append("--headless")
    cmd += ["--"] + sh_args

    print(f"[sitl-wsl] Starting: {' '.join(cmd)}", flush=True)
    print("[sitl-wsl] Gazebo window opens via WSLg. Wait for 'SITL + Gazebo running'.", flush=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout
    for line in proc.stdout:
        print(line, end="", flush=True)
    rc = proc.wait()
    print(f"\n[sitl-wsl] Exited (code {rc}).", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()

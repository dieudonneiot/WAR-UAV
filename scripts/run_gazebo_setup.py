"""Run scripts/setup_gazebo_wsl.sh inside WSL2 and stream its output.

Usage:
    python scripts/run_gazebo_setup.py [wsl-distro]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_SETUP_SH = _SCRIPTS_DIR / "setup_gazebo_wsl.sh"


def _wsl_path(p: Path) -> str:
    s = str(p).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        return f"/mnt/{s[0].lower()}/{s[3:]}"
    return s


def main() -> None:
    distro = sys.argv[1] if len(sys.argv) > 1 else ""
    cmd = ["wsl"]
    if distro:
        cmd += ["-d", distro]
    cmd += ["--", "bash", _wsl_path(_SETUP_SH)]

    print(f"[setup] Running: {' '.join(cmd)}", flush=True)
    print("[setup] This takes ~15 minutes on first run — output will stream below.", flush=True)

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
    print(f"\n[setup] Done (exit code {rc}).", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()

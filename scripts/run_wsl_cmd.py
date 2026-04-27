"""Run a bash command inside WSL2 and stream output.

Runs in an interactive bash session so ~/.bashrc is sourced automatically —
this ensures ArduPilot Tools/autotest is in PATH without manual sourcing.

Usage:
    python scripts/run_wsl_cmd.py --cmd "which sim_vehicle.py"
    python scripts/run_wsl_cmd.py --cmd "gz sim --version" --distro Ubuntu-22.04
    python scripts/run_wsl_cmd.py --cmd "ls ~/ardupilot_gazebo/models/"
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bash command in WSL2.")
    parser.add_argument("--cmd", required=True, help="Bash command to execute")
    parser.add_argument("--distro", default="", help="WSL2 distro name")
    args = parser.parse_args()

    wsl_cmd = ["wsl"]
    if args.distro:
        wsl_cmd += ["-d", args.distro]
    # bash -ic loads ~/.bashrc (PATH, env vars) before running the command
    wsl_cmd += ["--", "bash", "-ic", args.cmd]

    print(f"$ {args.cmd}", flush=True)
    proc = subprocess.Popen(
        wsl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout
    for line in proc.stdout:
        print(line, end="", flush=True)
    rc = proc.wait()
    if rc != 0:
        print(f"\n[exit {rc}]", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()

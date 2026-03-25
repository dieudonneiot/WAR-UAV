from __future__ import annotations

from rich import print

from uav.autonomy.mission_manager import MissionManager
from uav.common.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    manager = MissionManager(mission_name=settings.mission_name)
    print("[bold green]UAV workspace is ready.[/bold green]")
    print(f"Mission: {manager.mission_name}")
    print(f"Serial port: {settings.serial_port}")
    print(f"Simulation enabled: {settings.enable_simulation}")


if __name__ == "__main__":
    main()


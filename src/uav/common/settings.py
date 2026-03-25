from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    mission_name: str
    serial_port: str
    baudrate: int
    system_id: int
    component_id: int
    enable_simulation: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            mission_name=os.getenv("MISSION_NAME", "combat_uav"),
            serial_port=os.getenv("UAV_SERIAL_PORT", "COM6"),
            baudrate=int(os.getenv("UAV_BAUDRATE", "57600")),
            system_id=int(os.getenv("UAV_SYS_ID", "1")),
            component_id=int(os.getenv("UAV_COMP_ID", "1")),
            enable_simulation=os.getenv("ENABLE_SIMULATION", "true").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


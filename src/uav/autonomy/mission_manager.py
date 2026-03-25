from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MissionManager:
    mission_name: str
    current_phase: str = "standby"
    completed_phases: list[str] = field(default_factory=list)

    def transition_to(self, phase: str) -> None:
        if self.current_phase != phase:
            self.completed_phases.append(self.current_phase)
            self.current_phase = phase


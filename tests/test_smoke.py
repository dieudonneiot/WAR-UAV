from uav.autonomy.mission_manager import MissionManager
from uav.common.settings import Settings
from uav.vision.qr_reader import QRReader


def test_settings_defaults() -> None:
    settings = Settings.from_env()
    assert settings.mission_name


def test_mission_manager_transitions() -> None:
    manager = MissionManager(mission_name="combat")
    manager.transition_to("search")
    assert manager.current_phase == "search"


def test_qr_reader_construction() -> None:
    reader = QRReader()
    assert reader is not None

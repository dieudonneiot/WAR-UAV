from __future__ import annotations

from uav.autonomy.engagement import EngagementConfig, EngagementController
from uav.autonomy.mission_manager import MissionManager
from uav.vision.tracker import TrackState


def test_engagement_searches_without_track() -> None:
    manager = MissionManager(mission_name="test")
    controller = EngagementController(
        EngagementConfig(image_width=1920, image_height=1200, lock_duration_s=4.0)
    )

    state = controller.update(manager, track=None, dt_s=1.0)

    assert state.phase == "search"
    assert state.lock_progress_s == 0.0
    assert state.target_id is None


def test_engagement_locks_after_centered_target_duration() -> None:
    manager = MissionManager(mission_name="test")
    controller = EngagementController(
        EngagementConfig(image_width=1920, image_height=1200, lock_duration_s=2.0)
    )
    track = TrackState(
        target_id=1,
        center_x=960,
        center_y=600,
        confidence=0.9,
        class_id=0,
        label="uav",
        width=80,
        height=50,
    )

    first_state = controller.update(manager, track=track, dt_s=1.0)
    second_state = controller.update(manager, track=track, dt_s=1.0)

    assert first_state.phase == "track"
    assert second_state.phase == "lock"
    assert second_state.lock_active


def test_engagement_resets_lock_progress_when_target_moves_off_center() -> None:
    manager = MissionManager(mission_name="test")
    controller = EngagementController(
        EngagementConfig(image_width=1920, image_height=1200, lock_duration_s=2.0)
    )
    centered_track = TrackState(
        target_id=1,
        center_x=960,
        center_y=600,
        confidence=0.9,
        class_id=0,
        label="uav",
        width=80,
        height=50,
    )
    off_center_track = TrackState(
        target_id=1,
        center_x=400,
        center_y=600,
        confidence=0.9,
        class_id=0,
        label="uav",
        width=80,
        height=50,
    )

    controller.update(manager, track=centered_track, dt_s=1.0)
    state = controller.update(manager, track=off_center_track, dt_s=1.0)

    assert state.phase == "track"
    assert state.lock_progress_s == 0.0


def test_engagement_does_not_accumulate_lock_on_stale_track() -> None:
    manager = MissionManager(mission_name="test")
    controller = EngagementController(
        EngagementConfig(image_width=1920, image_height=1200, lock_duration_s=2.0)
    )
    stale_track = TrackState(
        target_id=1,
        center_x=960,
        center_y=600,
        confidence=0.4,
        class_id=0,
        label="uav",
        width=80,
        height=50,
        is_confirmed=False,
        missed_frames=1,
    )

    state = controller.update(manager, track=stale_track, dt_s=1.0)

    assert state.phase == "track"
    assert state.lock_progress_s == 0.0

from __future__ import annotations

import numpy as np

from uav.autonomy.engagement import EngagementState
from uav.simulation.vision_scenario import SimulationEvent
from uav.simulation.visualizer import SimulationVisualizer, VisualizerConfig
from uav.vision.tracker import TrackState


def test_visualizer_renders_non_blank_frame() -> None:
    visualizer = SimulationVisualizer(VisualizerConfig(canvas_width=640, canvas_height=360))
    event = SimulationEvent(
        time_s=1.0,
        track=TrackState(
            target_id=1,
            center_x=960,
            center_y=600,
            confidence=0.9,
            class_id=0,
            label="uav",
            width=80,
            height=50,
        ),
        engagement=_engagement_state(),
    )

    frame = visualizer.render(event)

    assert frame.shape == (360, 640, 3)
    assert frame.dtype == np.uint8
    assert frame.max() > frame.min()


def _engagement_state() -> EngagementState:
    return EngagementState(
        phase="track",
        lock_progress_s=1.0,
        target_id=1,
        center_error_x_px=0.0,
        center_error_y_px=0.0,
    )

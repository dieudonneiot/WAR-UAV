from __future__ import annotations

import cv2
import numpy as np
import pytest

from uav.vision.frame_source import OpenCVFrameSource


def test_opencv_frame_source_reads_video_frames(tmp_path) -> None:
    video_path = tmp_path / "sample.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer is unavailable in this environment")

    for index in range(3):
        frame = np.full((48, 64, 3), index * 40, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    with OpenCVFrameSource(video_path) as source:
        samples = list(source)

    assert len(samples) == 3
    assert samples[0].frame.shape == (48, 64, 3)
    assert samples[0].dt_s > 0

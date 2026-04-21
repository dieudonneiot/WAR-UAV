from __future__ import annotations

from uav.vision.detector import TargetDetector
from uav.vision.tracker import TargetTracker


class FakeModel:
    names = {0: "uav", 1: "bird"}


class FakeBoxes:
    xyxy = [[10, 20, 30, 60], [100, 120, 160, 180]]
    conf = [0.92, 0.10]
    cls = [0, 1]
    id = [7, 8]


class FakeResult:
    boxes = FakeBoxes()
    names = {0: "uav", 1: "bird"}


def make_detector(confidence_threshold: float = 0.25) -> TargetDetector:
    detector = TargetDetector.__new__(TargetDetector)
    detector.model = FakeModel()
    detector.confidence_threshold = confidence_threshold
    detector.target_class_ids = None
    return detector


def test_detector_returns_typed_detections() -> None:
    detector = make_detector()

    detections = detector._detections_from_result(FakeResult())

    assert len(detections) == 1
    detection = detections[0]
    assert detection.label == "uav"
    assert detection.confidence == 0.92
    assert detection.track_id == 7
    assert detection.center_x == 20
    assert detection.center_y == 40


def test_tracker_selects_best_detection_as_track_state() -> None:
    detector = make_detector(confidence_threshold=0.0)
    detections = detector._detections_from_result(FakeResult())
    tracker = TargetTracker(min_confidence=0.25)

    track = tracker.update(detections)

    assert track is not None
    assert track.target_id == 7
    assert track.label == "uav"
    assert track.center_x == 20
    assert track.center_y == 40
    assert track.width == 20
    assert track.height == 40


def test_tracker_returns_none_when_no_detection_is_confident() -> None:
    detector = make_detector(confidence_threshold=0.0)
    detections = detector._detections_from_result(FakeResult())
    tracker = TargetTracker(min_confidence=0.95)

    assert tracker.update(detections) is None

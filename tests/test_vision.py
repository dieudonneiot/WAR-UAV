from __future__ import annotations

from uav.vision.detector import Detection, TargetDetector
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
    orig_shape = (1200, 1920)


def make_detector(confidence_threshold: float = 0.25) -> TargetDetector:
    detector = TargetDetector.__new__(TargetDetector)
    detector.model = FakeModel()
    detector.confidence_threshold = confidence_threshold
    detector.iou_threshold = 0.45
    detector.image_size = None
    detector.target_class_ids = None
    detector.min_box_area_px = 0.0
    detector.max_box_area_ratio = 1.0
    detector.min_aspect_ratio = 0.05
    detector.max_aspect_ratio = 20.0
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
    assert track.is_confirmed


def test_tracker_returns_none_when_no_detection_is_confident() -> None:
    detector = make_detector(confidence_threshold=0.0)
    detections = detector._detections_from_result(FakeResult())
    tracker = TargetTracker(min_confidence=0.95)

    assert tracker.update(detections) is None


def test_detector_filters_implausible_geometry() -> None:
    detector = make_detector(confidence_threshold=0.0)
    detector.min_box_area_px = 4_000

    detections = detector._detections_from_result(FakeResult())

    assert detections == []


def test_tracker_smooths_same_target_motion() -> None:
    tracker = TargetTracker(min_confidence=0.25, smoothing_alpha=0.5)
    first_detection = _detection_at(100, 100, track_id=1)
    second_detection = _detection_at(140, 100, track_id=1)

    tracker.update([first_detection])
    track = tracker.update([second_detection])

    assert track is not None
    assert track.center_x == 120
    assert track.age == 2
    assert track.missed_frames == 0


def test_tracker_keeps_stale_track_briefly_when_detection_is_missing() -> None:
    tracker = TargetTracker(min_confidence=0.25, max_missed_frames=1)

    tracker.update([_detection_at(100, 100, track_id=1)])
    missed_track = tracker.update([])
    expired_track = tracker.update([])

    assert missed_track is not None
    assert missed_track.target_id == 1
    assert not missed_track.is_confirmed
    assert missed_track.missed_frames == 1
    assert expired_track is None


def test_tracker_prefers_active_target_over_higher_confidence_distraction() -> None:
    tracker = TargetTracker(min_confidence=0.25, smoothing_alpha=1.0)

    tracker.update([_detection_at(100, 100, track_id=7)])
    track = tracker.update(
        [
            _detection_at(104, 100, track_id=7, confidence=0.70),
            _detection_at(500, 500, track_id=8, confidence=0.99),
        ]
    )

    assert track is not None
    assert track.target_id == 7
    assert track.center_x == 104


def _detection_at(
    center_x: float,
    center_y: float,
    track_id: int,
    confidence: float = 0.9,
) -> Detection:
    return Detection(
        class_id=0,
        label="uav",
        confidence=confidence,
        x_min=center_x - 10,
        y_min=center_y - 10,
        x_max=center_x + 10,
        y_max=center_y + 10,
        track_id=track_id,
    )

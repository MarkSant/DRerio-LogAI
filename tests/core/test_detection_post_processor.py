"""Unit tests for ``zebtrack.core.detection.DetectionPostProcessor``.

All methods are stateless ``@staticmethod`` helpers, so these are fast, pure
tests. ``Settings`` / ``DetectorPlugin`` are duck-typed via ``getattr``/``hasattr``
in the production code, so they are stood in with ``SimpleNamespace`` — the real
classes are never imported here.

Golden IoU values are hand-computed in the test docstrings.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor as P


class TestValidateFrame:
    def test_valid_frame_passes(self):
        P.validate_frame(np.zeros((4, 5, 3), dtype=np.uint8))  # no raise

    def test_none_raises(self):
        with pytest.raises(ValueError, match="valid numpy array"):
            P.validate_frame(None)

    def test_non_ndarray_raises(self):
        with pytest.raises(ValueError, match="valid numpy array"):
            P.validate_frame([[1, 2, 3]])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            P.validate_frame(np.empty((0, 0, 3), dtype=np.uint8))

    def test_grayscale_2d_raises(self):
        with pytest.raises(ValueError, match="HxWx3"):
            P.validate_frame(np.zeros((4, 5), dtype=np.uint8))

    def test_wrong_channel_count_raises(self):
        with pytest.raises(ValueError, match="HxWx3"):
            P.validate_frame(np.zeros((4, 5, 4), dtype=np.uint8))


class TestEnsureTrackTuple:
    def test_five_element(self):
        out = P.ensure_track_tuple((1, 2, 3, 4, 0.9))
        assert out == (1.0, 2.0, 3.0, 4.0, 0.9, None, 0)

    def test_six_element(self):
        out = P.ensure_track_tuple((1, 2, 3, 4, 0.9, 7))
        assert out == (1.0, 2.0, 3.0, 4.0, 0.9, 7, 0)

    def test_seven_plus_element_slices_to_class_id(self):
        out = P.ensure_track_tuple((1, 2, 3, 4, 0.9, 7, 2, "extra"))
        assert out == (1.0, 2.0, 3.0, 4.0, 0.9, 7, 2)


class TestOffsetDetections:
    def test_offset_shifts_coords_and_maps_none_track_id(self):
        # 6-element tuple → track_id None → must become -1 after offset.
        out = P.offset_detections([(0, 0, 10, 10, 0.9, None)], dx=5, dy=5)
        assert out == [(5.0, 5.0, 15.0, 15.0, 0.9, -1, 0)]

    def test_empty_input(self):
        assert P.offset_detections([], 5, 5) == []

    def test_round_trip_offset(self):
        det = [(3, 4, 13, 14, 0.5, 1, 0)]
        once = P.offset_detections(det, 10, 20)
        back = P.offset_detections(once, -10, -20)
        assert back[0][:4] == (3.0, 4.0, 13.0, 14.0)


class TestCalculateIou:
    def test_identical_boxes(self):
        assert P.calculate_iou(0, 0, 10, 10, 0, 0, 10, 10) == pytest.approx(1.0)

    def test_disjoint_boxes(self):
        assert P.calculate_iou(0, 0, 10, 10, 20, 20, 30, 30) == 0.0

    def test_half_overlap_golden(self):
        # Two 10x10 boxes offset by (5, 5): intersection 5x5=25, union 175.
        assert P.calculate_iou(0, 0, 10, 10, 5, 5, 15, 15) == pytest.approx(25 / 175)

    def test_touching_edges_is_zero(self):
        # Share only an edge at x=10 → no area.
        assert P.calculate_iou(0, 0, 10, 10, 10, 0, 20, 10) == 0.0

    def test_symmetric(self):
        a = P.calculate_iou(0, 0, 10, 10, 5, 5, 15, 15)
        b = P.calculate_iou(5, 5, 15, 15, 0, 0, 10, 10)
        assert a == pytest.approx(b)


class TestApplyClassMismatchFallback:
    @staticmethod
    def _arena(side: int = 100) -> np.ndarray:
        return np.array([[0, 0], [side, 0], [side, side], [0, side]], dtype=np.int32)

    def test_small_aquarium_detection_reclassified_to_animal(self):
        # 10x10 det inside a 100x100 arena → area ratio 0.01 < 0.5 → becomes animal.
        dets = [(0, 0, 10, 10, 0.9, 1, 0)]
        out = P.apply_class_mismatch_fallback(dets, self._arena(), 0, 1)
        assert out[0][6] == 1  # class_id flipped to animal

    def test_large_aquarium_detection_unchanged(self):
        dets = [(0, 0, 90, 90, 0.9, 1, 0)]  # ratio 0.81 > 0.5
        out = P.apply_class_mismatch_fallback(dets, self._arena(), 0, 1)
        assert out[0][6] == 0

    def test_empty_polygon_returns_input(self):
        dets = [(0, 0, 10, 10, 0.9, 1, 0)]
        out = P.apply_class_mismatch_fallback(dets, np.array([]), 0, 1)
        assert out is dets

    def test_none_class_ids_returns_input(self):
        dets = [(0, 0, 10, 10, 0.9, 1, 0)]
        assert P.apply_class_mismatch_fallback(dets, self._arena(), None, 1) is dets
        assert P.apply_class_mismatch_fallback(dets, self._arena(), 0, None) is dets


class TestValidateTrackContinuity:
    def test_empty_does_not_raise(self):
        P.validate_track_continuity([])

    def test_all_none_track_ids_does_not_raise(self):
        P.validate_track_continuity([(0, 0, 1, 1, 0.9, None, 0)])

    def test_gap_does_not_raise(self):
        dets = [(0, 0, 1, 1, 0.9, 1, 0), (0, 0, 1, 1, 0.9, 3, 0)]  # missing id 2
        P.validate_track_continuity(dets)

    def test_duplicate_does_not_raise(self):
        dets = [(0, 0, 1, 1, 0.9, 1, 0), (0, 0, 1, 1, 0.9, 1, 0)]
        P.validate_track_continuity(dets)


class TestResolveClassIds:
    def test_two_class_model(self):
        plugin = SimpleNamespace(class_names={0: "aquarium", 1: "zebrafish"})
        assert P.resolve_class_ids(plugin) == (0, 1)

    def test_single_class_model_disables_aquarium(self):
        plugin = SimpleNamespace(class_names={0: "fish"})
        assert P.resolve_class_ids(plugin) == (-1, 0)

    def test_no_class_names_returns_defaults(self):
        assert P.resolve_class_ids(SimpleNamespace()) == (0, 1)


class TestSettingsGetters:
    def test_iou_threshold_default_and_value(self):
        assert P.get_iou_threshold(None) == pytest.approx(0.05)
        s = SimpleNamespace(bytetrack=SimpleNamespace(iou_threshold=0.3))
        assert P.get_iou_threshold(s) == pytest.approx(0.3)

    def test_max_center_distance_default_and_value(self):
        assert P.get_max_center_distance(None) == pytest.approx(400.0)
        s = SimpleNamespace(bytetrack=SimpleNamespace(max_center_distance=123.0))
        assert P.get_max_center_distance(s) == pytest.approx(123.0)

    def test_processing_interval_default_and_value(self):
        assert P.get_processing_interval(None) == 1
        s = SimpleNamespace(video_processing=SimpleNamespace(processing_interval=10))
        assert P.get_processing_interval(s) == 10

    def test_processing_interval_zero_falls_back_to_one(self):
        s = SimpleNamespace(video_processing=SimpleNamespace(processing_interval=0))
        assert P.get_processing_interval(s) == 1

    def test_fps_default_and_value(self):
        assert P.get_fps(None) == 30
        s = SimpleNamespace(video_processing=SimpleNamespace(fps=60))
        assert P.get_fps(s) == 60

    def test_should_use_bytetrack_default_and_value(self):
        assert P.should_use_bytetrack(None) is True
        s = SimpleNamespace(tracking=SimpleNamespace(use_bytetrack=False))
        assert P.should_use_bytetrack(s) is False

    def test_single_animal_mode_explicit_wins(self):
        assert P.get_single_animal_mode(None, explicit_mode=True) is True

    def test_single_animal_mode_from_settings(self):
        s = SimpleNamespace(video_processing=SimpleNamespace(single_animal_per_aquarium=True))
        assert P.get_single_animal_mode(s, explicit_mode=False) is True
        assert P.get_single_animal_mode(None, explicit_mode=False) is False

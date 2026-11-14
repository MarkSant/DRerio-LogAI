"""
Extended unit tests for DetectionPostProcessor stateless utilities.
"""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.detection.detection_post_processor import DetectionPostProcessor


class TestDetectionPostProcessorExtended:
    """Test DetectionPostProcessor validation, normalization, math, and fallbacks."""

    def test_validate_frame_success_and_errors(self):
        valid = np.zeros((100, 100, 3), dtype=np.uint8)
        DetectionPostProcessor.validate_frame(valid)  # Should not raise

        with pytest.raises(ValueError, match="valid numpy array"):
            DetectionPostProcessor.validate_frame(None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="cannot be empty"):
            DetectionPostProcessor.validate_frame(np.array([]))

        with pytest.raises(ValueError, match="HxWx3"):
            DetectionPostProcessor.validate_frame(np.zeros((100, 100), dtype=np.uint8))

    def test_ensure_track_tuple(self):
        # 5-element
        t5 = (10, 20, 30, 40, 0.85)
        res5 = DetectionPostProcessor.ensure_track_tuple(t5)
        assert res5 == (10.0, 20.0, 30.0, 40.0, 0.85, None, 0)

        # 6-element
        t6 = (10, 20, 30, 40, 0.85, 3)
        res6 = DetectionPostProcessor.ensure_track_tuple(t6)
        assert res6 == (10.0, 20.0, 30.0, 40.0, 0.85, 3, 0)

        # 7-element
        t7 = (10, 20, 30, 40, 0.85, 3, 1)
        res7 = DetectionPostProcessor.ensure_track_tuple(t7)
        assert res7 == (10.0, 20.0, 30.0, 40.0, 0.85, 3, 1)

    def test_offset_detections(self):
        raw = [(10, 10, 20, 20, 0.9, 1, 0)]
        offset = DetectionPostProcessor.offset_detections(raw, dx=50, dy=100)
        assert offset == [(60.0, 110.0, 70.0, 120.0, 0.9, 1, 0)]

    def test_calculate_iou(self):
        # Disjoint boxes
        assert DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 20, 20, 30, 30) == 0.0

        # Exact match 10x10
        iou_exact = DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 0, 0, 10, 10)
        assert iou_exact == pytest.approx(1.0)

        # 50% overlap: box A 0..10, box B 5..15 -> inter = 50, union = 150 -> 1/3
        iou = DetectionPostProcessor.calculate_iou(0, 0, 10, 10, 5, 0, 15, 10)
        assert iou == pytest.approx(50.0 / 150.0)

    def test_apply_class_mismatch_fallback(self):
        poly = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)  # Area 10,000

        # Small bbox (10x10 = 100 area, 1% of arena) misclassified as aquarium (class 1)
        # Should be reclassified to animal (class 0)
        dets = [(10, 10, 20, 20, 0.8, 1, 1)]
        corrected = DetectionPostProcessor.apply_class_mismatch_fallback(
            detections=dets,
            scaled_polygon=poly,
            aquarium_class_id=1,
            animal_class_id=0,
        )
        assert corrected[0][6] == 0  # Reclassified to class 0

        # Huge bbox (90x90 = 8100 area, 81% of arena) stays aquarium (class 1)
        dets_huge = [(5, 5, 95, 95, 0.8, 1, 1)]
        not_corrected = DetectionPostProcessor.apply_class_mismatch_fallback(
            detections=dets_huge,
            scaled_polygon=poly,
            aquarium_class_id=1,
            animal_class_id=0,
        )
        assert not_corrected[0][6] == 1


# ---------------------------------------------------------------------------
# Class-role helpers (ADR-009)
# ---------------------------------------------------------------------------


def _barnes_map():
    from zebtrack.core.detection.class_roles import resolve_class_role_map

    return resolve_class_role_map(
        {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"},
        weight_entry={
            "class_roles": {"arena": "arena", "experimenter": "context", "rat": "subject"}
        },
    )


class TestContextHelpers:
    _SQUARE = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.int32)

    @pytest.mark.parametrize("settings_obj", [None, object()])
    def test_context_settings_defaults(self, settings_obj):
        assert DetectionPostProcessor.context_settings(settings_obj) == (
            "arena_crop_margin",
            0.15,
            None,
        )

    def test_context_settings_reads_and_validates(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        good = SimpleNamespace(
            model_selection=SimpleNamespace(
                context_inference_scope="full_frame",
                context_crop_margin_frac=0.3,
                context_min_confidence=0.2,
            )
        )
        bad = SimpleNamespace(
            model_selection=SimpleNamespace(
                context_inference_scope="everywhere",
                context_crop_margin_frac=True,
                context_min_confidence=1.5,
            )
        )
        assert DetectionPostProcessor.context_settings(good) == ("full_frame", 0.3, 0.2)
        assert DetectionPostProcessor.context_settings(bad) == ("arena_crop_margin", 0.15, None)
        assert DetectionPostProcessor.context_settings(MagicMock()) == (
            "arena_crop_margin",
            0.15,
            None,
        )

    def test_margin_expands_per_axis_and_never_below_the_padding(self):
        box = DetectionPostProcessor.context_crop_box(
            self._SQUARE, (300, 400, 3), scope="arena_crop_margin", margin_frac=0.15
        )
        tiny = DetectionPostProcessor.context_crop_box(
            self._SQUARE, (300, 400, 3), scope="arena_crop_margin", margin_frac=0.01, padding=10
        )

        assert box == (85, 85, 216, 216)
        assert tiny == (90, 90, 211, 211)

    def test_arena_crop_keeps_the_box_and_full_frame_takes_all(self):
        arena = DetectionPostProcessor.context_crop_box(
            self._SQUARE, (300, 400, 3), scope="arena_crop", margin_frac=0.5
        )
        full = DetectionPostProcessor.context_crop_box(
            self._SQUARE, (300, 400, 3), scope="full_frame", margin_frac=0.5
        )

        assert arena == (100, 100, 201, 201)
        assert full == (0, 0, 400, 300)

    def test_crop_box_is_clamped_to_the_frame(self):
        edge = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
        box = DetectionPostProcessor.context_crop_box(
            edge, (120, 110, 3), scope="arena_crop_margin", margin_frac=0.5
        )
        assert box == (0, 0, 110, 120)

    def test_floors_use_the_lower_for_inference(self):
        assert DetectionPostProcessor.role_confidence_floors(0.5, 0.1) == (0.1, 0.5, 0.1)
        assert DetectionPostProcessor.role_confidence_floors(0.3, 0.6) == (0.3, 0.3, 0.6)
        assert DetectionPostProcessor.role_confidence_floors(0.4, None) == (0.4, 0.4, 0.4)

    def test_role_confidence_filter(self):
        detections = [
            (0, 0, 1, 1, 0.45, -1, 2),  # rat under the subject floor
            (0, 0, 1, 1, 0.55, -1, 2),  # rat over it
            (0, 0, 1, 1, 0.15, -1, 1),  # experimenter over the context floor
            (0, 0, 1, 1, 0.15, -1, 0),  # arena keeps the subject floor
        ]
        kept = DetectionPostProcessor.filter_by_role_confidence(
            detections, _barnes_map(), subject_floor=0.5, context_floor=0.1
        )
        assert [(d[4], d[6]) for d in kept] == [(0.55, 2), (0.15, 1)]

    def test_class_observations_keep_only_subject_and_context(self):
        detections = [
            (1, 2, 3, 4, 0.9, -1, 2),
            (5, 6, 7, 8, 0.8, -1, 1),
            (0, 0, 9, 9, 0.7, -1, 0),
            (0, 0, 9, 9, 0.6, -1, 3),
        ]
        observed = DetectionPostProcessor.class_observations(
            detections, _barnes_map(), aquarium_id=1
        )
        assert observed == [
            {
                "class_id": 2,
                "class_name": "rat",
                "role": "subject",
                "bbox": (1.0, 2.0, 3.0, 4.0),
                "confidence": 0.9,
                "aquarium_id": 1,
            },
            {
                "class_id": 1,
                "class_name": "experimenter",
                "role": "context",
                "bbox": (5.0, 6.0, 7.0, 8.0),
                "confidence": 0.8,
                "aquarium_id": 1,
            },
        ]

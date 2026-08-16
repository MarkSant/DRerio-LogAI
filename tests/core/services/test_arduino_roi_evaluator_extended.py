"""
Extended unit tests for ArduinoRoiEvaluator.
"""

from __future__ import annotations

from zebtrack.core.services.arduino_roi_evaluator import ArduinoRoiEvaluator
from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig


class TestArduinoRoiEvaluatorExtended:
    """Test ArduinoRoiEvaluator geometry evaluation branches."""

    def test_effective_rule_fallback_from_seg_overlap(self):
        cfg = RoiRuleConfig(rule="seg_overlap")
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        evaluator = ArduinoRoiEvaluator(
            roi_names=["Zone1"],
            roi_polygons=[poly],
            rule_config=cfg,
        )
        assert evaluator.rule == "centroid_in"
        assert evaluator.roi_names == ["Zone1"]
        assert evaluator.has_rois() is True

    def test_degenerate_polygon_skipped(self):
        evaluator = ArduinoRoiEvaluator(
            roi_names=["Valid", "Degenerate"],
            roi_polygons=[
                [[0.0, 0.0], [50.0, 0.0], [50.0, 50.0], [0.0, 50.0]],
                [[0.0, 0.0], [1.0, 1.0]],  # < 3 coords
            ],
        )
        assert len(evaluator._rois) == 1
        assert evaluator.roi_names == ["Valid"]

    def test_buffered_rule_expands_geometry(self):
        cfg = RoiRuleConfig(rule="centroid_in_on_buffered_roi", buffer_radius_value=5.0)
        poly = [[10.0, 10.0], [20.0, 10.0], [20.0, 20.0], [10.0, 20.0]]
        evaluator = ArduinoRoiEvaluator(
            roi_names=["Zone1"],
            roi_polygons=[poly],
            rule_config=cfg,
            px_per_cm=2.0,  # 5 cm * 2 = 10 px buffer
        )
        # Point at (5, 15) is outside unbuffered (10-20), but inside buffered
        occupied = evaluator.occupied_rois([(5.0, 15.0)])
        assert occupied == {"Zone1"}

    def test_bbox_intersects_evaluation_bases(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]  # Area = 10,000

        # Basis 'bbox'
        cfg_bbox = RoiRuleConfig(
            rule="bbox_intersects",
            min_bbox_overlap_ratio=0.5,
            bbox_overlap_basis="bbox",
        )
        evaluator_bbox = ArduinoRoiEvaluator(["Zone1"], [poly], rule_config=cfg_bbox)

        # Bbox of size 10x10 = 100 area. Half inside (50) -> ratio = 50 / 100 = 0.5 -> occupied
        # Bbox from x: 95 to 105, y: 0 to 10
        bboxes = [[95.0, 0.0, 105.0, 10.0]]
        occupied = evaluator_bbox.occupied_rois(bboxes)
        assert occupied == {"Zone1"}

        # Basis 'roi': 50 / 10000 = 0.005 < 0.5 -> not occupied
        cfg_roi = RoiRuleConfig(
            rule="bbox_intersects",
            min_bbox_overlap_ratio=0.5,
            bbox_overlap_basis="roi",
        )
        evaluator_roi = ArduinoRoiEvaluator(["Zone1"], [poly], rule_config=cfg_roi)
        occupied_roi = evaluator_roi.occupied_rois(bboxes)
        assert occupied_roi == set()

    def test_overlap_any_rule(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        cfg_any = RoiRuleConfig(
            rule="bbox_intersects",
            min_bbox_overlap_ratio=0.0,
            bbox_overlap_basis="bbox",
        )
        evaluator_any = ArduinoRoiEvaluator(["Zone1"], [poly], rule_config=cfg_any)
        # Any overlap (1 px overlap)
        bboxes = [[99.0, 0.0, 105.0, 10.0]]
        occupied = evaluator_any.occupied_rois(bboxes)
        assert occupied == {"Zone1"}

    def test_missing_bbox_fallback_to_centroid(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        cfg = RoiRuleConfig(rule="bbox_intersects", min_bbox_overlap_ratio=0.2)
        evaluator = ArduinoRoiEvaluator(["Zone1"], [poly], rule_config=cfg)

        # Passing 2D point (cx, cy) falls back to centroid containment
        occupied = evaluator.occupied_rois([(50.0, 50.0)])
        assert occupied == {"Zone1"}

    def test_empty_rois_returns_empty_set(self):
        evaluator = ArduinoRoiEvaluator([], [])
        assert evaluator.has_rois() is False
        assert evaluator.occupied_rois([(10.0, 10.0)]) == set()

    def test_centroid_of_bbox(self):
        assert ArduinoRoiEvaluator.centroid_of_bbox(0.0, 0.0, 10.0, 20.0) == (5.0, 10.0)

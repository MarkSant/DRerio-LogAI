"""Extended unit tests for core/services/weight_manager.py."""

from __future__ import annotations

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended4:
    """Test WeightManager classification patterns for weight types and camera perspectives."""

    def test_classify_weight_type_perspective_aware(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_weight_type("best_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("best_seg_topdown.pt") == "seg"
        assert wm._classify_weight_type("best_det_lateral.pt") == "det"
        assert wm._classify_weight_type("best_det_topdown.pt") == "det"

    def test_classify_weight_type_legacy(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("unknown_model.pt") is None

    def test_classify_perspective(self):
        wm = object.__new__(WeightManager)

        assert wm._classify_perspective("best_seg_lateral.pt") == "lateral"
        assert wm._classify_perspective("best_det_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_weights.pt") is None

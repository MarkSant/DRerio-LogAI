"""Extended unit tests for core/services/weight_manager.py (Part 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended7:
    """Test WeightManager weight addition security checks, classification, and error handling."""

    def test_add_weight_not_found(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        missing_path = tmp_path / "missing_model.pt"

        with pytest.raises(FileNotFoundError, match="model file was not found"):
            wm.add_weight(missing_path, set_as_default=False)

    def test_add_weight_already_registered(self, tmp_path: Path):
        weights_dir = tmp_path / "weights"
        weights_dir.mkdir()
        model_file = weights_dir / "existing.pt"
        model_file.touch()

        wm = WeightManager(settings_obj=None, config_dir=tmp_path, weights_dir=weights_dir)
        wm.weights["existing.pt"] = {"type": "det", "path": str(model_file)}

        with pytest.raises(ValueError, match="already exists"):
            wm.add_weight(model_file, set_as_default=False)

    def test_classify_weight_type_heuristics(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        assert wm._classify_weight_type("best_seg.pt") == "seg"
        assert wm._classify_weight_type("model_seg_lateral.pt") == "seg"
        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("best_det.pt") == "det"
        assert wm._classify_weight_type("model_det_topdown.pt") == "det"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("random_model.pt") is None

    def test_classify_perspective_heuristics(self, tmp_path: Path):
        wm = WeightManager(settings_obj=None, config_dir=tmp_path)
        assert wm._classify_perspective("model_seg_lateral.pt") == "lateral"
        assert wm._classify_perspective("model_det_topdown.pt") == "top_down"
        assert wm._classify_perspective("generic_model.pt") is None

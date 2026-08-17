"""Extended unit tests for ui/wizard/model_selection_step.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep


class TestModelSelectionStepExtended4:
    """Test ModelSelectionStep active perspective extraction and weight catalog loading."""

    def test_get_active_perspective_top_level(self):
        step = object.__new__(ModelSelectionStep)
        step.wizard_data = {"behavioral_analysis": {"aquarium_perspective": "top_down"}}
        assert step._get_active_perspective() == "top_down"

    def test_get_active_perspective_nested(self):
        step = object.__new__(ModelSelectionStep)
        step.wizard_data = {
            "calibration": {"behavioral_analysis": {"aquarium_perspective": "lateral"}}
        }
        assert step._get_active_perspective() == "lateral"

    def test_get_active_perspective_none(self):
        step = object.__new__(ModelSelectionStep)
        step.wizard_data = {}
        assert step._get_active_perspective() is None

    def test_load_weight_catalog(self):
        step = object.__new__(ModelSelectionStep)
        step.seg_weight_names = []
        step.det_weight_names = []
        step.weight_manager = MagicMock()
        step.weight_manager.get_all_weights.return_value = ["model_seg.pt", "model_det.pt"]
        step.weight_manager.get_weight_details.side_effect = lambda name: (
            {"type": "seg"} if "seg" in name else {"type": "det"}
        )

        step._load_weight_catalog()
        assert step.seg_weight_names == ["model_seg.pt"]
        assert step.det_weight_names == ["model_det.pt"]

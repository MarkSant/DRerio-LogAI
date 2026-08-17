"""Extended unit tests for ui/wizard/model_selection_step.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.model_selection_step import (
    DEFAULT_IOU_THRESHOLD,
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_MAX_CENTER_DISTANCE,
    DEFAULT_TRACK_BUFFER,
    DEFAULT_TRACK_THRESHOLD,
    ModelSelectionStep,
    _method_options,
    _recommended_suffix,
)


class TestModelSelectionStepExtended2:
    """Test ModelSelectionStep constants, labels, method display, and ByteTrack recommendation."""

    def test_bytetrack_default_constants(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.95
        assert DEFAULT_TRACK_BUFFER == 150
        assert DEFAULT_MAX_CENTER_DISTANCE == 200.0
        assert DEFAULT_IOU_THRESHOLD == 0.1

    def test_method_options_and_recommended_suffix(self):
        opts = _method_options()
        assert "seg" in opts
        assert "det" in opts
        assert "Segmentation" in opts["seg"]

        suffix = _recommended_suffix()
        assert "⭐" in suffix
        assert "Recommended" in suffix

    def test_step_id_and_initialization(self):
        step = object.__new__(ModelSelectionStep)
        step.step_id = WizardStepID.MODEL_SELECTION
        assert step.step_id == WizardStepID.MODEL_SELECTION

    def test_method_display(self):
        step = object.__new__(ModelSelectionStep)
        res_seg = step._method_display("seg")
        assert "Segmentation" in res_seg

        res_det = step._method_display("det")
        assert "Detection" in res_det

        res_unknown = step._method_display("custom_method")
        assert res_unknown == "custom_method"

    def test_recommended_use_bytetrack(self):
        step = object.__new__(ModelSelectionStep)
        step.settings = None
        step.wizard_data = {"animals_per_aquarium": 1}

        # Single animal + det -> False
        step._method_key_from_label = MagicMock(return_value="det")  # type: ignore[method-assign]
        assert step._recommended_use_bytetrack("Detection (det)") is False

        # Multi animal + det -> True
        step.wizard_data = {"animals_per_aquarium": 2}
        assert step._recommended_use_bytetrack("Detection (det)") is True

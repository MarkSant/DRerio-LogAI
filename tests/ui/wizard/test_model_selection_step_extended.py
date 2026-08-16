"""Extended unit tests for ui/wizard/model_selection_step.py."""

from __future__ import annotations

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


class TestModelSelectionStepExtended:
    """Test ModelSelectionStep constants, options mappings, and helper functions."""

    def test_default_constants(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.95
        assert DEFAULT_TRACK_BUFFER == 150
        assert DEFAULT_MAX_CENTER_DISTANCE == 200.0
        assert DEFAULT_IOU_THRESHOLD == 0.1

    def test_method_options(self):
        options = _method_options()
        assert "seg" in options
        assert "det" in options
        assert "Segmentation" in options["seg"]
        assert "Detection" in options["det"]

    def test_recommended_suffix(self):
        suffix = _recommended_suffix()
        assert "Recommended" in suffix

    def test_method_key_from_label(self):
        step = object.__new__(ModelSelectionStep)
        options = _method_options()

        assert step._method_key_from_label(options["seg"]) == "seg"
        assert step._method_key_from_label(options["det"]) == "det"
        assert step._method_key_from_label("seg") == "seg"
        assert step._method_key_from_label("det") == "det"
        assert step._method_key_from_label("") == "seg"

    def test_normalize_openvino_device(self):
        step = object.__new__(ModelSelectionStep)
        assert step._normalize_openvino_device("auto") == "AUTO"
        assert step._normalize_openvino_device(None) == "AUTO"
        assert step._normalize_openvino_device("INVALID_DEV") == "AUTO"

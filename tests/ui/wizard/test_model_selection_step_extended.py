"""Extended unit tests for ui/wizard/model_selection_step.py."""

from __future__ import annotations

from unittest.mock import MagicMock

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


class TestModelSelectionStepExtended2:
    def test_method_options_and_recommended_suffix(self):
        opts = _method_options()
        assert "seg" in opts
        assert "det" in opts
        assert "Segmentation" in opts["seg"]

        suffix = _recommended_suffix()
        assert "⭐" in suffix
        assert "Recommended" in suffix

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


class TestModelSelectionStepExtended3:
    def test_method_options(self):
        opts = _method_options()
        assert "seg" in opts
        assert "det" in opts
        assert "Segmentation" in opts["seg"] or "seg" in opts["seg"]
        assert "Detection" in opts["det"] or "det" in opts["det"]

    def test_recommended_suffix(self):
        suffix = _recommended_suffix()
        assert "⭐" in suffix or "Recommended" in suffix

    def test_bytetrack_types(self):
        assert isinstance(DEFAULT_TRACK_THRESHOLD, float)
        assert isinstance(DEFAULT_MATCH_THRESHOLD, float)
        assert isinstance(DEFAULT_TRACK_BUFFER, int)
        assert isinstance(DEFAULT_MAX_CENTER_DISTANCE, float)


class TestModelSelectionStepExtended4:
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

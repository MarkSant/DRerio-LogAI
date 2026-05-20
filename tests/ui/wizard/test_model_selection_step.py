"""
Tests for wizard Model Selection Step.

Validates:
- Model selection step UI creation
- Weight loading and catalog management
- Method selection (seg vs det)
- Threshold validation (confidence, NMS, track, match)
- OpenVINO backend selection
- Weight path validation
- Threshold restoration to defaults
- Data extraction

==============================================================================
GUI TEST EXECUTION REQUIREMENTS
==============================================================================

CRITICAL: These tests MUST be run with serial execution (-n0).

Correct usage:
  ✅ poetry run pytest -m gui -n0
  ✅ poetry run pytest tests/ui/wizard/ -n0

==============================================================================
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep


@pytest.mark.gui
class TestModelSelectionStep:
    """Tests for model selection step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root and mock WeightManager for testing."""
        self.root = wizard_dependencies["root"]

    @pytest.fixture
    def mock_weight_manager(self):
        """Mock WeightManager for testing."""
        with patch("zebtrack.ui.wizard.model_selection_step.WeightManager") as mock_wm:
            mock_instance = MagicMock()

            # Mock weight catalog
            mock_instance.get_all_weights.return_value = [
                "yolov8n-seg.pt",
                "yolov8s-seg.pt",
                "yolov8n.pt",
                "yolov8s.pt",
            ]

            def get_weight_details(name):
                if "-seg" in name:
                    return {"type": "seg", "path": f"/weights/{name}"}
                return {"type": "det", "path": f"/weights/{name}"}

            mock_instance.get_weight_details.side_effect = get_weight_details
            mock_instance.get_default_seg_weight.return_value = (
                "yolov8n-seg.pt",
                "/weights/yolov8n-seg.pt",
            )
            mock_instance.get_default_det_weight.return_value = (
                "yolov8n.pt",
                "/weights/yolov8n.pt",
            )
            # No perspective metadata in the default catalog — return
            # (None, None) so callers fall through to the type-based default.
            # Individual tests override this when they need perspective-aware
            # behaviour.
            mock_instance.get_weight_by_perspective_and_type.return_value = (None, None)

            mock_wm.return_value = mock_instance
            yield mock_instance

    def test_model_selection_step_builds_ui_without_error(self, mock_weight_manager):
        """Model selection step should build UI without errors."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.MODEL_SELECTION

    def test_model_selection_step_loads_weights_catalog(self, mock_weight_manager):
        """Step should load and categorize weights on initialization."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)

        # Should have loaded seg and det weights
        assert len(step.seg_weight_names) == 2  # yolov8n-seg.pt, yolov8s-seg.pt
        assert len(step.det_weight_names) == 2  # yolov8n.pt, yolov8s.pt

        assert "yolov8n-seg.pt" in step.seg_weight_names
        assert "yolov8n.pt" in step.det_weight_names

    def test_model_selection_step_default_values(self, mock_weight_manager):
        """Step should have sensible default values."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Default methods should be seg
        assert "seg" in step.aquarium_method_var.get().lower()
        assert "seg" in step.animal_method_var.get().lower()

        # Default thresholds
        confidence = float(step.confidence_var.get())
        nms = float(step.nms_var.get())
        track = float(step.track_var.get())
        match = float(step.match_var.get())

        assert 0.0 < confidence < 1.0
        assert 0.0 < nms < 1.0
        assert 0.0 < track < 1.0
        assert 0.0 < match < 1.0

    def test_validation_succeeds_with_valid_thresholds(self, mock_weight_manager):
        """Validation should succeed with valid threshold values."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        step.confidence_var.set("0.30")
        step.nms_var.set("0.50")
        step.track_var.set("0.25")
        step.match_var.set("0.15")

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

    def test_validation_fails_with_invalid_confidence_format(self, mock_weight_manager):
        """Validation should fail with non-numeric confidence."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        step.confidence_var.set("not_a_number")
        step.nms_var.set("0.45")
        step.track_var.set("0.25")
        step.match_var.set("0.15")

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "decimais" in error_message.lower() or "valor" in error_message.lower()

    def test_validation_fails_with_threshold_out_of_range(self, mock_weight_manager):
        """Validation should fail when threshold is outside (0, 1) range."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Test confidence > 1
        step.confidence_var.set("1.5")
        step.nms_var.set("0.45")
        step.track_var.set("0.25")
        step.match_var.set("0.15")

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "entre 0 e 1" in error_message.lower()

    def test_validation_fails_with_threshold_at_boundary(self, mock_weight_manager):
        """Validation should fail with threshold exactly at 0 or 1."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Test confidence = 0.0 (should be exclusive)
        step.confidence_var.set("0.0")
        step.nms_var.set("0.45")
        step.track_var.set("0.25")
        step.match_var.set("0.15")

        is_valid, _ = step.validate()

        assert not is_valid

    def test_get_data_returns_complete_configuration(self, mock_weight_manager):
        """get_data should return complete model configuration."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        step.confidence_var.set("0.35")
        step.nms_var.set("0.50")
        step.track_var.set("0.28")
        step.match_var.set("0.18")
        step.use_openvino_var.set(True)

        data = step.get_data()

        assert "aquarium_method" in data
        assert "animal_method" in data
        assert "use_openvino" in data
        assert "weight_assignments" in data
        assert "detector_parameters" in data

        assert data["use_openvino"] is True

        params = data["detector_parameters"]
        assert params["confidence_threshold"] == 0.35
        assert params["nms_threshold"] == 0.50
        assert params["track_threshold"] == 0.28
        assert params["match_threshold"] == 0.18

    def test_set_data_restores_ui_state(self, mock_weight_manager):
        """set_data should restore UI from previously collected data."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "aquarium_method": "det",
            "animal_method": "seg",
            "use_openvino": True,
            "weight_assignments": {
                "aquarium": "yolov8n.pt",
                "animal": "yolov8n-seg.pt",
            },
            "detector_parameters": {
                "confidence_threshold": 0.40,
                "nms_threshold": 0.55,
                "track_threshold": 0.30,
                "match_threshold": 0.20,
            },
        }

        step.set_data(previous_data)

        # Verify state restored
        assert step.use_openvino_var.get() is True
        assert float(step.confidence_var.get()) == 0.40
        assert float(step.nms_var.get()) == 0.55
        assert float(step.track_var.get()) == 0.30
        assert float(step.match_var.get()) == 0.20

    def test_restore_default_thresholds_button(self, mock_weight_manager):
        """Restore defaults button should reset all thresholds."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Modify thresholds
        step.confidence_var.set("0.80")
        step.nms_var.set("0.90")
        step.track_var.set("0.70")
        step.match_var.set("0.60")

        # Restore defaults
        step._restore_default_thresholds()

        # Should be back to defaults
        # Default values: confidence 0.25, nms 0.45, track 0.25, match 0.15
        assert float(step.confidence_var.get()) == 0.25
        assert float(step.nms_var.get()) == 0.45
        assert float(step.track_var.get()) == 0.25
        assert float(step.match_var.get()) == 0.95

    def test_weight_dropdown_updates_on_method_change(self, mock_weight_manager):
        """Weight dropdown should update when method changes."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Initially should have seg weights
        initial_animal_weight = step.animal_weight_var.get()
        assert "-seg" in initial_animal_weight or initial_animal_weight == "yolov8n-seg.pt"

        # Change to det method
        step.animal_method_var.set("Detecção (det)")
        step._on_animal_method_change()

        # Should now have a det weight
        new_animal_weight = step.animal_weight_var.get()
        # Should be a det weight (no -seg suffix)
        assert "-seg" not in new_animal_weight or new_animal_weight in step.det_weight_names

    def test_validation_fails_with_mismatched_weight(self, mock_weight_manager):
        """Validation should fail if selected weight doesn't match method type."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Force invalid state: seg method with det weight
        step.aquarium_method_var.set("Segmentação (seg)")
        step.aquarium_weight_var.set("invalid_weight_not_in_catalog.pt")

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "peso válido" in error_message.lower()

    def test_animal_method_hint_for_multiple_animals(self, mock_weight_manager):
        """Hint should appear when using det method with multiple animals."""
        wizard_data = {
            "animals_per_aquarium": 5,
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Set to det method
        step.animal_method_var.set("Detecção (det)")
        step._update_animal_method_hint()

        hint = step.animal_method_hint_var.get()

        # Should show warning about det with multiple animals
        assert "⚠️" in hint or "det" in hint.lower()
        assert "múltiplos animais" in hint.lower() or "1 animal" in hint.lower()

    def test_animal_method_hint_cleared_for_seg(self, mock_weight_manager):
        """Hint should be cleared when using seg method."""
        wizard_data = {
            "animals_per_aquarium": 5,
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Set to seg method
        step.animal_method_var.set("Segmentação (seg)")
        step._update_animal_method_hint()

        hint = step.animal_method_hint_var.get()

        # Should be empty or not show warning
        assert hint == "" or "⚠️" not in hint

    def test_bytetrack_default_disabled_for_single_animal_detection(self, mock_weight_manager):
        """ByteTrack should default to disabled for 1 animal + detection mode."""
        wizard_data = {
            "animals_per_aquarium": 1,
            "model_selection": {
                "animal_method": "det",
            },
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        assert step.use_bytetrack_var.get() is False

    def test_bytetrack_default_kept_enabled_for_single_animal_segmentation(
        self, mock_weight_manager
    ):
        """ByteTrack default should stay enabled when animal method is segmentation."""
        wizard_data = {
            "animals_per_aquarium": 1,
            "model_selection": {
                "animal_method": "seg",
            },
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        assert step.use_bytetrack_var.get() is True

    @pytest.mark.parametrize(
        "confidence,nms,track,match,expected_valid",
        [
            ("0.25", "0.45", "0.25", "0.95", True),  # Defaults
            ("0.001", "0.001", "0.001", "0.001", True),  # Very low but valid
            ("0.999", "0.999", "0.999", "0.999", True),  # Very high but valid
            ("0.5", "0.5", "0.5", "0.5", True),  # Mid-range
            ("0.0", "0.45", "0.25", "0.15", False),  # Confidence at boundary
            ("0.25", "1.0", "0.25", "0.15", False),  # NMS at boundary
            ("0.25", "0.45", "-0.1", "0.15", False),  # Negative track
            ("0.25", "0.45", "0.25", "1.5", False),  # Match > 1
        ],
    )
    def test_threshold_validation_boundaries(
        self, mock_weight_manager, confidence, nms, track, match, expected_valid
    ):
        """Test threshold validation with various boundary conditions."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        step.confidence_var.set(confidence)
        step.nms_var.set(nms)
        step.track_var.set(track)
        step.match_var.set(match)

        is_valid, _ = step.validate()

        assert is_valid == expected_valid

    # ------------------------------------------------------------------
    # _get_active_perspective — bug fix for top-down recommendation flow
    # ------------------------------------------------------------------

    def test_get_active_perspective_reads_flat_behavioral_analysis(self, mock_weight_manager):
        """Wizard merges step data flat into wizard_data, so behavioral_analysis
        lives at the top level — not nested under a 'calibration' key.
        """
        wizard_data: dict[str, Any] = {
            "behavioral_analysis": {"aquarium_perspective": "top_down"},
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)

        assert step._get_active_perspective() == "top_down"

    def test_get_active_perspective_falls_back_to_nested_layout(self, mock_weight_manager):
        """When wizard_data was hydrated from project_data, the nested
        calibration/behavioral_analysis form is still honored."""
        wizard_data: dict[str, Any] = {
            "calibration": {
                "behavioral_analysis": {"aquarium_perspective": "lateral"},
            },
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)

        assert step._get_active_perspective() == "lateral"

    def test_get_active_perspective_returns_none_when_unset(self, mock_weight_manager):
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        assert step._get_active_perspective() is None

    def test_get_active_perspective_normalizes_enum_style_value(self, mock_weight_manager):
        wizard_data: dict[str, Any] = {
            "behavioral_analysis": {"aquarium_perspective": "AquariumPerspective.TOP_DOWN"},
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        assert step._get_active_perspective() == "top_down"

    def test_top_down_perspective_drives_recommended_weight(self, mock_weight_manager):
        """When perspective=top_down is set in wizard_data, the dropdown
        recommendation must use the top-down weight, not the lateral one."""
        # Catalog: two seg weights, one tagged top_down and one lateral.
        mock_weight_manager.get_all_weights.return_value = [
            "yolov8n-seg-top.pt",
            "yolov8n-seg-side.pt",
        ]

        def weight_details(name):
            if name == "yolov8n-seg-top.pt":
                return {"type": "seg", "perspective": "top_down", "path": "/w/top.pt"}
            return {"type": "seg", "perspective": "lateral", "path": "/w/side.pt"}

        mock_weight_manager.get_weight_details.side_effect = weight_details

        def by_perspective(perspective, weight_type):
            for name in mock_weight_manager.get_all_weights.return_value:
                details = weight_details(name)
                if details["type"] == weight_type and details["perspective"] == perspective:
                    return name, details
            return None, None

        mock_weight_manager.get_weight_by_perspective_and_type.side_effect = by_perspective

        wizard_data: dict[str, Any] = {
            "behavioral_analysis": {"aquarium_perspective": "top_down"},
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)

        # Without the fix this returns the lateral default because the
        # perspective lookup silently fails.
        assert step._default_weight_for_method("seg") == "yolov8n-seg-top.pt"

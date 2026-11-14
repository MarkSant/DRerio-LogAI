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

from zebtrack.core.detection.class_roles import ClassRole
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
        assert "decimal values" in error_message.lower()

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
        assert "between 0 and 1" in error_message.lower()

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

    def test_new_project_prefills_bytetrack_from_the_configured_settings(self, mock_weight_manager):
        """#698: a new project starts from what config.yaml / config.local.yaml say.

        The wizard used to prefill its own 200 px / 0.1, and the project saved them,
        overriding the 400 / 0.05 the shipped configuration declares.
        """
        from zebtrack.settings import load_settings

        settings_obj = load_settings()
        settings_obj.bytetrack.track_threshold = 0.3
        settings_obj.bytetrack.match_threshold = 0.85
        settings_obj.bytetrack.track_buffer = 210
        settings_obj.bytetrack.max_center_distance = 333.0
        settings_obj.bytetrack.iou_threshold = 0.07
        step = ModelSelectionStep(self.root, {}, settings_obj=settings_obj)
        step.build_ui()

        assert float(step.track_var.get()) == pytest.approx(0.3)
        assert float(step.match_var.get()) == pytest.approx(0.85)
        assert int(step.track_buffer_var.get()) == 210
        assert float(step.max_center_dist_var.get()) == pytest.approx(333.0)
        assert float(step.iou_thresh_var.get()) == pytest.approx(0.07)

    def test_without_settings_the_prefill_is_the_shared_default(self, mock_weight_manager):
        from zebtrack.settings import (
            DEFAULT_IOU_THRESHOLD,
            DEFAULT_MATCH_THRESHOLD,
            DEFAULT_MAX_CENTER_DISTANCE,
            DEFAULT_TRACK_THRESHOLD,
        )

        step = ModelSelectionStep(self.root, {}, settings_obj=None)
        step.build_ui()

        assert float(step.track_var.get()) == pytest.approx(DEFAULT_TRACK_THRESHOLD)
        assert float(step.match_var.get()) == pytest.approx(DEFAULT_MATCH_THRESHOLD)
        assert float(step.max_center_dist_var.get()) == pytest.approx(DEFAULT_MAX_CENTER_DISTANCE)
        assert float(step.iou_thresh_var.get()) == pytest.approx(DEFAULT_IOU_THRESHOLD)

    def test_saved_project_values_still_win_over_the_settings(self, mock_weight_manager):
        from zebtrack.settings import load_settings

        settings_obj = load_settings()
        settings_obj.bytetrack.max_center_distance = 333.0
        wizard_data: dict[str, Any] = {"detector_parameters": {"max_center_distance": 120.0}}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=settings_obj)
        step.build_ui()

        assert float(step.max_center_dist_var.get()) == pytest.approx(120.0)

    def test_weight_dropdown_updates_on_method_change(self, mock_weight_manager):
        """Weight dropdown should update when method changes."""
        wizard_data: dict[str, Any] = {}
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Initially should have seg weights
        initial_animal_weight = step.animal_weight_var.get()
        assert "-seg" in initial_animal_weight or initial_animal_weight == "yolov8n-seg.pt"

        # Change to det method
        step.animal_method_var.set(step._method_display("det"))
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
        step.aquarium_method_var.set(step._method_display("seg"))
        step.aquarium_weight_var.set("invalid_weight_not_in_catalog.pt")

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "valid weight" in error_message.lower()

    def test_animal_method_hint_for_multiple_animals(self, mock_weight_manager):
        """Hint should appear when using det method with multiple animals."""
        wizard_data = {
            "animals_per_aquarium": 5,
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Set to det method
        step.animal_method_var.set(step._method_display("det"))
        step._update_animal_method_hint()

        hint = step.animal_method_hint_var.get()

        # Should show warning about det with multiple animals
        assert "⚠️" in hint or "det" in hint.lower()
        assert "several animals" in hint.lower() or "1 animal" in hint.lower()

    def test_animal_method_hint_cleared_for_seg(self, mock_weight_manager):
        """Hint should be cleared when using seg method."""
        wizard_data = {
            "animals_per_aquarium": 5,
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None)
        step.build_ui()

        # Set to seg method
        step.animal_method_var.set(step._method_display("seg"))
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


@pytest.mark.gui
class TestBytetrackFieldsAreValidated:
    """``track_buffer``, ``max_center_distance`` e ``iou_threshold``.

    Os três são ``Entry`` editáveis, eram lidos por ``get_data()`` e por nenhum
    validador. Consequências, da mais barulhenta para a mais cara:

    * texto → ``get_data()`` estoura fora de qualquer ``try`` no
      ``WizardDialog._on_next``, virando um diálogo genérico que não diz qual
      campo está errado;
    * valor fora de faixa → passa, e o ``DetectorService`` o recusa lá adiante
      dentro de um ``except Exception`` que só faz ``log.warning``. Como os
      parâmetros são aplicados em bloco, UM valor inválido descarta TODOS os
      overrides do projeto em silêncio.
    """

    @pytest.fixture
    def step(self, tkinter_root):
        from zebtrack.settings import load_settings

        instance = ModelSelectionStep(tkinter_root, {}, settings_obj=load_settings())
        instance.build_ui()
        return instance

    def test_text_in_track_buffer_is_rejected_before_get_data(self, step):
        step.track_buffer_var.set("abc")

        valid, msg = step.validate()

        assert valid is False
        assert msg, "a mensagem precisa nomear o campo, não sair vazia"

    def test_zero_track_buffer_is_rejected(self, step):
        step.track_buffer_var.set("0")
        assert step.validate()[0] is False

    def test_negative_max_distance_is_rejected(self, step):
        """-50 px atravessava inteiro e degradava o casamento por distância."""
        step.max_center_dist_var.set("-50")
        assert step.validate()[0] is False

    def test_zero_max_distance_is_rejected(self, step):
        step.max_center_dist_var.set("0")
        assert step.validate()[0] is False

    def test_iou_above_one_is_rejected(self, step):
        """O rótulo do campo diz "0-1"; 5 era aceito e propagado."""
        step.iou_thresh_var.set("5")
        assert step.validate()[0] is False

    def test_iou_negative_is_rejected(self, step):
        step.iou_thresh_var.set("-0.1")
        assert step.validate()[0] is False

    def test_iou_accepts_the_inclusive_bounds(self, step):
        """0 e 1 são válidos para IoU — a faixa do DetectorService é fechada."""
        for value in ("0", "1", "0.05"):
            step.iou_thresh_var.set(value)
            assert step.validate()[0] is True, f"IoU {value} deveria passar"

    def test_valid_values_still_pass_and_reach_get_data(self, step):
        step.track_buffer_var.set("120")
        step.max_center_dist_var.set("350.5")
        step.iou_thresh_var.set("0.2")

        assert step.validate()[0] is True

        params = step.get_data()["detector_parameters"]
        assert params["track_buffer"] == 120
        assert params["max_center_distance"] == 350.5
        assert params["iou_threshold"] == 0.2

    def test_get_data_never_runs_on_values_validate_rejected(self, step):
        """Contrato do ``_on_next``: ``get_data()`` só roda após validate() True.

        Amarra os dois: se alguém acrescentar um campo ao ``get_data()`` sem
        acrescentá-lo ao ``validate()``, este teste falha em vez de o assistente
        estourar na cara do usuário.
        """
        for var, bad in (
            (step.track_buffer_var, "x"),
            (step.max_center_dist_var, "x"),
            (step.iou_thresh_var, "x"),
            (step.confidence_var, "x"),
        ):
            original = var.get()
            var.set(bad)
            assert step.validate()[0] is False, f"valor {bad!r} passou pelo validate()"
            var.set(original)


BARNES_NAMES = {0: "arena", 1: "experimenter", 2: "rat", 3: "start_box"}


@pytest.mark.gui
class TestModelSelectionClassRoles:
    """Collapsed "Class roles" section: lazy, draft-only, validated (ADR-009)."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    @pytest.fixture
    def weight_manager(self):
        with patch("zebtrack.ui.wizard.model_selection_step.WeightManager") as mock_wm:
            wm = MagicMock()
            wm.get_all_weights.return_value = ["rat.pt", "zebra.pt"]
            wm.get_weight_details.side_effect = lambda name: {
                "type": "det",
                "path": f"/weights/{name}",
            }
            wm.get_default_seg_weight.return_value = (None, None)
            wm.get_default_det_weight.return_value = ("rat.pt", "/weights/rat.pt")
            wm.get_weight_by_perspective_and_type.return_value = (None, None)
            wm.get_weight_sha256.side_effect = lambda name: f"sha-{name}"
            mock_wm.return_value = wm
            yield wm

    def _step(self, model_service: Any) -> ModelSelectionStep:
        wizard_data: dict[str, Any] = {"animals_per_aquarium": 1}
        step = ModelSelectionStep(
            self.root, wizard_data, settings_obj=None, model_service=model_service
        )
        step.build_ui()
        step.animal_method_var.set("Detection (det)")
        step.animal_weight_var.set("rat.pt")
        assert step.class_roles_panel is not None
        step.class_roles_panel._background = False
        return step

    @staticmethod
    def _service(names: dict) -> MagicMock:
        service = MagicMock()
        service.inspect_model.return_value = {"class_names": names}
        return service

    def test_section_is_collapsed_and_reads_nothing_until_opened(self, weight_manager):
        service = self._service(BARNES_NAMES)
        step = self._step(service)

        assert step.class_roles_section is not None
        assert step.class_roles_section.is_collapsed is True
        service.inspect_model.assert_not_called()
        data = step.get_data()
        assert data["class_roles"] is None
        assert data["class_roles_weight_sha256"] is None

    def test_edited_roles_and_sha_go_to_the_step_data(self, weight_manager):
        service = self._service(BARNES_NAMES)
        step = self._step(service)
        panel = step.class_roles_panel
        assert panel is not None

        panel.refresh()  # what opening the section does
        service.inspect_model.assert_called_once_with("rat.pt")
        panel.set_role([1, 3], ClassRole.CONTEXT)

        data = step.get_data()
        assert data["class_roles"] == {
            "arena": "arena",
            "experimenter": "context",
            "rat": "subject",
            "start_box": "context",
        }
        assert data["class_roles_weight_sha256"] == "sha-rat.pt"

    def test_invalid_roles_block_the_step(self, weight_manager):
        step = self._step(self._service(BARNES_NAMES))
        panel = step.class_roles_panel
        assert panel is not None
        panel.refresh()
        panel.set_role([2], ClassRole.CONTEXT)
        step.confidence_var.set("0.25")
        step.nms_var.set("0.45")

        ok, message = step.validate()

        assert ok is False
        assert message == "Choose at least one class as the subject (the animal to track)."
        assert step.get_data()["class_roles"] is None

    def test_changing_the_animal_weight_retargets_the_section(self, weight_manager):
        step = self._step(self._service(BARNES_NAMES))
        panel = step.class_roles_panel
        assert panel is not None
        panel.refresh()

        step.animal_weight_var.set("zebra.pt")

        assert panel.editor.weight_name == "zebra.pt"
        assert panel.draft_weight_sha256() == "sha-zebra.pt"


@pytest.mark.gui
class TestModelSelectionTemplateClassRoles:
    """#646: a template's roles are re-validated against the chosen weight."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies, monkeypatch):
        from zebtrack.ui.components import class_roles_panel

        self.root = wizard_dependencies["root"]
        # Each test gives "rat.pt" different classes: no session-wide cache.
        monkeypatch.setattr(
            class_roles_panel, "SHARED_CLASS_NAMES", class_roles_panel.ClassNamesCache()
        )

    weight_manager = TestModelSelectionClassRoles.weight_manager

    def _step(self, names: dict, template_roles: dict | None) -> ModelSelectionStep:
        service = MagicMock()
        service.inspect_model.return_value = {"class_names": names}
        wizard_data: dict[str, Any] = {
            "animals_per_aquarium": 1,
            "model_selection": {"animal_method": "det"},
            "weight_assignments": {"animal": "rat.pt"},
            "template_class_roles": (
                None
                if template_roles is None
                else {"class_roles": template_roles, "class_roles_weight_sha256": None}
            ),
        }
        step = ModelSelectionStep(self.root, wizard_data, settings_obj=None, model_service=service)
        step.build_ui()
        step.animal_method_var.set("Detection (det)")
        step.animal_weight_var.set("rat.pt")
        step.confidence_var.set("0.25")
        step.nms_var.set("0.45")
        return step

    def test_template_roles_open_the_section(self, weight_manager):
        step = self._step(BARNES_NAMES, BARNES_TEMPLATE_ROLES)
        assert step.class_roles_section is not None
        assert step.class_roles_section.is_collapsed is False

    def test_template_roles_become_the_project_roles(self, weight_manager):
        step = self._step(BARNES_NAMES, BARNES_TEMPLATE_ROLES)

        assert step.validate() == (True, "")
        data = step.get_data()
        assert data["class_roles"] == BARNES_TEMPLATE_ROLES
        assert data["class_roles_weight_sha256"] == "sha-rat.pt"

    def test_unresolvable_weight_blocks_the_step(self, weight_manager):
        step = self._step({0: "person", 1: "bicycle", 2: "car"}, BARNES_TEMPLATE_ROLES)

        ok, message = step.validate()

        assert ok is False
        assert message.startswith("None of the model classes (0: person, 1: bicycle, 2: car)")
        assert step.get_data()["class_roles"] is None

    def test_choosing_the_subject_by_hand_unblocks_it(self, weight_manager):
        step = self._step({0: "person", 1: "bicycle", 2: "car"}, BARNES_TEMPLATE_ROLES)
        step.validate()
        panel = step.class_roles_panel
        assert panel is not None

        panel.set_role([0], ClassRole.SUBJECT)

        assert step.validate() == (True, "")
        assert step.get_data()["class_roles"] == {
            "person": "subject",
            "bicycle": "ignored",
            "car": "ignored",
        }

    def test_without_template_roles_nothing_changes(self, weight_manager):
        step = self._step(BARNES_NAMES, None)
        panel = step.class_roles_panel
        assert panel is not None
        assert step.class_roles_section is not None
        assert step.class_roles_section.is_collapsed is True
        assert not panel.has_seed()
        assert step.get_data()["class_roles"] is None

    def test_on_show_picks_up_a_template_loaded_later(self, weight_manager):
        step = self._step(BARNES_NAMES, None)
        step.wizard_data["template_class_roles"] = {"class_roles": BARNES_TEMPLATE_ROLES}

        step.on_show()

        panel = step.class_roles_panel
        assert panel is not None and panel.has_seed()
        assert step.get_data()["class_roles"] == BARNES_TEMPLATE_ROLES


BARNES_TEMPLATE_ROLES = {
    "arena": "arena",
    "experimenter": "context",
    "rat": "subject",
    "start_box": "context",
}

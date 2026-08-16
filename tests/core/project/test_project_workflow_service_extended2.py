"""Extended unit tests for core/project/project_workflow_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceValidationAndOverrides:
    """Test validation of project parameters, normalization, and overrides."""

    def test_valid_openvino_devices(self):
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES

    def test_validate_project_parameters_det_single_animal(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        is_valid, err = svc.validate_project_parameters(animal_method="det", animals_per_aquarium=1)
        assert is_valid is True
        assert err is None

    def test_validate_project_parameters_det_multi_animal_fails(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        is_valid, err = svc.validate_project_parameters(animal_method="det", animals_per_aquarium=3)
        assert is_valid is False
        assert "detection mode (det) for animals is only compatible with 1 animal" in str(err)

    def test_prepare_controller_parameters_whitelist(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        raw_params = {
            "project_path": "/test/path",
            "num_aquariums": 2,
            "unwanted_internal_param": 12345,
            "another_invalid": "ignored",
            "use_openvino": True,
        }
        filtered = svc.prepare_controller_parameters(**raw_params)
        assert "project_path" in filtered
        assert "num_aquariums" in filtered
        assert "use_openvino" in filtered
        assert "unwanted_internal_param" not in filtered
        assert "another_invalid" not in filtered

    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("  fish_model  ") == "fish_model"
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name(12345) is None
        assert ProjectWorkflowService._normalize_weight_name(None) is None

    def test_build_initial_slot_weights(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        slots = svc._build_initial_slot_weights(
            weight_assignments={"animal": "fish_v1", "aquarium": "tank_v1"},
            animal_method="seg",
            aquarium_method="det",
        )
        assert slots["seg:zebrafish"] == "fish_v1"
        assert slots["det:aquarium"] == "tank_v1"

    def test_build_detector_hyperparam_overrides(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        params = {
            "confidence_threshold": "0.45",
            "nms_threshold": 0.5,
            "out_of_bounds": 2.5,
            "invalid_str": "not_a_number",
        }
        overrides = svc._build_detector_hyperparam_overrides(params)
        assert overrides["confidence_threshold"] == 0.45
        assert overrides["nms_threshold"] == 0.5
        assert "out_of_bounds" not in overrides
        assert "invalid_str" not in overrides

    def test_normalize_slot_weights_from_tuples_and_strings(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        raw = {
            ("seg", "zebrafish"): "fish_v1",
            "det:aquarium": "tank_v1",
            "invalid_slot": "ignored",
            "unknown:target": "ignored",
        }
        normalized = svc._normalize_slot_weights(raw)
        assert normalized["seg:zebrafish"] == "fish_v1"
        assert normalized["det:aquarium"] == "tank_v1"
        assert "invalid_slot" not in normalized

    def test_global_model_defaults_state(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )
        svc.set_global_model_defaults("fish_seg", True)
        assert svc._global_model_defaults["active_weight"] == "fish_seg"
        assert svc._global_model_defaults["use_openvino"] is True

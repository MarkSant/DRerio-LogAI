"""Extended unit tests for core/project/project_workflow_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceExtended2:
    """Test ProjectWorkflowService parameter validation, whitelisting, and defaults."""

    def test_constants(self):
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_set_global_model_defaults(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        svc.set_global_model_defaults("best_seg.pt", True)
        assert svc._global_model_defaults == {
            "active_weight": "best_seg.pt",
            "use_openvino": True,
        }

    def test_validate_project_parameters_det_with_multiple_animals_fails(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        is_valid, msg = svc.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=2,
        )
        assert is_valid is False
        assert msg is not None
        assert "compatible with 1 animal" in msg or "compatível com 1 animal" in msg

    def test_validate_project_parameters_valid_configs(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        # Single animal + det
        is_valid, msg = svc.validate_project_parameters(
            animal_method="det",
            animals_per_aquarium=1,
        )
        assert is_valid is True
        assert msg is None

        # Multi animal + seg
        is_valid_seg, msg_seg = svc.validate_project_parameters(
            animal_method="seg",
            animals_per_aquarium=4,
        )
        assert is_valid_seg is True
        assert msg_seg is None

    def test_prepare_controller_parameters_filters_unwanted_keys(self):
        svc = ProjectWorkflowService(
            project_manager=MagicMock(),
            model_service=MagicMock(),
            state_manager=MagicMock(),
        )

        raw = {
            "project_path": "/path/proj",
            "num_aquariums": 2,
            "arbitrary_garbage_key": 12345,
            "another_random_field": "hello",
        }

        filtered = svc.prepare_controller_parameters(**raw)
        assert "project_path" in filtered
        assert "num_aquariums" in filtered
        assert "arbitrary_garbage_key" not in filtered
        assert "another_random_field" not in filtered

"""
Extended unit tests for ProjectWorkflowService in core/project/project_workflow_service.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.project_workflow_service import (
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceExtended:
    """Test ProjectWorkflowService parameter validation, model resolution, and slots."""

    @pytest.fixture
    def mock_deps(self) -> tuple[MagicMock, MagicMock, MagicMock]:
        pm = MagicMock()
        pm.project_data = {}
        pm.project_path = None
        ms = MagicMock()
        ms.get_all_weight_names.return_value = ["best_seg.pt", "best_det.pt"]
        ms.is_openvino_ready.return_value = True
        ms.get_default_weight.return_value = "best_seg.pt"
        sm = MagicMock()
        return pm, ms, sm

    @pytest.fixture
    def workflow_service(
        self, mock_deps: tuple[MagicMock, MagicMock, MagicMock]
    ) -> ProjectWorkflowService:
        pm, ms, sm = mock_deps
        return ProjectWorkflowService(
            project_manager=pm,
            model_service=ms,
            state_manager=sm,
        )

    def test_validate_project_parameters_detection_mode_single_animal(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="det", animals_per_aquarium=1
        )
        assert is_valid is True
        assert msg is None

    def test_validate_project_parameters_detection_mode_multi_animal_invalid(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="det", animals_per_aquarium=2
        )
        assert is_valid is False
        assert msg is not None
        assert "compatible with 1 animal" in msg

    def test_validate_project_parameters_segmentation_mode_multi_animal_valid(
        self, workflow_service: ProjectWorkflowService
    ):
        is_valid, msg = workflow_service.validate_project_parameters(
            animal_method="seg", animals_per_aquarium=4
        )
        assert is_valid is True
        assert msg is None

    def test_prepare_controller_parameters_whitelist(
        self, workflow_service: ProjectWorkflowService
    ):
        raw_params = {
            "project_path": "/path/to/proj",
            "project_type": "single",
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "_wizard_metadata": {"step": 2},
            "unauthorized_key": "injected_val",
            "another_random_key": 999,
        }
        filtered = workflow_service.prepare_controller_parameters(**raw_params)
        assert "project_path" in filtered
        assert "project_type" in filtered
        assert "num_aquariums" in filtered
        assert "_wizard_metadata" in filtered
        assert "unauthorized_key" not in filtered
        assert "another_random_key" not in filtered

    def test_set_global_model_defaults(self, workflow_service: ProjectWorkflowService):
        workflow_service.set_global_model_defaults("custom_model.pt", use_openvino=True)
        assert workflow_service._global_model_defaults["active_weight"] == "custom_model.pt"
        assert workflow_service._global_model_defaults["use_openvino"] is True

    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name(None) is None
        assert ProjectWorkflowService._normalize_weight_name("yolov8n.pt") == "yolov8n.pt"
        assert ProjectWorkflowService._normalize_weight_name("None") == "None"

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False
        assert ProjectWorkflowService._normalize_openvino_override("True") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False

    def test_resolve_openvino_device(self, workflow_service: ProjectWorkflowService):
        assert workflow_service._resolve_openvino_device({"device": "CPU"}) == "CPU"
        assert workflow_service._resolve_openvino_device({"device": "GPU"}) == "GPU"
        assert workflow_service._resolve_openvino_device({"device": "NPU"}) == "NPU"
        assert workflow_service._resolve_openvino_device({"device": "INVALID"}) == "AUTO"
        assert workflow_service._resolve_openvino_device(None) == "AUTO"

    def test_resolve_project_model_settings_explicit_override(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        overrides = {"active_weight": "best_det.pt", "use_openvino": True}
        weight, use_ov = workflow_service.resolve_project_model_settings(overrides=overrides)
        assert weight == "best_det.pt"
        assert use_ov is True

    def test_resolve_project_model_settings_fallback_to_global_defaults(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        workflow_service.set_global_model_defaults("best_seg.pt", use_openvino=False)
        weight, use_ov = workflow_service.resolve_project_model_settings(overrides=None)
        assert weight == "best_seg.pt"
        assert use_ov is False

    def test_slot_key_formatting(self):
        key = ProjectWorkflowService._slot_key("seg", "zebrafish")
        assert key == "seg:zebrafish"

    def test_save_project_model_slot_overrides_without_project_path(
        self, workflow_service: ProjectWorkflowService
    ):
        workflow_service.set_global_model_defaults("best_seg.pt", use_openvino=False)
        weight, use_ov = workflow_service.save_project_model_slot_overrides(
            slot_weights={"seg:zebrafish": "best_seg.pt"},
            use_openvino_override=True,
        )
        assert weight == "best_seg.pt"
        assert use_ov is True

    def test_save_project_model_slot_overrides_with_active_project(
        self,
        workflow_service: ProjectWorkflowService,
        mock_deps: tuple[MagicMock, MagicMock, MagicMock],
    ):
        pm, ms, sm = mock_deps
        pm.project_path = "/path/to/project"
        pm.project_data = {"animal_method": "seg"}

        active_setter = MagicMock()
        ov_setter = MagicMock()

        weight, use_ov = workflow_service.save_project_model_slot_overrides(
            slot_weights={"seg:zebrafish": "best_seg.pt"},
            use_openvino_override=True,
            active_weight_setter=active_setter,
            use_openvino_setter=ov_setter,
        )
        assert weight == "best_seg.pt"
        assert use_ov is True
        active_setter.assert_called_with("best_seg.pt")
        ov_setter.assert_called_with(True)
        pm.save_project.assert_called()

    def test_create_project_validation_failure(self, workflow_service: ProjectWorkflowService):
        res = workflow_service.create_project(
            project_path="/tmp/test",
            animal_method="det",
            animals_per_aquarium=3,
        )
        assert res["success"] is False
        assert "compatible with 1 animal" in str(res["error_message"])

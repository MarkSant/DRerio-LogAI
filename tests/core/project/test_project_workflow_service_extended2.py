"""Extended unit tests for core/project/project_workflow_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceExtended2:
    """Test ProjectWorkflowService parameter validation, whitelist filtering,
    device resolution, and defaults.
    """

    def test_openvino_device_constants(self):
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES

    def test_global_model_defaults_setting(self):
        mock_proj = MagicMock()
        mock_model = MagicMock()
        mock_state = MagicMock()

        svc = ProjectWorkflowService(
            project_manager=mock_proj,
            model_service=mock_model,
            state_manager=mock_state,
        )

        assert svc._using_project_overrides is False
        assert svc._SLOT_SEPARATOR == ":"

        svc.set_global_model_defaults(active_weight="yolo11n.pt", use_openvino=True)
        assert svc._global_model_defaults["active_weight"] == "yolo11n.pt"
        assert svc._global_model_defaults["use_openvino"] is True

    def test_validate_project_parameters_multi_animal_det_mode(self):
        svc = object.__new__(ProjectWorkflowService)

        # 1. Valid: single animal + det mode
        is_valid, err = svc.validate_project_parameters(animal_method="det", animals_per_aquarium=1)
        assert is_valid is True
        assert err is None

        # 2. Invalid: multi animal + det mode
        is_valid, err = svc.validate_project_parameters(animal_method="det", animals_per_aquarium=2)
        assert is_valid is False
        assert err is not None
        assert "compatible with 1 animal" in err

        # 3. Valid: multi animal + seg mode
        is_valid, err = svc.validate_project_parameters(animal_method="seg", animals_per_aquarium=4)
        assert is_valid is True
        assert err is None

    def test_prepare_controller_parameters_whitelist(self):
        svc = object.__new__(ProjectWorkflowService)

        params = {
            "project_path": "/my/proj",
            "num_aquariums": 2,
            "unsupported_extra_param": "ignore_me",
            "arbitrary_garbage": 123,
            "use_arduino": True,
        }

        filtered = svc.prepare_controller_parameters(**params)
        assert "project_path" in filtered
        assert "num_aquariums" in filtered
        assert "use_arduino" in filtered
        assert "unsupported_extra_param" not in filtered
        assert "arbitrary_garbage" not in filtered

    def test_resolve_openvino_device_from_overrides(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_data = {}
        svc.settings = None

        dev_gpu = svc._resolve_openvino_device({"device": "gpu"})
        assert dev_gpu == "GPU"

        dev_npu = svc._resolve_openvino_device({"device": "NPU"})
        assert dev_npu == "NPU"

        dev_auto = svc._resolve_openvino_device({"device": "INVALID_DEV"})
        assert dev_auto == "AUTO"

    def test_resolve_openvino_device_from_project_and_settings(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_data = {"openvino_device": "CPU"}
        svc.settings = MagicMock()
        svc.settings.openvino.device = "GPU"

        # Project level overrides settings
        dev = svc._resolve_openvino_device()
        assert dev == "CPU"

        # Settings level when project is empty
        svc.project_manager.project_data = {}
        dev_settings = svc._resolve_openvino_device()
        assert dev_settings == "GPU"

"""
Extended unit tests for ProjectWorkflowService in core/project/project_workflow_service.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceExtended:
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


class TestProjectWorkflowServiceExtended2:
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


class TestProjectWorkflowServiceExtended3:
    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("weight.pt") == "weight.pt"
        assert ProjectWorkflowService._normalize_weight_name("  ") is None
        assert ProjectWorkflowService._normalize_weight_name(None) is None

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override(None) is None

    def test_normalize_slot_weights_tuple_and_string_keys(self):
        raw = {
            ("seg", "zebrafish"): "seg_fish.pt",
            "det:aquarium": "det_aq.pt",
            "invalid_key": "junk.pt",
        }
        svc = object.__new__(ProjectWorkflowService)
        normalized = svc._normalize_slot_weights(raw)
        assert normalized["seg:zebrafish"] == "seg_fish.pt"
        assert normalized["det:aquarium"] == "det_aq.pt"
        assert "invalid_key" not in normalized

    def test_normalize_slot_weights_invalid_input(self):
        svc = object.__new__(ProjectWorkflowService)
        assert svc._normalize_slot_weights(None) == {}
        assert svc._normalize_slot_weights([]) == {}

    def test_normalize_openvino_override_case_insensitive(self):
        assert ProjectWorkflowService._normalize_openvino_override("TRUE") is True
        assert ProjectWorkflowService._normalize_openvino_override("False") is False
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None


class TestProjectWorkflowServiceExtended4:
    def test_build_initial_slot_weights_valid(self):
        svc = object.__new__(ProjectWorkflowService)
        raw_assignments = {
            "animal": "yolov8n_fish.pt",
            "aquarium": "yolov8n_aq.pt",
        }
        res = svc._build_initial_slot_weights(
            weight_assignments=raw_assignments,
            animal_method="det",
            aquarium_method="seg",
        )
        assert res["det:zebrafish"] == "yolov8n_fish.pt"
        assert res["seg:aquarium"] == "yolov8n_aq.pt"

    def test_build_initial_slot_weights_invalid_input(self):
        svc = object.__new__(ProjectWorkflowService)
        assert (
            svc._build_initial_slot_weights(
                weight_assignments=None,
                animal_method="det",
                aquarium_method="seg",
            )
            == {}
        )

    def test_build_detector_hyperparam_overrides(self):
        svc = object.__new__(ProjectWorkflowService)
        params = {
            "confidence_threshold": 0.35,
            "nms_threshold": 0.45,
            "unsupported_param": 100,
        }
        overrides = svc._build_detector_hyperparam_overrides(params)
        assert overrides["confidence_threshold"] == 0.35
        assert overrides["nms_threshold"] == 0.45
        assert "unsupported_param" not in overrides

    def test_build_detector_hyperparam_overrides_invalid_type(self):
        svc = object.__new__(ProjectWorkflowService)
        assert svc._build_detector_hyperparam_overrides(None) == {}
        assert svc._build_detector_hyperparam_overrides("string") == {}


class TestProjectWorkflowServiceExtended5:
    def test_persist_initial_project_overrides_empty(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        # With empty args, returns without modifying project data
        svc._persist_initial_project_overrides(None, None)
        svc.project_manager.save_project.assert_not_called()

    def test_persist_initial_project_overrides_updates_and_saves(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_path = "/path/to/project.zeb"
        svc.project_manager.project_data = {}

        slot_weights = {"det:zebrafish": "fish_v8.pt"}
        hyperparams = {"confidence_threshold": 0.40}

        svc._persist_initial_project_overrides(slot_weights, hyperparams)

        overrides = svc.project_manager.project_data["model_overrides"]
        assert overrides["slot_weights"]["det:zebrafish"] == "fish_v8.pt"
        assert overrides["confidence_threshold"] == 0.40
        svc.project_manager.save_project.assert_called_once()

    def test_persist_initial_project_overrides_no_changes(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.project_manager = MagicMock()
        svc.project_manager.project_path = "/path/to/project.zeb"
        svc.project_manager.project_data = {
            "model_overrides": {
                "slot_weights": {"det:zebrafish": "fish_v8.pt"},
                "confidence_threshold": 0.40,
            }
        }

        # Passing identical overrides should not trigger save_project
        svc._persist_initial_project_overrides(
            {"det:zebrafish": "fish_v8.pt"},
            {"confidence_threshold": 0.40},
        )
        svc.project_manager.save_project.assert_not_called()

    def test_normalize_weight_name(self):
        assert ProjectWorkflowService._normalize_weight_name("  model.pt  ") == "model.pt"
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name(123) is None

    def test_normalize_openvino_override(self):
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("yes") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override(None) is None

    def test_normalize_slot_weights(self):
        svc = object.__new__(ProjectWorkflowService)
        raw = {
            ("det", "zebrafish"): " fish.pt ",
            "seg:aquarium": "aq.pt",
            "invalid_key": "bad.pt",
            ("det", "invalid_target"): "bad2.pt",
        }
        normalized = svc._normalize_slot_weights(raw)
        assert normalized["det:zebrafish"] == "fish.pt"
        assert normalized["seg:aquarium"] == "aq.pt"
        assert "invalid_key" not in normalized


class TestProjectWorkflowServiceExtended6:
    def test_get_default_weight_name_tuple(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.model_service = MagicMock()
        svc.model_service.get_default_weight.return_value = ("model_v8.pt", {"type": "det"})

        assert svc._get_default_weight_name() == "model_v8.pt"

    def test_get_default_weight_name_none(self):
        svc = object.__new__(ProjectWorkflowService)
        svc.model_service = MagicMock()
        svc.model_service.get_default_weight.return_value = None

        assert svc._get_default_weight_name() is None

    def test_set_runtime_slot_overrides(self):
        svc = object.__new__(ProjectWorkflowService)
        svc._SLOT_SEPARATOR = ":"
        svc.model_service = MagicMock()
        weight_manager = MagicMock()
        svc.model_service.weight_manager = weight_manager

        slot_weights = {"det:zebrafish": "fish_v8.pt", "seg:aquarium": "aq_v8.pt"}
        svc._set_runtime_slot_overrides(slot_weights)

        weight_manager.set_runtime_slot_overrides.assert_called_once_with(
            {("det", "zebrafish"): "fish_v8.pt", ("seg", "aquarium"): "aq_v8.pt"}
        )

    def test_normalize_openvino_override_strings(self):
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("") is None
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("yes") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False
        assert ProjectWorkflowService._normalize_openvino_override("0") is False
        assert ProjectWorkflowService._normalize_openvino_override("no") is False
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override(True) is True
        assert ProjectWorkflowService._normalize_openvino_override(False) is False

    def test_resolve_slot_weights_from_overrides_empty(self, monkeypatch: pytest.MonkeyPatch):
        svc = object.__new__(ProjectWorkflowService)
        monkeypatch.setattr(svc, "_normalize_slot_weights", lambda val: {})
        monkeypatch.setattr(svc, "_normalize_weight_name", lambda val: None)
        monkeypatch.setattr(svc, "_get_legacy_animal_slot_key", lambda val: None)

        res = svc._resolve_slot_weights_from_overrides({})
        assert res == {}

    def test_resolve_slot_weights_from_overrides_with_legacy_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        svc = object.__new__(ProjectWorkflowService)
        monkeypatch.setattr(svc, "_normalize_slot_weights", lambda val: {})
        monkeypatch.setattr(svc, "_normalize_weight_name", lambda val: "legacy_fish.pt")
        monkeypatch.setattr(svc, "_get_legacy_animal_slot_key", lambda val: "det:zebrafish")

        res = svc._resolve_slot_weights_from_overrides({"active_weight": "legacy_fish.pt"})
        assert res == {"det:zebrafish": "legacy_fish.pt"}


class TestProjectWorkflowServiceExtended7:
    def test_normalize_weight_name_none_or_blank(self):
        assert ProjectWorkflowService._normalize_weight_name(None) is None
        assert ProjectWorkflowService._normalize_weight_name("") is None
        assert ProjectWorkflowService._normalize_weight_name("   ") is None
        assert ProjectWorkflowService._normalize_weight_name("  model.pt  ") == "model.pt"

    def test_normalize_openvino_override_values(self):
        assert ProjectWorkflowService._normalize_openvino_override(None) is None
        assert ProjectWorkflowService._normalize_openvino_override("auto") is None
        assert ProjectWorkflowService._normalize_openvino_override("inherit") is None
        assert ProjectWorkflowService._normalize_openvino_override("") is None
        assert ProjectWorkflowService._normalize_openvino_override("true") is True
        assert ProjectWorkflowService._normalize_openvino_override("1") is True
        assert ProjectWorkflowService._normalize_openvino_override("false") is False

    def test_normalize_slot_weights_none(self):
        pws: Any = object.__new__(ProjectWorkflowService)
        assert pws._normalize_slot_weights(None) == {}
        assert pws._normalize_slot_weights("not_a_dict") == {}

    def test_get_legacy_animal_slot_key_none(self):
        pws: Any = object.__new__(ProjectWorkflowService)
        pws._get_project_slot_pairs = lambda: []

        key = pws._get_legacy_animal_slot_key(None)
        assert key is None


class TestProjectWorkflowServiceExtended8:
    def test_slot_key_formatting(self):
        key = ProjectWorkflowService._slot_key("det", "zebrafish")
        assert key == "det:zebrafish"

        key2 = ProjectWorkflowService._slot_key("seg", "aquarium")
        assert key2 == "seg:aquarium"

    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_slot_key_empty_inputs(self):
        assert ProjectWorkflowService._slot_key("", "") == ":"
        assert ProjectWorkflowService._slot_key("det", "") == "det:"

    def test_slot_key_custom_labels(self):
        res = ProjectWorkflowService._slot_key("segmentation", "subject_01")
        assert res == "segmentation:subject_01"


class TestProjectWorkflowServiceExtended9:
    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_valid_openvino_devices_tuple(self):
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES


class TestOpenProjectZoneSetup:
    """Opening a project must APPLY its zones — including "it has none".

    The callback used to be gated on the opened project already having an arena
    or ROIs, with no ``else``. A project without zones therefore left the
    detector configured with whatever the previous session installed, most
    damagingly an ad-hoc single-video run.
    """

    @pytest.fixture
    def service(self) -> ProjectWorkflowService:
        pm = MagicMock()
        pm.project_data = {}
        pm.project_path = None
        pm.get_detector_state.return_value = None
        pm.get_project_name.return_value = "Experiment"
        pm.get_all_videos.return_value = []
        pm.get_active_zone_video.return_value = None
        ms = MagicMock()
        ms.get_all_weight_names.return_value = ["best_seg.pt"]
        ms.is_openvino_ready.return_value = True
        ms.get_default_weight.return_value = "best_seg.pt"
        return ProjectWorkflowService(
            project_manager=pm, model_service=ms, state_manager=MagicMock()
        )

    @staticmethod
    def _zone_data(*, polygon=None, rois=None):
        zone = MagicMock()
        zone.polygon = polygon or []
        zone.roi_polygons = rois or []
        return zone

    def test_callback_runs_when_the_project_has_zones(self, service, tmp_path):
        service.project_manager.get_zone_data.return_value = self._zone_data(
            polygon=[[0, 0], [1, 0], [1, 1], [0, 1]]
        )
        setup_zones = MagicMock()

        result = service.open_project(tmp_path, setup_zones_callback=setup_zones)

        assert result["success"] is True
        setup_zones.assert_called_once()

    def test_callback_still_runs_when_the_project_has_no_zones(self, service, tmp_path):
        """ "No zones" must actively CLEAR, not skip the step."""
        service.project_manager.get_zone_data.return_value = self._zone_data()
        setup_zones = MagicMock()

        result = service.open_project(tmp_path, setup_zones_callback=setup_zones)

        assert result["success"] is True
        setup_zones.assert_called_once()
        assert result["project_info"]["zone_status"] == "✗"

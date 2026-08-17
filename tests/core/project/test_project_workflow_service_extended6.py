"""Extended unit tests for core/project/project_workflow_service.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended6:
    """Test ProjectWorkflowService runtime slot overrides and openvino options."""

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

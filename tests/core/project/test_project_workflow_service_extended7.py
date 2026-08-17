"""Extended unit tests for core/project/project_workflow_service.py (Part 7)."""

from __future__ import annotations

from typing import Any

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended7:
    """Test slot weight normalization and legacy animal slot key resolution."""

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

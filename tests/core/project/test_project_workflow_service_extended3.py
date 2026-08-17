"""Extended unit tests for core/project/project_workflow_service.py."""

from __future__ import annotations

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended3:
    """Test ProjectWorkflowService normalization helpers."""

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

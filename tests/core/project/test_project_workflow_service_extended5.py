"""Extended unit tests for core/project/project_workflow_service.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended5:
    """Test ProjectWorkflowService project override persistence and normalization."""

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

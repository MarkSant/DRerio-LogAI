"""Extended unit tests for core/project/project_workflow_service.py (Part 4)."""

from __future__ import annotations

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended4:
    """Test ProjectWorkflowService initial slot weights and hyperparameter override extraction."""

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

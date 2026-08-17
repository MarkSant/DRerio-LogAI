"""Extended unit tests for ui/wizard/detection_step.py (Part 4)."""

from __future__ import annotations

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels
from zebtrack.ui.wizard.enums import WizardStepID


class TestDetectionStepExtended4:
    """Test DetectionStep data payload formatting and method labels."""

    def test_method_labels_mapping(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels
        assert "Segmentation" in labels["seg"]
        assert "Detection" in labels["det"]

    def test_detection_step_initial_wizard_data(self):
        step = object.__new__(DetectionStep)
        step.step_id = WizardStepID.DETECTION_VALIDATION
        step.wizard_data = {"input_paths": ["/videos"]}
        step.scanned_videos = []
        step.detected_design = None

        assert step.step_id == WizardStepID.DETECTION_VALIDATION
        assert step.wizard_data["input_paths"] == ["/videos"]
        assert step.detected_design is None

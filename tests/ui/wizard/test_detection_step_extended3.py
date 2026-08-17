"""Extended unit tests for ui/wizard/detection_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels
from zebtrack.ui.wizard.enums import WizardStepID


class TestDetectionStepExtended3:
    """Test DetectionStep constants and method labels."""

    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels

    def test_step_id(self):
        step = object.__new__(DetectionStep)
        step.step_id = WizardStepID.DETECTION_VALIDATION
        step.scanned_videos = []

        assert step.step_id == WizardStepID.DETECTION_VALIDATION
        assert step.scanned_videos == []

    def test_initial_design_editor_confirmed(self):
        step = object.__new__(DetectionStep)
        step.design_editor_confirmed = False
        assert step.design_editor_confirmed is False

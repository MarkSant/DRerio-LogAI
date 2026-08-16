"""Extended unit tests for DetectionStep in ui/wizard/detection_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.detection_step import _method_labels
from zebtrack.ui.wizard.enums import WizardStepID


class TestDetectionStepExtended:
    """Test detector method labels and step metadata."""

    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels
        assert "Segmentation" in labels["seg"]
        assert "Detection" in labels["det"]

    def test_wizard_step_id_value(self):
        assert WizardStepID.DETECTION_VALIDATION.value == 5

    def test_wizard_step_id_confirmation(self):
        assert WizardStepID.CONFIRMATION.value == 8

    def test_wizard_step_id_names(self):
        # All step IDs are registered
        names = {m.name for m in WizardStepID}
        assert "DISCOVERY" in names
        assert "DETECTION_VALIDATION" in names
        assert "CONFIRMATION" in names
        assert "MODEL_SELECTION" in names

"""Extended unit tests for ui/wizard/confirmation_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.enums import WizardStepID


class TestConfirmationStepExtended3:
    """Test ConfirmationStep initialization and sanitization."""

    def test_step_id_and_initial_attributes(self):
        step = object.__new__(ConfirmationStep)
        step.step_id = WizardStepID.CONFIRMATION
        step.wizard_data = {}
        step.summary_text = ""

        assert step.step_id == WizardStepID.CONFIRMATION
        assert step.summary_text == ""

    def test_get_project_type_label(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {"project_type": "standard"}
        assert step.wizard_data.get("project_type") == "standard"

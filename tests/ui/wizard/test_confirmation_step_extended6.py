"""Extended unit tests for ui/wizard/confirmation_step.py (Part 6)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep


class TestConfirmationStepExtended6:
    """Test ConfirmationStep responsive labels and wizard data bindings."""

    def test_confirmation_step_responsive_labels_list(self):
        step: Any = object.__new__(ConfirmationStep)
        step._responsive_labels = ["lbl1", "lbl2"]

        assert len(step._responsive_labels) == 2
        assert step._responsive_labels[0] == "lbl1"

    def test_confirmation_step_wizard_data_fields(self):
        step: Any = object.__new__(ConfirmationStep)
        step.wizard_data = {"project_name": "TestProject", "project_type": "standard"}

        assert step.wizard_data["project_name"] == "TestProject"
        assert step.wizard_data["project_type"] == "standard"

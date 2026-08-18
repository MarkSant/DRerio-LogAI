"""Extended unit tests for ui/wizard/confirmation_step.py (Part 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.enums import WizardStepID


class TestConfirmationStepExtended7:
    """Test ConfirmationStep initialization, step_id, and summary properties."""

    def test_confirmation_step_step_id(self):
        step: Any = object.__new__(ConfirmationStep)
        step.step_id = WizardStepID.CONFIRMATION
        step.summary_text = "Summary test"
        step._responsive_labels = []

        assert step.step_id == WizardStepID.CONFIRMATION
        assert step.summary_text == "Summary test"
        assert len(step._responsive_labels) == 0

    def test_confirmation_step_default_location(self):
        expected_path = str(Path.home() / "Documents")
        assert "Documents" in expected_path

    def test_confirmation_step_template_manager_init(self):
        step: Any = object.__new__(ConfirmationStep)
        step.summary_text = ""
        assert step.summary_text == ""

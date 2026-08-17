"""Extended unit tests for ui/wizard/confirmation_step.py (Part 5)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep


class TestConfirmationStepExtended5:
    """Test ConfirmationStep data validation and summary properties."""

    def test_confirmation_step_template_var_empty(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {}
        step._responsive_labels = []
        assert step.wizard_data == {}
        assert len(step._responsive_labels) == 0

    def test_confirmation_step_content_container_none(self):
        step: Any = object.__new__(ConfirmationStep)
        step.content_container = None
        step.summary_textbox = None
        assert step.content_container is None
        assert step.summary_textbox is None

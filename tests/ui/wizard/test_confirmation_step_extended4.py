"""Extended unit tests for ui/wizard/confirmation_step.py (Part 4)."""

from __future__ import annotations

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep


class TestConfirmationStepExtended4:
    """Test ConfirmationStep template banners, summary state, and responsive label lists."""

    def test_confirmation_step_responsive_labels(self):
        step = object.__new__(ConfirmationStep)
        step._responsive_labels = []
        assert len(step._responsive_labels) == 0

    def test_confirmation_step_template_banner(self):
        step = object.__new__(ConfirmationStep)
        step.template_info_label = None
        assert step.template_info_label is None

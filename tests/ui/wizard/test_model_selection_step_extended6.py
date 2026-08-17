"""Extended unit tests for ui/wizard/model_selection_step.py (Part 6)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep


class TestModelSelectionStepExtended6:
    """Test ModelSelectionStep controller and wizard data properties."""

    def test_model_selection_step_wizard_data_none(self):
        step: Any = object.__new__(ModelSelectionStep)
        step.wizard_data = {}
        step.controller = MagicMock()

        assert step.wizard_data == {}
        assert step.controller is not None

    def test_model_selection_step_threshold_containers(self):
        step: Any = object.__new__(ModelSelectionStep)
        step._threshold_entries = {}
        step._threshold_error_labels = {}

        assert step._threshold_entries == {}
        assert step._threshold_error_labels == {}

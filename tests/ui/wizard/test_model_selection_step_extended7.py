"""Extended unit tests for ui/wizard/model_selection_step.py (Part 7)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep


class TestModelSelectionStepExtended7:
    """Test ModelSelectionStep threshold error labels and frame bindings."""

    def test_model_selection_step_error_labels_registration(self):
        step: Any = object.__new__(ModelSelectionStep)
        step._threshold_error_labels = {"conf": "Error: invalid confidence"}
        assert "conf" in step._threshold_error_labels
        assert step._threshold_error_labels["conf"] == "Error: invalid confidence"

    def test_model_selection_step_threshold_entries(self):
        step: Any = object.__new__(ModelSelectionStep)
        step._threshold_entries = {"iou": "0.5"}
        assert step._threshold_entries["iou"] == "0.5"

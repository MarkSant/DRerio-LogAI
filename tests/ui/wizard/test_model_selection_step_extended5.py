"""Extended unit tests for ui/wizard/model_selection_step.py (Part 5)."""

from __future__ import annotations

from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep


class TestModelSelectionStepExtended5:
    """Test ModelSelectionStep threshold collections and responsive label buckets."""

    def test_threshold_entries_initial(self):
        step = object.__new__(ModelSelectionStep)
        step._threshold_entries = {}
        step._threshold_error_labels = {}
        step._responsive_labels = {"left": [], "right": []}
        step._methods_frame = None
        step._bytetrack_frame = None

        assert step._threshold_entries == {}
        assert step._threshold_error_labels == {}
        assert "left" in step._responsive_labels
        assert "right" in step._responsive_labels
        assert step._methods_frame is None
        assert step._bytetrack_frame is None

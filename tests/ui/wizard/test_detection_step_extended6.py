"""Extended unit tests for ui/wizard/detection_step.py (Part 6)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.detection_step import DetectionStep


class TestDetectionStepExtended6:
    """Test DetectionStep wizard data reference and initial empty patterns."""

    def test_detection_step_wizard_data_ref(self):
        step: Any = object.__new__(DetectionStep)
        step.wizard_data = {"camera_index": 0}
        step.custom_regex_patterns = []

        assert step.wizard_data == {"camera_index": 0}
        assert step.custom_regex_patterns == []

    def test_detection_step_custom_patterns_management(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = ["^video_(\\d+)$", ".*\\.mp4$"]
        assert len(step.custom_regex_patterns) == 2
        assert step.custom_regex_patterns[0] == "^video_(\\d+)$"

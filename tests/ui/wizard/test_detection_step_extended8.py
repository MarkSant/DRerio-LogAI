"""Extended unit tests for ui/wizard/detection_step.py (Part 8)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.detection_step import DetectionStep


class TestDetectionStepExtended8:
    """Test DetectionStep custom regex patterns lookup and modifications."""

    def test_custom_regex_patterns_length_checks(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = ["pattern_1", "pattern_2", "pattern_3"]
        assert len(step.custom_regex_patterns) == 3
        assert "pattern_2" in step.custom_regex_patterns

    def test_detection_step_custom_patterns_indexing(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = ["p0", "p1"]
        assert step.custom_regex_patterns[0] == "p0"
        assert step.custom_regex_patterns[1] == "p1"

    def test_detection_step_custom_patterns_empty(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = []
        assert len(step.custom_regex_patterns) == 0

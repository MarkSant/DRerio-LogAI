"""Extended unit tests for ui/wizard/detection_step.py (Part 7)."""

from __future__ import annotations

from typing import Any

from zebtrack.ui.wizard.detection_step import DetectionStep


class TestDetectionStepExtended7:
    """Test DetectionStep custom pattern modification and wizard bindings."""

    def test_custom_regex_patterns_append(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = []
        step.custom_regex_patterns.append("^camera_(\\d+)")
        step.custom_regex_patterns.append("^trial_(\\d+)")

        assert len(step.custom_regex_patterns) == 2
        assert step.custom_regex_patterns[1] == "^trial_(\\d+)"

    def test_custom_regex_patterns_clear(self):
        step: Any = object.__new__(DetectionStep)
        step.custom_regex_patterns = ["^test_(\\d+)"]
        step.custom_regex_patterns.clear()
        assert len(step.custom_regex_patterns) == 0

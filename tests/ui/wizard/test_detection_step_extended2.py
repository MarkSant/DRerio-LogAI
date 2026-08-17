"""Extended unit tests for ui/wizard/detection_step.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels
from zebtrack.ui.wizard.enums import WizardStepID


class TestDetectionStepExtended2:
    """Test DetectionStep labels, step id, custom regex extraction, and empty path handling."""

    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels
        assert "Segmentation" in labels["seg"]
        assert "Detection" in labels["det"]

    def test_step_id_and_initial_state(self):
        step = object.__new__(DetectionStep)
        step.step_id = WizardStepID.DETECTION_VALIDATION
        step.scanned_videos = []
        step.detected_design = None
        step.custom_regex_patterns = None
        step.design_editor_confirmed = False

        assert step.step_id == WizardStepID.DETECTION_VALIDATION
        assert step.scanned_videos == []
        assert step.detected_design is None

    def test_run_detection_empty_video_paths(self):
        step = object.__new__(DetectionStep)
        step.custom_regex_patterns = None
        step.status_var = MagicMock()
        step.wizard_data = {"video_paths": []}
        step.scanned_videos = []
        step.detected_design = None
        step.results_text = MagicMock()

        # Running detection with empty paths sets error status
        step._run_detection()
        step.status_var.set.assert_called_with("Error!")
        step.results_text.delete.assert_called_once_with("1.0", "end")

    def test_pattern_custom_regex_no_group_pattern(self):
        step = object.__new__(DetectionStep)
        res = step._pattern_custom_regex([Path("test.mp4")], {})
        assert res is None

    def test_extract_match_data(self):
        step = object.__new__(DetectionStep)
        d = {"group": "Control", "day": "2", "subject": "S1"}
        extracted = step._extract_match_data(d)
        assert extracted["group"] == "Control"
        assert extracted["day"] == "Day02"
        assert extracted["subject"] == "S1"

    def test_update_detected_sets(self):
        step = object.__new__(DetectionStep)
        groups: set[str] = set()
        days: set[str] = set()
        subjects: dict[str, set[str]] = {}

        data = {"group": "Treated", "day": "Day03", "subject": "S5"}
        step._update_detected_sets(data, groups, days, subjects)

        assert "Treated" in groups
        assert "Day03" in days
        assert "S5" in subjects["Treated"]

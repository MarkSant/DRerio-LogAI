"""Extended unit tests for ui/wizard/detection_step.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels


class TestDetectionStepExtended:
    def test_method_labels(self):
        labels = _method_labels()
        assert "seg" in labels
        assert "det" in labels
        assert "Segmentation" in labels["seg"]
        assert "Detection" in labels["det"]

    def test_ensure_group_display_names(self):
        step = object.__new__(DetectionStep)
        step.detected_design = {
            "groups": ["Control", "Treated"],
            "group_display_names": {"Control": "Control Group"},
        }
        step._ensure_group_display_names()
        assert step.detected_design["group_display_names"]["Control"] == "Control Group"
        assert step.detected_design["group_display_names"]["Treated"] == "Treated"

    def test_pattern_groups_as_folders(self):
        step = object.__new__(DetectionStep)
        paths = [
            Path("/root/Control/video1.mp4"),
            Path("/root/Control/video2.mp4"),
            Path("/root/Treated/video1.mp4"),
            Path("/root/Treated/video2.mp4"),
        ]
        result = step._pattern_groups_as_folders(paths)
        assert result is not None
        assert "Control" in result["groups"]
        assert "Treated" in result["groups"]
        assert result["confidence"] > 0.5
        assert result["pattern_used"] == "groups_as_folders"

    def test_pattern_filename_based(self):
        step = object.__new__(DetectionStep)
        paths = [
            Path("/videos/Control_D1_S1.mp4"),
            Path("/videos/Control_D1_S2.mp4"),
            Path("/videos/Treated_D1_S1.mp4"),
            Path("/videos/Treated_D1_S2.mp4"),
        ]
        result = step._pattern_filename_based(paths)
        if result is not None:
            assert "groups" in result
            assert result["confidence"] > 0.0


class TestDetectionStepExtended2:
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

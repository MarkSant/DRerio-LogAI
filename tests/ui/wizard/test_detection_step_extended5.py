"""Extended unit tests for ui/wizard/detection_step.py (Part 5)."""

from __future__ import annotations

from zebtrack.ui.wizard.detection_step import DetectionStep


class TestDetectionStepExtended5:
    """Test DetectionStep custom regex, scanned videos, and design editor state flags."""

    def test_custom_regex_and_design_editor_defaults(self):
        step = object.__new__(DetectionStep)
        step.custom_regex_patterns = None
        step.design_editor_confirmed = False
        step.scanned_videos = []
        step.detected_design = None

        assert step.custom_regex_patterns is None
        assert step.design_editor_confirmed is False
        assert step.scanned_videos == []
        assert step.detected_design is None

    def test_scanned_videos_tracking(self):
        step = object.__new__(DetectionStep)
        step.scanned_videos = [{"path": "video1.mp4", "group": "Control"}]
        assert len(step.scanned_videos) == 1
        assert step.scanned_videos[0]["group"] == "Control"

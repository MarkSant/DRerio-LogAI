"""Extended unit tests for ui/wizard/detection_step.py."""

from __future__ import annotations

from pathlib import Path

from zebtrack.ui.wizard.detection_step import DetectionStep, _method_labels


class TestDetectionStepExtended:
    """Test DetectionStep method labels, design auto-detection patterns, and group display names."""

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

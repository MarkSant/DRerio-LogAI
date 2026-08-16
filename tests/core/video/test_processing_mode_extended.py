"""
Extended unit tests for ProcessingMode and ProcessingReport in core/video/processing_mode.py.
"""

from __future__ import annotations

from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport


class TestProcessingModeExtended:
    """Test ProcessingMode enum values and display names."""

    def test_enum_values(self):
        assert ProcessingMode.MULTI_TRACK == "multi_track"
        assert ProcessingMode.SINGLE_SUBJECT == "single_subject"

    def test_display_name_localization(self):
        assert ProcessingMode.SINGLE_SUBJECT.display_name != ""
        assert ProcessingMode.MULTI_TRACK.display_name != ""


class TestProcessingReportExtended:
    """Test ProcessingReport dataclass and helpers."""

    def test_is_single_subject_true(self):
        report = ProcessingReport(mode=ProcessingMode.SINGLE_SUBJECT, source="video.mp4")
        assert report.is_single_subject() is True
        assert report.source == "video.mp4"

    def test_is_single_subject_false(self):
        report = ProcessingReport(mode=ProcessingMode.MULTI_TRACK)
        assert report.is_single_subject() is False
        assert report.source is None

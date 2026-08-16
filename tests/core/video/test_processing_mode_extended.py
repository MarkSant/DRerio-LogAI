"""Extended unit tests for ProcessingMode and ProcessingReport in core/video/processing_mode.py."""

from __future__ import annotations

import pytest

from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport


class TestProcessingModeExtended:
    """Test ProcessingMode enumeration values and display names."""

    def test_processing_mode_values(self):
        assert ProcessingMode.MULTI_TRACK.value == "multi_track"
        assert ProcessingMode.SINGLE_SUBJECT.value == "single_subject"

    def test_display_name_localization(self):
        assert len(ProcessingMode.SINGLE_SUBJECT.display_name) > 0
        assert len(ProcessingMode.MULTI_TRACK.display_name) > 0
        assert ProcessingMode.SINGLE_SUBJECT.display_name != ProcessingMode.MULTI_TRACK.display_name

    def test_str_enum_behavior(self):
        assert ProcessingMode.MULTI_TRACK == "multi_track"
        assert ProcessingMode.SINGLE_SUBJECT == "single_subject"


class TestProcessingReportExtended:
    """Test ProcessingReport dataclass methods and immutability."""

    def test_processing_report_single_subject(self):
        report = ProcessingReport(mode=ProcessingMode.SINGLE_SUBJECT, source="camera_0")
        assert report.mode == ProcessingMode.SINGLE_SUBJECT
        assert report.source == "camera_0"
        assert report.is_single_subject() is True

    def test_processing_report_multi_track(self):
        report = ProcessingReport(mode=ProcessingMode.MULTI_TRACK)
        assert report.mode == ProcessingMode.MULTI_TRACK
        assert report.source is None
        assert report.is_single_subject() is False

    def test_processing_report_frozen_immutable(self):
        report = ProcessingReport(mode=ProcessingMode.MULTI_TRACK, source="video.mp4")
        with pytest.raises(AttributeError):
            report.mode = ProcessingMode.SINGLE_SUBJECT  # type: ignore[misc]

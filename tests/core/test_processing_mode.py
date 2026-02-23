"""Tests for processing mode utilities."""

from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport


def test_processing_mode_display_names():
    assert ProcessingMode.MULTI_TRACK.display_name == "Multi-indivíduos"
    assert ProcessingMode.SINGLE_SUBJECT.display_name == "Individual"


def test_processing_report_is_single_subject():
    report = ProcessingReport(mode=ProcessingMode.SINGLE_SUBJECT, source="test")
    assert report.is_single_subject() is True

    report_multi = ProcessingReport(mode=ProcessingMode.MULTI_TRACK)
    assert report_multi.is_single_subject() is False

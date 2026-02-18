"""Tests for DetectorContextManager in live_camera_service."""

from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.core.recording.live_camera_service import DetectorContextManager


class DummyDetector:
    def __init__(self):
        self._context = "default"
        self.set_context = MagicMock(side_effect=self._set_context)

    def _set_context(self, value: str) -> None:
        self._context = value


class DummyDetectorService:
    def __init__(self, detector):
        self.detector = detector


def test_context_manager_sets_and_restores_context():
    detector = DummyDetector()
    service = DummyDetectorService(detector)

    with DetectorContextManager(cast(Any, service), "tracking"):
        assert detector._context == "tracking"

    assert detector._context == "default"
    assert detector.set_context.call_count == 2


def test_context_manager_no_detector_service_is_noop():
    with DetectorContextManager(None, "tracking"):
        assert True


def test_context_manager_restore_failure_is_suppressed():
    detector = DummyDetector()

    def failing_set_context(value: str) -> None:
        if value == "default":
            raise AttributeError("restore failed")
        detector._context = value

    detector.set_context.side_effect = failing_set_context
    service = DummyDetectorService(detector)

    with DetectorContextManager(cast(Any, service), "tracking"):
        assert detector._context == "tracking"

    # Should not raise even if restore failed
    assert detector._context == "tracking"

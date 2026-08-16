"""
Extended unit tests for DetectorContextManager.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.live_camera_service import DetectorContextManager


class TestDetectorContextManagerExtended:
    """Test DetectorContextManager context lifecycle and error handling."""

    def test_context_manager_success(self):
        mock_detector = MagicMock()
        mock_detector._context = "idle"
        mock_detector_service = MagicMock()
        mock_detector_service.detector = mock_detector

        with DetectorContextManager(mock_detector_service, "tracking") as mgr:
            assert mgr.saved_context == "idle"
            mock_detector.set_context.assert_called_once_with("tracking")

        # Context restored on exit
        assert mock_detector.set_context.call_count == 2
        mock_detector.set_context.assert_called_with("idle")

    def test_context_manager_exception_restores_context(self):
        mock_detector = MagicMock()
        mock_detector._context = "idle"
        mock_detector_service = MagicMock()
        mock_detector_service.detector = mock_detector

        with pytest.raises(ValueError, match="Boom"):
            with DetectorContextManager(mock_detector_service, "tracking"):
                raise ValueError("Boom")

        # Context restored even after exception
        mock_detector.set_context.assert_called_with("idle")

    def test_context_manager_none_service(self):
        with DetectorContextManager(None, "tracking") as mgr:
            assert mgr.saved_context is None

    def test_context_manager_restore_exception_handled(self):
        mock_detector = MagicMock()
        mock_detector._context = "idle"
        mock_detector.set_context.side_effect = [None, AttributeError("Failed restore")]
        mock_detector_service = MagicMock()
        mock_detector_service.detector = mock_detector

        with DetectorContextManager(mock_detector_service, "tracking"):
            pass  # Should not crash on exit even if set_context raises AttributeError

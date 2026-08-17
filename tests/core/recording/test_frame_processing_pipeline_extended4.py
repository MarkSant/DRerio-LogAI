"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin


class DummyPipeline(FrameProcessingMixin):
    def __init__(self):
        self.root = None
        self.preview_window = None


class TestFrameProcessingPipelineExtended4:
    """Test FrameProcessingMixin preview post status and delegation."""

    def test_post_preview_status_none_window(self):
        pipe = DummyPipeline()
        # Should return silently when preview_window is None
        pipe._post_preview_status("Recording...", "green")

    def test_post_preview_status_direct_call(self):
        pipe = DummyPipeline()
        mock_preview = MagicMock()
        pipe.preview_window = mock_preview

        pipe._post_preview_status("Processing Frame", "white")
        mock_preview.update_status_text.assert_called_once_with("Processing Frame", "white")

    def test_post_preview_status_via_root_after(self):
        pipe = DummyPipeline()
        mock_preview = MagicMock()
        mock_root = MagicMock()
        pipe.preview_window = mock_preview
        pipe.root = mock_root

        pipe._post_preview_status("Syncing...", "yellow")
        mock_root.after.assert_called_once_with(
            0, mock_preview.update_status_text, "Syncing...", "yellow"
        )

    def test_post_preview_status_red_error(self):
        pipe = DummyPipeline()
        mock_preview = MagicMock()
        pipe.preview_window = mock_preview

        pipe._post_preview_status("Camera Error", "red")
        mock_preview.update_status_text.assert_called_once_with("Camera Error", "red")

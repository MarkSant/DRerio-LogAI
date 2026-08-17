"""Extended unit tests for core/recording/frame_processing_pipeline.py (Part 5)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin


class DummyPipeline(FrameProcessingMixin):
    def __init__(self):
        self._dropped_frames_processing = 0
        self._dropped_frames_video = 0
        self._video_frames_written = 0
        self._live_detected_frames = 0
        self._analysis_lag_frames = 0
        self.preview_window = None
        self.root = None


class TestFrameProcessingPipelineExtended5:
    """Test FrameProcessingMixin queue metrics, frame counters, and preview status."""

    def test_pipeline_initial_metrics(self):
        pipe = DummyPipeline()
        assert pipe._dropped_frames_processing == 0
        assert pipe._dropped_frames_video == 0
        assert pipe._video_frames_written == 0
        assert pipe._live_detected_frames == 0
        assert pipe._analysis_lag_frames == 0

    def test_post_preview_status_no_preview(self):
        pipe = DummyPipeline()
        pipe.preview_window = None
        # Should return early without error
        pipe._post_preview_status("Recording...", "green")

    def test_post_preview_status_direct_call_without_root(self):
        pipe = DummyPipeline()
        mock_prev = MagicMock()
        pipe.preview_window = mock_prev
        pipe.root = None

        pipe._post_preview_status("Ready", "white")
        mock_prev.update_status_text.assert_called_once_with("Ready", "white")

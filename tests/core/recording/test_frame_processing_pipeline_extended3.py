"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended3:
    """Test FrameProcessingMixin queue operations, unpacking, and metadata."""

    def test_default_constants(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_attributes(self):
        meta = VideoFrameMeta(
            pipeline_frame=100,
            t_capture_perf=123.456,
            t_capture_wall=1600000000.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )

        assert meta.pipeline_frame == 100
        assert meta.t_capture_perf == 123.456
        assert meta.t_capture_wall == 1600000000.0
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

    def test_unpack_video_item_legacy(self):
        raw_frame = MagicMock()
        frame, meta = _unpack_video_item(raw_frame)
        assert frame is raw_frame
        assert meta is None

    def test_unpack_video_item_tuple(self):
        raw_frame = MagicMock()
        item = (42, 10.5, 20.5, True, False, raw_frame)
        frame, meta = _unpack_video_item(item)
        assert frame is raw_frame
        assert meta is not None
        assert meta.pipeline_frame == 42
        assert meta.t_capture_perf == 10.5
        assert meta.t_capture_wall == 20.5
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

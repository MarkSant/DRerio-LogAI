"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

import numpy as np

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended:
    """Test frame processing pipeline metadata extraction, item unpacking, and constants."""

    def test_default_constants(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_attributes(self):
        meta = VideoFrameMeta(
            pipeline_frame=42,
            t_capture_perf=100.5,
            t_capture_wall=1700000000.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 42
        assert meta.t_capture_perf == 100.5
        assert meta.t_capture_wall == 1700000000.0
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

    def test_unpack_video_item_tuple_format(self):
        fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        item = (15, 100.1, 1700.2, True, True, fake_frame)

        frame, meta = _unpack_video_item(item)
        assert frame is fake_frame
        assert meta is not None
        assert meta.pipeline_frame == 15
        assert meta.t_capture_perf == 100.1
        assert meta.is_analysis_frame is True

    def test_unpack_video_item_legacy_frame_only(self):
        fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        frame, meta = _unpack_video_item(fake_frame)
        assert frame is fake_frame
        assert meta is None

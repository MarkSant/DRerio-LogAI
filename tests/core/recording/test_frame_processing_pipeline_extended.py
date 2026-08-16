"""
Extended unit tests for FrameProcessingPipeline helpers and data structures.
"""

from __future__ import annotations

import numpy as np

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended:
    """Test VideoFrameMeta named tuple and unpack helpers."""

    def test_default_arduino_exit_grace_frames_constant(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_fields(self):
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

    def test_unpack_video_item_legacy_frame_only(self):
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        frame, meta = _unpack_video_item(dummy_frame)
        assert frame is dummy_frame
        assert meta is None

    def test_unpack_video_item_6tuple(self):
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        # 6-tuple: (frame_count, perf, wall, is_analysis, queued, frame)
        item = (1, 10.0, 20.0, True, True, dummy_frame)
        frame, meta = _unpack_video_item(item)
        assert frame is dummy_frame
        assert meta is not None
        assert meta.pipeline_frame == 1
        assert meta.t_capture_perf == 10.0
        assert meta.t_capture_wall == 20.0
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is True

    def test_unpack_video_item_invalid_tuple(self):
        # 2-tuple that is not a 6-tuple returns the raw item and None
        item = ("dummy", "not_meta")
        frame, meta = _unpack_video_item(item)
        assert frame == item
        assert meta is None

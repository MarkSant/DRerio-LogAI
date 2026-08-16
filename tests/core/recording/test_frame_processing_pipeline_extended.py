"""
Extended unit tests for FrameProcessingPipeline helpers and data structures.
"""

from __future__ import annotations

import queue

import numpy as np

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    FrameProcessingMixin,
    VideoFrameMeta,
    _unpack_video_item,
)


class DummyPipeline(FrameProcessingMixin):
    """Test harness for FrameProcessingMixin."""

    def __init__(self):
        self.frame_queue = queue.Queue()
        self.video_queue = queue.Queue()
        self._processing_times: list[float] = []
        self._fps_adjustment_interval = 10
        self._target_fps = 30.0
        self._current_fps = 30.0
        self._frame_skip_count = 0


class TestFrameProcessingPipelineExtended:
    """Test VideoFrameMeta named tuple, unpack helpers, queues, and dynamic FPS."""

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
        item = ("dummy", "not_meta")
        frame, meta = _unpack_video_item(item)
        assert frame == item
        assert meta is None

    def test_clear_queues(self):
        pipeline = DummyPipeline()
        pipeline.frame_queue.put("frame1")
        pipeline.video_queue.put("video1")
        assert pipeline.frame_queue.qsize() == 1
        assert pipeline.video_queue.qsize() == 1

        pipeline._clear_queues()
        assert pipeline.frame_queue.empty()
        assert pipeline.video_queue.empty()

    def test_adjust_fps_dynamically(self):
        pipeline = DummyPipeline()
        assert pipeline._adjust_fps_dynamically(1, 0.01) is True

    def test_adjust_fps_slow_down_triggers_skip(self):
        pipeline = DummyPipeline()
        pipeline._target_fps = 30.0
        # Feed 15 slow frames (e.g. 100ms each = 10 FPS, below target * 0.7 = 21 FPS)
        for i in range(1, 16):
            pipeline._adjust_fps_dynamically(i, 0.10)
        assert pipeline._frame_skip_count >= 1

    def test_adjust_fps_speed_up_reduces_skip(self):
        pipeline = DummyPipeline()
        pipeline._target_fps = 30.0
        pipeline._frame_skip_count = 2
        # Feed 15 fast frames (e.g. 10ms each = 100 FPS, above target * 1.2 = 36 FPS)
        for i in range(1, 16):
            pipeline._adjust_fps_dynamically(i, 0.01)
        assert pipeline._frame_skip_count <= 1

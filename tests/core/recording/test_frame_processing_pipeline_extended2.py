"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    FrameProcessingMixin,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended2:
    """Test FrameProcessingMixin helpers, video metadata unpacking, and Arduino latency hooks."""

    def test_default_constants(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_namedtuple(self):
        meta = VideoFrameMeta(
            pipeline_frame=42,
            t_capture_perf=123.456,
            t_capture_wall=1700000.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 42
        assert meta.t_capture_perf == 123.456
        assert meta.t_capture_wall == 1700000.0
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

    def test_unpack_video_item_legacy_format(self):
        frame_raw = "raw_frame_matrix"
        frame, meta = _unpack_video_item(frame_raw)
        assert frame == "raw_frame_matrix"
        assert meta is None

    def test_unpack_video_item_tuple_format(self):
        item = (10, 100.5, 200.5, True, False, "frame_data")
        frame, meta = _unpack_video_item(item)
        assert frame == "frame_data"
        assert meta is not None
        assert meta.pipeline_frame == 10
        assert meta.t_capture_perf == 100.5
        assert meta.t_capture_wall == 200.5
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

    def test_on_arduino_latency_sample_logging(self):
        mixin = object.__new__(FrameProcessingMixin)
        mock_log = MagicMock()
        mixin._closed_loop_log = mock_log
        mixin._arduino_inverted_ack_seen = set()

        ctx = {"roi": "Zone1", "edge": "enter", "token": 1}
        mixin._on_arduino_latency_sample(ctx, 10.0, 10.05, "ACK: Zone1 ON")

        mock_log.on_sample.assert_called_once_with(ctx, 10.0, 10.05, "ACK: Zone1 ON")

    def test_maybe_create_closed_loop_log_none_when_no_output_folder(self):
        mixin = object.__new__(FrameProcessingMixin)
        mixin.recorder = MagicMock()
        mixin.recorder.output_folder = None

        assert mixin._maybe_create_closed_loop_log() is None

    def test_clear_queues(self):
        mixin = object.__new__(FrameProcessingMixin)
        mixin.frame_queue = queue.Queue()
        mixin.video_queue = queue.Queue()

        mixin.frame_queue.put("frame1")
        mixin.frame_queue.put("frame2")
        mixin.video_queue.put("vid1")

        assert not mixin.frame_queue.empty()
        assert not mixin.video_queue.empty()

        mixin._clear_queues()

        assert mixin.frame_queue.empty()
        assert mixin.video_queue.empty()

    def test_arduino_zone_session_end_sweep_disabled(self):
        mixin = object.__new__(FrameProcessingMixin)
        mixin._arduino_zone_enabled = False
        mixin._arduino_session_end_tokens = [1, 2]

        # Should return without raising or touching manager
        mixin._arduino_zone_session_end_sweep()

    def test_finalize_closed_loop_log_none(self):
        mixin = object.__new__(FrameProcessingMixin)
        mixin._closed_loop_log = None

        # Should safely return
        mixin._finalize_closed_loop_log()
        assert mixin._closed_loop_log is None

    def test_adjust_fps_dynamically(self):
        mixin = object.__new__(FrameProcessingMixin)
        mixin._processing_times = []
        mixin._frame_skip_count = 0
        mixin._current_fps = 30.0
        mixin._target_fps = 30.0
        mixin._fps_adjustment_interval = 5

        # Frame fast -> should not skip
        should_process = mixin._adjust_fps_dynamically(1, 0.01)
        assert should_process is True
        assert len(mixin._processing_times) == 1

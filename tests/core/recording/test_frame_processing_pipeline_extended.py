"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    FrameProcessingMixin,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended:
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


class TestFrameProcessingPipelineExtended2:
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


class TestFrameProcessingPipelineExtended3:
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


class DummyPipeline(FrameProcessingMixin):
    def __init__(self):
        self.root = None
        self.preview_window = None


class TestFrameProcessingPipelineExtended4:
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


class DummyPipelinePart5(FrameProcessingMixin):
    def __init__(self):
        self._dropped_frames_processing = 0
        self._dropped_frames_video = 0
        self._video_frames_written = 0
        self._live_detected_frames = 0
        self._analysis_lag_frames = 0
        self.preview_window = None
        self.root = None


class TestFrameProcessingPipelineExtended5:
    def test_pipeline_initial_metrics(self):
        pipe = DummyPipelinePart5()
        assert pipe._dropped_frames_processing == 0
        assert pipe._dropped_frames_video == 0
        assert pipe._video_frames_written == 0
        assert pipe._live_detected_frames == 0
        assert pipe._analysis_lag_frames == 0

    def test_post_preview_status_no_preview(self):
        pipe = DummyPipelinePart5()
        pipe.preview_window = None
        # Should return early without error
        pipe._post_preview_status("Recording...", "green")

    def test_post_preview_status_direct_call_without_root(self):
        pipe = DummyPipelinePart5()
        mock_prev = MagicMock()
        pipe.preview_window = mock_prev
        pipe.root = None

        pipe._post_preview_status("Ready", "white")
        mock_prev.update_status_text.assert_called_once_with("Ready", "white")


class DummyPipelineIsolated(FrameProcessingMixin):
    pass


class TestFrameProcessingPipelineExtended6:
    def test_define_arena_from_detections_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        with pytest.raises(NotImplementedError, match="_define_arena_from_detections"):
            pipe._define_arena_from_detections()

    def test_start_recording_after_arena_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        with pytest.raises(NotImplementedError, match="_start_recording_after_arena"):
            pipe._start_recording_after_arena()

    def test_run_multi_aquarium_detection_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        with pytest.raises(NotImplementedError, match="_run_multi_aquarium_detection"):
            pipe._run_multi_aquarium_detection(dummy_frame, 1, None)


class TestFrameProcessingPipelineExtended7:
    def test_default_arduino_exit_grace_frames(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_named_tuple(self):
        meta = VideoFrameMeta(
            pipeline_frame=10,
            t_capture_perf=123.456,
            t_capture_wall=789.012,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 10
        assert meta.t_capture_perf == 123.456
        assert meta.t_capture_wall == 789.012
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is True

    def test_unpack_video_item_legacy_frame_only(self):
        frame_data = "raw_frame"
        frame, meta = _unpack_video_item(frame_data)
        assert frame == "raw_frame"
        assert meta is None

    def test_unpack_video_item_with_meta(self):
        item = (1, 10.0, 20.0, True, False, "raw_frame_data")
        frame, extracted_meta = _unpack_video_item(item)
        assert frame == "raw_frame_data"
        assert extracted_meta is not None
        assert extracted_meta.pipeline_frame == 1
        assert extracted_meta.t_capture_perf == 10.0
        assert extracted_meta.t_capture_wall == 20.0
        assert extracted_meta.is_analysis_frame is True
        assert extracted_meta.queued_for_analysis is False

    def test_unpack_video_item_short_tuple_fallback(self):
        short_item = ("item1", "item2", "item3")
        frame, meta = _unpack_video_item(short_item)
        assert frame == short_item
        assert meta is None


class TestFrameProcessingPipelineExtended8:
    def test_video_frame_meta_equality(self):
        meta1 = VideoFrameMeta(
            pipeline_frame=5,
            t_capture_perf=10.0,
            t_capture_wall=20.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        meta2 = VideoFrameMeta(
            pipeline_frame=5,
            t_capture_perf=10.0,
            t_capture_wall=20.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta1 == meta2

    def test_video_frame_meta_immutability(self):
        meta = VideoFrameMeta(
            pipeline_frame=1,
            t_capture_perf=None,
            t_capture_wall=None,
            is_analysis_frame=False,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 1
        assert meta.t_capture_perf is None
        assert meta.t_capture_wall is None

    def test_video_frame_meta_attributes_retrieval(self):
        meta = VideoFrameMeta(
            pipeline_frame=100,
            t_capture_perf=1.23,
            t_capture_wall=4.56,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 100
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is True


class TestFrameProcessingPipelineExtended9:
    def test_video_frame_meta_default_flags(self):
        meta = VideoFrameMeta(
            pipeline_frame=0,
            t_capture_perf=0.0,
            t_capture_wall=0.0,
            is_analysis_frame=False,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 0
        assert meta.is_analysis_frame is False
        assert meta.queued_for_analysis is False

    def test_video_frame_meta_perf_timestamp(self):
        meta = VideoFrameMeta(
            pipeline_frame=42,
            t_capture_perf=100.5,
            t_capture_wall=1700000000.0,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 42
        assert meta.t_capture_perf == 100.5
        assert meta.t_capture_wall == 1700000000.0

    def test_video_frame_meta_analysis_flag(self):
        meta = VideoFrameMeta(
            pipeline_frame=1,
            t_capture_perf=0.0,
            t_capture_wall=0.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False

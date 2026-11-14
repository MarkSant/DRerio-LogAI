"""Extended unit tests for core/recording/frame_processing_pipeline.py."""

from __future__ import annotations

import math
import queue
import threading
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.core.conditions import (
    ClassPresence,
    ClassTarget,
    External,
    FrameReached,
    Hold,
    Persist,
    RoiEdge,
    TimeReached,
    WindowSpec,
    read_artifact,
)
from zebtrack.core.conditions.presets import external_trigger_preset
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
        """Both queues end empty; a video item with metadata gets its ledger row (#636)."""
        mixin = object.__new__(FrameProcessingMixin)
        mixin.frame_queue = queue.Queue()
        mixin.video_queue = queue.Queue()
        recorded: list[tuple] = []
        mixin._ledger_record = lambda *args, **kwargs: recorded.append((args, kwargs))  # type: ignore[method-assign]

        mixin.frame_queue.put("frame1")
        mixin.frame_queue.put("frame2")
        mixin.video_queue.put("vid1")  # legacy item: no metadata, no row
        mixin.video_queue.put((7, 1.5, 100.5, True, True, "vid2"))

        mixin._clear_queues()

        assert mixin.frame_queue.empty()
        assert mixin.video_queue.empty()
        ((args, kwargs),) = recorded
        assert args == (7, 1.5, 100.5, "dropped_on_stop")
        assert kwargs["is_analysis_frame"] is True

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


# ---------------------------------------------------------------------------
# Live analysis window, capture clock and 3c heartbeat (ADR-011, v8 F5)
#
# These drive the REAL ``_processing_loop`` over a scripted frame queue, so the
# order of the calls inside the loop (trajectory -> 3c -> window -> Arduino) is
# what is under test, not a re-implementation of it.
# ---------------------------------------------------------------------------

T0 = 500.0  # perf_counter instant of the first captured frame of the session


class _ScriptedQueue:
    """Frame queue that ends the loop once its items are consumed."""

    def __init__(self, items, exit_event):
        self._items = list(items)
        self._exit_event = exit_event

    def get(self, timeout=None):
        if self._items:
            return self._items.pop(0)
        self._exit_event.set()
        raise queue.Empty


class _FakeLedger:
    def __init__(self, origin):
        self.origin_perf = origin

    def current_fps_measured(self):
        return 30.0


class _FakeRecorder:
    def __init__(self, folder):
        self.start_time = 1.0  # truthy: recording
        self.output_folder = str(folder)
        self.base_name = "sessao"
        self.trajectory: list[tuple] = []
        self.objects: list[tuple] = []

    def write_detection_data(self, timestamp, frame_number, detections):
        self.trajectory.append((frame_number, list(detections)))

    def write_object_data(self, timestamp, frame_number, t_event_s, observations):
        self.objects.append((frame_number, t_event_s, list(observations)))


class _FakeManager:
    def __init__(self):
        self.sent: list[int] = []
        self.sink: Any = None

    def is_connected(self):
        return True

    def enqueue(self, token):
        self.sent.append(token)
        return True

    def set_event_sink(self, sink):
        self.sink = sink

    def set_latency_sink(self, sink):
        pass


class _FakeRoot:
    def __init__(self):
        self.calls: list[tuple] = []

    def after(self, delay, fn, *args):
        self.calls.append((fn, args))


class _FakeDetector:
    """Returns scripted detections/observations per frame number."""

    def __init__(self, script):
        self.script = script  # frame -> (detections, observations)
        self._observations: list = []
        self.roi_names = ["A"]
        self.scaled_roi_polygons = [np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.int32)]
        self.class_role_map = None
        self.frames: list[int] = []

    def detect(self, frame, context, conf_threshold=None):
        current = self.frames.pop(0)
        detections, observations = self.script.get(current, ([], []))
        self._observations = list(observations)
        return list(detections), None

    def pop_class_observations(self):
        out, self._observations = self._observations, []
        return out

    def pop_track_masks(self, detections):
        return {}

    def draw_overlay(self, frame, detections):
        pass


class _LoopHarness(FrameProcessingMixin):
    def __init__(self, tmp_path, *, window=None, script=None, project_data=None, origin=T0):
        self.exit_event = threading.Event()
        self.manager = _FakeManager()
        self.detector = _FakeDetector(script or {})
        harness: Any = self
        harness.controller = SimpleNamespace(arduino_manager=self.manager)
        harness.detector_service = SimpleNamespace(detector=self.detector)
        harness.project_manager = SimpleNamespace(
            project_data=project_data or {},
            get_zone_data=lambda: SimpleNamespace(aquariums=[]),
        )
        harness.settings = None
        harness.recorder = _FakeRecorder(tmp_path)
        harness.event_bus = MagicMock()
        harness.root = _FakeRoot()
        harness.preview_window = None
        self._use_external_preview = True
        self._aquarium_detection_phase = False
        self.analysis_interval_frames = 1
        self.display_interval_frames = 10_000
        self._last_captured_frame = 0
        self._analysis_lag_warning_threshold = 10_000
        self._live_detected_frames = 0
        self._experiment_id = "exp"
        self._frame_ledger = _FakeLedger(origin)
        self._analysis_window_raw = (
            None if window is None else window.model_dump(mode="json", by_alias=True)
        )
        self._last: list = []

    # facade bits the loop touches
    def get_last_detections(self):
        return self._last

    def set_last_detections(self, detections):
        self._last = detections

    def _on_session_active(self):
        pass

    def finish_session_early(self):
        return True

    def run(self, frames):
        """``frames``: list of ``(frame_number, capture_perf)``."""
        items = [(f, np.zeros((4, 4, 3), dtype=np.uint8), capture) for f, capture in frames]
        self.detector.frames = [f for f, _ in frames]
        harness: Any = self
        harness.frame_queue = _ScriptedQueue(items, self.exit_event)
        self._processing_loop()

    def published_states(self):
        """``ANALYSIS_WINDOW_STATE_CHANGED`` states scheduled on the Tk thread."""
        root: Any = self.root
        return [
            args[0].state
            for fn, args in root.calls
            if getattr(fn, "__name__", "") == "_publish_window_state"
        ]

    def finish_requests(self):
        root: Any = self.root
        return [fn for fn, _ in root.calls if getattr(fn, "__name__", "") == "finish_session_early"]

    def arm(self):
        """What the processing loop does before its first frame."""
        self._reset_arduino_zone_state()
        self._reset_condition_runtime()


def _rat(conf=0.9):
    return {"class_name": "rat", "role": "subject", "confidence": conf, "bbox": (1, 1, 3, 3)}


def _box(cx, cy):
    return (cx - 1, cy - 1, cx + 1, cy + 1, 0.9, 1, 0)


class TestObjectSidecarLive:
    def test_heartbeat_on_every_analysed_frame_even_without_detections(self, tmp_path):
        h = _LoopHarness(tmp_path, script={2: ([_box(5, 5)], [_rat()])})
        h.run([(1, T0 + 1.0), (2, T0 + 2.0), (3, T0 + 3.0)])

        recorder: Any = h.recorder
        assert [frame for frame, _ in recorder.trajectory] == [2]  # schema unchanged
        assert [frame for frame, _, _ in recorder.objects] == [1, 2, 3]
        assert recorder.objects[1][2] == [_rat()]

    def test_t_event_is_the_capture_clock_from_the_ledger_anchor(self, tmp_path):
        h = _LoopHarness(tmp_path)
        h.run([(7, T0 + 2.5)])
        recorder: Any = h.recorder
        ((frame, t_event, _obs),) = recorder.objects
        assert frame == 7
        assert t_event == pytest.approx(2.5)

    def test_unknown_capture_clock_is_nan_never_the_processing_clock(self, tmp_path):
        h = _LoopHarness(tmp_path, origin=None)
        h.run([(1, T0 + 1.0)])
        recorder: Any = h.recorder
        assert math.isnan(recorder.objects[0][1])

    def test_capture_thread_pins_the_origin_on_the_ledger(self):
        pipeline = object.__new__(FrameProcessingMixin)
        ledger = MagicMock()
        pipeline._frame_ledger = ledger
        pipeline._pin_capture_origin(12.5, 1_700_000_000.0)
        ledger.pin_origin.assert_called_once_with(12.5, 1_700_000_000.0)


class TestAnalysisWindowLive:
    def test_no_window_no_runtime_no_artifact(self, tmp_path):
        h = _LoopHarness(tmp_path)
        h.run([(1, T0 + 1.0)])
        assert h.published_states() == []
        assert not list(tmp_path.glob("7_AnalysisWindow_*"))
        assert h.manager.sink is None

    def test_window_dates_frames_by_capture_and_writes_the_artifact(self, tmp_path):
        spec = WindowSpec(start=TimeReached(clock="video", at_s=2.0))
        h = _LoopHarness(tmp_path, window=spec)
        h.run([(1, T0 + 1.0), (2, T0 + 2.2), (3, T0 + 3.0)])

        artifact = read_artifact(tmp_path / "7_AnalysisWindow_sessao.json")
        assert artifact is not None
        assert artifact.clock == "capture_perf"
        assert artifact.online.start is not None
        assert artifact.online.start.frame == 2
        assert artifact.online.start.t_s == pytest.approx(2.2)
        assert artifact.fps_video == pytest.approx(30.0)
        assert h.published_states() == ["waiting_start", "in_analysis", "finished"]
        assert h.manager.sink is None  # unregistered at session end

    def test_start_never_met_is_published(self, tmp_path):
        h = _LoopHarness(tmp_path, window=WindowSpec(start=External(source="manual")))
        h.run([(1, T0 + 1.0)])
        assert h.published_states() == ["waiting_start", "start_not_met"]

    def test_arduino_code_is_claimed_by_a_window_that_waits_for_it(self, tmp_path):
        h = _LoopHarness(tmp_path, window=external_trigger_preset())
        h.arm()
        assert h.manager.sink is not None
        assert h.manager.sink(1, T0 + 0.5) is True  # coordinators never see it

    def test_arduino_code_is_not_claimed_by_a_window_that_ignores_it(self, tmp_path):
        h = _LoopHarness(tmp_path, window=WindowSpec(start=External(source="manual")))
        h.arm()
        assert h.manager.sink(0, T0 + 0.5) is False

    def test_end_session_goes_through_finish_session_early_once(self, tmp_path):
        h = _LoopHarness(tmp_path, window=external_trigger_preset())
        h.arm()
        h.manager.sink(1, T0 + 0.5)
        h._step_condition_runtime(1, T0 + 1.0, [], [])
        h.manager.sink(0, T0 + 1.5)
        h._step_condition_runtime(2, T0 + 2.0, [], [])
        h._step_condition_runtime(3, T0 + 3.0, [], [])
        h._finalize_condition_runtime()

        # On the Tk thread, through the keep_data path, exactly once.
        assert len(h.finish_requests()) == 1

    def test_mark_does_not_end_the_session(self, tmp_path):
        spec = WindowSpec(
            start=External(source="arduino", code=1), stop=External(source="arduino", code=0)
        )
        h = _LoopHarness(tmp_path, window=spec)
        h.arm()
        h.manager.sink(1, T0)
        h._step_condition_runtime(1, T0 + 1.0, [], [])
        h.manager.sink(0, T0 + 1.5)
        h._step_condition_runtime(2, T0 + 2.0, [], [])

        runtime: Any = h._condition_runtime
        assert runtime.phase.value == "finished"
        assert h.finish_requests() == []

    def test_frame_without_capture_stamp_is_not_dated(self, tmp_path):
        h = _LoopHarness(tmp_path, window=WindowSpec())
        h.arm()
        h._step_condition_runtime(1, None, [], [])
        runtime: Any = h._condition_runtime
        assert runtime.phase.value == "waiting_start"

    def test_manual_press_reaches_the_window(self, tmp_path):
        h = _LoopHarness(tmp_path, window=WindowSpec(start=External(source="manual")))
        assert h.push_manual_condition_event() is False  # no session yet
        h.arm()
        assert h.push_manual_condition_event() is True
        h._step_condition_runtime(1, time.perf_counter() + 1.0, [], [])
        runtime: Any = h._condition_runtime
        assert runtime.phase.value == "in_analysis"

    def test_subject_rois_follow_the_arduino_rule(self, tmp_path):
        spec = WindowSpec(start=RoiEdge(roi="A", edge="enter"))
        h = _LoopHarness(tmp_path, window=spec)
        h.arm()
        h._step_condition_runtime(1, T0 + 1.0, [_box(50, 50)], [])
        h._step_condition_runtime(2, T0 + 2.0, [_box(5, 5)], [])
        runtime: Any = h._condition_runtime
        assert runtime.phase.value == "in_analysis"
        assert runtime.result.start.frame == 2

    def test_classes_come_from_the_class_observations(self, tmp_path):
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_class("Rat")), hold=Hold(seconds=1.0)
            )
        )
        h = _LoopHarness(tmp_path, window=spec)
        h.arm()
        h._step_condition_runtime(1, T0 + 1.0, [], [_rat()])
        h._step_condition_runtime(2, T0 + 2.0, [], [_rat()])
        runtime: Any = h._condition_runtime
        assert runtime.result.start.t_s == pytest.approx(1.0)

    def test_multi_aquarium_session_arms_no_single_window(self, tmp_path):
        """The session's aquariums decide it (#635, #656).

        This used to stub ``get_zone_data()`` with ``aquariums`` — something
        the aquarium-0 shim never returns, so in the app the window was armed
        in 2-aquarium sessions and fed with both aquariums' detections. Since
        #656 each aquarium gets its own window instead of a shared one.
        """
        h = _LoopHarness(tmp_path, window=WindowSpec())
        h._live_multi_zone_data = SimpleNamespace(aquariums=[_aquarium(0), _aquarium(1)])
        h.arm()
        assert h._condition_runtime is None

    def test_single_aquarium_session_arms_the_window(self, tmp_path):
        h = _LoopHarness(tmp_path, window=WindowSpec())
        h._live_multi_zone_data = None
        h.arm()
        assert h._condition_runtime is not None


ZONE_PROJECT = {
    "use_arduino": True,
    "arduino_bindings": [{"roi": "A", "on_enter": 1, "on_exit": 2}],
}


class TestArduinoCommandsInsideTheWindow:
    @staticmethod
    def _spy(h):
        sent_at_frame: dict[int, list[int]] = {}
        original = h._dispatch_arduino_zone_commands

        def _dispatch(detections, frame_number=None, *args):
            original(detections, frame_number, *args)
            sent_at_frame[frame_number] = list(h.manager.sent)

        h._dispatch_arduino_zone_commands = _dispatch
        return sent_at_frame

    def test_nothing_before_start_and_sweep_at_stop(self, tmp_path):
        spec = WindowSpec(start=FrameReached(frame=2), stop=FrameReached(frame=4))
        script = {f: ([_box(5, 5)], [_rat()]) for f in range(1, 7)}
        h = _LoopHarness(tmp_path, window=spec, script=script, project_data=ZONE_PROJECT)
        sent_at_frame = self._spy(h)
        h.run([(f, T0 + f) for f in range(1, 7)])

        assert sent_at_frame[1] == []  # before START: nothing
        assert sent_at_frame[2] == [1]  # the START frame dispatches the enter
        # exit tokens swept AT THE STOP frame, not at the end of the session
        assert sent_at_frame[4] == [1, 2]
        assert h.manager.sent == [1, 2]  # nothing after STOP, no second sweep

    def test_window_never_opened_sends_nothing_at_all(self, tmp_path):
        script = {f: ([_box(5, 5)], [_rat()]) for f in range(1, 4)}
        h = _LoopHarness(
            tmp_path,
            window=WindowSpec(start=External(source="manual")),
            script=script,
            project_data=ZONE_PROJECT,
        )
        h.run([(f, T0 + f) for f in range(1, 4)])
        assert h.manager.sent == []

    def test_open_window_sweeps_once_at_session_end(self, tmp_path):
        script = {f: ([_box(5, 5)], [_rat()]) for f in range(1, 4)}
        h = _LoopHarness(
            tmp_path,
            window=WindowSpec(start=FrameReached(frame=1)),
            script=script,
            project_data=ZONE_PROJECT,
        )
        h.run([(f, T0 + f) for f in range(1, 4)])
        assert h.manager.sent == [1, 2]

    def test_without_window_session_end_still_sweeps(self, tmp_path):
        h = _LoopHarness(tmp_path, script={1: ([_box(5, 5)], [_rat()])}, project_data=ZONE_PROJECT)
        h.run([(1, T0 + 1.0)])
        assert h.manager.sent == [1, 2]


class _PartitionedRecorder(_FakeRecorder):
    """Parent of a multi-aquarium session: partitioned writers only."""

    def __init__(self, folder):
        super().__init__(folder)
        self.partitioned_objects: list[tuple] = []

    def write_partitioned_object_data(
        self, timestamp, frame_number, t_event_s, observations, aquarium_polygons
    ):
        self.partitioned_objects.append((frame_number, t_event_s, dict(aquarium_polygons)))


class TestMultiAquariumProcessingLoop:
    """#635: the loop decided "multi" from ``get_zone_data()``, the aquarium-0
    shim, so the partitioned branch was unreachable in the app."""

    def _harness(self, tmp_path):
        from zebtrack.core.detection import ZoneData

        h = _LoopHarness(tmp_path, script={1: ([_box(5, 5)], [])})
        project_manager: Any = h.project_manager
        # What the app really returns: never ``aquariums``.
        project_manager.get_zone_data = lambda: ZoneData(polygon=[[0, 0], [9, 9]])
        h.recorder = _PartitionedRecorder(tmp_path)
        polygons = {0: [[0, 0], [2, 0], [2, 4], [0, 4]], 1: [[2, 0], [4, 0], [4, 4], [2, 4]]}
        h._live_multi_zone_data = SimpleNamespace(
            aquariums=[SimpleNamespace(id=k, polygon=v) for k, v in polygons.items()]
        )
        calls: list[tuple] = []

        def _multi(frame, frame_number, zone_data):
            calls.append((frame_number, zone_data))
            return [_box(1, 1)]

        harness: Any = h
        harness._run_multi_aquarium_detection = _multi
        return h, calls, polygons

    def test_two_aquariums_run_the_partitioned_detector(self, tmp_path):
        h, calls, _polygons = self._harness(tmp_path)
        h.run([(1, T0 + 1.0)])

        assert [frame for frame, _ in calls] == [1]
        assert calls[0][1] is h._live_multi_zone_data
        assert h.detector.frames == [1]  # the single detector never ran

    def test_rows_are_not_duplicated_into_the_parent(self, tmp_path):
        """The partitioned call already wrote them per aquarium."""
        h, _calls, _polygons = self._harness(tmp_path)
        h.run([(1, T0 + 1.0)])

        recorder: Any = h.recorder
        assert recorder.trajectory == []

    def test_object_heartbeat_goes_to_every_aquarium(self, tmp_path):
        h, _calls, polygons = self._harness(tmp_path)
        h.run([(1, T0 + 1.0)])

        recorder: Any = h.recorder
        assert recorder.objects == []
        ((frame, t_event, sent_polygons),) = recorder.partitioned_objects
        assert frame == 1
        assert t_event == pytest.approx(1.0)
        assert sent_polygons == polygons


class TestOneSamplingCadence:
    """#637: the processing thread decimated a SECOND time, by the count of frames
    it happened to receive, so the effective cadence drifted from N to ~N^2."""

    def test_analysed_frames_follow_one_cadence_whatever_arrives(self, tmp_path):
        h = _LoopHarness(tmp_path)
        h.analysis_interval_frames = 3
        # A thinned stream: the opportunistic frames 5 and 8 never made it.
        h.run([(f, T0 + f) for f in (1, 2, 3, 4, 6, 7, 9)])

        recorder: Any = h.recorder
        # Offset 0, counted from the first captured frame (pipeline frame 1):
        # frames 1, 4, 7 — never the frames that happened to arrive (#637, #638).
        assert [frame for frame, _t, _obs in recorder.objects] == [1, 4, 7]

    def test_the_processing_thread_honours_the_offset(self, tmp_path):
        """#638: the processing thread agrees with the capture thread's offset."""
        h = _LoopHarness(tmp_path)
        h.analysis_interval_frames = 3
        h.analysis_offset_frames = 1
        h.run([(f, T0 + f) for f in range(1, 10)])

        recorder: Any = h.recorder
        # Pipeline frames are 1-based: source indices 1, 4, 7 -> frames 2, 5, 8.
        assert [frame for frame, _t, _obs in recorder.objects] == [2, 5, 8]

    def test_slow_inference_never_thins_the_cadence(self, tmp_path, monkeypatch):
        """#669: the cadence is ``analysis_interval_frames`` and nothing else.

        A "dynamic FPS" step used to run after every ``detect()``: it measured
        inference throughput, raised a ``_frame_skip_count`` against a fixed
        30 fps target and returned a skip verdict that only reached a debug log.
        Inference that takes 100 ms per frame (10/s, well under 0.7 x 30) is the
        load that armed it. The loop must still analyse exactly the cadence's
        frames, carry no skip state and say nothing about frame skipping.
        """
        import structlog.testing

        from zebtrack.core.recording import frame_processing_pipeline as fpp

        clock = {"now": 1_000.0}

        def slow_clock() -> float:
            # Every wall-clock read moves 50 ms, so any timing taken around
            # ``detect()`` sees ~100 ms of "inference" per analysed frame.
            clock["now"] += 0.05
            return clock["now"]

        monkeypatch.setattr(fpp.time, "time", slow_clock)

        h = _LoopHarness(tmp_path)
        h.analysis_interval_frames = 2
        frames = list(range(1, 81))
        with structlog.testing.capture_logs() as logs:
            h.run([(f, T0 + f) for f in frames])

        recorder: Any = h.recorder
        expected = [f for f in frames if (f - 1) % 2 == 0]
        assert [frame for frame, _t, _obs in recorder.objects] == expected

        skip_events = {
            "live_camera_service.fps_too_low",
            "live_camera_service.fps_improved",
            "live_camera_service.frame_skipped",
            "live_camera_service.fps_skip_triggered",
        }
        assert [e["event"] for e in logs if e["event"] in skip_events] == []
        for dead in (
            "_target_fps",
            "_current_fps",
            "_processing_times",
            "_frame_skip_count",
            "_fps_adjustment_interval",
        ):
            assert not hasattr(h, dead), dead
        assert not hasattr(FrameProcessingMixin, "_adjust_fps_dynamically")


class TestLiveRecordingFps:
    """#637: the MP4 is written at the rate the camera really delivers."""

    def _host(self, *, ledger=None, camera=None):
        host = object.__new__(FrameProcessingMixin)
        host_any: Any = host
        host_any._frame_ledger = ledger
        host_any.camera = camera
        return host

    def test_the_session_ledger_wins_once_it_has_a_sample(self):
        ledger = SimpleNamespace(row_count=30, current_fps_measured=lambda: 39.5)
        camera = SimpleNamespace(measured_fps=lambda: 41.0, actual_fps=30.0)

        assert self._host(ledger=ledger, camera=camera)._live_recording_fps() == 39.5

    def test_a_short_ledger_defers_to_the_camera_measurement(self):
        ledger = SimpleNamespace(row_count=5, current_fps_measured=lambda: 12.0)
        camera = SimpleNamespace(measured_fps=lambda: 41.0, actual_fps=30.0)

        assert self._host(ledger=ledger, camera=camera)._live_recording_fps() == 41.0

    def test_without_a_measurement_the_driver_value(self):
        camera = SimpleNamespace(measured_fps=lambda: None, actual_fps=30.0)

        assert self._host(camera=camera)._live_recording_fps() == 30.0

    def test_nothing_known_lets_the_recorder_use_the_settings(self):
        assert self._host()._live_recording_fps() is None


class TestMultiAquariumObjectSidecarDegrades:
    """The 3c sidecar is an audit aid: its failure never stops the recording."""

    def _host(self, recorder):
        host = object.__new__(FrameProcessingMixin)
        host_any: Any = host
        host_any.recorder = recorder
        host_any._frame_ledger = _FakeLedger(T0)
        return host

    _ZONES = SimpleNamespace(aquariums=[SimpleNamespace(id=0, polygon=[[0, 0], [1, 1]])])

    def test_a_failing_partitioned_writer_is_swallowed(self):
        recorder = SimpleNamespace(
            write_partitioned_object_data=MagicMock(side_effect=OSError("disk full"))
        )

        self._host(recorder)._write_object_frame(
            0.1, 3, T0 + 1.0, [], multi_zone_data=self._ZONES
        )  # must not raise

        recorder.write_partitioned_object_data.assert_called_once()

    def test_a_recorder_without_the_partitioned_writer_writes_nothing(self):
        recorder = SimpleNamespace(write_object_data=MagicMock())

        self._host(recorder)._write_object_frame(0.1, 3, T0 + 1.0, [], multi_zone_data=self._ZONES)

        recorder.write_object_data.assert_not_called()


# ---------------------------------------------------------------------------
# Issue #654: ByteTrack ages lost tracks on the CAPTURE clock, not the driver fps.
# ---------------------------------------------------------------------------


class _ClockedTrackerDetector(_FakeDetector):
    """A real ByteTrack behind the loop: one box per scripted frame, then none.

    The tracker is built for the DRIVER's 30 fps, while the loop only analyses
    one captured frame in two (15 Hz). It ages lost tracks on whatever instant
    the loop declares through ``set_frame_time``.
    """

    def __init__(self, box_frames):
        super().__init__({})
        from zebtrack.tracker.basetrack import BaseTrack
        from zebtrack.tracker.byte_tracker import BYTETracker

        BaseTrack.reset_id_counter()
        args = SimpleNamespace(track_thresh=0.5, match_thresh=0.8, track_buffer=30, mot20=False)
        self.tracker = BYTETracker(args=args, frame_rate=30)  # 30 frames = 1 s
        self.box_frames = set(box_frames)
        self.declared: list[float | None] = []
        self._frame_time_s: float | None = None
        self.removed_at: float | None = None

    def set_frame_time(self, t_s):
        self.declared.append(t_s)
        self._frame_time_s = t_s

    def detect(self, frame, context, conf_threshold=None):
        current = self.frames.pop(0)
        boxes = (
            np.array([[100.0, 100.0, 140.0, 140.0, 0.95]])
            if current in self.box_frames
            else np.empty((0, 5))
        )
        t_s, self._frame_time_s = self._frame_time_s, None
        self.tracker.update(boxes, (480, 640), (480, 640), frame_time_s=t_s)
        if self.tracker.removed_stracks and self.removed_at is None:
            self.removed_at = t_s
        return [], None


class TestTrackerAgesOnTheCaptureClock:
    def test_capture_instant_is_declared_before_each_detection(self, tmp_path):
        h = _LoopHarness(tmp_path)
        h.detector = _ClockedTrackerDetector(box_frames=[])
        harness: Any = h
        harness.detector_service = SimpleNamespace(detector=h.detector)

        h.run([(0, T0), (2, T0 + 2 / 30), (4, T0 + 4 / 30)])

        assert h.detector.declared == [T0, T0 + 2 / 30, T0 + 4 / 30]

    def test_buffer_in_seconds_is_the_configured_one_with_a_1_in_2_cadence(self, tmp_path):
        # 30 fps capture, every other frame analysed (queue drops / skip 1:2).
        h = _LoopHarness(tmp_path)
        last_hit = 4
        h.detector = _ClockedTrackerDetector(box_frames=range(0, last_hit + 1))
        harness: Any = h
        harness.detector_service = SimpleNamespace(detector=h.detector)

        h.run([(f, T0 + f / 30) for f in range(0, 200, 2)])

        assert h.detector.removed_at is not None
        lost_for_s = h.detector.removed_at - (T0 + last_hit / 30)
        # 1 s configured; one analysed frame (2/30 s) of slack. Counting
        # updates against the driver's 30 fps would have kept it 2 s.
        assert lost_for_s == pytest.approx(1.0, abs=2 / 30 + 1e-9)


# ---------------------------------------------------------------------------
# #656: what happens DURING a 2-aquarium live session -- the analysis window,
# the per-zone Arduino commands and the overlay -- per aquarium.
#
# Geometry: aquarium 0 is x 0..20, aquarium 1 is x 20..40. Each has an ROI
# named "A" (the names repeat across aquariums in real projects): aquarium 0's
# at x 0..10, aquarium 1's at x 20..30. The single detector holds aquarium 0's
# zones only, which is what the live loop used to evaluate both aquariums with.
# ---------------------------------------------------------------------------

_ROI_A = {
    0: [[0, 0], [10, 0], [10, 10], [0, 10]],
    1: [[20, 0], [30, 0], [30, 10], [20, 10]],
}


def _aquarium(aq_id):
    from zebtrack.core.detection.detection_types import AquariumData

    x0 = 20 * aq_id
    return AquariumData(
        id=aq_id,
        polygon=[[x0, 0], [x0 + 20, 0], [x0 + 20, 20], [x0, 20]],
        roi_polygons=[_ROI_A[aq_id]],
        roi_names=["A"],
    )


def _abox(aq_id, cx, cy, local_id=1):
    """A detection of aquarium ``aq_id`` (global track id, full-frame pixels)."""
    return (cx - 1, cy - 1, cx + 1, cy + 1, 0.9, aq_id * 1000 + local_id, 0)


IN_A = {0: (5, 5), 1: (25, 5)}
OUT_A = {0: (15, 15), 1: (35, 15)}


class _FakeMultiDetector:
    """The surface of ``MultiAquariumDetector`` the live loop reads."""

    def __init__(self, aquariums):
        self._aquariums = aquariums
        self._observations: list = []
        self.overlay_calls: list[dict] = []

    def get_multi_aquarium_data(self):
        return self._aquariums

    def get_aquarium_roi_polygons(self, aquarium_id):
        polygon = _ROI_A.get(aquarium_id)
        return [] if polygon is None else [np.array(polygon, dtype=np.int32)]

    def pop_class_observations(self):
        out, self._observations = self._observations, []
        return out

    def draw_multi_aquarium_overlay(self, frame, partitioned_detections):
        self.overlay_calls.append(dict(partitioned_detections))
        return frame


class _MultiSessionRecorder(_PartitionedRecorder):
    """Parent recorder with one sub-recorder per ``aquarium_N/`` folder."""

    def __init__(self, folder):
        super().__init__(folder)
        self.subs = {}
        for aq_id in (0, 1):
            sub_dir = folder / f"aquarium_{aq_id + 1}"
            sub_dir.mkdir()
            self.subs[aq_id] = SimpleNamespace(
                output_folder=str(sub_dir), base_name=f"sessao_aquarium_{aq_id + 1}"
            )

    def get_aquarium_recorders(self):
        return dict(self.subs)


class _CountingDetector(_FakeDetector):
    def __init__(self, script):
        super().__init__(script)
        self.overlays = 0

    def draw_overlay(self, frame, detections):
        self.overlays += 1


def _multi_harness(tmp_path, *, positions, window=None, project_data=None):
    """``positions``: frame -> {aquarium_id: (cx, cy)} of each aquarium's animal."""
    h = _LoopHarness(tmp_path, window=window, project_data=project_data)
    h.detector = _CountingDetector({})
    harness: Any = h
    harness.detector_service = SimpleNamespace(detector=h.detector)
    h.recorder = _MultiSessionRecorder(tmp_path)
    aquariums = [_aquarium(0), _aquarium(1)]
    h._live_multi_zone_data = SimpleNamespace(aquariums=aquariums)
    multi = _FakeMultiDetector(aquariums)

    def _detect(frame, frame_number, zone_data):
        # The real detector is created lazily on the first analysed frame.
        harness._multi_aq_detector = multi
        return [_abox(aq, *xy) for aq, xy in positions.get(frame_number, {}).items()]

    harness._run_multi_aquarium_detection = _detect
    return h, multi


def _window_of(tmp_path, aq_id):
    folder = tmp_path / f"aquarium_{aq_id + 1}"
    return read_artifact(folder / f"7_AnalysisWindow_sessao_aquarium_{aq_id + 1}.json")


class TestMultiAquariumLiveWindow:
    def test_each_aquarium_gets_its_own_window(self, tmp_path):
        """Aquarium 1's animal entering ITS "A" starts aquarium 1's window only."""
        spec = WindowSpec(start=RoiEdge(roi="A", edge="enter"))
        positions = {
            1: {0: OUT_A[0], 1: OUT_A[1]},
            2: {0: OUT_A[0], 1: IN_A[1]},
            3: {0: OUT_A[0], 1: IN_A[1]},
        }
        h, _multi = _multi_harness(tmp_path, positions=positions, window=spec)
        h.run([(f, T0 + f) for f in (1, 2, 3)])

        first, second = _window_of(tmp_path, 0), _window_of(tmp_path, 1)
        assert first is not None and second is not None
        assert first.online.start is None  # aquarium 0 never entered
        assert second.online.start is not None
        assert second.online.start.frame == 2
        # Nothing at the session root: the parent has no trajectory of its own.
        assert not list(tmp_path.glob("7_AnalysisWindow_*"))

    def test_states_are_published_per_aquarium(self, tmp_path):
        spec = WindowSpec(start=RoiEdge(roi="A", edge="enter"))
        h, _multi = _multi_harness(
            tmp_path, positions={1: {1: OUT_A[1]}, 2: {1: IN_A[1]}}, window=spec
        )
        h.run([(1, T0 + 1.0), (2, T0 + 2.0)])
        root: Any = h.root
        published = [
            (args[0].aquarium_id, args[0].state)
            for fn, args in root.calls
            if getattr(fn, "__name__", "") == "_publish_window_state"
        ]
        assert (0, "waiting_start") in published
        assert (1, "waiting_start") in published
        assert (1, "in_analysis") in published
        assert (0, "in_analysis") not in published

    def test_end_session_waits_for_every_aquarium(self, tmp_path):
        spec = WindowSpec(
            start=FrameReached(frame=1), stop=RoiEdge(roi="A", edge="enter"), on_stop="end_session"
        )
        positions = {
            1: {0: OUT_A[0], 1: OUT_A[1]},
            2: {0: IN_A[0], 1: OUT_A[1]},  # aquarium 0 stops
            3: {0: IN_A[0], 1: OUT_A[1]},
        }
        h, _multi = _multi_harness(tmp_path, positions=positions, window=spec)
        h.run([(f, T0 + f) for f in (1, 2, 3)])
        assert _window_of(tmp_path, 0).online.stop is not None  # it did stop
        assert h.finish_requests() == []  # aquarium 1's trial is still running

    def test_end_session_once_every_aquarium_stopped(self, tmp_path):
        spec = WindowSpec(
            start=FrameReached(frame=1), stop=RoiEdge(roi="A", edge="enter"), on_stop="end_session"
        )
        positions = {
            1: {0: OUT_A[0], 1: OUT_A[1]},
            2: {0: IN_A[0], 1: OUT_A[1]},
            3: {0: IN_A[0], 1: IN_A[1]},
            4: {0: IN_A[0], 1: IN_A[1]},
        }
        h, _multi = _multi_harness(tmp_path, positions=positions, window=spec)
        h.run([(f, T0 + f) for f in (1, 2, 3, 4)])
        assert len(h.finish_requests()) == 1

    def test_arduino_code_reaches_every_aquarium_window(self, tmp_path):
        h, _multi = _multi_harness(tmp_path, positions={}, window=external_trigger_preset())
        h.arm()
        assert h.manager.sink is not None
        assert h.manager.sink(1, T0 + 0.5) is True  # claimed: coordinators never see it
        h._step_condition_runtime(1, T0 + 1.0, [], [])
        h._finalize_condition_runtime()

        for aq_id in (0, 1):
            window = _window_of(tmp_path, aq_id)
            assert window is not None
            assert window.online.start is not None
            assert window.online.start.frame == 1

    def test_manual_press_reaches_every_aquarium_window(self, tmp_path):
        h, _multi = _multi_harness(
            tmp_path, positions={}, window=WindowSpec(start=External(source="manual"))
        )
        assert h.push_manual_condition_event() is False  # nothing armed yet
        h.arm()
        assert h.push_manual_condition_event() is True
        h._step_condition_runtime(1, time.perf_counter() + 1.0, [], [])
        h._finalize_condition_runtime()
        for aq_id in (0, 1):
            window = _window_of(tmp_path, aq_id)
            assert window is not None
            assert window.online.start is not None

    def test_classes_are_read_per_aquarium(self, tmp_path):
        spec = WindowSpec(
            start=Persist(
                level=ClassPresence(target=ClassTarget.of_class("Rat")), hold=Hold(seconds=1.0)
            )
        )
        h, _multi = _multi_harness(tmp_path, positions={}, window=spec)
        h.arm()
        rat_in_1 = dict(_rat(), aquarium_id=1)
        h._step_condition_runtime(1, T0 + 1.0, [], [rat_in_1])
        h._step_condition_runtime(2, T0 + 2.0, [], [rat_in_1])
        h._finalize_condition_runtime()
        first, second = _window_of(tmp_path, 0), _window_of(tmp_path, 1)
        assert first is not None and second is not None
        assert first.online.start is None
        assert second.online.start is not None


SCOPED_PROJECT = {
    "use_arduino": True,
    "arduino_bindings": [
        {"roi": "A", "aquarium_id": 0, "on_enter": 1, "on_exit": 2},
        {"roi": "A", "aquarium_id": 1, "on_enter": 11, "on_exit": 12},
    ],
}


class TestMultiAquariumArduinoCommands:
    @staticmethod
    def _sent_per_frame(h):
        # Everything queued since the previous frame's dispatch: the window's
        # STOP sweep runs in the step, just before the dispatch.
        sent: dict[int, list[int]] = {}
        original = h._dispatch_arduino_zone_commands
        seen = [0]

        def _dispatch(detections, frame_number=None, *args):
            original(detections, frame_number, *args)
            sent[frame_number] = list(h.manager.sent[seen[0] :])
            seen[0] = len(h.manager.sent)

        h._dispatch_arduino_zone_commands = _dispatch
        return sent

    def test_animal_in_aquarium_2_fires_aquarium_2_binding(self, tmp_path):
        positions = {1: {1: IN_A[1]}, 2: {1: OUT_A[1]}}
        h, _multi = _multi_harness(tmp_path, positions=positions, project_data=SCOPED_PROJECT)
        sent = self._sent_per_frame(h)
        h.run([(1, T0 + 1.0), (2, T0 + 2.0)])
        assert sent[1] == [11]
        assert sent[2] == [12]

    def test_animal_in_aquarium_1_never_fires_aquarium_2_binding(self, tmp_path):
        positions = {1: {0: IN_A[0]}, 2: {0: OUT_A[0]}}
        h, _multi = _multi_harness(tmp_path, positions=positions, project_data=SCOPED_PROJECT)
        sent = self._sent_per_frame(h)
        h.run([(1, T0 + 1.0), (2, T0 + 2.0)])
        assert sent[1] == [1]
        assert sent[2] == [2]

    def test_unscoped_binding_holds_while_any_aquarium_is_inside(self, tmp_path):
        positions = {
            1: {0: IN_A[0], 1: OUT_A[1]},
            2: {0: IN_A[0], 1: IN_A[1]},
            3: {0: OUT_A[0], 1: IN_A[1]},
            4: {0: OUT_A[0], 1: OUT_A[1]},
        }
        h, _multi = _multi_harness(tmp_path, positions=positions, project_data=ZONE_PROJECT)
        sent = self._sent_per_frame(h)
        h.run([(f, T0 + f) for f in (1, 2, 3, 4)])
        assert [sent[f] for f in (1, 2, 3, 4)] == [[1], [], [], [2]]

    def test_stop_of_one_aquarium_closes_only_its_commands(self, tmp_path):
        spec = WindowSpec(start=FrameReached(frame=1), stop=RoiEdge(roi="A", edge="exit"))
        positions = {
            1: {0: IN_A[0], 1: IN_A[1]},
            2: {0: OUT_A[0], 1: IN_A[1]},  # aquarium 0 STOP
            3: {0: IN_A[0], 1: IN_A[1]},  # aquarium 0 is closed: nothing
            4: {0: IN_A[0], 1: OUT_A[1]},  # aquarium 1 STOP: the last one
        }
        h, _multi = _multi_harness(
            tmp_path, positions=positions, window=spec, project_data=SCOPED_PROJECT
        )
        sent = self._sent_per_frame(h)
        h.run([(f, T0 + f) for f in (1, 2, 3, 4)])
        assert sent[1] == [1, 11]
        assert sent[2] == [2]  # only aquarium 0's outputs swept
        assert sent[3] == []
        assert sent[4] == [2, 12]  # last window closed: the full sweep
        assert h.manager.sent == [1, 11, 2, 2, 12]  # no second sweep at session end


class TestMultiAquariumOverlay:
    def test_overlay_draws_every_aquarium_zones_only(self, tmp_path):
        h, multi = _multi_harness(tmp_path, positions={1: {1: IN_A[1]}})
        h.display_interval_frames = 1
        h.run([(1, T0 + 1.0)])
        assert multi.overlay_calls == [{}]  # zones only: boxes are drawn by the consumer
        detector: Any = h.detector
        assert detector.overlays == 0  # never the aquarium-0 single detector

    def test_single_aquarium_overlay_is_unchanged(self, tmp_path):
        h = _LoopHarness(tmp_path)
        detector = _CountingDetector({})
        h.detector = detector
        harness: Any = h
        harness.detector_service = SimpleNamespace(detector=detector)
        h.display_interval_frames = 1
        h.run([(1, T0 + 1.0)])
        assert detector.overlays == 1


class TestLiveOverlayClassRoles:
    """#645: the live canvas draws with the live detector's own role map."""

    class _Pipeline(FrameProcessingMixin):
        def __init__(self, detector: Any) -> None:
            self.detector_service = SimpleNamespace(detector=detector)

    def test_explicit_map_is_published_by_id(self):
        from zebtrack.core.detection.class_roles import resolve_class_role_map

        role_map = resolve_class_role_map(
            {0: "arena", 1: "experimenter", 2: "rat"},
            weight_entry={
                "class_roles": {"arena": "arena", "experimenter": "context", "rat": "subject"}
            },
        )
        pipe = self._Pipeline(SimpleNamespace(class_role_map=role_map))
        assert pipe._live_overlay_class_roles() == {0: "arena", 1: "context", 2: "subject"}

    def test_legacy_map_is_published_empty(self):
        from zebtrack.core.detection.class_roles import resolve_class_role_map

        role_map = resolve_class_role_map({0: "aqua", 1: "zebrafish"})
        pipe = self._Pipeline(SimpleNamespace(class_role_map=role_map))
        assert pipe._live_overlay_class_roles() == {}

    def test_no_detector_publishes_none(self):
        assert self._Pipeline(None)._live_overlay_class_roles() is None

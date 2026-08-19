"""Extended unit tests for core/video/processing_worker.py."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
    WorkerConfig,
)


class TestProcessingWorkerExtended:
    def test_processing_context_defaults(self):
        ctx = ProcessingContext(
            videos_to_process=[{"path": "/path/video.mp4"}],
            output_base_dir="/path/output",
            cancel_event=threading.Event(),
            settings=MagicMock(),
        )
        assert len(ctx.videos_to_process) == 1
        assert ctx.output_base_dir == "/path/output"
        assert ctx.zone_data is None
        assert ctx.analysis_interval_frames == 10
        assert ctx.display_interval_frames == 10
        assert ctx.retry_strategy == "stop"

    def test_processing_callbacks_invocation(self):
        mock_started = MagicMock()
        mock_progress = MagicMock()
        mock_frame = MagicMock()
        mock_video_comp = MagicMock()
        mock_error = MagicMock()
        mock_comp = MagicMock()
        mock_fatal = MagicMock()

        callbacks = ProcessingCallbacks(
            on_started=mock_started,
            on_progress=mock_progress,
            on_frame_processed=mock_frame,
            on_video_completed=mock_video_comp,
            on_error=mock_error,
            on_completed=mock_comp,
            on_fatal_error=mock_fatal,
        )

        callbacks.on_started()
        mock_started.assert_called_once()

        callbacks.on_progress(1, 5, "exp_1", 0.2, "Processing frame 10", None)
        mock_progress.assert_called_once_with(1, 5, "exp_1", 0.2, "Processing frame 10", None)

        callbacks.on_video_completed(1, 5, "exp_1", True)
        mock_video_comp.assert_called_once_with(1, 5, "exp_1", True)

        err = RuntimeError("Disk full")
        callbacks.on_error(err, "exp_1")
        mock_error.assert_called_once_with(err, "exp_1")

        callbacks.on_completed(True, "All videos processed", None)
        mock_comp.assert_called_once_with(True, "All videos processed", None)

        callbacks.on_fatal_error(err, "Fatal context", {})
        mock_fatal.assert_called_once_with(err, "Fatal context", {})

    def test_worker_config_structure(self):
        cfg = WorkerConfig(
            settings=MagicMock(),
            output_base_dir="/path/output",
            tasks=[{"video_path": "/path/v.mp4"}],
            model_path="/path/yolo11n.pt",
            model_type="yolo",
        )
        assert cfg.output_base_dir == "/path/output"
        assert len(cfg.tasks) == 1
        assert cfg.model_type == "yolo"
        assert cfg.single_video_mode is False
        assert cfg.shm_name == ""

    def test_processing_worker_initialization(self):
        ctx = ProcessingContext(
            videos_to_process=[],
            output_base_dir="/path/output",
            cancel_event=threading.Event(),
            settings=MagicMock(),
        )
        callbacks = ProcessingCallbacks(
            on_started=MagicMock(),
            on_progress=MagicMock(),
            on_frame_processed=MagicMock(),
            on_video_completed=MagicMock(),
            on_error=MagicMock(),
            on_completed=MagicMock(),
            on_fatal_error=MagicMock(),
        )
        worker = ProcessingWorker(ctx, callbacks)

        assert worker.is_running is False
        assert worker.result_queue is not None
        assert worker.command_queue is not None
        assert worker.process is None
        assert worker._shm_buffer is None


class TestProcessingWorkerExtended2:
    def test_processing_context_dataclass(self):
        cancel_evt = threading.Event()
        ctx = ProcessingContext(
            videos_to_process=[{"path": "vid1.mp4"}],
            output_base_dir="/output",
            cancel_event=cancel_evt,
            settings=MagicMock(),
            analysis_interval_frames=15,
            display_interval_frames=30,
            retry_strategy="continue",
        )

        assert len(ctx.videos_to_process) == 1
        assert ctx.output_base_dir == "/output"
        assert ctx.cancel_event is cancel_evt
        assert ctx.analysis_interval_frames == 15
        assert ctx.display_interval_frames == 30
        assert ctx.retry_strategy == "continue"
        assert ctx.single_video_config is None

    def test_processing_callbacks_dataclass(self):
        cb = ProcessingCallbacks(
            on_started=MagicMock(),
            on_progress=MagicMock(),
            on_frame_processed=MagicMock(),
            on_video_completed=MagicMock(),
            on_error=MagicMock(),
            on_completed=MagicMock(),
            on_fatal_error=MagicMock(),
        )

        assert callable(cb.on_started)
        assert callable(cb.on_progress)
        assert callable(cb.on_completed)

    def test_worker_config_dataclass_defaults(self):
        cfg = WorkerConfig(
            settings=MagicMock(),
            output_base_dir="/tmp/out",
            tasks=[{"video": "v.mp4"}],
        )

        assert cfg.single_video_mode is False
        assert cfg.analysis_interval_frames == 10
        assert cfg.display_interval_frames == 10
        assert cfg.model_type == "yolo"
        assert cfg.shm_name == ""
        assert cfg.zone_data is None

    def test_processing_worker_initialization(self):
        ctx = MagicMock()
        cb = MagicMock()
        worker = ProcessingWorker(ctx, cb)

        assert worker.process is None
        assert worker._monitor_thread is None
        assert worker.is_running is False
        assert worker.context is ctx
        assert worker.callbacks is cb


class TestProcessingWorkerExtended3:
    def test_is_running_lifecycle(self):
        ctx = ProcessingContext(
            videos_to_process=[{"path": "/test/v.mp4"}],
            output_base_dir="/test/out",
            cancel_event=threading.Event(),
            settings=MagicMock(),
        )
        cb = ProcessingCallbacks(
            on_started=MagicMock(),
            on_progress=MagicMock(),
            on_frame_processed=MagicMock(),
            on_video_completed=MagicMock(),
            on_error=MagicMock(),
            on_completed=MagicMock(),
            on_fatal_error=MagicMock(),
        )
        worker = ProcessingWorker(ctx, cb)

        assert worker.is_running is False

        mock_t = MagicMock(spec=threading.Thread)
        mock_t.is_alive.return_value = True
        worker._monitor_thread = mock_t

        assert worker.is_running is True

    def test_queues_and_process_initial_state(self):
        ctx = ProcessingContext(
            videos_to_process=[],
            output_base_dir="/test/out",
            cancel_event=threading.Event(),
            settings=MagicMock(),
        )
        cb = ProcessingCallbacks(
            on_started=MagicMock(),
            on_progress=MagicMock(),
            on_frame_processed=MagicMock(),
            on_video_completed=MagicMock(),
            on_error=MagicMock(),
            on_completed=MagicMock(),
            on_fatal_error=MagicMock(),
        )
        worker = ProcessingWorker(ctx, cb)

        assert worker.result_queue is not None
        assert worker.command_queue is not None
        assert worker.process is None
        assert worker._shm_buffer is None


class TestProcessingWorkerExtended4:
    def test_worker_config_initialization(self):
        settings = MagicMock()
        cfg = WorkerConfig(
            settings=settings,
            output_base_dir="/output",
            tasks=[{"path": "vid1.mp4"}],
            single_video_mode=True,
            model_type="openvino",
        )

        assert cfg.output_base_dir == "/output"
        assert cfg.tasks == [{"path": "vid1.mp4"}]
        assert cfg.single_video_mode is True
        assert cfg.model_type == "openvino"
        assert cfg.analysis_interval_frames == 10


class TestProcessingWorkerExtended5:
    def test_processing_worker_initial_queues_and_context(self):
        ctx = MagicMock()
        callbacks = MagicMock()
        worker = ProcessingWorker(ctx, callbacks)

        assert worker.context is ctx
        assert worker.callbacks is callbacks
        assert worker.process is None
        assert worker._monitor_thread is None
        assert worker._shm_buffer is None
        assert worker.is_running is False

    def test_worker_config_defaults(self):
        config = WorkerConfig(
            settings=MagicMock(),
            output_base_dir="/tmp",
            tasks=[],
        )
        assert config.single_video_mode is False
        assert config.analysis_interval_frames == 10
        assert config.display_interval_frames == 10
        assert config.model_path == ""
        assert config.model_type == "yolo"
        assert config.zone_data is None
        assert config.shm_name == ""

    def test_processing_worker_is_running_with_alive_thread(self):
        ctx = MagicMock()
        callbacks = MagicMock()
        worker = ProcessingWorker(ctx, callbacks)

        mock_th = MagicMock(spec=threading.Thread)
        mock_th.is_alive.return_value = True
        worker._monitor_thread = mock_th

        assert worker.is_running is True


class TestProcessingWorkerExtended6:
    def test_processing_worker_is_running_false_no_thread(self):
        ctx = MagicMock()
        callbacks = MagicMock()
        worker = ProcessingWorker(ctx, callbacks)

        assert worker.is_running is False

    def test_processing_context_dataclass_defaults(self):
        cancel_evt = threading.Event()
        ctx = ProcessingContext(
            videos_to_process=[],
            output_base_dir="/tmp",
            cancel_event=cancel_evt,
            settings=MagicMock(),
        )

        assert ctx.analysis_interval_frames == 10
        assert ctx.display_interval_frames == 10
        assert ctx.single_video_config is None
        assert ctx.zone_data is None


class TestProcessingWorkerExtended7:
    def test_processing_context_fields(self):
        cancel_evt = threading.Event()
        settings = MagicMock()
        ctx = ProcessingContext(
            videos_to_process=[{"path": "/path/v1.mp4"}],
            output_base_dir="/outputs",
            cancel_event=cancel_evt,
            settings=settings,
            analysis_interval_frames=5,
            display_interval_frames=15,
            retry_strategy="skip",
        )
        assert len(ctx.videos_to_process) == 1
        assert ctx.output_base_dir == "/outputs"
        assert ctx.cancel_event is cancel_evt
        assert ctx.settings is settings
        assert ctx.analysis_interval_frames == 5
        assert ctx.display_interval_frames == 15
        assert ctx.retry_strategy == "skip"

    def test_processing_callbacks_instantiation(self):
        cb = ProcessingCallbacks(
            on_started=MagicMock(),
            on_progress=MagicMock(),
            on_frame_processed=MagicMock(),
            on_video_completed=MagicMock(),
            on_error=MagicMock(),
            on_completed=MagicMock(),
            on_fatal_error=MagicMock(),
        )
        assert cb.on_started is not None
        assert cb.on_progress is not None
        assert cb.on_frame_processed is not None
        assert cb.on_completed is not None

    def test_worker_config_instantiation(self):
        settings = MagicMock()
        cfg = WorkerConfig(settings=settings, output_base_dir="/out_dir", tasks=[])
        assert cfg.settings is settings
        assert cfg.output_base_dir == "/out_dir"
        assert cfg.tasks == []


class TestProcessingWorkerExtended8:
    def test_processing_context_custom_function_hooks(self):
        hook_called = False

        def hook(video_entry: dict) -> None:
            nonlocal hook_called
            hook_called = True

        cancel_evt = threading.Event()
        ctx = ProcessingContext(
            videos_to_process=[{"group": "A", "subject": "S1"}],
            output_base_dir="/tmp/out",
            cancel_event=cancel_evt,
            settings=MagicMock(),
            process_single_video_func=hook,
        )

        assert len(ctx.videos_to_process) == 1
        assert ctx.output_base_dir == "/tmp/out"
        assert ctx.cancel_event is cancel_evt
        assert ctx.process_single_video_func is not None
        ctx.process_single_video_func({"group": "A"})
        assert hook_called is True

    def test_processing_context_intervals_func_hook(self):
        cancel_evt = threading.Event()
        mock_func = MagicMock()
        ctx = ProcessingContext(
            videos_to_process=[],
            output_base_dir="/tmp/out",
            cancel_event=cancel_evt,
            settings=MagicMock(),
            determine_intervals_func=mock_func,
        )
        assert ctx.determine_intervals_func is mock_func
        assert ctx.analysis_interval_frames == 10
        assert ctx.display_interval_frames == 10

    def test_processing_callbacks_initialization(self):
        cb_started = MagicMock()
        cb_progress = MagicMock()
        cb_frame = MagicMock()
        cb_video_comp = MagicMock()
        cb_error = MagicMock()
        cb_completed = MagicMock()
        cb_fatal = MagicMock()

        callbacks = ProcessingCallbacks(
            on_started=cb_started,
            on_progress=cb_progress,
            on_frame_processed=cb_frame,
            on_video_completed=cb_video_comp,
            on_error=cb_error,
            on_completed=cb_completed,
            on_fatal_error=cb_fatal,
        )
        assert callbacks.on_started is cb_started
        assert callbacks.on_fatal_error is cb_fatal

    def test_worker_config_defaults(self):
        cfg = WorkerConfig(
            settings=MagicMock(),
            output_base_dir="/tmp/out",
            tasks=[{"id": 1}],
        )
        assert cfg.single_video_mode is False
        assert cfg.model_type == "yolo"
        assert cfg.analysis_interval_frames == 10

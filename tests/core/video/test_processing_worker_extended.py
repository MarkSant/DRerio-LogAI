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
    """Test ProcessingWorker context, callbacks, configuration dataclasses, and worker state."""

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

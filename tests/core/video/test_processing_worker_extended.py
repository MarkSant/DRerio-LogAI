"""Extended unit tests for ProcessingWorker in core/video/processing_worker.py."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
    WorkerConfig,
)
from zebtrack.settings import load_settings


class TestProcessingWorkerExtended:
    """Test ProcessingContext, ProcessingCallbacks, WorkerConfig, and ProcessingWorker."""

    def test_processing_context_dataclass(self):
        cancel_event = threading.Event()
        settings = load_settings()
        ctx = ProcessingContext(
            videos_to_process=[{"path": "/tmp/v1.mp4"}],
            output_base_dir="/tmp/out",
            cancel_event=cancel_event,
            settings=settings,
            analysis_interval_frames=5,
            display_interval_frames=10,
        )
        assert len(ctx.videos_to_process) == 1
        assert ctx.output_base_dir == "/tmp/out"
        assert ctx.cancel_event is cancel_event
        assert ctx.analysis_interval_frames == 5
        assert ctx.display_interval_frames == 10
        assert ctx.retry_strategy == "stop"

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

    def test_worker_config_dataclass(self):
        settings = load_settings()
        cfg = WorkerConfig(
            settings=settings,
            output_base_dir="/tmp/out",
            tasks=[{"experiment_id": "exp1"}],
            single_video_mode=True,
            model_path="yolov8n.pt",
            model_type="yolo",
        )
        assert cfg.single_video_mode is True
        assert cfg.model_type == "yolo"
        assert cfg.model_path == "yolov8n.pt"

    def test_processing_worker_initialization(self):
        settings = load_settings()
        ctx = ProcessingContext(
            videos_to_process=[],
            output_base_dir="/tmp/out",
            cancel_event=threading.Event(),
            settings=settings,
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
        worker = ProcessingWorker(context=ctx, callbacks=cb)
        assert worker.is_running is False
        assert worker.result_queue is not None
        assert worker.command_queue is not None

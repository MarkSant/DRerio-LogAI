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


class TestProcessingWorkerExtended2:
    """Test ProcessingWorker dataclasses, configuration, and worker process lifecycle."""

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

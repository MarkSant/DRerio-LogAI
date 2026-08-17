"""Extended unit tests for core/video/processing_worker.py (Part 7)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    WorkerConfig,
)


class TestProcessingWorkerExtended7:
    """Test ProcessingContext and ProcessingCallbacks configurations."""

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

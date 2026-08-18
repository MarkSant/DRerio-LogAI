"""Extended unit tests for core/video/processing_worker.py (Part 8)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    WorkerConfig,
)


class TestProcessingWorkerExtended8:
    """Test ProcessingContext hooks, intervals, and processing callbacks."""

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

"""Extended unit tests for core/video/processing_worker.py."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import (
    ProcessingCallbacks,
    ProcessingContext,
    ProcessingWorker,
)


class TestProcessingWorkerExtended3:
    """Test ProcessingWorker running state and queue lifecycle."""

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

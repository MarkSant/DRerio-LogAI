"""Extended unit tests for core/video/processing_worker.py (Part 6)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import ProcessingContext, ProcessingWorker


class TestProcessingWorkerExtended6:
    """Test ProcessingWorker and ProcessingContext defaults."""

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

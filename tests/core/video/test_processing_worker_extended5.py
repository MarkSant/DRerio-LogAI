"""Extended unit tests for core/video/processing_worker.py (Part 5)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import ProcessingWorker, WorkerConfig


class TestProcessingWorkerExtended5:
    """Test ProcessingWorker queue creation, context references, and worker configuration."""

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

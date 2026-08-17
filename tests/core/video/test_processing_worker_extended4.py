"""Extended unit tests for core/video/processing_worker.py (Part 4)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import ProcessingWorker, WorkerConfig


class TestProcessingWorkerExtended4:
    """Test WorkerConfig dataclass attributes and ProcessingWorker is_running state."""

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

    def test_processing_worker_is_running(self):
        worker = object.__new__(ProcessingWorker)
        worker._monitor_thread = None
        assert worker.is_running is False

        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True
        worker._monitor_thread = mock_thread
        assert worker.is_running is True

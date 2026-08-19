"""Extended unit tests for core/video/processing_worker.py (Part 4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.video.processing_worker import WorkerConfig


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

import multiprocessing as mp
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_worker import WorkerConfig, _WorkerProcess


class FakePlugin:
    """Lightweight detector plugin stub."""

    class_names: dict[int, str] = {}

    def __init__(self, model_path: str, settings_obj):
        self.model_path = model_path
        self.settings_obj = settings_obj

    @staticmethod
    def get_name() -> str:
        return "FakePlugin"


class FakeDetector:
    """Detector stub capturing single-subject mode updates."""

    def __init__(self, plugin, base_width: int, base_height: int, settings_obj=None):
        self.plugin = plugin
        self.base_width = base_width
        self.base_height = base_height
        self.settings_obj = settings_obj
        self.single_mode = None

    def set_single_subject_mode(self, enabled: bool):
        self.single_mode = enabled


@pytest.fixture
def worker_config():
    settings = SimpleNamespace(
        video_processing=SimpleNamespace(processing_interval=2, animals_per_aquarium=1),
        camera=SimpleNamespace(desired_width=320, desired_height=240),
        yolo_model=SimpleNamespace(path="model.pt"),
        tracking=SimpleNamespace(use_single_subject_tracker=False),
    )

    return WorkerConfig(
        settings=settings,
        output_base_dir="/tmp",
        tasks=[],
        analysis_interval_frames=5,
        display_interval_frames=5,
        zone_data=None,
    )


def test_initialize_detector_syncs_interval_and_single_mode(worker_config):
    result_queue = mp.Queue()
    command_queue = mp.Queue()

    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    with patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", FakePlugin), patch(
        "zebtrack.core.processing_worker.Detector", FakeDetector
    ):
        detector = worker._initialize_detector()

    assert worker.config.settings.video_processing.processing_interval == 5
    assert detector.single_mode is True
    assert hasattr(worker, "_default_zone_data")


def test_get_zone_data_prefers_video_metadata(worker_config):
    result_queue = mp.Queue()
    command_queue = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)
    worker._default_zone_data = ZoneData(polygon=[[1, 0], [0, 1], [1, 1]])

    meta_with_zone = {
        "path": "/video.mp4",
        "zone_data": {
            "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
            "roi_polygons": [[[1, 1], [2, 1], [2, 2], [1, 2]]],
            "roi_names": ["roi"],
            "roi_colors": [(1, 2, 3)],
        },
    }

    zone = worker._get_zone_data_for_video(meta_with_zone)
    assert zone.polygon == meta_with_zone["zone_data"]["polygon"]
    assert zone.roi_names == ["roi"]

    meta_without_zone = {"path": "/video2.mp4"}
    fallback_zone = worker._get_zone_data_for_video(meta_without_zone)
    assert fallback_zone is worker._default_zone_data

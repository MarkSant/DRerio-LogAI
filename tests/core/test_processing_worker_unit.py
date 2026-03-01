import multiprocessing as mp
import typing
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.video.processing_worker import WorkerConfig, _WorkerProcess


class FakePlugin:
    """Lightweight detector plugin stub."""

    class_names: typing.ClassVar[dict[int, str]] = {}

    def __init__(self, model_path: str, settings_obj):
        self.model_path = model_path
        self.settings_obj = settings_obj

    @staticmethod
    def get_name() -> str:
        return "FakePlugin"


class FakeDetector:
    """Detector stub capturing single-subject mode updates."""

    def __init__(
        self,
        plugin,
        base_width: int,
        base_height: int,
        settings_obj=None,
        zone_scaler=None,
        post_processor=None,
    ):
        self.plugin = plugin
        self.base_width = base_width
        self.base_height = base_height
        self.settings_obj = settings_obj
        self.zone_scaler = zone_scaler
        self.post_processor = post_processor
        self.single_mode: bool | None = None

    def set_single_subject_mode(self, enabled: bool):
        self.single_mode = enabled


@pytest.fixture
def worker_config():
    settings = SimpleNamespace(
        video_processing=SimpleNamespace(processing_interval=2, single_animal_per_aquarium=True),
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
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()

    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    with (
        patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", FakePlugin),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
    ):
        detector = worker._initialize_detector()

    assert worker.config.settings.video_processing.processing_interval == 5
    assert detector.single_mode is True
    assert hasattr(worker, "_default_zone_data")


def test_get_zone_data_prefers_video_metadata(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)
    worker._default_zone_data = ZoneData(polygon=[[1, 0], [0, 1], [1, 1]])

    zone_polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    roi_polygons = [[[1, 1], [2, 1], [2, 2], [1, 2]]]
    roi_names = ["roi"]
    roi_colors = [(1, 2, 3)]

    meta_with_zone = {
        "path": "/video.mp4",
        "zone_data": {
            "polygon": zone_polygon,
            "roi_polygons": roi_polygons,
            "roi_names": roi_names,
            "roi_colors": roi_colors,
        },
    }

    zone = worker._get_zone_data_for_video(meta_with_zone)
    assert isinstance(zone, ZoneData)
    assert zone.polygon == zone_polygon
    assert zone.roi_names == ["roi"]

    meta_without_zone = {"path": "/video2.mp4"}
    fallback_zone = worker._get_zone_data_for_video(meta_without_zone)
    assert isinstance(fallback_zone, ZoneData)
    assert fallback_zone is worker._default_zone_data


def test_sanitize_component_replaces_invalid_chars():
    assert _WorkerProcess._sanitize_component("A/B:C*") == "A_B_C"
    assert _WorkerProcess._sanitize_component("  many   spaces ") == "many_spaces"
    assert _WorkerProcess._sanitize_component("") == "Indefinido"


def test_format_day_handles_numeric_and_strings():
    assert _WorkerProcess._format_day(None) == "Indefinido"
    assert _WorkerProcess._format_day("2") == "02"
    assert _WorkerProcess._format_day(3.0) == "03"
    assert _WorkerProcess._format_day("D7") == "07"
    assert _WorkerProcess._format_day("Day") == "Day"


def test_format_subject_handles_numeric_and_strings():
    assert _WorkerProcess._format_subject(None) == "Indefinido"
    assert _WorkerProcess._format_subject("4") == "04"
    assert _WorkerProcess._format_subject(5.0) == "05"
    assert _WorkerProcess._format_subject("S9") == "09"
    assert _WorkerProcess._format_subject("Subject") == "Subject"


def test_check_cancellation_sets_flag(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[str] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    assert worker._check_cancellation() is False
    command_queue.put("cancel")
    assert worker._check_cancellation() is True
    assert worker._check_cancellation() is True


def test_send_progress_puts_message(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    worker._send_progress(1, 2, 0.5, "Processing", "exp1", stats={"fps": 30})

    msg = result_queue.get(timeout=1)
    assert isinstance(msg, dict)
    assert msg["type"] == "progress"
    assert msg["index"] == 1
    assert msg["total"] == 2
    assert msg["fraction"] == 0.5
    assert msg["message"] == "Processing"
    assert msg["experiment_id"] == "exp1"
    assert msg["stats"] == {"fps": 30}

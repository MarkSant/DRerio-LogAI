import multiprocessing as mp
import queue
import typing
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
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
    assert zone.metadata == {}

    meta_without_zone = {"path": "/video2.mp4"}
    fallback_zone = worker._get_zone_data_for_video(meta_without_zone)
    assert isinstance(fallback_zone, ZoneData)
    assert fallback_zone is worker._default_zone_data


def test_get_zone_data_preserves_zone_metadata(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    metadata = {"source_video_width": 1920, "source_video_height": 1080}
    zone = worker._get_zone_data_for_video(
        {
            "path": "/video.mp4",
            "zone_data": {
                "polygon": [[0, 0], [10, 0], [10, 10]],
                "roi_polygons": [],
                "roi_names": [],
                "roi_colors": [],
                "metadata": metadata,
            },
        }
    )

    assert isinstance(zone, ZoneData)
    assert zone.metadata == metadata


def test_resolve_zone_source_dimensions_prefers_explicit_metadata(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    zone_data = ZoneData(metadata={"source_video_width": 1920, "source_video_height": 1080})

    assert worker._resolve_zone_source_dimensions(zone_data) == (1920, 1080)


def test_resolve_zone_source_dimensions_reads_multi_aquarium_video_size(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    multi_data = MultiAquariumZoneData(video_width=1920, video_height=1080)

    assert worker._resolve_zone_source_dimensions(multi_data) == (1920, 1080)


def test_repair_source_dimensions_switches_to_desired_base_when_polygon_tiny(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    zone_data = ZoneData(polygon=[[100, 80], [520, 80], [520, 320], [100, 320]])

    repaired = worker._repair_source_dimensions_if_needed(
        zone_data,
        source_width=1920,
        source_height=1080,
        actual_width=1920,
        actual_height=1080,
    )

    assert repaired == (320, 240)


def test_repair_source_dimensions_keeps_source_when_ratio_is_reasonable(worker_config):
    result_queue: mp.Queue[object] = mp.Queue()
    command_queue: mp.Queue[object] = mp.Queue()
    worker = _WorkerProcess(worker_config, result_queue, command_queue)

    zone_data = ZoneData(polygon=[[120, 90], [1040, 90], [1040, 600], [120, 600]])

    repaired = worker._repair_source_dimensions_if_needed(
        zone_data,
        source_width=1920,
        source_height=1080,
        actual_width=1920,
        actual_height=1080,
    )

    assert repaired == (1920, 1080)


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


# ---------------------------------------------------------------------------
# Cancellation polling cost — the frame loop must never take the blocking path.
# ---------------------------------------------------------------------------


class _RecordingQueue:
    """Queue stub that records how each read was attempted."""

    def __init__(self, payload=None):
        self.payload = payload
        self.calls: list[float | None] = []

    def get_nowait(self):
        self.calls.append(None)
        raise queue.Empty

    def get(self, timeout=None):
        self.calls.append(timeout)
        if self.payload is None:
            raise queue.Empty
        payload, self.payload = self.payload, None
        return payload


def test_check_cancellation_hot_path_never_blocks(worker_config):
    """``wait_s=0.0`` must stop at ``get_nowait`` and never issue a timed read.

    The timed read costs ~15.7 ms on Windows (system timer granularity), and the
    frame loop runs this once per video frame, so a blocking read here is minutes
    of dead time per video.
    """
    command_queue = _RecordingQueue()
    worker = _WorkerProcess(worker_config, mp.Queue(), cast(Any, command_queue))

    assert worker._check_cancellation(wait_s=0.0) is False

    assert command_queue.calls == [None], (
        f"wait_s=0.0 must issue exactly one non-blocking read; got {command_queue.calls}"
    )


def test_check_cancellation_default_still_waits(worker_config):
    """The default keeps the bounded wait that closes the feeder-thread window."""
    command_queue = _RecordingQueue()
    worker = _WorkerProcess(worker_config, mp.Queue(), cast(Any, command_queue))

    assert worker._check_cancellation() is False

    assert command_queue.calls == [None, 0.005], (
        f"default must fall back to a bounded blocking read; got {command_queue.calls}"
    )


def test_check_cancellation_hot_path_still_observes_cancel(worker_config):
    """A cancel missed by one non-blocking read is caught by the next one."""
    command_queue = _RecordingQueue(payload="cancel")
    worker = _WorkerProcess(worker_config, mp.Queue(), cast(Any, command_queue))

    # get_nowait always misses on this stub, mimicking the feeder-thread race.
    assert worker._check_cancellation(wait_s=0.0) is False
    # A real queue hands the payload over once flushed; the default path reads it.
    assert worker._check_cancellation() is True
    # And the flag latches, so later polls short-circuit.
    assert worker._check_cancellation(wait_s=0.0) is True


def test_frame_loop_polls_cancellation_without_blocking():
    """Both ``_process_single_video`` cancel polls must pass ``wait_s=0.0``.

    Guards the actual regression: the function-level default is deliberately
    still blocking, so a call site that forgets the keyword silently reinstates
    ~15.7 ms per frame with no test failing anywhere else.
    """
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(_WorkerProcess._process_single_video))
    tree = ast.parse(source)

    polls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_check_cancellation"
    ]

    assert len(polls) == 2, f"expected 2 cancel polls in the frame loop, found {len(polls)}"
    for call in polls:
        waits = [kw.value for kw in call.keywords if kw.arg == "wait_s"]
        assert waits, "frame-loop cancel poll must pass wait_s explicitly"
        assert isinstance(waits[0], ast.Constant) and waits[0].value == 0.0, (
            "frame-loop cancel poll must pass wait_s=0.0"
        )


# ---------------------------------------------------------------------------
# Calibration lookup — raw pixels are the contract both pipelines share.
# ---------------------------------------------------------------------------


def test_aquarium_dimensions_read_from_the_task_top_level():
    assert _WorkerProcess._aquarium_dimensions_cm(
        {"aquarium_width_cm": 12.5, "aquarium_height_cm": 8}
    ) == (12.5, 8.0)


@pytest.mark.parametrize(
    "descriptor",
    [
        {},
        {"aquarium_width_cm": 0, "aquarium_height_cm": 0},
        {"aquarium_width_cm": None, "aquarium_height_cm": None},
        {"aquarium_width_cm": "", "aquarium_height_cm": ""},
        {"aquarium_width_cm": "abc", "aquarium_height_cm": "abc"},
    ],
)
def test_aquarium_dimensions_absent_degrade_to_zero(descriptor):
    """Missing or unparseable dimensions must return zeros, never raise.

    This is the NORMAL path: no production caller puts these keys at the top
    level of a task descriptor.
    """
    assert _WorkerProcess._aquarium_dimensions_cm(descriptor) == (0.0, 0.0)


def test_aquarium_dimensions_ignore_the_nested_metadata():
    """Nested ``metadata`` is deliberately NOT consulted.

    Project entries DO carry the dimensions there. Reading them would build a
    ``Calibration``, whose homography warps coordinates into a rectified 600 px
    space — while the report pipeline subtracts an arena offset measured in raw
    video pixels and the ROIs are stored in raw pixels. Every distance, speed
    and ROI membership would be wrong, and the run would still look successful.

    If someone wants the ``x_cm``/``y_cm`` columns, the way in is
    ``pixel_per_cm_ratio`` WITHOUT ``calibration`` — not this lookup.
    """
    descriptor = {
        "path": "C:/videos/exp.mp4",
        "metadata": {"aquarium_width_cm": 20.0, "aquarium_height_cm": 10.0},
    }

    assert _WorkerProcess._aquarium_dimensions_cm(descriptor) == (0.0, 0.0)


def test_settings_has_no_calibration_attribute():
    """The removed fallback probed an attribute that cannot exist.

    ``Settings`` is a Pydantic model with ``extra="forbid"``, so ``calibration``
    is not merely absent — it can never be added at runtime either. The old
    ``hasattr(settings, "calibration")`` branch was unreachable by construction.
    """
    from zebtrack.settings import Settings

    assert "calibration" not in Settings.model_fields
    assert Settings.model_config.get("extra") == "forbid"

import multiprocessing as mp
import os
import queue
import threading
import typing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
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
        class_role_map=None,
    ):
        self.plugin = plugin
        self.class_role_map = class_role_map
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


# ---------------------------------------------------------------------------
# ADR-009: the weight chosen in the PROJECT is the one the worker loads.
#
# Confirmed bug (AUDIT §1): the worker rebuilt its model from the global
# settings, so a project whose slot pointed at a rat weight processed every
# video with the zebrafish default and reported nothing unusual.
# ---------------------------------------------------------------------------


class _RecordingPlugin(FakePlugin):
    loaded_paths: typing.ClassVar[list[str]] = []

    def __init__(self, model_path: str, settings_obj):
        super().__init__(model_path, settings_obj)
        _RecordingPlugin.loaded_paths.append(str(model_path))


def _start_worker_and_capture_config(context, monkeypatch) -> WorkerConfig:
    from zebtrack.core.video import processing_worker as pw

    captured: dict[str, WorkerConfig] = {}

    class _CapturingProcess:
        def __init__(self, config, result_queue, command_queue):
            captured["config"] = config

        def start(self) -> None:
            return None

    def _no_shared_memory(*_args, **_kwargs):
        raise OSError("shared memory disabled in this test")

    monkeypatch.setattr(pw, "_WorkerProcess", _CapturingProcess)
    monkeypatch.setattr(pw, "SharedFrameBuffer", _no_shared_memory)
    monkeypatch.setattr(pw.ProcessingWorker, "_monitor_loop", lambda self: None)

    callbacks = cast(Any, SimpleNamespace())
    worker = pw.ProcessingWorker(context, callbacks)
    worker.start_in_thread().join(timeout=5)
    return captured["config"]


def _project_registry(tmp_path):
    from zebtrack.core.services.weight_manager import WeightManager
    from zebtrack.settings import load_settings

    settings = load_settings()
    settings.model_selection.animal_method = "det"
    settings.model_selection.use_openvino = False
    weights = tmp_path / "weights"
    weights.mkdir()
    zebra = weights / "best_det_topdown.pt"
    rat = weights / "best_det_topdown_rat_v1.pt"
    zebra.write_bytes(b"zebrafish")
    rat.write_bytes(b"rat")
    wm = WeightManager(settings_obj=settings, config_dir=tmp_path, weights_dir=weights)
    for path, default in ((zebra, True), (rat, False)):
        wm.weights[path.name] = {
            "path": str(path),
            "type": "det",
            "target": "aquarium",
            "perspective": settings.behavioral_analysis.aquarium_perspective,
            "is_default": default,
            "is_default_det": default,
            "is_default_det_aquarium": default,
            "is_default_det_zebrafish": False,
            "is_default_seg_aquarium": False,
            "is_default_seg_zebrafish": False,
            "openvino_path": "",
            "openvino_status": "not_converted",
        }
    wm.weights[rat.name]["class_roles"] = {"rat": "subject", "experimenter": "context"}
    return wm, settings, zebra, rat


def test_the_project_weight_is_the_one_the_worker_loads(tmp_path, monkeypatch):
    import threading

    from zebtrack.core.services.worker_model_resolution import resolve_worker_model
    from zebtrack.core.video.processing_worker import ProcessingContext

    wm, settings, zebra, rat = _project_registry(tmp_path)
    project = {"model_overrides": {"slot_weights": {"det:zebrafish": rat.name}}}
    context = ProcessingContext(
        videos_to_process=[],
        output_base_dir=str(tmp_path),
        cancel_event=threading.Event(),
        settings=settings,
        model_spec=resolve_worker_model(wm, settings, project),
    )

    config = _start_worker_and_capture_config(context, monkeypatch)

    assert config.model_path == str(rat)
    assert config.model_type == "yolo"
    assert config.weight_sha256 == wm.get_weight_sha256(rat.name)
    assert config.class_roles == {"rat": "subject", "experimenter": "context"}
    assert config.class_roles_source == "weight"

    _RecordingPlugin.loaded_paths.clear()
    worker = _WorkerProcess(config, mp.Queue(), mp.Queue())
    with (
        patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", _RecordingPlugin),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
    ):
        worker._initialize_detector()

    assert _RecordingPlugin.loaded_paths == [str(rat)]
    assert str(zebra) not in _RecordingPlugin.loaded_paths


def test_without_a_spec_the_worker_warns_and_uses_the_settings(tmp_path, monkeypatch):
    import threading

    from zebtrack.core.video import processing_worker as pw
    from zebtrack.core.video.processing_worker import ProcessingContext

    fake_log = MagicMock()
    monkeypatch.setattr(pw, "log", fake_log)
    settings = SimpleNamespace(
        model_selection=SimpleNamespace(use_openvino=False, animal_method="det"),
        yolo_model=SimpleNamespace(path="settings_default.pt"),
    )
    context = ProcessingContext(
        videos_to_process=[],
        output_base_dir=str(tmp_path),
        cancel_event=threading.Event(),
        settings=settings,
    )

    config = _start_worker_and_capture_config(context, monkeypatch)

    assert config.model_path == "settings_default.pt"
    assert config.weight_sha256 == ""
    assert config.class_roles is None
    warnings = [c.args[0] for c in fake_log.warning.call_args_list]
    assert "worker.model.spec_missing" in warnings


def test_the_spec_beats_the_settings_even_when_they_name_another_file(tmp_path, monkeypatch):
    import threading

    from zebtrack.core.services.worker_model_resolution import WorkerModelSpec
    from zebtrack.core.video.processing_worker import ProcessingContext

    settings = SimpleNamespace(
        model_selection=SimpleNamespace(use_openvino=True, animal_method="seg"),
        yolo_model=SimpleNamespace(path="settings_default.pt"),
    )
    spec = WorkerModelSpec(model_path="chosen.pt", model_type="yolo", weight_sha256="f" * 64)
    context = ProcessingContext(
        videos_to_process=[],
        output_base_dir=str(tmp_path),
        cancel_event=threading.Event(),
        settings=settings,
        model_spec=spec,
    )

    config = _start_worker_and_capture_config(context, monkeypatch)

    assert (config.model_path, config.model_type) == ("chosen.pt", "yolo")
    assert config.weight_sha256 == "f" * 64


def _barnes_plugin_class():
    class _BarnesPlugin(FakePlugin):
        class_names: typing.ClassVar[dict[int, str]] = {
            0: "arena",
            1: "experimenter",
            2: "rat",
            3: "start_box",
        }

    return _BarnesPlugin


def _init_with(config) -> Any:
    worker = _WorkerProcess(config, mp.Queue(), mp.Queue())
    with (
        patch(
            "zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin",
            _barnes_plugin_class(),
        ),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
    ):
        return worker._initialize_detector()


def test_worker_rebuilds_the_shipped_roles_against_the_model_names(worker_config):
    worker_config.weight_sha256 = "e" * 64
    worker_config.class_roles = {"rat": "subject", "experimenter": "context", "arena": "arena"}
    worker_config.class_roles_source = "weight"

    detector = _init_with(worker_config)

    role_map = detector.class_role_map
    assert role_map.subject_ids == frozenset({2})
    assert role_map.context_ids == frozenset({1})
    assert role_map.source.value == "weight"


def test_worker_project_roles_keep_their_source(worker_config):
    worker_config.weight_sha256 = "e" * 64
    worker_config.class_roles = {"experimenter": "subject"}
    worker_config.class_roles_source = "project"

    detector = _init_with(worker_config)

    assert detector.class_role_map.source.value == "project"
    assert detector.class_role_map.subject_ids == frozenset({1})


def test_worker_without_roles_uses_the_aliases(worker_config):
    detector = _init_with(worker_config)

    assert detector.class_role_map.source.value == "aliases"
    assert detector.class_role_map.to_legacy_tuple() == (0, 2)


def test_worker_with_a_spec_refuses_a_weight_without_a_subject(worker_config):
    from zebtrack.core.detection.class_roles import ClassRolesUnresolvedError

    class _CocoPlugin(FakePlugin):
        class_names: typing.ClassVar[dict[int, str]] = {0: "person", 1: "bicycle", 2: "car"}

    worker_config.weight_sha256 = "e" * 64
    worker = _WorkerProcess(worker_config, mp.Queue(), mp.Queue())
    with (
        patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", _CocoPlugin),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
        pytest.raises(ClassRolesUnresolvedError),
    ):
        worker._initialize_detector()


def test_worker_without_a_spec_keeps_the_7_2_positional_guess(worker_config):
    class _CocoPlugin(FakePlugin):
        class_names: typing.ClassVar[dict[int, str]] = {0: "person", 1: "bicycle", 2: "car"}

    worker = _WorkerProcess(worker_config, mp.Queue(), mp.Queue())
    with (
        patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", _CocoPlugin),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
    ):
        detector = worker._initialize_detector()

    assert detector.class_role_map.to_legacy_tuple() == (0, 1)


# =============================================================================
# Object sidecar ``3c_Objetos_`` written by the frame loop (ADR-010)
# =============================================================================

_SIDECAR_SHA = "ab" * 32
_RAT_ROLES = {"arena": "arena", "rat": "subject", "experimenter": "context"}
_RAT_NAMES = {0: "arena", 1: "rat", 2: "experimenter"}


def _read_3c(path):
    """Read a ``3c_Objetos_`` sidecar the test expects to be valid."""
    from zebtrack.io.object_sidecar import read_object_sidecar

    df = read_object_sidecar(path)
    assert df is not None, f"unreadable object sidecar: {path}"
    return df


def _golden_plugin_class():
    from tests.helpers.prerecorded_pipeline import GoldenDeterministicPlugin

    class _RatPlugin(GoldenDeterministicPlugin):
        """The golden square as class ``rat`` + an experimenter at the crop centre.

        ``blind_every`` makes every n-th call see nothing at all, so the loop
        processes frames that have no detection.
        """

        class_names: typing.ClassVar[dict[int, str]] = _RAT_NAMES

        def __init__(self, *, with_context: bool, blind_every: int = 0):
            super().__init__()
            self.with_context = with_context
            self.blind_every = blind_every
            self.calls = 0

        def detect(self, frame, conf_threshold=None):
            self.calls += 1
            if self.blind_every and self.calls % self.blind_every == 0:
                return []
            found = [(*det[:6], 1) for det in super().detect(frame, conf_threshold)]
            if self.with_context:
                h, w = frame.shape[:2]
                found.append((w // 2 - 10, h // 2 - 10, w // 2 + 10, h // 2 + 10, 0.8, None, 2))
            return found

    return _RatPlugin


def _run_frame_loop(
    tmp_path, *, interval, settings=None, with_context=False, blind_every=0, zone_dict=None
):
    """Drive ``_process_single_video`` in-process on the golden video."""
    from tests.helpers.prerecorded_pipeline import (
        ARENA_POLYGON,
        EXPERIMENT_ID,
        HEIGHT,
        WIDTH,
        _QueueStub,
        load_pristine_settings,
        write_golden_video,
    )

    from zebtrack.core.detection import Detector
    from zebtrack.core.detection.class_roles import resolve_class_role_map

    settings = settings or load_pristine_settings()
    video_path = tmp_path / f"{EXPERIMENT_ID}.mp4"
    try:
        write_golden_video(video_path)
    except RuntimeError as exc:  # pragma: no cover - codec-less CI image
        pytest.skip(str(exc))
    output_dir = tmp_path / "results"
    zone_dict = zone_dict or {
        "polygon": [[x, y] for x, y in ARENA_POLYGON],
        "roi_polygons": [],
        "roi_names": [],
        "roi_colors": [],
        "metadata": {"source_width": WIDTH, "source_height": HEIGHT},
    }
    task = {"path": str(video_path), "experiment_id": EXPERIMENT_ID, "zone_data": zone_dict}
    config = WorkerConfig(
        settings=settings,
        output_base_dir=str(output_dir),
        tasks=[task],
        single_video_mode=True,
        analysis_interval_frames=interval,
        display_interval_frames=10_000,
        zone_data=zone_dict,
        weight_sha256=_SIDECAR_SHA,
        class_roles=dict(_RAT_ROLES),
        class_roles_source="weight",
    )
    role_map = resolve_class_role_map(
        _RAT_NAMES, weight_entry={"class_roles": _RAT_ROLES}, weight_sha256="cd" * 32
    )
    plugin = _golden_plugin_class()(with_context=with_context, blind_every=blind_every)
    detector = Detector(
        plugin=plugin,
        base_width=WIDTH,
        base_height=HEIGHT,
        settings_obj=settings,
        class_role_map=role_map,
    )
    worker = _WorkerProcess(config, cast(Any, _QueueStub()), cast(Any, _QueueStub()))
    assert worker._process_single_video(
        index=0,
        total_videos=1,
        video_path=str(video_path),
        experiment_id=EXPERIMENT_ID,
        detector=detector,
        video_metadata=task,
    )
    return output_dir, EXPERIMENT_ID


def test_frame_loop_writes_a_heartbeat_on_every_processed_frame(tmp_path):
    """Frames with no detection still get their heartbeat; skipped frames get none."""
    import pandas as pd

    output_dir, base = _run_frame_loop(tmp_path, interval=3, blind_every=2)

    objects = _read_3c(output_dir / f"3c_Objetos_{base}.parquet")
    trajectory = pd.read_parquet(output_dir / f"3_CoordMovimento_{base}.parquet")
    heartbeat = objects[objects["class_id"] == -1]
    # config.yaml ships ``processing_offset: 1``: the 2nd frame of each interval (#638).
    processed = list(range(1, 120, 3))
    assert heartbeat["frame"].tolist() == processed
    # Every other processed frame was blind: the trajectory skips those frames.
    assert len(trajectory) == len(processed) // 2
    assert set(trajectory["frame"]) < set(processed)
    # Pre-recorded: the event clock IS the trajectory's PTS timestamp.
    assert (heartbeat["t_event_s"] == heartbeat["timestamp"]).all()
    merged = trajectory.merge(heartbeat, on="frame", suffixes=("_traj", "_obj"))
    assert len(merged) == len(trajectory)
    assert (merged["timestamp_traj"] == merged["timestamp_obj"]).all()


def test_frame_loop_records_context_observations_and_metadata(tmp_path):
    output_dir, base = _run_frame_loop(tmp_path, interval=4, with_context=True)

    objects = _read_3c(output_dir / f"3c_Objetos_{base}.parquet")
    context = objects[objects["role"] == "context"]
    subjects = objects[objects["role"] == "subject"]
    # config.yaml ships ``processing_offset: 1``: the 2nd frame of each interval (#638).
    processed = list(range(1, 120, 4))
    assert context["frame"].tolist() == processed
    assert set(context["class_name"]) == {"experimenter"}
    assert subjects["frame"].tolist() == processed
    assert set(subjects["class_name"]) == {"rat"}

    metadata = objects.attrs["objects_metadata"]
    assert metadata.clock == "pts"
    assert metadata.analysis_interval_frames == 4
    # The sha of the file the worker LOADED (config), not the map's.
    assert metadata.weight_sha256 == _SIDECAR_SHA
    assert metadata.class_names == _RAT_NAMES
    assert metadata.class_roles == _RAT_ROLES
    assert metadata.class_roles_source == "weight"


def test_frame_loop_honours_the_kill_switch(tmp_path):
    from tests.helpers.prerecorded_pipeline import load_pristine_settings

    settings = load_pristine_settings()
    settings.recorder.persist_object_sidecar = False

    output_dir, base = _run_frame_loop(tmp_path, interval=5, settings=settings)

    assert (output_dir / f"3_CoordMovimento_{base}.parquet").exists()
    assert not (output_dir / f"3c_Objetos_{base}.parquet").exists()


def test_frame_loop_multi_aquarium_writes_one_sidecar_per_aquarium(tmp_path):
    left = [[40, 40], [300, 40], [300, 440], [40, 440]]
    right = [[340, 40], [600, 40], [600, 440], [340, 440]]
    zone_dict = {
        "aquariums": [
            {"id": 0, "polygon": left, "group": "G", "subject_id": "S1", "day": 1},
            {"id": 1, "polygon": right, "group": "G", "subject_id": "S2", "day": 1},
        ],
        "video_width": 640,
        "video_height": 480,
    }

    output_dir, base = _run_frame_loop(tmp_path, interval=6, with_context=True, zone_dict=zone_dict)

    found = sorted(output_dir.rglob("3c_Objetos_*.parquet"))
    assert [p.name for p in found] == [
        f"3c_Objetos_{base}_aquarium_1.parquet",
        f"3c_Objetos_{base}_aquarium_2.parquet",
    ]
    # config.yaml ships ``processing_offset: 1``: the 2nd frame of each interval (#638).
    processed = list(range(1, 120, 6))
    for aquarium_id, path in enumerate(found):
        objects = _read_3c(path)
        heartbeat = objects[objects["class_id"] == -1]
        assert heartbeat["frame"].tolist() == processed
        assert set(heartbeat["aquarium_id"]) == {aquarium_id}
        # Each crop's experimenter sits inside that aquarium: routed there by
        # position (no null rows, nothing from the other aquarium).
        context = objects[objects["role"] == "context"]
        assert context["frame"].tolist() == processed
        assert set(context["aquarium_id"].tolist()) == {aquarium_id}
        subjects = objects[objects["role"] == "subject"]
        assert set(subjects["aquarium_id"].tolist()) <= {aquarium_id}


def test_frame_loop_applies_the_processing_offset(tmp_path):
    """#638: ``processing_offset=2`` with interval 5 analyses frames 2, 7, 12, ...

    The option was documented and validated but the loop sampled 0, N, 2N.
    """
    from tests.helpers.prerecorded_pipeline import load_pristine_settings

    settings = load_pristine_settings()
    settings.video_processing.processing_offset = 2

    output_dir, base = _run_frame_loop(tmp_path, interval=5, settings=settings)

    heartbeat = _read_3c(output_dir / f"3c_Objetos_{base}.parquet")
    heartbeat = heartbeat[heartbeat["class_id"] == -1]
    assert heartbeat["frame"].tolist() == list(range(2, 120, 5))


def test_frame_loop_builds_bytetrack_with_the_run_interval(tmp_path, monkeypatch):
    """#667: the Kalman dt is the cadence this run detects at, not the settings value.

    ``_initialize_detector`` used to be the only place the run's interval reached
    the tracker (by mutating the settings). The golden helper and any caller that
    hands ``_process_single_video`` its own detector skipped it, and tracked
    every frame with ``dt = 10``.
    """
    from tests.helpers.prerecorded_pipeline import load_pristine_settings

    from zebtrack.core.detection import single_detector as single_detector_module

    built_intervals: list[int] = []
    real_tracker = single_detector_module.BYTETracker

    def _spy(*args, **kwargs):
        built_intervals.append(kwargs["processing_interval"])
        return real_tracker(*args, **kwargs)

    monkeypatch.setattr(single_detector_module, "BYTETracker", _spy)
    settings = load_pristine_settings()
    settings.video_processing.processing_interval = 10

    _run_frame_loop(tmp_path, interval=3, settings=settings)

    assert built_intervals
    assert set(built_intervals) == {3}


# ---------------------------------------------------------------------------
# #645 — the worker publishes the role map its detector REALLY resolved
# ---------------------------------------------------------------------------


class TestFrameInfoClassRoles:
    def test_roles_travel_inside_info(self):
        from zebtrack.core.video.processing_worker import frame_info_with_roles

        info = frame_info_with_roles({"info": {"fps": 9.9}, "class_roles": {2: "subject"}})
        assert info == {"fps": 9.9, "class_roles": {2: "subject"}}

    def test_message_info_is_not_mutated(self):
        from zebtrack.core.video.processing_worker import frame_info_with_roles

        original = {"fps": 9.9}
        frame_info_with_roles({"info": original, "class_roles": {}})
        assert original == {"fps": 9.9}

    def test_empty_map_is_carried_not_dropped(self):
        from zebtrack.core.video.processing_worker import frame_info_with_roles

        assert frame_info_with_roles({"info": None, "class_roles": {}}) == {"class_roles": {}}

    def test_without_roles_info_passes_through(self):
        from zebtrack.core.video.processing_worker import frame_info_with_roles

        stats = {"fps": 1.0}
        assert frame_info_with_roles({"info": stats}) is stats

    def test_read_back(self):
        from zebtrack.core.video.processing_worker import class_roles_from_frame_info

        assert class_roles_from_frame_info({"class_roles": {0: "arena"}}) == {0: "arena"}
        assert class_roles_from_frame_info({"class_roles": {}}) == {}
        assert class_roles_from_frame_info({"fps": 1.0}) is None
        assert class_roles_from_frame_info({"class_roles": "subject"}) is None
        assert class_roles_from_frame_info(42) is None
        assert class_roles_from_frame_info(None) is None

    def test_monitor_hands_the_roles_to_on_frame_processed(self):
        """The main-process monitor forwards the map the child sent."""
        import numpy as np

        from zebtrack.core.video.processing_worker import (
            ProcessingCallbacks,
            ProcessingContext,
            ProcessingWorker,
        )

        received: list[Any] = []
        callbacks = ProcessingCallbacks(
            on_started=lambda: None,
            on_progress=lambda *a: None,
            on_frame_processed=lambda frame, dets, info: received.append(info),
            on_video_completed=lambda *a: None,
            on_error=lambda *a: None,
            on_completed=lambda *a: None,
            on_fatal_error=lambda *a: None,
        )
        context = ProcessingContext(
            videos_to_process=[],
            output_base_dir="out",
            cancel_event=threading.Event(),
            settings=MagicMock(),
        )
        worker = ProcessingWorker(context, callbacks)
        results: queue.Queue[Any] = queue.Queue()
        results.put(
            {
                "type": "frame",
                "frame": np.zeros((2, 2, 3), dtype=np.uint8),
                "detections": [],
                "info": {"fps": 5.0},
                "class_roles": {2: "subject"},
            }
        )
        results.put({"type": "completed", "cancelled": False})
        worker.result_queue = cast(Any, results)
        worker._monitor_loop()
        assert received == [{"fps": 5.0, "class_roles": {2: "subject"}}]


def test_worker_frame_messages_carry_the_detectors_role_map(tmp_path):
    """Every preview frame carries the map the worker's detector used (#645).

    The detector here runs the Barnes WEIGHT map (``experimenter`` = context);
    the UI resolving the same weight from aliases would call ``experimenter``
    ignored — the published map is the detector's, not a re-derivation.
    """
    from tests.helpers.prerecorded_pipeline import (
        BARNES_ARENA,
        BARNES_ID,
        BARNES_NAMES,
        BARNES_ROLES,
        BARNES_WEIGHT_SHA,
        HEIGHT,
        WIDTH,
        BarnesDeterministicPlugin,
        _as_vertex_lists,
        _QueueStub,
        load_pristine_settings,
        write_barnes_video,
    )

    from zebtrack.core.detection import Detector
    from zebtrack.core.detection.class_roles import resolve_class_role_map

    video_path = tmp_path / f"{BARNES_ID}.mp4"
    try:
        write_barnes_video(video_path)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    settings = load_pristine_settings()
    zone_dict = {
        "polygon": _as_vertex_lists(BARNES_ARENA),
        "roi_polygons": [],
        "roi_names": [],
        "metadata": {"source_width": WIDTH, "source_height": HEIGHT},
    }
    task = {"path": str(video_path), "experiment_id": BARNES_ID, "zone_data": zone_dict}
    config = WorkerConfig(
        settings=settings,
        output_base_dir=str(tmp_path / "results"),
        tasks=[task],
        single_video_mode=True,
        analysis_interval_frames=1,
        display_interval_frames=10,
        model_path="",
        model_type="yolo",
        zone_data=zone_dict,
    )
    results = _QueueStub()
    worker = _WorkerProcess(config, cast(Any, results), cast(Any, _QueueStub()))
    detector = Detector(
        plugin=BarnesDeterministicPlugin(),
        base_width=WIDTH,
        base_height=HEIGHT,
        settings_obj=settings,
        class_role_map=resolve_class_role_map(
            BARNES_NAMES,
            weight_entry={"class_roles": BARNES_ROLES},
            weight_sha256=BARNES_WEIGHT_SHA,
        ),
    )
    assert worker._process_single_video(
        index=0,
        total_videos=1,
        video_path=str(video_path),
        experiment_id=BARNES_ID,
        detector=detector,
        video_metadata=task,
    )
    frames = [m for m in results.items if isinstance(m, dict) and m.get("type") == "frame"]
    assert frames, "the worker sent no preview frame"
    expected = {0: "arena", 1: "context", 2: "subject", 3: "context"}
    assert all(m.get("class_roles") == expected for m in frames)


# ---------------------------------------------------------------------------
# ProcessingWorker (parent side): start_in_thread / _monitor_loop / cancel
# (TASK-087). Nothing here starts a process: the child is a scripted stand-in
# and the queues are plain in-memory queues, so the real parent-side code runs
# on the test thread and the assertions are on what the callbacks received.
# ---------------------------------------------------------------------------


class _ScriptedQueue:
    """Queue whose ``get`` never blocks: yields its items, then ``queue.Empty``.

    ``hook`` (optional) runs on every ``get`` with the 1-based call number, so
    a test can flip the cancel event between two polls of the monitor loop.
    """

    def __init__(self, items=(), hook=None):
        self.items = list(items)
        self.hook = hook
        self.gets = 0
        self.puts: list[Any] = []

    def put(self, item):
        self.puts.append(item)

    def get(self, timeout=None):
        self.gets += 1
        if self.hook is not None:
            self.hook(self.gets)
        if not self.items:
            raise queue.Empty
        return self.items.pop(0)

    def get_nowait(self):
        return self.get()


class _FakeChild:
    """Stands in for ``_WorkerProcess`` in the parent."""

    script: typing.ClassVar[list[Any]] = []
    instances: typing.ClassVar[list["_FakeChild"]] = []

    def __init__(self, config, result_queue, command_queue):
        self.config = config
        self.result_queue = result_queue
        self.command_queue = command_queue
        self.started = False
        self.alive = False
        self.terminated = False
        self.join_timeouts: list[Any] = []
        type(self).instances.append(self)

    def start(self):
        self.started = True
        for message in type(self).script:
            self.result_queue.put(message)

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)

    def terminate(self):
        self.terminated = True


class _Calls:
    """Records every callback of a ``ProcessingCallbacks``."""

    def __init__(self):
        self.events: list[tuple[str, tuple[Any, ...]]] = []

    def _rec(self, name):
        def _record(*args):
            self.events.append((name, args))

        return _record

    def named(self, name):
        return [args for event, args in self.events if event == name]

    def callbacks(self):
        from zebtrack.core.video.processing_worker import ProcessingCallbacks

        return ProcessingCallbacks(
            on_started=self._rec("started"),
            on_progress=self._rec("progress"),
            on_frame_processed=self._rec("frame"),
            on_video_completed=self._rec("video_completed"),
            on_error=self._rec("error"),
            on_completed=self._rec("completed"),
            on_fatal_error=self._rec("fatal"),
        )


def _make_parent(monkeypatch, *, zone_data=None, model_spec=None, settings=None, **context_kw):
    """A ``ProcessingWorker`` wired to in-memory queues and the fake child."""
    from zebtrack.core.video import processing_worker as pw

    monkeypatch.setattr(pw.multiprocessing, "Queue", queue.Queue)
    _FakeChild.script = []
    _FakeChild.instances = []
    monkeypatch.setattr(pw, "_WorkerProcess", _FakeChild)
    calls = _Calls()
    context = pw.ProcessingContext(
        videos_to_process=[{"path": "a.mp4"}],
        output_base_dir="out_dir",
        cancel_event=threading.Event(),
        settings=settings if settings is not None else SimpleNamespace(),
        zone_data=zone_data,
        model_spec=model_spec,
        **context_kw,
    )
    worker = pw.ProcessingWorker(context, calls.callbacks())
    return worker, calls


def _scripted_clock(monkeypatch, values):
    """Replace ``time.monotonic`` as the monitor loop sees it."""
    from zebtrack.core.video import processing_worker as pw

    ticks = iter(values)
    monkeypatch.setattr(pw, "time", SimpleNamespace(monotonic=lambda: next(ticks)))


def _frame(value=7):
    return np.full((4, 6, 3), value, dtype=np.uint8)


class TestMonitorLoopMessages:
    def test_each_message_type_reaches_its_callback_with_exact_arguments(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        frame = _frame()
        worker.result_queue = _ScriptedQueue(
            [
                {
                    "type": "progress",
                    "index": 2,
                    "total": 5,
                    "experiment_id": "E2",
                    "fraction": 0.5,
                    "message": "half",
                    "stats": {"fps": 3},
                },
                # No index/total/experiment_id/stats: the documented defaults.
                {"type": "progress", "fraction": 0.1, "message": "tick"},
                {
                    "type": "frame",
                    "frame": frame,
                    "detections": [(1, 2, 3, 4, 0.9, 7, 0)],
                    "info": {"frame": 3},
                    "class_roles": {0: "subject"},
                },
                {"type": "video_completed", "index": 4, "experiment_id": "E4", "success": False},
                {"type": "error", "error": "disk full", "experiment_id": "E5"},
                {"type": "error", "error": "no id"},
                {"type": "completed", "cancelled": True, "summary": {"n": 1}},
                {"type": "progress", "fraction": 1.0, "message": "never read"},
            ]
        )
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        assert calls.named("started") == [()]
        assert calls.named("progress") == [
            (2, 5, "E2", 0.5, "half", {"fps": 3}),
            (0, 1, "", 0.1, "tick", None),
        ]
        ((got_frame, detections, info),) = calls.named("frame")
        assert got_frame is frame
        assert detections == [(1, 2, 3, 4, 0.9, 7, 0)]
        # ``info`` travels with the role map merged in (frame_info_with_roles).
        assert info == {"frame": 3, "class_roles": {0: "subject"}}
        # The total is not echoed back by the child, so the parent reports 0.
        assert calls.named("video_completed") == [(4, 0, "E4", False)]
        errors = calls.named("error")
        assert [(str(e), exp) for e, exp in errors] == [("disk full", "E5"), ("no id", "unknown")]
        # ``completed`` carries the PARENT's output dir and ends the loop: the
        # progress queued after it is never consumed.
        assert calls.named("completed") == [(True, "out_dir", {"n": 1})]
        assert len(worker.result_queue.items) == 1

    def test_frame_without_pixels_is_not_forwarded(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.result_queue = _ScriptedQueue(
            [{"type": "frame", "detections": []}, {"type": "completed"}]
        )
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        assert calls.named("frame") == []
        # ``cancelled`` and ``summary`` default to False / None.
        assert calls.named("completed") == [(False, "out_dir", None)]

    def test_frame_is_read_from_shared_memory_and_falls_back_to_the_pickle(self, monkeypatch):
        from zebtrack.core.video.shared_frame_buffer import SharedFrameBuffer

        worker, calls = _make_parent(monkeypatch)
        buffer = SharedFrameBuffer(name=f"zt_test_{id(worker)}", max_bytes=4 * 6 * 3, create=True)
        worker._shm_buffer = buffer
        shm_pixels = _frame(200)
        meta = buffer.write(shm_pixels)
        pickled = _frame(9)
        worker.result_queue = _ScriptedQueue(
            [
                # Matching sequence: the shared-memory pixels win over the payload.
                {"type": "frame", "frame": pickled, **meta},
                # Stale sequence: ``read`` returns None, the pickled frame is used.
                {"type": "frame", "frame": pickled, "shm_seq": meta["shm_seq"] + 5},
                {"type": "completed"},
            ]
        )
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        frames = [args[0] for args in calls.named("frame")]
        assert len(frames) == 2
        assert np.array_equal(frames[0], shm_pixels)
        assert frames[1] is pickled
        # The loop releases the block it owns and forgets it.
        assert worker._shm_buffer is None

    def test_fatal_error_prefers_the_fatal_callback_and_stops_the_loop(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.result_queue = _ScriptedQueue(
            [{"type": "fatal_error", "error": "boom"}, {"type": "progress", "fraction": 1}]
        )
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        ((error, context, info),) = calls.named("fatal")
        assert (str(error), context, info) == (
            "boom",
            "Fatal Worker Error",
            {"affected_videos": []},
        )
        assert calls.named("error") == []
        assert calls.named("progress") == []
        assert calls.named("completed") == []

    def test_fatal_error_degrades_to_on_error_without_a_fatal_callback(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.callbacks.on_fatal_error = cast(Any, None)
        worker.result_queue = _ScriptedQueue([{"type": "fatal_error", "error": "boom"}])
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        ((error, context),) = calls.named("error")
        assert (str(error), context) == ("boom", "Fatal Worker Error")

    @pytest.mark.parametrize("has_fatal", [True, False])
    def test_a_raising_callback_ends_the_loop_through_the_error_channel(
        self, monkeypatch, has_fatal
    ):
        worker, calls = _make_parent(monkeypatch)

        def explode(*_args):
            raise RuntimeError("callback bug")

        worker.callbacks.on_progress = explode
        if not has_fatal:
            worker.callbacks.on_fatal_error = cast(Any, None)
        worker.result_queue = _ScriptedQueue(
            [
                {"type": "progress", "fraction": 0.1, "message": "x"},
                {"type": "video_completed", "index": 0, "experiment_id": "E", "success": True},
            ]
        )
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        channel = calls.named("fatal" if has_fatal else "error")
        ((error, *rest),) = channel
        assert str(error) == "callback bug"
        assert rest[0] == "Monitor loop failure"
        # The loop stopped at the failure: the next message is still queued.
        assert len(worker.result_queue.items) == 1
        assert calls.named("video_completed") == []

    def test_unknown_message_types_are_counted_and_ignored(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.result_queue = _ScriptedQueue([{"type": "mystery"}, {"type": "completed"}])
        worker.process = _FakeChild(None, None, None)

        worker._monitor_loop()

        assert [event for event, _ in calls.events] == ["started", "completed"]


class TestMonitorLoopLifecycle:
    def test_cancel_is_forwarded_once_however_long_the_loop_keeps_polling(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.command_queue = _ScriptedQueue()
        child = _FakeChild(None, None, None)
        child.alive = True
        worker.process = child

        results = _ScriptedQueue()

        def hook(call_number):
            if call_number == 1:
                worker.context.cancel_event.set()
            if call_number == 4:
                results.items.append({"type": "completed", "cancelled": True})

        results.hook = hook
        worker.result_queue = results

        worker._monitor_loop()

        assert worker.command_queue.puts == ["cancel"]
        assert calls.named("completed") == [(True, "out_dir", None)]

    def test_a_child_that_dies_silently_is_reported_after_the_grace_window(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        child = _FakeChild(None, None, None)  # not alive
        worker.process = child
        worker.result_queue = _ScriptedQueue()
        # 1st empty poll arms the timer (t=100); 2nd is inside the 1 s window
        # (100.9); 3rd is past it (101.0 is exactly 1.0 s: not "< 1.0").
        _scripted_clock(monkeypatch, [100.0, 100.9, 101.0])

        worker._monitor_loop()

        assert worker.result_queue.gets == 3
        ((error, context, info),) = calls.named("fatal")
        assert str(error) == "Worker exited without completion signal"
        assert (context, info) == ("Worker monitor", {"affected_videos": []})
        assert calls.named("completed") == []

    def test_a_message_resets_the_grace_window(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.process = _FakeChild(None, None, None)  # dead from the start
        worker.result_queue = _ScriptedQueue()
        script = [
            "empty",  # arms the timer at t=10
            {"type": "progress", "fraction": 0.2, "message": "late flush"},
            "empty",  # arms it AGAIN at t=50 — not 40 s past the old one
            "empty",  # t=50.2: inside the window
            "empty",  # t=51.5: past it
        ]

        def feed(call_number):
            step = script[call_number - 1]
            if step != "empty":
                worker.result_queue.items.append(step)

        worker.result_queue.hook = feed
        _scripted_clock(monkeypatch, [10.0, 50.0, 50.2, 51.5])

        worker._monitor_loop()

        assert worker.result_queue.gets == 5
        assert len(calls.named("progress")) == 1
        assert len(calls.named("fatal")) == 1

    def test_a_dead_child_without_fatal_callback_still_ends_the_loop(self, monkeypatch):
        worker, calls = _make_parent(monkeypatch)
        worker.callbacks.on_fatal_error = cast(Any, None)
        worker.process = _FakeChild(None, None, None)
        worker.result_queue = _ScriptedQueue()
        _scripted_clock(monkeypatch, [1.0, 5.0])

        worker._monitor_loop()

        assert calls.events == [("started", ())]

    def test_a_child_that_outlives_the_join_is_terminated(self, monkeypatch):
        worker, _ = _make_parent(monkeypatch)
        child = _FakeChild(None, None, None)
        child.alive = True
        worker.process = child
        worker.result_queue = _ScriptedQueue([{"type": "completed"}])

        worker._monitor_loop()

        assert child.join_timeouts == [2.0]
        assert child.terminated is True

    def test_a_child_that_exits_in_time_is_left_alone(self, monkeypatch):
        worker, _ = _make_parent(monkeypatch)
        child = _FakeChild(None, None, None)
        worker.process = child
        worker.result_queue = _ScriptedQueue([{"type": "completed"}])

        worker._monitor_loop()

        assert child.terminated is False

    def test_cancel_sets_the_event_and_reports_whether_the_monitor_stopped(self, monkeypatch):
        worker, _ = _make_parent(monkeypatch)
        # No monitor thread yet: nothing to wait for.
        assert worker.cancel() is True
        assert worker.context.cancel_event.is_set()

        release = threading.Event()
        stuck = threading.Thread(target=release.wait, daemon=True)
        stuck.start()
        worker._monitor_thread = stuck
        try:
            # A monitor that does not stop within the timeout is reported as running.
            assert worker.cancel(timeout=0.01) is False
            assert worker.is_running is True
        finally:
            release.set()
            stuck.join(5)
        assert worker.cancel(timeout=5) is True
        assert worker.is_running is False


class TestStartInThread:
    def _run(self, worker):
        thread = worker.start_in_thread()
        thread.join(10)
        assert not thread.is_alive()
        return thread

    def test_the_child_gets_the_spec_model_and_the_monitor_is_a_daemon(self, monkeypatch):
        spec = SimpleNamespace(
            model_type="openvino",
            model_path="weights/mouse_openvino_model",
            weight_name="mouse",
            resolved_from="project",
            class_roles_source="project",
            weight_sha256="ab" * 32,
            class_roles={"mouse": "subject"},
        )
        worker, calls = _make_parent(
            monkeypatch,
            model_spec=spec,
            analysis_interval_frames=7,
            display_interval_frames=3,
            single_video_config={"x": 1},
        )
        _FakeChild.script = [{"type": "completed"}]

        thread = worker.start_in_thread()
        assert thread.daemon is True
        assert thread.name == "ProcessingMonitor"
        thread.join(10)

        (child,) = _FakeChild.instances
        assert child.started is True
        config = child.config
        assert (config.model_type, config.model_path) == (
            "openvino",
            "weights/mouse_openvino_model",
        )
        assert config.weight_sha256 == "ab" * 32
        assert config.class_roles == {"mouse": "subject"}
        assert config.class_roles_source == "project"
        assert config.single_video_mode is True
        assert (config.analysis_interval_frames, config.display_interval_frames) == (7, 3)
        assert config.output_base_dir == "out_dir"
        assert config.tasks == [{"path": "a.mp4"}]
        # The shared block was created, then released by the monitor at the end.
        assert config.shm_name == f"zebtrack_preview_{os.getpid()}"
        assert worker._shm_buffer is None
        assert calls.named("completed") == [(False, "out_dir", None)]

    def test_a_spec_without_roles_sends_none_and_an_empty_source(self, monkeypatch):
        spec = SimpleNamespace(
            model_type="yolo",
            model_path="m.pt",
            weight_name=None,
            resolved_from="settings",
            class_roles_source=None,
            weight_sha256="",
            class_roles=None,
        )
        worker, _ = _make_parent(monkeypatch, model_spec=spec)
        _FakeChild.script = [{"type": "completed"}]

        self._run(worker)

        config = _FakeChild.instances[0].config
        assert config.class_roles is None
        assert config.class_roles_source == ""
        assert config.single_video_mode is False

    def test_without_a_spec_the_model_is_rebuilt_from_the_settings(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        settings = SimpleNamespace(
            model_selection=SimpleNamespace(use_openvino=False, animal_method="det"),
            yolo_model=SimpleNamespace(path="legacy.pt"),
        )
        worker, _ = _make_parent(monkeypatch, settings=settings)
        _FakeChild.script = [{"type": "completed"}]

        self._run(worker)

        config = _FakeChild.instances[0].config
        assert (config.model_type, config.model_path) == ("yolo", "legacy.pt")
        assert config.weight_sha256 == ""
        assert config.class_roles_source == ""

    def test_a_second_start_returns_the_running_monitor_without_a_second_child(self, monkeypatch):
        worker, _ = _make_parent(monkeypatch)
        gate = threading.Event()
        worker._monitor_thread = threading.Thread(target=gate.wait, daemon=True)
        worker._monitor_thread.start()
        try:
            assert worker.start_in_thread() is worker._monitor_thread
            assert _FakeChild.instances == []
        finally:
            gate.set()
            worker._monitor_thread.join(5)

    def test_zone_data_is_serialised_for_the_child(self, monkeypatch):
        from zebtrack.core.project.zone_manager import ZoneManager

        zone = ZoneData(
            polygon=[[0, 0], [9, 0], [9, 9]],
            roi_polygons=[[[1, 1], [2, 1], [2, 2]]],
            roi_names=["r"],
            roi_colors=[(1, 2, 3)],
            metadata={"source_video_width": 9},
        )
        worker, _ = _make_parent(monkeypatch, zone_data=zone)
        _FakeChild.script = [{"type": "completed"}]
        self._run(worker)
        assert _FakeChild.instances[0].config.zone_data == {
            "polygon": [[0, 0], [9, 0], [9, 9]],
            "roi_polygons": [[[1, 1], [2, 1], [2, 2]]],
            "roi_names": ["r"],
            "roi_colors": [(1, 2, 3)],
            "metadata": {"source_video_width": 9},
        }

        # A dict passes through untouched.
        as_dict = {"polygon": [[1, 1]], "extra": True}
        worker, _ = _make_parent(monkeypatch, zone_data=as_dict)
        _FakeChild.script = [{"type": "completed"}]
        self._run(worker)
        assert _FakeChild.instances[0].config.zone_data is as_dict

        # Multi-aquarium data goes through ZoneManager and keeps its marker.
        multi = MultiAquariumZoneData(aquariums=[], video_width=640, video_height=480)
        worker, _ = _make_parent(monkeypatch, zone_data=multi)
        _FakeChild.script = [{"type": "completed"}]
        self._run(worker)
        assert _FakeChild.instances[
            0
        ].config.zone_data == ZoneManager.multi_aquarium_zone_data_to_dict(multi)

        # No zones at all: the child is told there is nothing to restore.
        worker, _ = _make_parent(monkeypatch, zone_data=None)
        _FakeChild.script = [{"type": "completed"}]
        self._run(worker)
        assert _FakeChild.instances[0].config.zone_data is None

    def test_without_shared_memory_the_child_is_told_to_use_the_pickle(self, monkeypatch):
        from zebtrack.core.video import processing_worker as pw

        def refuse(*_a, **_k):
            raise OSError("no shm here")

        monkeypatch.setattr(pw, "SharedFrameBuffer", refuse)
        worker, _ = _make_parent(monkeypatch)
        _FakeChild.script = [{"type": "completed"}]

        self._run(worker)

        assert _FakeChild.instances[0].config.shm_name == ""
        assert worker._shm_buffer is None


class TestModelFromSettings:
    @staticmethod
    def _settings(*, use_openvino, method, det="det.pt", seg="seg.pt", source_dir="weights"):
        weights = SimpleNamespace(
            source_dir=source_dir,
            get_filenames_for_perspective=lambda perspective: SimpleNamespace(
                det_filename=det, seg_filename=seg, perspective=perspective
            ),
        )
        return SimpleNamespace(
            model_selection=SimpleNamespace(use_openvino=use_openvino, animal_method=method),
            weights=weights,
            behavioral_analysis=SimpleNamespace(aquarium_perspective="top_down"),
            yolo_model=SimpleNamespace(path="fallback.pt"),
        )

    def test_settings_without_model_selection_default_to_yolo_and_no_path(self):
        from zebtrack.core.video.processing_worker import ProcessingWorker

        assert ProcessingWorker._model_from_settings(SimpleNamespace()) == ("yolo", "")

    def test_the_weight_file_on_disk_wins_and_follows_the_animal_method(
        self, monkeypatch, tmp_path
    ):
        from zebtrack.core.video.processing_worker import ProcessingWorker

        monkeypatch.chdir(tmp_path)
        (tmp_path / "weights").mkdir()
        (tmp_path / "weights" / "det.pt").write_bytes(b"x")
        (tmp_path / "weights" / "seg.pt").write_bytes(b"x")

        det = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=False, method="det")
        )
        seg = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=False, method="seg")
        )

        assert det == ("yolo", os.path.join("weights", "det.pt"))
        assert seg == ("yolo", os.path.join("weights", "seg.pt"))

    def test_a_missing_weight_file_falls_back_to_the_yolo_model_path(self, monkeypatch, tmp_path):
        from zebtrack.core.video.processing_worker import ProcessingWorker

        monkeypatch.chdir(tmp_path)
        result = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=False, method="det")
        )
        assert result == ("yolo", "fallback.pt")

        blank = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=False, method="det", det="")
        )
        assert blank == ("yolo", "fallback.pt")

    def test_openvino_uses_the_cached_export_when_it_exists(self, monkeypatch, tmp_path):
        from zebtrack.core.video.processing_worker import ProcessingWorker

        monkeypatch.chdir(tmp_path)
        (tmp_path / "weights").mkdir()
        (tmp_path / "weights" / "det.pt").write_bytes(b"x")
        cache = tmp_path / "openvino_model_cache" / "det_openvino_model"
        cache.mkdir(parents=True)

        result = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=True, method="det")
        )

        assert result == ("openvino", os.path.abspath(cache))

    def test_openvino_without_a_cached_export_degrades_to_yolo(self, monkeypatch, tmp_path):
        from zebtrack.core.video.processing_worker import ProcessingWorker

        monkeypatch.chdir(tmp_path)
        (tmp_path / "weights").mkdir()
        (tmp_path / "weights" / "det.pt").write_bytes(b"x")

        result = ProcessingWorker._model_from_settings(
            self._settings(use_openvino=True, method="det")
        )

        assert result == ("yolo", os.path.join("weights", "det.pt"))


# ---------------------------------------------------------------------------
# _WorkerProcess.run / _process_single_video with a scripted capture (TASK-087)
# ---------------------------------------------------------------------------

_W, _H = 64, 48


class _ScriptedCapture:
    """``cv2.VideoCapture`` stand-in: frame ``i`` carries ``i`` in pixel [0, 0, 0].

    ``timestamp`` after reading frame ``i`` is ``i * 100`` ms.
    """

    def __init__(self, n_frames, *, width=_W, height=_H, count=None, fps=10.0, opened=True):
        self.frames = []
        for i in range(n_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[0, 0, 0] = i
            self.frames.append(frame)
        self.pos = 0
        self.opened = opened
        self.released = False
        self.reads = 0
        self.grabs = 0
        self.props = {
            cv2.CAP_PROP_FRAME_WIDTH: width,
            cv2.CAP_PROP_FRAME_HEIGHT: height,
            cv2.CAP_PROP_FRAME_COUNT: n_frames if count is None else count,
            cv2.CAP_PROP_FPS: fps,
        }

    def isOpened(self):
        return self.opened

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC:
            return (self.pos - 1) * 100.0
        return self.props.get(prop, 0.0)

    def read(self):
        self.reads += 1
        if self.pos >= len(self.frames):
            return False, None
        frame = self.frames[self.pos]
        self.pos += 1
        return True, frame.copy()

    def grab(self):
        self.grabs += 1
        if self.pos >= len(self.frames):
            return False
        self.pos += 1
        return True

    def release(self):
        self.released = True


class _IndexPlugin:
    """Detector plugin: the box depends on the frame index stored in the frame."""

    class_names: typing.ClassVar[dict[int, str]] = {}

    def __init__(self, hits):
        self.hits = hits  # frame index -> (x1, y1, x2, y2)

    def detect(self, frame, conf_threshold=None):
        box = self.hits.get(int(frame[0, 0, 0]))
        if box is None:
            return []
        return [(*box, 0.9, 1, 0)]

    @staticmethod
    def get_name():
        return "IndexPlugin"

    @property
    def model_input_shape(self):
        return (_W, _H)


def _zone(width=_W, height=_H):
    return {
        "polygon": [[0, 0], [width, 0], [width, height], [0, height]],
        "roi_polygons": [],
        "roi_names": [],
        "roi_colors": [],
        "metadata": {},
    }


class _Run:
    """One ``_process_single_video`` run wired to a scripted capture."""

    def __init__(self, tmp_path, monkeypatch, *, capture, hits=None, **config_kw):
        import pandas as pd
        from tests.helpers.prerecorded_pipeline import load_pristine_settings

        from zebtrack.core.detection import Detector

        self.pd = pd
        self.tmp_path = tmp_path
        self.capture = capture
        self.opened_with: list[Any] = []

        def factory(arg):
            self.opened_with.append(arg)
            return capture

        monkeypatch.setattr(cv2, "VideoCapture", factory)
        self.settings = load_pristine_settings()
        zone = config_kw.pop(
            "zone",
            _zone(
                capture.props[cv2.CAP_PROP_FRAME_WIDTH], capture.props[cv2.CAP_PROP_FRAME_HEIGHT]
            ),
        )
        self.out = tmp_path / "out"
        self.out.mkdir(exist_ok=True)
        config = WorkerConfig(
            settings=self.settings,
            output_base_dir=str(self.out),
            tasks=[],
            single_video_mode=config_kw.pop("single_video_mode", True),
            analysis_interval_frames=config_kw.pop("interval", 1),
            display_interval_frames=config_kw.pop("display", 10_000),
            zone_data=zone,
        )
        self.results = _ScriptedQueue()
        self.commands = _ScriptedQueue()
        self.worker = _WorkerProcess(config, cast(Any, self.results), cast(Any, self.commands))
        self.worker._default_zone_data = None
        self.zone = zone
        self.detector = Detector(
            plugin=cast(Any, _IndexPlugin(hits or {})),
            base_width=capture.props[cv2.CAP_PROP_FRAME_WIDTH],
            base_height=capture.props[cv2.CAP_PROP_FRAME_HEIGHT],
            settings_obj=self.settings,
        )

    def run(self, video_path="clip.mp4", experiment_id="EXP", metadata=None):
        task = {"path": str(video_path), "experiment_id": experiment_id, "zone_data": self.zone}
        task.update(metadata or {})
        return self.worker._process_single_video(
            index=0,
            total_videos=1,
            video_path=video_path,
            experiment_id=experiment_id,
            detector=self.detector,
            video_metadata=task,
        )

    def trajectory(self, directory=None, experiment_id="EXP"):
        path = (directory or self.out) / f"3_CoordMovimento_{experiment_id}.parquet"
        return self.pd.read_parquet(path)

    def messages(self, kind):
        return [m for m in self.results.puts if isinstance(m, dict) and m.get("type") == kind]


class TestProcessSingleVideo:
    def test_only_analysed_frames_are_decoded_and_recorded_with_their_pts(
        self, tmp_path, monkeypatch
    ):
        cap = _ScriptedCapture(10)
        # The pristine config has processing_offset = 1, so at interval 3 the
        # analysed frames are 1, 4, 7 (frame_num % 3 == 1).
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=cap,
            hits={1: (10, 10, 20, 20), 4: (11, 10, 21, 20)},
            interval=3,
            display=1,
        )

        assert run.run() is True

        trajectory = run.trajectory()
        assert trajectory["frame"].tolist() == [1, 4]
        assert trajectory["timestamp"].round(6).tolist() == [0.1, 0.4]
        assert trajectory["x1"].tolist() == [10, 11]
        # 1, 4, 7 and the failing read of frame 10 are reads; 7 frames are grabbed.
        assert cap.reads == 4
        assert cap.grabs == 7
        assert cap.released is True
        frames = run.messages("frame")
        assert [m["info"]["frame"] for m in frames] == [1, 4, 7]
        assert [m["info"]["processed_frames"] for m in frames] == [1, 2, 3]
        # Frame 7 has no detection: 2 of the 3 processed frames detected something.
        assert [m["info"]["detected_frames"] for m in frames] == [1, 2, 2]
        assert all(m["info"]["total_frames"] == 10 for m in frames)
        assert frames[0]["experiment_id"] == "EXP"
        progress = [m for m in run.messages("progress") if m["message"] == "Processing..."]
        assert [m["fraction"] for m in progress] == [0.1, 0.4, 0.7]
        assert all(m["stats"] is not None for m in progress)

    def test_a_video_shorter_than_its_header_ends_the_run_cleanly(self, tmp_path, monkeypatch):
        # The container claims 50 frames; only 4 exist.
        cap = _ScriptedCapture(4, count=50)
        run = _Run(tmp_path, monkeypatch, capture=cap, hits={0: (1, 1, 5, 5)})

        assert run.run() is True

        assert run.trajectory()["frame"].tolist() == [0]
        assert cap.reads == 5  # the fifth read is the one that fails
        assert cap.released is True

    def test_end_of_video_is_also_detected_on_a_skipped_frame(self, tmp_path, monkeypatch):
        cap = _ScriptedCapture(2)
        run = _Run(tmp_path, monkeypatch, capture=cap, hits={1: (1, 1, 5, 5)}, interval=3)

        assert run.run() is True

        # The pristine offset is 1: frame 0 is grabbed, frame 1 is read and
        # analysed, frame 2 is grabbed and the grab fails.
        assert (cap.reads, cap.grabs) == (1, 2)
        assert run.trajectory()["frame"].tolist() == [1]

    def test_an_unopenable_video_raises_with_the_path(self, tmp_path, monkeypatch):
        run = _Run(tmp_path, monkeypatch, capture=_ScriptedCapture(3, opened=False))
        with pytest.raises(FileNotFoundError, match="missing.mp4"):
            run.run(video_path="missing.mp4")

    @pytest.mark.parametrize("source", ["0", Path("2")])
    def test_a_numeric_source_opens_the_camera_index_not_a_file(
        self, tmp_path, monkeypatch, source
    ):
        run = _Run(tmp_path, monkeypatch, capture=_ScriptedCapture(1))
        assert run.run(video_path=source) is True
        assert run.opened_with == [int(str(source))]

    def test_a_path_is_opened_as_a_string(self, tmp_path, monkeypatch):
        run = _Run(tmp_path, monkeypatch, capture=_ScriptedCapture(1))
        run.run(video_path=tmp_path / "clip.mp4")
        assert run.opened_with == [str(tmp_path / "clip.mp4")]

    def test_a_cancel_before_the_first_frame_records_nothing_and_closes_the_capture(
        self, tmp_path, monkeypatch
    ):
        cap = _ScriptedCapture(5)
        run = _Run(tmp_path, monkeypatch, capture=cap, hits={0: (1, 1, 5, 5)})
        run.commands.items.append("cancel")

        assert run.run() is False

        assert cap.reads == 0
        assert cap.released is True
        assert len(run.trajectory()) == 0
        assert run.worker._cancel_requested is True

    def test_a_cancel_after_detection_drops_that_frame(self, tmp_path, monkeypatch):
        cap = _ScriptedCapture(5)
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=cap,
            hits={i: (1, 1, 5, 5) for i in range(5)},
        )
        # Poll 1 is the loop head of frame 0, poll 2 the check after its
        # detection; the third poll (frame 1's head) would be too late.
        run.commands.hook = lambda n: run.commands.items.append("cancel") if n == 2 else None

        assert run.run() is False

        assert cap.reads == 1
        assert cap.released is True
        assert len(run.trajectory()) == 0
        assert run.messages("frame") == []

    def test_unknown_commands_are_ignored(self, tmp_path, monkeypatch):
        cap = _ScriptedCapture(2)
        run = _Run(tmp_path, monkeypatch, capture=cap, hits={0: (1, 1, 5, 5)})
        run.commands.items.append("pause")

        assert run.run() is True

        assert run.worker._cancel_requested is False
        assert run.trajectory()["frame"].tolist() == [0]

    def test_batch_mode_writes_into_the_task_results_dir(self, tmp_path, monkeypatch):
        target = tmp_path / "Grupo_A" / "Dia_1" / "Sujeito_2"
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=_ScriptedCapture(2),
            hits={0: (1, 1, 5, 5)},
            single_video_mode=False,
        )

        assert run.run(metadata={"results_dir": str(target)}) is True

        assert run.trajectory(target)["frame"].tolist() == [0]

    @pytest.mark.parametrize("bad", [None, 42, ""])
    def test_batch_mode_without_a_usable_results_dir_falls_back_next_to_the_video(
        self, tmp_path, monkeypatch, bad
    ):
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=_ScriptedCapture(2),
            hits={0: (1, 1, 5, 5)},
            single_video_mode=False,
        )
        video = tmp_path / "videos" / "EXP.mp4"

        assert run.run(video_path=str(video), metadata={"results_dir": bad}) is True

        assert run.trajectory(tmp_path / "videos" / "EXP_results")["frame"].tolist() == [0]

    def test_tall_previews_are_scaled_to_1280_px_with_their_boxes(self, tmp_path, monkeypatch):
        cap = _ScriptedCapture(1, width=1400, height=10)
        run = _Run(tmp_path, monkeypatch, capture=cap, hits={0: (140, 2, 700, 8)}, display=1)

        assert run.run() is True

        (message,) = run.messages("frame")
        assert message["frame"].shape[1] == 1280
        scale = 1280 / 1400
        (x1, y1, x2, y2, confidence, track_id, class_id) = message["detections"][0]
        assert (x1, y1, x2, y2) == (
            round(140 * scale),
            round(2 * scale),
            round(700 * scale),
            round(8 * scale),
        )
        assert confidence == pytest.approx(0.9)
        # The detector stamps the subject role's class id (1), not the plugin's 0.
        assert class_id == 1
        # The trajectory itself stays in RAW pixels.
        assert run.trajectory()["x1"].tolist() == [140]

    def test_six_tuple_detections_are_scaled_too(self, tmp_path, monkeypatch):
        cap = _ScriptedCapture(1, width=2560, height=4)
        run = _Run(tmp_path, monkeypatch, capture=cap, display=1)
        run.detector.detect = cast(  # type: ignore[method-assign]
            Any, lambda frame, project_type=None: ([(256, 0, 512, 2, 0.5, 3)], frame)
        )
        assert run.run() is True
        (message,) = run.messages("frame")
        assert message["detections"] == [(128, 0, 256, 1, 0.5, 3)]

    def test_preview_goes_through_shared_memory_when_it_fits(self, tmp_path, monkeypatch):
        from zebtrack.core.video.shared_frame_buffer import SharedFrameBuffer

        cap = _ScriptedCapture(1)
        run = _Run(tmp_path, monkeypatch, capture=cap, display=1)
        buffer = SharedFrameBuffer(name=f"zt_run_{id(run)}", max_bytes=_W * _H * 3, create=True)
        try:
            run.worker._shm_buffer = buffer
            assert run.run() is True
            (message,) = run.messages("frame")
            assert message["shm_seq"] == 1
            assert "frame" not in message
            assert message["shm_shape"] == (_H, _W, 3)
            assert buffer.read(1) is not None
        finally:
            buffer.close_and_unlink()

    def test_preview_falls_back_to_the_pickle_when_shared_memory_refuses(
        self, tmp_path, monkeypatch
    ):
        from zebtrack.core.video.shared_frame_buffer import SharedFrameBuffer

        cap = _ScriptedCapture(1)
        run = _Run(tmp_path, monkeypatch, capture=cap, display=1)
        buffer = SharedFrameBuffer(name=f"zt_small_{id(run)}", max_bytes=10, create=True)
        try:
            run.worker._shm_buffer = buffer
            assert run.run() is True
            (message,) = run.messages("frame")
            assert "shm_seq" not in message
            assert message["frame"].shape == (_H, _W, 3)
        finally:
            buffer.close_and_unlink()

    def test_without_a_polygon_the_detector_is_told_no_arena_exists(self, tmp_path, monkeypatch):
        zone: dict[str, Any] = {
            "polygon": [],
            "roi_polygons": [],
            "roi_names": [],
            "roi_colors": [],
        }
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=_ScriptedCapture(1),
            hits={0: (1, 1, 5, 5)},
            zone=zone,
        )
        assert run.run() is True
        assert run.detector._aquarium_region_defined is False

    def test_top_level_aquarium_dimensions_calibrate_the_recording(self, tmp_path, monkeypatch):
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=_ScriptedCapture(2),
            hits={0: (10, 10, 20, 20)},
        )

        assert run.run(metadata={"aquarium_width_cm": 32.0, "aquarium_height_cm": 24.0}) is True

        trajectory = run.trajectory()
        assert trajectory["frame"].tolist() == [0]
        assert trajectory["x_cm"].notna().all()

    def test_a_degenerate_polygon_does_not_stop_the_run_when_calibrating(
        self, tmp_path, monkeypatch
    ):
        from zebtrack.core.detection import calibration as calibration_module

        def reject(*_args, **_kwargs):
            raise ValueError("homography failed")

        monkeypatch.setattr(calibration_module, "Calibration", reject)
        run = _Run(
            tmp_path,
            monkeypatch,
            capture=_ScriptedCapture(2),
            hits={0: (1, 1, 5, 5)},
        )

        assert run.run(metadata={"aquarium_width_cm": 32.0, "aquarium_height_cm": 24.0}) is True

        trajectory = run.trajectory()
        assert trajectory["frame"].tolist() == [0]
        # The recording ran uncalibrated: raw pixels, no cm.
        assert "x_cm" not in trajectory.columns
        assert trajectory["x1"].tolist() == [1]


# ---------------------------------------------------------------------------
# _WorkerProcess.run(): task loop, ids, error isolation (TASK-087)
# ---------------------------------------------------------------------------


class _AttachSpy:
    """``SharedFrameBuffer`` stand-in for the attach side of ``run``."""

    created: typing.ClassVar[list["_AttachSpy"]] = []

    def __init__(self, name, create=True):
        self.name = name
        self.create = create
        self.closed = False
        self.unlinked = False
        type(self).created.append(self)

    def close(self):
        self.closed = True

    def close_and_unlink(self):
        self.closed = True
        self.unlinked = True


def _run_child(monkeypatch, tasks, *, init=None, process=None, shm_name="", commands=()):
    """A ``_WorkerProcess`` whose heavy collaborators are scripted.

    ``run`` is the orchestration under test; the detector build and the
    per-video decode loop have their own tests, so they are scripted here.
    """
    from zebtrack import logging_config

    monkeypatch.setattr(logging_config, "configure_logging", lambda **_kw: None)
    config = WorkerConfig(
        settings=SimpleNamespace(),
        output_base_dir="out",
        tasks=tasks,
        shm_name=shm_name,
    )
    results = _ScriptedQueue()
    commands_queue = _ScriptedQueue(commands)
    child = _WorkerProcess(config, cast(Any, results), cast(Any, commands_queue))
    detector = object()
    seen: list[dict[str, Any]] = []

    def default_init():
        return detector

    def default_process(**kwargs):
        seen.append(kwargs)
        return True

    monkeypatch.setattr(child, "_initialize_detector", init or default_init)
    monkeypatch.setattr(child, "_process_single_video", process or default_process)
    if process is None:
        child._seen = seen  # type: ignore[attr-defined]
    return child, results, detector


class TestWorkerRun:
    def test_each_task_gets_its_id_a_progress_a_result_and_the_full_path(self, monkeypatch):
        tasks = [
            {"path": "/v/Dia_1/CECT_4/CECT_4.mp4"},
            {"path": "/v/Dia_2/CECT_4/CECT_4.mp4"},
            {"path": "", "experiment_id": None},
            {"path": "a.mp4", "experiment_id": "X", "aquarium_id": 1},
        ]
        child, results, detector = _run_child(monkeypatch, tasks)

        child.run()

        seen = child._seen
        # Two videos share the basename CECT_4: they stay two tasks, told apart
        # by the FULL path handed to the processing loop.
        assert [s["video_path"] for s in seen] == [
            "/v/Dia_1/CECT_4/CECT_4.mp4",
            "/v/Dia_2/CECT_4/CECT_4.mp4",
            "",
            "a.mp4",
        ]
        assert [s["experiment_id"] for s in seen] == ["CECT_4", "CECT_4", "video_3", "X_aq2"]
        assert [s["index"] for s in seen] == [0, 1, 2, 3]
        assert all(s["total_videos"] == 4 and s["detector"] is detector for s in seen)
        assert [s["video_metadata"] for s in seen] == tasks

        progress = [m for m in results.puts if m["type"] == "progress"]
        assert [(m["index"], m["total"], m["fraction"], m["message"]) for m in progress] == [
            (0, 4, 0.0, "Starting: CECT_4"),
            (1, 4, 0.0, "Starting: CECT_4"),
            (2, 4, 0.0, "Starting: video_3"),
            (3, 4, 0.0, "Starting: X_aq2"),
        ]
        done = [m for m in results.puts if m["type"] == "video_completed"]
        assert [(m["index"], m["experiment_id"], m["success"]) for m in done] == [
            (0, "CECT_4", True),
            (1, "CECT_4", True),
            (2, "video_3", True),
            (3, "X_aq2", True),
        ]
        assert results.puts[-1] == {"type": "completed", "cancelled": False}

    def test_a_video_that_returns_false_is_reported_as_unsuccessful(self, monkeypatch):
        child, results, _ = _run_child(
            monkeypatch, [{"path": "a.mp4"}], process=lambda **_kw: False
        )
        child.run()
        (done,) = [m for m in results.puts if m["type"] == "video_completed"]
        assert done["success"] is False

    def test_a_failing_video_is_reported_and_the_next_one_still_runs(self, monkeypatch):
        calls: list[str] = []

        def process(**kwargs):
            calls.append(kwargs["experiment_id"])
            if kwargs["experiment_id"] == "bad":
                raise FileNotFoundError("Could not open video: bad.mp4")
            return True

        child, results, _ = _run_child(
            monkeypatch,
            [{"path": "bad.mp4"}, {"path": "good.mp4"}],
            process=process,
        )

        child.run()

        assert calls == ["bad", "good"]
        (error,) = [m for m in results.puts if m["type"] == "error"]
        assert error["experiment_id"] == "bad"
        assert error["error"] == "Could not open video: bad.mp4"
        assert "FileNotFoundError" in error["traceback"]
        # No video_completed for the failed one, one for the good one.
        done = [m for m in results.puts if m["type"] == "video_completed"]
        assert [m["experiment_id"] for m in done] == ["good"]
        assert results.puts[-1] == {"type": "completed", "cancelled": False}

    def test_a_detector_that_cannot_be_built_is_fatal_and_still_completes(self, monkeypatch):
        def init():
            raise RuntimeError("weights missing")

        child, results, _ = _run_child(monkeypatch, [{"path": "a.mp4"}], init=init)

        child.run()

        types = [m["type"] for m in results.puts]
        assert types == ["fatal_error", "completed"]
        assert results.puts[0]["error"] == "weights missing"
        assert "RuntimeError" in results.puts[0]["traceback"]

    def test_a_cancel_command_stops_before_the_first_video(self, monkeypatch):
        child, results, _ = _run_child(
            monkeypatch, [{"path": "a.mp4"}, {"path": "b.mp4"}], commands=["cancel"]
        )

        child.run()

        assert child._seen == []
        assert results.puts == [{"type": "completed", "cancelled": True}]

    def test_a_cancel_between_videos_skips_the_rest(self, monkeypatch):
        commands = _ScriptedQueue()

        def process(**kwargs):
            commands.items.append("cancel")
            return True

        child, results, _ = _run_child(
            monkeypatch,
            [{"path": "a.mp4"}, {"path": "b.mp4"}],
            process=process,
        )
        child.command_queue = commands

        child.run()

        done = [m for m in results.puts if m["type"] == "video_completed"]
        assert [m["experiment_id"] for m in done] == ["a"]
        assert results.puts[-1] == {"type": "completed", "cancelled": True}

    def test_the_child_attaches_to_the_shared_block_and_only_closes_it(self, monkeypatch):
        from zebtrack.core.video import processing_worker as pw

        _AttachSpy.created = []
        monkeypatch.setattr(pw, "SharedFrameBuffer", _AttachSpy)
        child, _, _ = _run_child(monkeypatch, [], shm_name="zt_block")

        child.run()

        (spy,) = _AttachSpy.created
        assert (spy.name, spy.create) == ("zt_block", False)
        # The parent owns the block: the child closes its handle, never unlinks.
        assert spy.closed is True and spy.unlinked is False
        assert child._shm_buffer is None

    def test_a_block_that_cannot_be_attached_falls_back_to_the_pickle(self, monkeypatch):
        from zebtrack.core.video import processing_worker as pw

        def refuse(*_a, **_k):
            raise FileNotFoundError("gone")

        monkeypatch.setattr(pw, "SharedFrameBuffer", refuse)
        child, results, _ = _run_child(monkeypatch, [{"path": "a.mp4"}], shm_name="zt_block")

        child.run()

        assert child._shm_buffer is None
        assert [m["type"] for m in results.puts][-1] == "completed"
        assert len(child._seen) == 1

    def test_without_a_block_name_nothing_is_attached(self, monkeypatch):
        from zebtrack.core.video import processing_worker as pw

        _AttachSpy.created = []
        monkeypatch.setattr(pw, "SharedFrameBuffer", _AttachSpy)
        child, _, _ = _run_child(monkeypatch, [], shm_name="")
        child.run()
        assert _AttachSpy.created == []


# ---------------------------------------------------------------------------
# _initialize_detector / zones / dimension repair / cancellation queue errors
# ---------------------------------------------------------------------------


class _OvPlugin(FakePlugin):
    def __init__(self, model_path, settings_obj, mode):
        super().__init__(model_path, settings_obj)
        self.mode = mode


def _child(config):
    return _WorkerProcess(config, cast(Any, _ScriptedQueue()), cast(Any, _ScriptedQueue()))


def _build_detector(child):
    with (
        patch("zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", FakePlugin),
        patch("zebtrack.plugins.openvino_detector.OpenVINOPlugin", _OvPlugin),
        patch("zebtrack.core.video.processing_worker.Detector", FakeDetector),
    ):
        return child._initialize_detector()


class TestInitializeDetector:
    def test_openvino_models_use_the_openvino_plugin_in_batch_mode(self, worker_config):
        worker_config.model_type = "openvino"
        worker_config.model_path = "cache/mouse_openvino_model"
        child = _child(worker_config)

        detector = _build_detector(child)

        assert isinstance(detector.plugin, _OvPlugin)
        assert detector.plugin.mode == "batch"
        assert detector.plugin.model_path == "cache/mouse_openvino_model"

    def test_an_empty_model_path_falls_back_to_the_settings_path(self, worker_config):
        worker_config.model_path = ""
        detector = _build_detector(_child(worker_config))
        assert detector.plugin.model_path == "model.pt"

    @pytest.mark.parametrize(
        ("per_aquarium", "tracker", "expected"),
        [(False, False, False), (True, False, True), (False, True, True)],
    )
    def test_single_subject_mode_comes_from_either_setting(
        self, worker_config, per_aquarium, tracker, expected
    ):
        settings = worker_config.settings
        settings.video_processing.single_animal_per_aquarium = per_aquarium
        settings.tracking.use_single_subject_tracker = tracker
        detector = _build_detector(_child(worker_config))
        assert detector.single_mode is expected

    def test_a_matching_interval_leaves_the_settings_alone(self, worker_config):
        worker_config.analysis_interval_frames = 2  # fixture already has 2
        _build_detector(_child(worker_config))
        assert worker_config.settings.video_processing.processing_interval == 2

    def test_single_zone_data_is_restored_with_its_metadata(self, worker_config):
        worker_config.zone_data = {
            "polygon": [[0, 0], [5, 0], [5, 5]],
            "roi_polygons": [[[1, 1], [2, 1], [2, 2]]],
            "roi_names": ["r"],
            "roi_colors": [[1, 2, 3]],
            "metadata": {"source_video_width": 320},
        }
        child = _child(worker_config)

        _build_detector(child)

        zone = child._default_zone_data
        assert isinstance(zone, ZoneData)
        assert zone.polygon == [[0, 0], [5, 0], [5, 5]]
        assert zone.roi_names == ["r"]
        assert zone.roi_colors == [[1, 2, 3]]
        assert zone.metadata == {"source_video_width": 320}

    def test_multi_aquarium_zone_data_is_restored_as_such(self, worker_config):
        from zebtrack.core.project.zone_manager import ZoneManager

        multi = MultiAquariumZoneData(aquariums=[], video_width=640, video_height=480)
        worker_config.zone_data = ZoneManager.multi_aquarium_zone_data_to_dict(multi)
        child = _child(worker_config)

        _build_detector(child)

        assert isinstance(child._default_zone_data, MultiAquariumZoneData)
        assert (child._default_zone_data.video_width, child._default_zone_data.video_height) == (
            640,
            480,
        )

    @pytest.mark.parametrize("per_video", [True, False])
    def test_without_global_zones_the_default_is_an_empty_zone(self, worker_config, per_video):
        worker_config.zone_data = None
        worker_config.tasks = (
            [{"path": "a.mp4", "zone_data": {"polygon": [[0, 0]]}}]
            if per_video
            else [
                {"path": "a.mp4"},
                "not a task",
            ]
        )
        child = _child(worker_config)

        _build_detector(child)

        assert isinstance(child._default_zone_data, ZoneData)
        assert child._default_zone_data.polygon == []


class TestResolveClassRoleMap:
    def test_a_project_override_wins_and_is_bound_to_the_weight_sha(self, worker_config):
        worker_config.class_roles = {"cage": "arena", "mouse": "subject"}
        worker_config.class_roles_source = "project"
        worker_config.weight_sha256 = "ab" * 32
        plugin = SimpleNamespace(class_names={0: "cage", 1: "mouse"})

        roles = _child(worker_config)._resolve_class_role_map(plugin)

        assert roles.source == "project"
        assert roles.role_of_name("mouse") == "subject"
        assert roles.role_of_name("cage") == "arena"
        assert roles.weight_sha256 == "ab" * 32

    def test_a_weight_level_map_is_used_when_the_source_is_not_the_project(self, worker_config):
        worker_config.class_roles = {"arena": "arena", "rat": "subject", "box": "context"}
        worker_config.class_roles_source = "weight"
        worker_config.weight_sha256 = "cd" * 32
        plugin = SimpleNamespace(class_names={0: "arena", 1: "rat", 2: "box"})

        roles = _child(worker_config)._resolve_class_role_map(plugin)

        assert roles.source == "weight"
        assert roles.role_of_name("box") == "context"

    def test_without_roles_the_aliases_decide_and_two_classes_stay_legal(self, worker_config):
        plugin = SimpleNamespace(class_names={0: "aquarium", 1: "fish"})

        roles = _child(worker_config)._resolve_class_role_map(plugin)

        assert roles.role_of_name("fish") == "subject"


class TestZoneDataForVideo:
    def test_a_multi_aquarium_dict_on_the_task_becomes_multi_aquarium_data(self, worker_config):
        from zebtrack.core.project.zone_manager import ZoneManager

        multi = MultiAquariumZoneData(aquariums=[], video_width=100, video_height=50)
        child = _child(worker_config)

        zone = child._get_zone_data_for_video(
            {"path": "v.mp4", "zone_data": ZoneManager.multi_aquarium_zone_data_to_dict(multi)}
        )

        assert isinstance(zone, MultiAquariumZoneData)
        assert (zone.video_width, zone.video_height) == (100, 50)

    def test_no_default_zone_yields_an_empty_one(self, worker_config):
        child = _child(worker_config)
        child._default_zone_data = None
        zone = child._get_zone_data_for_video({"path": "v.mp4"})
        assert isinstance(zone, ZoneData)
        assert zone.polygon == []

    def test_a_non_dict_zone_payload_falls_back_to_the_default(self, worker_config):
        child = _child(worker_config)
        default = ZoneData(polygon=[[0, 0], [1, 0], [1, 1]])
        child._default_zone_data = default
        assert child._get_zone_data_for_video({"path": "v.mp4", "zone_data": "junk"}) is default

    def test_a_multi_aquarium_default_is_returned_as_is(self, worker_config):
        from zebtrack.core.detection.detection_types import AquariumData

        child = _child(worker_config)
        aquarium = AquariumData(id=0, polygon=[[0, 0], [4, 0], [4, 4]])
        default = MultiAquariumZoneData(aquariums=[aquarium], video_width=4, video_height=4)
        child._default_zone_data = default
        assert child._get_zone_data_for_video({"path": "v.mp4"}) is default


class TestDimensionRepair:
    def test_area_ratio_is_zero_for_unusable_inputs(self):
        ratio = _WorkerProcess._polygon_area_ratio_for_base
        square = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        kw = {"actual_width": 100, "actual_height": 100}

        assert ratio(square, base_width=0, base_height=10, **kw) == 0.0
        assert ratio(square, base_width=10, base_height=-1, **kw) == 0.0
        assert ratio(ZoneData(polygon=[[0, 0], [1, 1]]), base_width=10, base_height=10, **kw) == 0.0
        assert ratio(square, base_width=10, base_height=10, actual_width=0, actual_height=5) == 0.0

    def test_area_ratio_is_the_scaled_polygon_over_the_frame(self):
        square = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        # base 20x20 -> frame 100x100: the 10x10 square becomes 50x50 = 25 % of the frame.
        value = _WorkerProcess._polygon_area_ratio_for_base(
            square, base_width=20, base_height=20, actual_width=100, actual_height=100
        )
        assert value == pytest.approx(0.25)

    def test_repair_is_skipped_for_unknown_dimensions_and_multi_aquarium(self, worker_config):
        child = _child(worker_config)
        zone = ZoneData(polygon=[[0, 0], [1, 0], [1, 1]])
        kw = {"actual_width": 640, "actual_height": 480}

        assert child._repair_source_dimensions_if_needed(
            zone, source_width=None, source_height=480, **kw
        ) == (None, 480)
        multi = MultiAquariumZoneData(aquariums=[], video_width=1, video_height=1)
        assert child._repair_source_dimensions_if_needed(
            multi, source_width=10, source_height=10, **kw
        ) == (10, 10)

    def test_repair_is_skipped_without_desired_dimensions(self, worker_config):
        worker_config.settings.camera.desired_width = 0
        child = _child(worker_config)
        zone = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])
        assert child._repair_source_dimensions_if_needed(
            zone, source_width=10000, source_height=10000, actual_width=640, actual_height=480
        ) == (10000, 10000)

    def test_repair_requires_a_realistic_desired_area(self, worker_config):
        # Both bases make the arena tiny: nothing to prefer, the source is kept.
        child = _child(worker_config)  # desired 320x240
        zone = ZoneData(polygon=[[0, 0], [2, 0], [2, 2], [0, 2]])
        assert child._repair_source_dimensions_if_needed(
            zone, source_width=10000, source_height=10000, actual_width=640, actual_height=480
        ) == (10000, 10000)


class TestCheckCancellationQueueFaults:
    @pytest.mark.parametrize("error", [OSError("pipe"), EOFError(), ValueError("closed")])
    def test_a_broken_command_queue_cancels_the_run(self, worker_config, error):
        child = _child(worker_config)

        def broken():
            raise error

        child.command_queue.get_nowait = broken  # type: ignore[attr-defined]

        assert child._check_cancellation() is True
        assert child._cancel_requested is True

    def test_a_late_cancel_is_seen_by_the_blocking_read(self, worker_config):
        child = _child(worker_config)
        queue_ = _ScriptedQueue()
        child.command_queue = cast(Any, queue_)
        # get_nowait finds nothing, the timed read finds the command.
        calls = {"n": 0}

        def nowait():
            raise queue.Empty

        def timed(timeout=None):
            calls["n"] += 1
            assert timeout == 0.005
            return "cancel"

        queue_.get_nowait = nowait  # type: ignore[method-assign]
        queue_.get = timed  # type: ignore[method-assign]

        assert child._check_cancellation() is True
        assert calls["n"] == 1

    def test_the_hot_loop_never_blocks(self, worker_config):
        child = _child(worker_config)
        queue_ = _ScriptedQueue()
        child.command_queue = cast(Any, queue_)

        assert child._check_cancellation(wait_s=0.0) is False

        # Only the non-blocking read was attempted.
        assert queue_.gets == 1

    def test_an_empty_timed_read_is_not_a_cancel(self, worker_config):
        child = _child(worker_config)
        child.command_queue = cast(Any, _ScriptedQueue())
        assert child._check_cancellation() is False
        assert child.command_queue.gets == 2  # nowait, then the timed read

    def test_an_unknown_command_is_ignored(self, worker_config):
        child = _child(worker_config)
        child.command_queue = cast(Any, _ScriptedQueue(["pause"]))
        assert child._check_cancellation() is False
        assert child._cancel_requested is False


def test_worker_process_is_a_daemon_so_closing_the_app_never_waits_for_the_batch(
    worker_config,
):
    """A6-S2: a non-daemon child is ``join()``-ed by multiprocessing at exit.

    The monitor thread that would ``terminate()`` it is itself a daemon thread
    and dies with the interpreter, so a worker that ignores the cancel kept the
    closed application alive until the whole batch finished.
    """
    worker = _WorkerProcess(worker_config, mp.Queue(), mp.Queue())

    assert worker.daemon is True
    assert worker.name == "ZebTrack-ProcessingWorker"

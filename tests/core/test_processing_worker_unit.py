import multiprocessing as mp
import queue
import typing
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

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

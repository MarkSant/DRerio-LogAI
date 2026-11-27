"""Tests for AnalysisControlViewModel."""

from __future__ import annotations

from pathlib import Path
from threading import Event as ThreadingEvent
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.analysis.time_base import (
    SOURCE_HEARTBEAT,
    SOURCE_LEDGER,
    SOURCE_TRAJECTORY,
    TimeBase,
)
from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents


@pytest.fixture
def view_model():
    """Create a view model with minimal dependencies."""
    settings = SimpleNamespace(
        model_selection=SimpleNamespace(animal_method="seg", use_openvino=False)
    )
    state_manager = Mock()
    state_manager.get_processing_state.return_value = SimpleNamespace(is_processing=False)

    processing_coordinator = Mock()
    processing_coordinator.processing_worker = None
    processing_coordinator.processing_thread = Mock()
    processing_coordinator.processing_thread.is_alive.return_value = False

    # Phase 4.7: Use live_camera_session_coordinator instead of session_coordinator
    live_camera_session_coordinator = Mock()
    live_camera_session_coordinator.live_camera_service = Mock()
    live_camera_session_coordinator.live_camera_service.camera = None

    dependencies = SimpleNamespace(
        video_processing_service=Mock(),
        processing_coordinator=processing_coordinator,
        live_camera_session_coordinator=live_camera_session_coordinator,
        state_manager=state_manager,
        project_manager=Mock(),
        settings_obj=settings,
    )
    bootstrap_result = SimpleNamespace(
        analysis_service=Mock(),
        ui_state_controller=Mock(),
        hardware=SimpleNamespace(recorder=Mock()),
        runtime=SimpleNamespace(cancel_event=ThreadingEvent()),
    )
    event_bus = Mock()
    return AnalysisControlViewModel(
        cast(Any, dependencies),
        cast(Any, bootstrap_result),
        event_bus,
    )


def test_is_processing_reads_state(view_model):
    """Reads processing state from StateManager."""
    view_model.state_manager.get_processing_state.return_value = SimpleNamespace(is_processing=True)

    assert view_model.is_processing is True


def test_start_single_video_workflow_invalid_det_config(view_model):
    """Publish error when det mode has multiple animals."""
    config = {"animal_method": "det", "animals_per_aquarium": 2}

    view_model.start_single_video_workflow("/video.mp4", config)

    view_model.ui_event_bus.publish.assert_called_once()
    event = view_model.ui_event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.SHOW_ERROR
    assert event.data.title == "Invalid Configuration"


def test_start_single_video_workflow_detector_setup_failure(view_model):
    """Early return when detector setup fails."""
    detector_vm = Mock()
    detector_vm.detector = None
    detector_vm.setup_detector.return_value = False

    view_model.start_single_video_workflow("/video.mp4", {"animal_method": "seg"}, detector_vm)

    view_model.ui_event_bus.publish.assert_not_called()
    view_model.project_manager.set_active_zone_video.assert_called_once_with(
        str(Path("/video.mp4"))
    )


def test_start_single_video_workflow_detector_setup_success(view_model):
    """Publish setup event when detector is ready."""
    detector_vm = Mock()
    detector_vm.detector = None
    detector_vm.setup_detector.return_value = True

    config = {"animal_method": "seg", "use_openvino": True}
    view_model.start_single_video_workflow("/video.mp4", config, detector_vm)

    assert detector_vm.use_openvino is True
    view_model.project_manager.set_active_zone_video.assert_called_once_with(
        str(Path("/video.mp4"))
    )
    from zebtrack.ui.payloads import SetupZoneDefinitionPayload

    view_model.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO,
            data=SetupZoneDefinitionPayload(video_path=str(Path("/video.mp4")), config=config),
        )
    )


def test_start_single_video_workflow_without_detector_vm(view_model):
    """Publish setup event even without detector VM."""
    config = {"animal_method": "seg"}

    view_model.start_single_video_workflow("/video.mp4", config)

    view_model.ui_event_bus.publish.assert_called_once()
    event = view_model.ui_event_bus.publish.call_args[0][0]
    assert event.type == UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO
    assert event.data.config == config


def test_start_single_video_processing_delegates(view_model):
    """Delegate to ProcessingCoordinator."""
    view_model.start_single_video_processing(
        video_path="/video.mp4", config={"x": 1}, zone_data="zone"
    )

    view_model.processing_coordinator.start_single_video_processing.assert_called_once_with(
        video_path="/video.mp4", config={"x": 1}, zone_data="zone"
    )


def test_cancel_current_analysis_no_active_processing(view_model):
    """No-op when nothing is running."""
    view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is False
    view_model.state_manager.update_processing_state.assert_not_called()
    view_model.ui_event_bus.publish.assert_not_called()
    view_model.ui_state_controller._show_cancel_feedback.assert_not_called()


def test_cancel_current_analysis_stops_live_session(view_model):
    """Stops live session and requests cancel."""
    view_model.live_camera_session_coordinator.live_camera_service.camera = object()
    view_model.live_camera_session_coordinator.stop_live_session.return_value = True

    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is True
    view_model.live_camera_session_coordinator.stop_live_session.assert_called_once()
    view_model.processing_coordinator.cancel_processing.assert_called_once()
    view_model.state_manager.update_processing_state.assert_called_once()
    view_model.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.SET_STATUS,
            data=payloads.StatusPayload(message="Cancelling the analysis in progress..."),
        )
    )
    view_model.ui_state_controller._show_cancel_feedback.assert_called_once()
    tmock.assert_called_once()


def test_generate_parquet_summaries_starts_thread(view_model):
    """Starts background thread for summaries."""
    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.generate_parquet_summaries(["/v1.mp4", "/v2.mp4"])

    tmock.assert_called_once()
    tmock.return_value.start.assert_called_once()


def test_generate_summaries_applies_the_analysis_window(view_model, tmp_path):
    """The summary entry resolves the window like the report coordinator (ADR-011)."""
    trajectory = tmp_path / "3_CoordMovimento_exp1.parquet"
    trajectory.write_text("data")
    pm = view_model.project_manager
    pm.find_video_entry.return_value = {"experiment_id": "exp1", "metadata": {}}
    pm.resolve_results_directory.return_value = str(tmp_path)
    pm.project_data = {"analysis_window": {"version": 1}}
    pm.get_zone_data.return_value = SimpleNamespace(
        polygon=[],
        roi_polygons=[[(10, 10), (60, 10), (60, 60), (10, 60)]],
        roi_names=["toca"],
        roi_colors=[],
    )
    view_model.analysis_service.collect_analysis_parameters.return_value = {
        "freezing_vel_threshold": 1.0,
        "freezing_min_duration": 1.0,
        "smoothing_window_length": 5,
        "smoothing_polyorder": 2,
    }
    sentinel = object()

    with (
        patch(
            "zebtrack.core.viewmodels.analysis_control_view_model.resolve_analysis_window",
            return_value=sentinel,
        ) as resolve,
        patch("zebtrack.analysis.reporters.ReporterContext"),
        patch("zebtrack.analysis.reporters.ExcelReporter"),
        patch("zebtrack.analysis.reporters.ParquetSummaryReporter"),
        patch("zebtrack.analysis.reporters.WordReporter"),
        patch("zebtrack.core.video.video_metadata_service.VideoMetadataService"),
        patch(
            "zebtrack.core.viewmodels.analysis_control_view_model.resolve_recording_time_base",
            side_effect=_TimeBaseStub(),
        ),
    ):
        view_model._generate_summaries_impl(["v.mp4"])

    args, kwargs = resolve.call_args
    assert args[1] == str(trajectory)
    assert [roi.name for roi in kwargs["rois"]] == ["toca"]
    call = view_model.analysis_service.run_full_analysis_as_dto.call_args
    assert call.kwargs["window"] is sentinel


def test_generate_summaries_hands_the_project_profile_to_the_protocol_hook(
    view_model, tmp_path, monkeypatch
):
    """A Barnes project analysed from "Generate summaries" reaches its protocol (ADR-014).

    Without the project's behavioural config the analysis fell back to the settings
    defaults, which carry no profile, and the protocol metrics read status none.
    """
    import pandas as pd

    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.analysis.protocols import registry
    from zebtrack.analysis.protocols.base import ProtocolSpec
    from zebtrack.core.services.experiment_profile import ProtocolId
    from zebtrack.settings import load_settings

    seen = []

    def compute(context):
        seen.append(context)
        return {"status": "ok", "protocol": "barnes", "version": 1, "reason": None}

    spec = ProtocolSpec(
        protocol=ProtocolId.BARNES, display_name=lambda: "Barnes", compute_metrics=compute
    )
    monkeypatch.setattr(registry, "_registry", registry._build_registry((spec,)))

    frames = list(range(40))
    xs = [100.0 + 2.0 * f for f in frames]
    pd.DataFrame(
        {
            "timestamp": [f / 10 for f in frames],
            "frame": frames,
            "track_id": [1] * len(frames),
            "x1": [x - 5 for x in xs],
            "y1": [195.0] * len(frames),
            "x2": [x + 5 for x in xs],
            "y2": [205.0] * len(frames),
            "confidence": [0.9] * len(frames),
            "x_center_px": xs,
            "y_center_px": [200.0] * len(frames),
        }
    ).to_parquet(tmp_path / "3_CoordMovimento_exp1.parquet")
    pm = view_model.project_manager
    pm.find_video_entry.return_value = {
        "experiment_id": "exp1",
        "metadata": {},
        "protocol_inputs": {"barnes": {"trial_type": "probe"}},
    }
    pm.resolve_results_directory.return_value = str(tmp_path)
    pm.project_data = {"behavioral_config": {"protocol": "barnes"}, "calibration": {}}
    pm.get_zone_data.return_value = SimpleNamespace(
        polygon=[(0, 0), (400, 0), (400, 400), (0, 400)],
        roi_polygons=[[(10, 10), (60, 10), (60, 60), (10, 60)]],
        roi_names=["toca"],
        roi_colors=[],
    )
    view_model.analysis_service = AnalysisService(settings_obj=load_settings())

    with (
        patch("zebtrack.analysis.reporters.ReporterContext"),
        patch("zebtrack.analysis.reporters.ExcelReporter"),
        patch("zebtrack.analysis.reporters.ParquetSummaryReporter"),
        patch("zebtrack.analysis.reporters.WordReporter"),
        patch("zebtrack.core.video.video_metadata_service.VideoMetadataService"),
    ):
        view_model._generate_summaries_impl(["v.mp4"])

    (context,) = seen
    assert context.profile.protocol is ProtocolId.BARNES
    assert dict(context.inputs) == {"trial_type": "probe"}


# ---------------------------------------------------------------------------
# Workflow entry points
# ---------------------------------------------------------------------------


def test_project_processing_workflow_delegates_and_degrades_without_a_coordinator(view_model):
    view_model.start_project_processing_workflow()
    view_model.processing_coordinator.start_project_processing_workflow.assert_called_once_with()

    view_model.processing_coordinator = None
    view_model.start_project_processing_workflow()  # must not raise


def _error_payloads(view_model):
    return [
        e.data
        for e in map(lambda c: c.args[0], view_model.ui_event_bus.publish.call_args_list)
        if e.type == UIEvents.SHOW_ERROR
    ]


def test_invalid_det_config_message_names_the_animal_count(view_model):
    view_model.start_single_video_workflow(
        Path("/v.mp4"), {"animal_method": "det", "animals_per_aquarium": 3}
    )

    (error,) = _error_payloads(view_model)
    assert error.title == "Invalid Configuration"
    assert "Current configuration: 3 animals per aquarium." in error.message
    # The invalid config stops BEFORE any state is touched downstream.
    view_model.ui_event_bus.publish.assert_called_once()


def test_det_with_exactly_one_animal_is_valid(view_model):
    view_model.start_single_video_workflow(
        "/v.mp4", {"animal_method": "det", "animals_per_aquarium": 1}
    )

    event = view_model.ui_event_bus.publish.call_args.args[0]
    assert event.type == UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO


def test_seg_with_many_animals_is_valid(view_model):
    view_model.start_single_video_workflow(
        "/v.mp4", {"animal_method": "seg", "animals_per_aquarium": 5}
    )

    assert _error_payloads(view_model) == []


def test_animal_method_defaults_to_the_settings_value(view_model):
    view_model.settings.model_selection.animal_method = "det"

    view_model.start_single_video_workflow("/v.mp4", {"animals_per_aquarium": 2})

    assert len(_error_payloads(view_model)) == 1


def test_invalid_config_without_a_bus_still_stops_the_workflow(view_model):
    view_model.ui_event_bus = None
    detector_vm = Mock()
    detector_vm.detector = None

    view_model.start_single_video_workflow(
        "/v.mp4", {"animal_method": "det", "animals_per_aquarium": 2}, detector_vm
    )

    detector_vm.setup_detector.assert_not_called()


def test_detector_vm_with_a_ready_detector_is_not_set_up_again(view_model):
    detector_vm = Mock()
    detector_vm.detector = object()
    view_model.settings.model_selection.use_openvino = True

    view_model.start_single_video_workflow("/v.mp4", {"animal_method": "seg"}, detector_vm)

    assert detector_vm.use_openvino is True  # from the settings default
    detector_vm.setup_detector.assert_not_called()
    event = view_model.ui_event_bus.publish.call_args.args[0]
    assert event.type == UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO


def test_detector_setup_receives_the_method_and_perspective_from_config(view_model):
    detector_vm = Mock()
    detector_vm.detector = None
    detector_vm.setup_detector.return_value = True

    view_model.start_single_video_workflow(
        "/v.mp4", {"animal_method": "seg", "perspective": "top"}, detector_vm
    )

    detector_vm.setup_detector.assert_called_once_with("seg", perspective="top")


def test_single_video_processing_normalises_missing_arguments(view_model):
    view_model.start_single_video_processing()
    view_model.start_single_video_processing(video_path="/v.mp4", zone_data=[])

    calls = view_model.processing_coordinator.start_single_video_processing.call_args_list
    assert [c.kwargs for c in calls] == [
        {"video_path": "", "config": {}, "zone_data": None},
        {"video_path": "/v.mp4", "config": {}, "zone_data": None},
    ]


def test_single_video_processing_degrades_without_a_coordinator(view_model):
    view_model.processing_coordinator = None

    view_model.start_single_video_processing(video_path="/v.mp4")  # must not raise


# ---------------------------------------------------------------------------
# Arena / ROI editing
# ---------------------------------------------------------------------------


def test_save_manual_arena_hands_integer_lists_to_the_coordinator(view_model):
    view_model.processing_coordinator.save_manual_arena.return_value = True

    assert view_model.save_manual_arena([(1.9, 2.1), (30, 4)]) is True

    view_model.processing_coordinator.save_manual_arena.assert_called_once_with([[1, 2], [30, 4]])


def test_set_main_arena_polygon_passes_the_points_through(view_model):
    points = [(0, 0), (5, 0), (5, 5)]
    view_model.processing_coordinator.set_main_arena_polygon.return_value = True

    assert view_model.set_main_arena_polygon(points) is True

    view_model.processing_coordinator.set_main_arena_polygon.assert_called_once_with(points)


def test_add_roi_polygon_converts_points_and_keeps_name_and_color(view_model):
    view_model.processing_coordinator.add_roi_polygon.return_value = True

    assert view_model.add_roi_polygon([(1.5, 2.5), (3, 4)], "toca", (255, 0, 10)) is True

    view_model.processing_coordinator.add_roi_polygon.assert_called_once_with(
        [[1, 2], [3, 4]], "toca", (255, 0, 10)
    )


def test_zone_editing_fails_closed_without_a_coordinator(view_model):
    view_model.processing_coordinator = None

    assert view_model.save_manual_arena([(0, 0)]) is False
    assert view_model.set_main_arena_polygon([(0, 0)]) is False
    assert view_model.add_roi_polygon([(0, 0)], "r", (0, 0, 0)) is False


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class _Alive:
    """Thread-like: alive flag and a record of join timeouts."""

    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.joined: list[float | None] = []

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)


class _Worker:
    def __init__(self, running: bool = True) -> None:
        self.is_running = running
        self.cancelled = 0

    def cancel(self) -> None:
        self.cancelled += 1


def _cancel_capturing_shutdown(view_model):
    """Run cancel_current_analysis and return the shutdown closure it started."""
    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.cancel_current_analysis()
    assert tmock.call_args.kwargs["daemon"] is True
    tmock.return_value.start.assert_called_once()
    return tmock.call_args.kwargs["target"]


@pytest.mark.parametrize(
    "arrange",
    [
        lambda vm: setattr(vm.processing_coordinator, "processing_worker", _Worker()),
        lambda vm: setattr(vm.processing_coordinator, "processing_thread", _Alive()),
        lambda vm: setattr(vm, "processing_worker", _Worker()),
        lambda vm: setattr(vm, "processing_thread", _Alive()),
    ],
    ids=["coordinator-worker", "coordinator-thread", "legacy-worker", "legacy-thread"],
)
def test_each_kind_of_running_work_triggers_a_cancel(view_model, arrange):
    arrange(view_model)

    _cancel_capturing_shutdown(view_model)

    assert view_model.cancel_event.is_set() is True
    view_model.processing_coordinator.cancel_processing.assert_called_once_with()
    update = view_model.state_manager.update_processing_state.call_args
    assert update.kwargs == {
        "source": "controller.cancel_current_analysis",
        "cancel_requested": True,
    }


@pytest.mark.parametrize(
    "arrange",
    [
        lambda vm: setattr(vm.processing_coordinator, "processing_worker", _Worker(running=False)),
        lambda vm: setattr(vm.processing_coordinator, "processing_thread", _Alive(alive=False)),
        lambda vm: setattr(vm, "processing_worker", _Worker(running=False)),
        lambda vm: setattr(vm, "processing_thread", _Alive(alive=False)),
    ],
    ids=["coordinator-worker", "coordinator-thread", "legacy-worker", "legacy-thread"],
)
def test_idle_work_is_not_cancelled(view_model, arrange):
    arrange(view_model)

    view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is False
    view_model.processing_coordinator.cancel_processing.assert_not_called()


def test_cancel_without_a_coordinator_and_nothing_running_is_a_noop(view_model):
    view_model.processing_coordinator = None
    view_model.live_camera_session_coordinator = None

    view_model.cancel_current_analysis()

    assert view_model.cancel_event.is_set() is False


def test_cancel_announces_the_status_and_shows_feedback(view_model):
    view_model.processing_thread = _Alive()

    _cancel_capturing_shutdown(view_model)

    view_model.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.SET_STATUS,
            data=payloads.StatusPayload(message="Cancelling the analysis in progress..."),
        )
    )
    view_model.ui_state_controller._show_cancel_feedback.assert_called_once_with()


def test_cancel_without_bus_or_ui_controller_still_cancels(view_model):
    view_model.processing_thread = _Alive()
    view_model.ui_event_bus = None
    view_model.ui_state_controller = None

    _cancel_capturing_shutdown(view_model)

    assert view_model.cancel_event.is_set() is True


def test_a_live_session_that_fails_to_stop_does_not_block_the_cancel(view_model):
    view_model.live_camera_session_coordinator.live_camera_service.camera = object()
    view_model.live_camera_session_coordinator.stop_live_session.side_effect = RuntimeError("hw")

    _cancel_capturing_shutdown(view_model)

    assert view_model.cancel_event.is_set() is True
    view_model.processing_coordinator.cancel_processing.assert_called_once_with()


def test_live_session_without_a_camera_is_not_treated_as_active(view_model):
    view_model.live_camera_session_coordinator.live_camera_service = None

    view_model.cancel_current_analysis()

    view_model.live_camera_session_coordinator.stop_live_session.assert_not_called()
    assert view_model.cancel_event.is_set() is False


def test_shutdown_cancels_a_running_legacy_worker_instead_of_joining(view_model):
    worker = _Worker()
    thread = _Alive()
    view_model.processing_worker = worker
    view_model.processing_thread = thread

    shutdown = _cancel_capturing_shutdown(view_model)
    shutdown()

    assert worker.cancelled == 1
    assert thread.joined == []  # elif: a running worker is cancelled, not joined


def test_shutdown_joins_a_legacy_thread_and_the_coordinator_thread_for_five_seconds(view_model):
    legacy = _Alive()
    coordinator_thread = _Alive()
    view_model.processing_thread = legacy
    view_model.processing_coordinator.processing_thread = coordinator_thread

    shutdown = _cancel_capturing_shutdown(view_model)
    shutdown()

    assert legacy.joined == [5.0]
    assert coordinator_thread.joined == [5.0]


def test_shutdown_skips_dead_threads(view_model):
    live = _Alive()
    dead = _Alive(alive=False)
    view_model.processing_thread = live
    view_model.processing_coordinator.processing_thread = dead

    shutdown = _cancel_capturing_shutdown(view_model)
    shutdown()

    assert live.joined == [5.0]
    assert dead.joined == []


def test_shutdown_without_a_coordinator_only_handles_the_legacy_side(view_model):
    legacy = _Alive()
    view_model.processing_thread = legacy
    shutdown = _cancel_capturing_shutdown(view_model)
    view_model.processing_coordinator = None

    shutdown()

    assert legacy.joined == [5.0]


# ---------------------------------------------------------------------------
# _process_single_video
# ---------------------------------------------------------------------------


def test_process_single_video_forwards_detector_and_kwargs(view_model):
    view_model.video_processing_service.process_single_video.return_value = "done"
    detector = object()

    result = view_model._process_single_video(detector, video_path="/v.mp4", config={"a": 1})

    assert result == "done"
    call = view_model.video_processing_service.process_single_video.call_args
    assert call.kwargs["detector"] is detector
    # The worker records with its own recorder: none is handed over (#726).
    assert "recorder" not in call.kwargs
    assert call.kwargs["video_path"] == "/v.mp4"
    assert call.kwargs["config"] == {"a": 1}


def test_process_single_video_progress_callback_republishes_the_processing_mode(view_model):
    view_model.processing_coordinator._publish_processing_mode.return_value = "published"

    view_model._process_single_video(object())
    callback = view_model.video_processing_service.process_single_video.call_args.kwargs[
        "processing_report_callback"
    ]

    assert callback() == "published"
    view_model.processing_coordinator._publish_processing_mode.assert_called_once_with(
        source="analysis_progress", force=False
    )


def test_process_single_video_callback_goes_quiet_if_the_coordinator_disappears(view_model):
    view_model._process_single_video(object())
    callback = view_model.video_processing_service.process_single_video.call_args.kwargs[
        "processing_report_callback"
    ]

    view_model.processing_coordinator = None

    assert callback() is None


def test_process_single_video_has_no_callback_without_a_coordinator(view_model):
    view_model.processing_coordinator = None

    view_model._process_single_video(object())

    call = view_model.video_processing_service.process_single_video.call_args
    assert call.kwargs["processing_report_callback"] is None


# ---------------------------------------------------------------------------
# Summary generation pipeline
# ---------------------------------------------------------------------------

_PARAMS = {
    "freezing_vel_threshold": 2.5,
    "freezing_min_duration": 0.75,
    "smoothing_window_length": 7,
    "smoothing_polyorder": 3,
}
_ARENA = [(10, 10), (110, 10), (110, 60), (10, 60)]  # 100 x 50 px


class _FakeProjectManager:
    def __init__(self, tmp_path, entries, zone_data, project_data=None):
        self.entries = entries
        self.zone_data = zone_data
        self.project_data = project_data if project_data is not None else {}
        self.results_dir = tmp_path
        self.registered: list[dict] = []
        self.resolve_calls: list[dict] = []

    def find_video_entry(self, path):
        return self.entries.get(path)

    def resolve_results_directory(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return str(self.results_dir)

    def get_zone_data(self, video_path=None):
        return self.zone_data

    def register_processing_outputs(self, **kwargs):
        self.registered.append(kwargs)


def _time_base(source: str, fps_video: float) -> TimeBase:
    return TimeBase(
        fps_sampling=fps_video,
        fps_video=fps_video,
        duration_s=10.0,
        t_first=0.0,
        t_last=10.0 - 1.0 / fps_video,
        median_dt=1.0 / fps_video,
        source=source,
    )


class _TimeBaseStub:
    """Stands in for ``resolve_recording_time_base``: the fakes' trajectory is a string."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, float | None]] = []
        self.result = _time_base(SOURCE_TRAJECTORY, 29.97)

    def __call__(self, df, trajectory_path, *, ledger=None, fallback_fps=None):
        self.calls.append((df, trajectory_path, fallback_fps))
        return self.result


class _FakeAnalysisService:
    def __init__(self, fail_for=None):
        self.analysis_calls: list[dict] = []
        self.fail_for = fail_for

    def collect_analysis_parameters(self, project_data):
        self.project_data_seen = project_data
        return dict(_PARAMS)

    def load_trajectory_dataframe(self, path):
        return f"df:{path}"

    def resolve_roi_rule(self):
        return "centroid_in"

    def run_full_analysis_as_dto(self, **kwargs):
        if self.fail_for and kwargs["video_path"] == self.fail_for:
            raise ValueError("analysis blew up")
        self.analysis_calls.append(kwargs)
        return SimpleNamespace(video=kwargs["video_path"])


@pytest.fixture
def summaries(view_model, tmp_path):
    """Wire the view model to fakes and patch the heavy reporters; yields a harness."""
    zone = SimpleNamespace(
        polygon=list(_ARENA),
        roi_polygons=[[(10, 10), (60, 10), (60, 60), (10, 60)], [(0, 0), (1, 0)]],
        roi_names=["toca"],
        roi_colors=[(1, 2, 3)],
    )
    entry = {
        "experiment_id": "exp1",
        "group": "Grupo_A",
        "subject": "S 1",
        "fps": 25.0,
        "metadata": {"day": "Dia_1"},
    }
    pm = _FakeProjectManager(
        tmp_path,
        {"v.mp4": entry},
        zone,
        {"calibration": {"aquarium_width_cm": 20, "aquarium_height_cm": 10}},
    )
    service = _FakeAnalysisService()
    view_model.project_manager = pm
    view_model.analysis_service = service
    view_model.settings = SimpleNamespace(model_selection=SimpleNamespace(animal_method="seg"))
    (tmp_path / "3_CoordMovimento_exp1.parquet").write_text("x")

    exported: list[tuple[str, str]] = []

    def reporter(kind):
        def factory(ctx):
            def export(path):
                exported.append((kind, path))

            return SimpleNamespace(export_summary=export, export_individual_report=export, ctx=ctx)

        return factory

    window = object()
    time_base = _TimeBaseStub()
    patches = [
        patch("zebtrack.analysis.reporters.ExcelReporter", side_effect=reporter("excel")),
        patch(
            "zebtrack.analysis.reporters.ParquetSummaryReporter", side_effect=reporter("parquet")
        ),
        patch("zebtrack.analysis.reporters.WordReporter", side_effect=reporter("word")),
        patch(
            "zebtrack.analysis.reporters.ReporterContext.from_analysis",
            side_effect=lambda result: SimpleNamespace(result=result),
        ),
        patch(
            "zebtrack.core.video.video_metadata_service.VideoMetadataService.get_video_dimensions",
            return_value=(1280, 960),
        ),
        patch(
            "zebtrack.core.viewmodels.analysis_control_view_model.resolve_analysis_window",
            return_value=window,
        ),
        patch(
            "zebtrack.core.viewmodels.analysis_control_view_model.resolve_recording_time_base",
            side_effect=time_base,
        ),
    ]
    for p in patches:
        p.start()
    yield SimpleNamespace(
        vm=view_model,
        pm=pm,
        service=service,
        exported=exported,
        zone=zone,
        entry=entry,
        tmp_path=tmp_path,
        window=window,
        time_base=time_base,
    )
    for p in patches:
        p.stop()


def _statuses(vm):
    return [
        e.data.message
        for e in (c.args[0] for c in vm.ui_event_bus.publish.call_args_list)
        if e.type == UIEvents.SET_STATUS
    ]


def test_summaries_without_a_bus_do_nothing(summaries):
    summaries.vm.ui_event_bus = None

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.analysis_calls == []


def test_summaries_pass_calibration_geometry_and_parameters_to_the_analysis(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert call["pixelcm_x"] == 5.0  # 100 px / 20 cm
    assert call["pixelcm_y"] == 5.0  # 50 px / 10 cm
    assert call["video_height_px"] == 960
    assert call["fps"] == 25.0
    assert call["arena_polygon_px"] == [(10.0, 10.0), (110.0, 10.0), (110.0, 60.0), (10.0, 60.0)]
    assert call["freezing_vel_threshold"] == 2.5
    assert call["freezing_min_duration"] == 0.75
    assert call["smoothing_window_length"] == 7
    assert call["smoothing_polyorder"] == 3
    assert call["trajectory_df"] == f"df:{summaries.tmp_path / '3_CoordMovimento_exp1.parquet'}"
    assert call["window"] is summaries.window
    assert call["video_path"] == "v.mp4"


def test_summaries_feed_the_project_data_to_the_parameter_collector(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.project_data_seen is summaries.pm.project_data


def test_summaries_convert_roi_colors_from_bgr_to_rgb_and_name_by_index(summaries):
    summaries.zone.roi_polygons = [
        [(10, 10), (60, 10), (60, 60), (10, 60)],
        [(0, 0), (9, 0), (9, 9), (0, 9)],
    ]
    summaries.zone.roi_colors = [(1, 2, 3)]  # second ROI has no colour

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert [r.name for r in call["rois"]] == ["toca", "ROI_1"]
    assert call["roi_colors"] == {"toca": (3, 2, 1), "ROI_1": (0, 0, 255)}


def test_summaries_skip_a_degenerate_roi_and_keep_the_rest(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    # The fixture's second ROI has 2 points: not a valid ring, so it is dropped.
    assert [r.name for r in call["rois"]] == ["toca"]
    assert list(call["roi_colors"]) == ["toca"]


def test_summaries_name_the_outputs_from_group_day_subject_and_experiment(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    tmp = summaries.tmp_path
    assert summaries.exported == [
        ("excel", str(tmp / "Sumario_Grupo_A_Dia_1_S1_exp1.xlsx")),
        ("parquet", str(tmp / "exp1_summary.parquet")),
        ("word", str(tmp / "Relatorio_Grupo_A_Dia_1_S1_exp1.docx")),
    ]


def test_summaries_register_every_output_with_the_project(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    tmp = summaries.tmp_path
    assert summaries.pm.registered == [
        {
            "video_path": "v.mp4",
            "results_dir": str(tmp),
            "trajectory_path": str(tmp / "3_CoordMovimento_exp1.parquet"),
            "summary_parquet": str(tmp / "exp1_summary.parquet"),
            "summary_excel": str(tmp / "Sumario_Grupo_A_Dia_1_S1_exp1.xlsx"),
            "report_path": str(tmp / "Relatorio_Grupo_A_Dia_1_S1_exp1.docx"),
        }
    ]


def test_summaries_resolve_the_results_directory_by_path_and_metadata(summaries):
    """Never by experiment id alone: two days share ``CECT_4`` (see CLAUDE.md)."""
    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.pm.resolve_calls
    assert call["video_path"] == "v.mp4"
    assert call["experiment_id"] == "exp1"
    assert call["metadata"] == {
        "day": "Dia_1",
        "experiment_id": "exp1",
        "subject": "S 1",
        "group": "Grupo_A",
    }


def _shown_errors(vm):
    """(video, reason) pairs listed in the SHOW_ERROR messages, in order."""
    pairs = []
    for event in (c.args[0] for c in vm.ui_event_bus.publish.call_args_list):
        if event.type != UIEvents.SHOW_ERROR:
            continue
        for line in event.data.message.splitlines():
            if line.startswith("- "):
                name, _sep, reason = line[2:].partition(": ")
                pairs.append((name, reason))
    return pairs


def test_summaries_publish_progress_then_finish_and_refresh_the_tree(summaries):
    summaries.pm.entries["w.mp4"] = summaries.entry  # second video, same entry
    summaries.vm._generate_summaries_impl(["v.mp4", "w.mp4"])

    assert _statuses(summaries.vm) == [
        "Generating report 1/2...",
        "Generating report 2/2...",
        "Report generation finished.",
    ]
    last = summaries.vm.ui_event_bus.publish.call_args.args[0]
    assert last.type == UIEvents.UI_REFRESH_PROJECT_VIEWS
    assert last.data == payloads.ProjectViewsRefreshRequestedPayload(
        reason="reports_generated", append_summary=True, immediate=False
    )


def test_summaries_skip_a_video_the_project_does_not_know(summaries):
    summaries.vm._generate_summaries_impl(["ghost.mp4"])

    assert summaries.service.analysis_calls == []
    assert summaries.pm.registered == []
    assert _statuses(summaries.vm)[-1] == (
        "Report generation finished: 1 of 1 video(s) without a report."
    )
    assert _shown_errors(summaries.vm) == [("ghost.mp4", "not registered in the project")]


def test_summaries_skip_a_video_without_a_trajectory(summaries):
    (summaries.tmp_path / "3_CoordMovimento_exp1.parquet").unlink()

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.analysis_calls == []


def test_summaries_date_the_recording_by_its_own_3c_sidecar(summaries):
    """The summary path resolves the time base from the trajectory's own files.

    Until it did, this path analysed every video at the project entry's fps (30
    when unknown) and never read the ``3c`` heartbeat.
    """
    summaries.time_base.result = _time_base(SOURCE_HEARTBEAT, 9.9)

    summaries.vm._generate_summaries_impl(["v.mp4"])

    trajectory = summaries.tmp_path / "3_CoordMovimento_exp1.parquet"
    ((df, path, fallback),) = summaries.time_base.calls
    assert df == f"df:{trajectory}"
    assert path == str(trajectory)
    # The entry's fps is only the fallback of the resolution.
    assert fallback == 25.0
    (call,) = summaries.service.analysis_calls
    assert call["time_base"] is summaries.time_base.result
    assert call["fps"] == 9.9


def test_summaries_take_the_rate_of_a_ledger_clock_too(summaries):
    summaries.time_base.result = _time_base(SOURCE_LEDGER, 14.5)

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert call["fps"] == 14.5


def test_summaries_keep_the_entry_fps_when_only_the_trajectory_dates_it(summaries):
    """Without a 3c/ledger the analysis is unchanged: entry fps, PTS re-measured inside."""
    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert call["fps"] == 25.0
    assert call["time_base"] is summaries.time_base.result


def test_summaries_fall_back_to_the_generic_detections_file(summaries):
    (summaries.tmp_path / "3_CoordMovimento_exp1.parquet").unlink()
    fallback = summaries.tmp_path / "detections.parquet"
    fallback.write_text("x")

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.pm.registered[0]["trajectory_path"] == str(fallback)


def test_summaries_default_experiment_id_subject_group_and_fps(summaries):
    summaries.pm.entries["v.mp4"] = {"metadata": {}}
    (summaries.tmp_path / "3_CoordMovimento_v.parquet").write_text("x")

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert call["fps"] == 30.0
    assert call["metadata"] == {"experiment_id": "v", "subject": "Unknown", "group": "Unknown"}
    assert summaries.exported[0][1].endswith("Sumario_Unknown_D_Unknown_v.xlsx")


def test_summaries_sanitise_tags_and_fall_back_when_they_empty_out(summaries):
    summaries.pm.entries["v.mp4"] = {
        "experiment_id": "exp1",
        "group": "!!!",
        "subject": "a/b c",
        "metadata": {"day": "Dia 1"},
    }

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.exported[0][1].endswith("Sumario_Grp_Dia1_abc_exp1.xlsx")


def test_summaries_width_only_calibration_assumes_square_pixels(summaries):
    summaries.pm.project_data = {"calibration": {"aquarium_width_cm": 20}}

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (5.0, 5.0)


def test_summaries_height_only_calibration_leaves_x_at_one(summaries):
    summaries.pm.project_data = {"calibration": {"aquarium_height_cm": 25}}

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (1.0, 2.0)  # 50 px / 25 cm


def test_summaries_without_calibration_use_one_pixel_per_unit(summaries):
    summaries.pm.project_data = {}

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (1.0, 1.0)


def test_summaries_with_a_malformed_calibration_degrade_to_one(summaries):
    summaries.pm.project_data = {"calibration": {"aquarium_width_cm": "twenty"}}

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (1.0, 1.0)


def test_summaries_ignore_calibration_when_the_arena_is_not_a_polygon(summaries):
    summaries.zone.polygon = [(0, 0), (10, 10)]  # two points

    summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (1.0, 1.0)


def test_summaries_with_a_ragged_arena_log_and_keep_the_default_calibration(summaries):
    summaries.zone.polygon = [(0, 0), (10, 10), (5,)]  # a point without y

    summaries.vm._generate_summaries_impl(["v.mp4"])

    # float(x), float(y) of a one-element point raises: the video is reported as failed
    # (logged, not raised) and nothing is registered for it.
    assert summaries.pm.registered == []


def test_summaries_video_height_defaults_to_720_when_dimensions_are_unknown(summaries):
    with patch(
        "zebtrack.core.video.video_metadata_service.VideoMetadataService.get_video_dimensions",
        return_value=None,
    ):
        summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.analysis_calls[0]["video_height_px"] == 720


def test_summaries_estimate_the_height_from_the_arena_when_the_probe_fails(summaries):
    with patch(
        "zebtrack.core.video.video_metadata_service.VideoMetadataService.get_video_dimensions",
        side_effect=OSError("cannot open"),
    ):
        summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.analysis_calls[0]["video_height_px"] == int(60 * 1.1)


def test_summaries_keep_720_when_the_probe_fails_and_there_is_no_arena(summaries):
    summaries.zone.polygon = []
    with patch(
        "zebtrack.core.video.video_metadata_service.VideoMetadataService.get_video_dimensions",
        side_effect=ValueError("bad"),
    ):
        summaries.vm._generate_summaries_impl(["v.mp4"])

    assert summaries.service.analysis_calls[0]["video_height_px"] == 720


def test_one_failing_video_does_not_stop_the_batch(summaries):
    summaries.service.fail_for = "v.mp4"
    summaries.pm.entries["w.mp4"] = {**summaries.entry, "experiment_id": "exp2"}
    (summaries.tmp_path / "3_CoordMovimento_exp2.parquet").write_text("x")

    summaries.vm._generate_summaries_impl(["v.mp4", "w.mp4"])

    assert [c["video_path"] for c in summaries.service.analysis_calls] == ["w.mp4"]
    assert [r["video_path"] for r in summaries.pm.registered] == ["w.mp4"]
    # The batch goes on, but it no longer ends as if nothing had happened (A5-S-003).
    assert _statuses(summaries.vm)[-1] == (
        "Report generation finished: 1 of 2 video(s) without a report."
    )
    assert [name for name, _reason in _shown_errors(summaries.vm)] == ["v.mp4"]


def test_generate_parquet_summaries_hands_the_paths_to_a_daemon_thread(view_model):
    with patch("zebtrack.core.viewmodels.analysis_control_view_model.threading.Thread") as tmock:
        view_model.generate_parquet_summaries(["/a.mp4"])

    assert tmock.call_args.kwargs == {
        "target": view_model._generate_summaries_impl,
        "args": (["/a.mp4"],),
        "daemon": True,
    }


def test_summaries_degrade_when_arena_coordinates_cannot_be_measured(summaries):
    summaries.zone.polygon = [(0, "5"), (10, "60"), (10, "30")]  # numeric strings
    with patch(
        "zebtrack.core.video.video_metadata_service.VideoMetadataService.get_video_dimensions",
        side_effect=OSError("cannot open"),
    ):
        summaries.vm._generate_summaries_impl(["v.mp4"])

    (call,) = summaries.service.analysis_calls
    assert (call["pixelcm_x"], call["pixelcm_y"]) == (
        1.0,
        1.0,
    )  # the y span raises before x is stored
    assert call["video_height_px"] == 720  # the 1.1 estimate fails on strings too


# --- Videos that end without a report are named to the user (audit A5-S-003) ---


def test_summaries_that_all_succeed_show_no_error(summaries):
    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert _shown_errors(summaries.vm) == []
    assert _statuses(summaries.vm)[-1] == "Report generation finished."


def test_a_failing_video_is_named_and_the_others_still_get_their_report(summaries):
    summaries.pm.entries["w.mp4"] = summaries.entry
    calls = {"n": 0}
    real = summaries.service.run_full_analysis_as_dto

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("unreadable trajectory")
        return real(**kwargs)

    summaries.service.run_full_analysis_as_dto = flaky

    summaries.vm._generate_summaries_impl(["v.mp4", "w.mp4"])

    assert _shown_errors(summaries.vm) == [("v.mp4", "unreadable trajectory")]
    assert _statuses(summaries.vm)[-1] == (
        "Report generation finished: 1 of 2 video(s) without a report."
    )
    # The second video was still analysed and registered.
    assert len(summaries.pm.registered) == 1


def test_when_every_video_fails_the_run_does_not_claim_to_have_finished_cleanly(summaries):
    def boom(**kwargs):
        raise RuntimeError("analysis crashed")

    summaries.service.run_full_analysis_as_dto = boom

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert "Report generation finished." not in _statuses(summaries.vm)
    assert _shown_errors(summaries.vm) == [("v.mp4", "analysis crashed")]
    assert summaries.pm.registered == []


def test_a_video_without_a_trajectory_is_reported_with_that_reason(summaries):
    (summaries.tmp_path / "3_CoordMovimento_exp1.parquet").unlink()

    summaries.vm._generate_summaries_impl(["v.mp4"])

    assert _shown_errors(summaries.vm) == [("v.mp4", "no trajectory file found")]


def test_the_tree_is_refreshed_even_when_a_video_failed(summaries):
    summaries.vm._generate_summaries_impl(["ghost.mp4"])

    last = summaries.vm.ui_event_bus.publish.call_args.args[0]
    assert last.type == UIEvents.UI_REFRESH_PROJECT_VIEWS

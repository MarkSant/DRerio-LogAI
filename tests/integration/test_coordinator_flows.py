from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.coordinators.live_camera_session_coordinator import (
    LiveCameraSessionCoordinator,
    LiveCameraSessionCoordinatorError,
)
from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.project_lifecycle_coordinator import ProjectLifecycleCoordinator
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.sequential_processing_coordinator import SequentialProcessingCoordinator
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detection import AquariumData, MultiAquariumZoneData, ZoneData
from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
from zebtrack.core.project.zone_manager import ZoneManager
from zebtrack.core.state_manager import StateManager
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter
from zebtrack.ui.wizard.enums import ProjectType


class DummyProjectManager:
    def __init__(self) -> None:
        self.project_path: str | None = None
        self.project_data: dict = {}
        self._active_zone_video: str | None = None
        self.saved = False

    def create_new_project(self, **kwargs) -> None:
        self.project_path = str(kwargs.get("project_path")) if kwargs.get("project_path") else None
        self.project_data = {
            "project_type": kwargs.get("project_type"),
            "animals_per_aquarium": kwargs.get("animals_per_aquarium"),
        }

    def save_project(self) -> None:
        self.saved = True

    def get_active_zone_video(self) -> str | None:
        return self._active_zone_video

    def import_parquets_from_wizard(self, **_kwargs) -> bool:
        return True


@pytest.mark.integration
def test_project_lifecycle_create_project_happy_path(tmp_path, test_settings) -> None:
    state_manager = StateManager()
    project_manager = DummyProjectManager()
    typed_project_manager = cast(ProjectManager, project_manager)
    model_service = MagicMock()
    model_service.get_default_weight.return_value = ("best_seg.pt", "/fake/path")
    model_service.get_all_weight_names.return_value = ["best_seg.pt"]
    detector_service = MagicMock()
    detector_service.initialize_detector.return_value = (True, None)

    service = ProjectWorkflowService(
        project_manager=typed_project_manager,
        model_service=model_service,
        state_manager=state_manager,
        settings_obj=test_settings,
    )
    event_bus = EventBusV2()
    adapter = ProjectWorkflowAdapter(
        project_workflow_service=service,
        project_manager=typed_project_manager,
        detector_service=detector_service,
        state_manager=state_manager,
        ui_event_bus=event_bus,
    )
    coordinator = ProjectLifecycleCoordinator(
        state_manager=state_manager,
        project_manager=typed_project_manager,
        project_workflow_service=service,
        project_workflow_adapter=adapter,
        settings_obj=test_settings,
        event_bus=event_bus,
        detector_service=detector_service,
    )

    events: list[payloads.EventPayload | dict[str, object]] = []
    event_bus.subscribe(UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW, lambda data: events.append(data))

    project_path = tmp_path / "proj"
    result = coordinator.create_project(
        project_path=str(project_path),
        project_type=ProjectType.EXPERIMENTAL.value,
        animals_per_aquarium=1,
        num_aquariums=1,
        aquarium_width_cm=10.0,
        aquarium_height_cm=10.0,
    )

    assert result is True
    assert project_manager.project_path is not None
    assert state_manager.get_project_state().project_path == Path(project_manager.project_path)
    assert events


@pytest.mark.integration
def test_project_lifecycle_create_project_validation_error(tmp_path, test_settings) -> None:
    state_manager = StateManager()
    project_manager = MagicMock()
    project_manager.project_path = None
    project_manager.project_data = {}
    project_manager.get_active_zone_video.return_value = None
    project_manager.create_new_project.side_effect = ProjectInvalidError("invalid")

    model_service = MagicMock()
    model_service.get_default_weight.return_value = ("best_seg.pt", "/fake/path")
    model_service.get_all_weight_names.return_value = ["best_seg.pt"]
    detector_service = MagicMock()
    detector_service.initialize_detector.return_value = (True, None)

    service = ProjectWorkflowService(
        project_manager=project_manager,
        model_service=model_service,
        state_manager=state_manager,
        settings_obj=test_settings,
    )
    event_bus = EventBusV2()
    adapter = ProjectWorkflowAdapter(
        project_workflow_service=service,
        project_manager=project_manager,
        detector_service=detector_service,
        state_manager=state_manager,
        ui_event_bus=event_bus,
    )
    coordinator = ProjectLifecycleCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        project_workflow_service=service,
        project_workflow_adapter=adapter,
        settings_obj=test_settings,
        event_bus=event_bus,
        detector_service=detector_service,
    )

    errors: list[payloads.EventPayload | dict[str, object]] = []
    event_bus.subscribe(UIEvents.SHOW_ERROR, lambda data: errors.append(data))

    result = coordinator.create_project(
        project_path=str(tmp_path / "proj"),
        project_type=ProjectType.EXPERIMENTAL.value,
        animals_per_aquarium=1,
        num_aquariums=1,
        aquarium_width_cm=10.0,
        aquarium_height_cm=10.0,
    )

    assert result is False
    assert state_manager.get_project_state().project_path is None
    assert errors


@pytest.mark.integration
def test_video_processing_process_pending_videos_happy_path(monkeypatch, tmp_path, test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    video_path = str(tmp_path / "video.mp4")
    video_entry = {
        "path": video_path,
        "has_arena": False,
        "has_rois": False,
        "metadata": {},
    }

    project_manager = MagicMock()
    project_manager.project_path = str(tmp_path / "project")
    project_manager.project_data = {}
    project_manager.get_all_videos.return_value = [video_entry]
    project_manager.get_multi_aquarium_zone_data.return_value = None
    project_manager.resolve_results_directory.return_value = tmp_path / "results"
    project_manager.save_zone_data.return_value = None
    project_manager.save_project.return_value = None

    selection_result = SimpleNamespace(
        selection_mode="targeted",
        candidate_entries=[video_entry],
        candidate_count=1,
        has_missing=False,
        missing_targets=[],
    )
    video_selection_service = MagicMock()
    video_selection_service.select_candidates.return_value = selection_result

    scan_result = SimpleNamespace(
        has_missing=False,
        missing_files=[],
        info_by_norm={},
    )
    video_validation_service = MagicMock()
    video_validation_service.scan_and_validate_paths.return_value = scan_result

    classification_result = SimpleNamespace(
        ready_with_trajectory=[video_entry],
        ready_with_zones=[],
        arena_only=[],
        without_arena=[],
        data_changed=False,
    )
    video_classification_service = MagicMock()
    video_classification_service.classify_videos.return_value = classification_result

    class DummyWorker:
        def __init__(self, context, callbacks) -> None:
            self.context = context
            self.callbacks = callbacks
            self.is_running = False

        def start_in_thread(self):
            thread = MagicMock()
            thread.is_alive.return_value = False
            return thread

    monkeypatch.setattr(
        "zebtrack.coordinators.video_processing_coordinator.ProcessingWorker",
        DummyWorker,
    )

    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=threading.Event(),
        video_selection_service=video_selection_service,
        video_validation_service=video_validation_service,
        video_classification_service=video_classification_service,
        event_bus=event_bus,
    )

    coordinator.process_pending_project_videos(video_paths=[video_path])

    assert state_manager.get_processing_state().is_processing is True
    project_manager.update_video_status.assert_called_with(video_entry["path"], "processing")


@pytest.mark.integration
def test_video_processing_process_pending_videos_validation_error(test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    project_manager = MagicMock()
    project_manager.project_path = None
    project_manager.get_all_videos.return_value = []

    warnings: list[payloads.EventPayload | dict[str, object]] = []
    event_bus.subscribe(UIEvents.UI_SHOW_WARNING, lambda data: warnings.append(data))

    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=threading.Event(),
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        event_bus=event_bus,
    )

    coordinator.process_pending_project_videos()

    assert warnings


@pytest.mark.integration
def test_report_generation_generate_reports_happy_path(monkeypatch, tmp_path, test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    video_path = str(tmp_path / "video.mp4")
    exp_id = "video"

    results_dir = tmp_path / "results"
    results_dir.mkdir()
    trajectory_path = results_dir / f"3_CoordMovimento_{exp_id}.parquet"
    trajectory_path.write_text("stub")

    project_manager = MagicMock()
    project_manager.find_video_entry.return_value = {
        "path": video_path,
        "metadata": {"group": "g1", "day": "1", "subject": "s1"},
    }
    project_manager.resolve_results_directory.return_value = results_dir
    project_manager.get_zone_data.return_value = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
    project_manager.get_multi_aquarium_zone_data.return_value = None
    project_manager.project_data = {}

    analysis_service = MagicMock()
    analysis_service.collect_analysis_parameters.return_value = {}
    analysis_service.run_full_analysis_as_dto.return_value = MagicMock()

    coordinator = ReportGenerationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        settings_obj=test_settings,
        analysis_service=analysis_service,
        event_bus=event_bus,
    )

    monkeypatch.setattr(
        coordinator,
        "_read_trajectory",
        lambda _path: pd.DataFrame(
            {
                "x_center_px": [1.0],
                "y_center_px": [1.0],
                "x1": [0.5],
                "y1": [0.5],
                "x2": [1.5],
                "y2": [1.5],
            }
        ),
    )
    monkeypatch.setattr(coordinator, "_prepare_background_image", lambda *_args: video_path)
    monkeypatch.setattr(coordinator, "_probe_video_dimensions", lambda *_args: (10, 10))
    monkeypatch.setattr(
        coordinator,
        "_export_individual_outputs",
        lambda *_args: {
            "docx": str(results_dir / "report.docx"),
            "xlsx": str(results_dir / "report.xlsx"),
        },
    )

    coordinator.generate_project_reports([video_path])

    assert analysis_service.run_full_analysis_as_dto.called
    project_manager.register_processing_outputs.assert_called_once()


@pytest.mark.integration
def test_report_generation_generate_reports_missing_trajectory(tmp_path, test_settings):
    state_manager = StateManager()

    video_path = str(tmp_path / "video.mp4")
    project_manager = MagicMock()
    project_manager.find_video_entry.return_value = {
        "path": video_path,
        "metadata": {"group": "g1", "day": "1", "subject": "s1"},
    }
    project_manager.resolve_results_directory.return_value = tmp_path / "results"
    project_manager.get_zone_data.return_value = ZoneData(polygon=[(0, 0), (10, 0), (10, 10)])
    project_manager.get_multi_aquarium_zone_data.return_value = None
    project_manager.project_data = {}

    analysis_service = MagicMock()
    analysis_service.collect_analysis_parameters.return_value = {}

    coordinator = ReportGenerationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        settings_obj=test_settings,
        analysis_service=analysis_service,
        event_bus=None,
    )

    coordinator.generate_project_reports([video_path])

    assert analysis_service.run_full_analysis_as_dto.call_count == 0


@pytest.mark.integration
def test_live_camera_session_start_stop_happy_path(test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    live_camera_service = MagicMock()
    live_camera_service.start_session.return_value = True
    live_camera_service.stop_session.return_value = True

    coordinator = LiveCameraSessionCoordinator(
        state_manager=state_manager,
        live_camera_service=live_camera_service,
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=MagicMock(),
        event_bus=event_bus,
    )

    started: list[payloads.EventPayload | dict[str, object]] = []
    stopped: list[payloads.EventPayload | dict[str, object]] = []
    event_bus.subscribe(UIEvents.LIVE_SESSION_STARTED, lambda data: started.append(data))
    event_bus.subscribe(UIEvents.LIVE_SESSION_STOPPED, lambda data: stopped.append(data))

    assert coordinator.start_live_session(camera_index=0, duration_s=1.0) is True
    assert state_manager.get_processing_state().is_live_session_active is True
    assert started

    assert coordinator.stop_live_session() is True
    assert state_manager.get_processing_state().is_live_session_active is False
    assert stopped


@pytest.mark.integration
def test_live_session_publishes_metadata_profile_and_live_task_status(test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    live_camera_service = MagicMock()
    live_camera_service.start_session.return_value = True

    pm = MagicMock()
    pm.get_active_zone_video.return_value = None
    pm.project_data = {"analysis_profile": "project_default"}
    pm.resolve_analysis_profile.return_value = {"name": "live_profile"}

    calibration = MagicMock()

    coordinator = LiveCameraSessionCoordinator(
        state_manager=state_manager,
        live_camera_service=live_camera_service,
        project_manager=pm,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=calibration,
        event_bus=event_bus,
    )

    metadata_events: list[payloads.AnalysisMetadataPayload] = []
    task_events: list[payloads.AnalysisTaskStatusPayload] = []
    event_bus.subscribe(
        UIEvents.UI_UPDATE_ANALYSIS_METADATA,
        lambda data: metadata_events.append(cast(payloads.AnalysisMetadataPayload, data)),
    )
    event_bus.subscribe(
        UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
        lambda data: task_events.append(cast(payloads.AnalysisTaskStatusPayload, data)),
    )

    assert coordinator.start_live_session(
        camera_index=0,
        duration_s=1.0,
        experiment_id="live_exp_01",
        wizard_data={
            "experimental_group": "Controle",
            "experiment_day": "Dia_1",
            "subject_id": "S1",
            "use_countdown": True,
            "countdown_duration_s": 5,
        },
    )

    assert metadata_events
    assert task_events
    assert metadata_events[-1].metadata["group"] == "Controle"
    assert metadata_events[-1].metadata["day"] == "Dia_1"
    assert metadata_events[-1].metadata["subject"] == "S1"
    assert metadata_events[-1].metadata["profile"] == "live_profile"
    assert any(
        event.step == "Contagem regressiva para iniciar a análise ao vivo." for event in task_events
    )
    assert task_events[-1].step == "Análise ao vivo em andamento."


@pytest.mark.integration
def test_live_project_session_resolves_camera_by_friendly_name(monkeypatch, test_settings):
    """When DirectShow ordering shifts, start_live_project_session should silently
    re-resolve the index via the saved friendly_name."""
    state_manager = StateManager()
    event_bus = EventBusV2()

    live_camera_service = MagicMock()
    live_camera_service.start_session.return_value = True

    pm = MagicMock()
    pm.get_project_type.return_value = "live"
    pm.get_project_name.return_value = "test_project"
    pm.project_data = {
        "camera_index": 1,
        "camera_friendly_name": "USB2.0 HD UVC WebCam",
        "recording_duration_s": 60.0,
        "analysis_interval_frames": 1,
        "display_interval_frames": 1,
        "animals_per_aquarium": 1,
    }

    calibration = MagicMock()
    calibration.ensure_zones_before_recording.return_value = True

    coordinator = LiveCameraSessionCoordinator(
        state_manager=state_manager,
        live_camera_service=live_camera_service,
        project_manager=pm,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=calibration,
        event_bus=event_bus,
    )

    # Camera reordered: USB now at index 0 (was 1 when saved).
    from zebtrack.core.services.wizard_service import WizardService

    monkeypatch.setattr(
        WizardService,
        "resolve_camera_index",
        classmethod(lambda cls, idx, name: (0, "SHIFTED")),
    )

    assert coordinator.start_live_project_session(day=1, group="Controle", subject="1")
    live_camera_service.start_session.assert_called_once()
    assert live_camera_service.start_session.call_args.kwargs["camera_index"] == 0


@pytest.mark.integration
def test_live_project_session_aborts_when_camera_missing(monkeypatch, test_settings):
    """Missing camera must surface a UI error and NOT silently fall back."""
    event_bus = EventBusV2()

    live_camera_service = MagicMock()

    pm = MagicMock()
    pm.get_project_type.return_value = "live"
    pm.get_project_name.return_value = "test_project"
    pm.project_data = {
        "camera_index": 1,
        "camera_friendly_name": "Disconnected Cam",
        "recording_duration_s": 60.0,
        "analysis_interval_frames": 1,
        "display_interval_frames": 1,
        "animals_per_aquarium": 1,
    }

    coordinator = LiveCameraSessionCoordinator(
        state_manager=StateManager(),
        live_camera_service=live_camera_service,
        project_manager=pm,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=MagicMock(),
        event_bus=event_bus,
    )

    errors: list = []
    event_bus.subscribe(UIEvents.UI_SHOW_ERROR, lambda data: errors.append(data))

    from zebtrack.core.services.wizard_service import WizardService

    monkeypatch.setattr(
        WizardService,
        "resolve_camera_index",
        classmethod(lambda cls, idx, name: (idx, "MISSING")),
    )

    assert coordinator.start_live_project_session(day=1, group="Controle", subject="1") is False
    live_camera_service.start_session.assert_not_called()
    assert errors, "An UI_SHOW_ERROR event should be published when camera is missing"


@pytest.mark.integration
def test_live_project_session_override_skips_resolver(monkeypatch, test_settings):
    """When the caller passes camera_index_override, the resolver is bypassed."""
    live_camera_service = MagicMock()
    live_camera_service.start_session.return_value = True

    pm = MagicMock()
    pm.get_project_type.return_value = "live"
    pm.get_project_name.return_value = "test_project"
    pm.project_data = {
        "camera_index": 1,
        "camera_friendly_name": "Some Cam",
        "recording_duration_s": 60.0,
        "analysis_interval_frames": 1,
        "display_interval_frames": 1,
        "animals_per_aquarium": 1,
    }

    calibration = MagicMock()
    calibration.ensure_zones_before_recording.return_value = True

    coordinator = LiveCameraSessionCoordinator(
        state_manager=StateManager(),
        live_camera_service=live_camera_service,
        project_manager=pm,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=calibration,
        event_bus=EventBusV2(),
    )

    from zebtrack.core.services.wizard_service import WizardService

    called = {"n": 0}

    def _spy(cls, idx, name):
        called["n"] += 1
        return (idx, "MATCH")

    monkeypatch.setattr(WizardService, "resolve_camera_index", classmethod(_spy))

    assert coordinator.start_live_project_session(
        day=1,
        group="Controle",
        subject="1",
        camera_index_override=3,
        camera_friendly_name_override="Override Cam",
    )
    assert called["n"] == 0, "Resolver must be bypassed when override is provided"
    assert live_camera_service.start_session.call_args.kwargs["camera_index"] == 3


@pytest.mark.integration
def test_live_camera_session_invalid_camera_index_raises(test_settings):
    coordinator = LiveCameraSessionCoordinator(
        state_manager=StateManager(),
        live_camera_service=MagicMock(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        settings_obj=test_settings,
        live_calibration_coordinator=MagicMock(),
        event_bus=None,
    )

    with pytest.raises(LiveCameraSessionCoordinatorError):
        coordinator.start_live_session(camera_index=-1, duration_s=1.0)


@pytest.mark.integration
def test_multi_aquarium_sequential_flow_happy_path(monkeypatch, tmp_path, test_settings):
    state_manager = StateManager()

    aquariums = [
        AquariumData(id=0, polygon=[(0, 0), (10, 0), (10, 10)], subject_id="1"),
        AquariumData(id=1, polygon=[(20, 0), (30, 0), (30, 10)], subject_id="2"),
    ]
    multi_data = MultiAquariumZoneData(aquariums=aquariums, sequential_processing=False)

    entry: dict[str, object] = {"path": str(tmp_path / "video.mp4")}

    project_manager = MagicMock()
    project_manager.project_path = str(tmp_path / "project")
    project_manager.get_multi_aquarium_zone_data.return_value = multi_data
    project_manager.find_video_entry.return_value = entry

    multi_coord = MultiAquariumCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=threading.Event(),
        video_classification_service=MagicMock(),
        weight_manager=MagicMock(),
        event_bus=None,
    )

    multi_coord._on_processing_mode_changed({"sequential": True, "video_path": entry["path"]})

    zone_data_dict = cast(dict, entry["multi_aquarium_zone_data"])
    assert zone_data_dict["sequential_processing"] is True

    seq_coord = SequentialProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        cancel_event=threading.Event(),
        recorder_factory=None,
        event_bus=None,
    )

    started: dict[str, bool] = {"called": False}

    def _fake_start(*_args, **_kwargs):
        started["called"] = True

    monkeypatch.setattr(seq_coord, "_start_single_aquarium_for_sequential", _fake_start)

    entry_path = cast(str, entry["path"])
    result = seq_coord._handle_sequential_single_video_start(
        entry_path,
        MultiAquariumZoneData(aquariums=aquariums, sequential_processing=True),
        {"analysis_interval_frames": 1},
    )

    assert result is True
    assert started["called"] is True
    assert seq_coord.sequential_context is not None


@pytest.mark.integration
def test_multi_aquarium_sequential_flow_skipped(test_settings):
    seq_coord = SequentialProcessingCoordinator(
        state_manager=StateManager(),
        project_manager=MagicMock(),
        detector_service=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        cancel_event=threading.Event(),
        recorder_factory=None,
        event_bus=None,
    )

    result = seq_coord._handle_sequential_single_video_start(
        "video.mp4",
        MultiAquariumZoneData(aquariums=[], sequential_processing=False),
        None,
    )

    assert result is False


@pytest.mark.integration
def test_sequential_single_aquarium_preserves_source_dimensions(
    monkeypatch, tmp_path, test_settings
):
    state_manager = StateManager()
    video_path = str(tmp_path / "video.mp4")
    aquarium = AquariumData(id=1, polygon=[(100, 50), (300, 50), (300, 250), (100, 250)])
    multi_data = MultiAquariumZoneData(
        aquariums=[aquarium],
        video_width=1920,
        video_height=1080,
        sequential_processing=True,
    )

    project_manager = MagicMock()
    project_manager.resolve_results_directory.return_value = tmp_path / "results"

    detector_service = MagicMock()
    created_contexts: list[object] = []

    class DummyWorker:
        def __init__(self, context, callbacks):
            created_contexts.append(context)

        def start_in_thread(self):
            return MagicMock(name="worker_thread")

    monkeypatch.setattr(
        "zebtrack.core.video.processing_worker.ProcessingWorker",
        DummyWorker,
    )

    seq_coord = SequentialProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        cancel_event=threading.Event(),
        recorder_factory=None,
        event_bus=None,
    )

    seq_coord._start_single_aquarium_for_sequential(
        aquarium,
        {
            "video_path": video_path,
            "multi_zone_data": multi_data,
            "current_index": 0,
            "single_video_config": {"analysis_interval_frames": 2, "display_interval_frames": 3},
        },
    )

    detector_service.configure_zones.assert_called_once()
    configure_kwargs = detector_service.configure_zones.call_args.kwargs
    assert configure_kwargs["video_width"] == 1920
    assert configure_kwargs["video_height"] == 1080

    zone_data = configure_kwargs["zones_data"]
    assert zone_data.metadata == {
        "source_video_width": 1920,
        "source_video_height": 1080,
    }

    assert created_contexts
    context_zone_data = created_contexts[0].zone_data  # type: ignore[attr-defined]
    assert context_zone_data["metadata"] == {
        "source_video_width": 1920,
        "source_video_height": 1080,
    }


@pytest.mark.integration
def test_explode_sequential_tasks_preserves_source_dimensions(tmp_path, test_settings):
    state_manager = StateManager()
    event_bus = EventBusV2()

    project_manager = MagicMock()
    project_manager.project_path = str(tmp_path / "project")
    project_manager.project_data = {}
    project_manager.resolve_multi_aquarium_results_directories.return_value = {
        0: tmp_path / "aq0",
        1: tmp_path / "aq1",
    }

    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=MagicMock(),
        settings_obj=test_settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=threading.Event(),
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        event_bus=event_bus,
    )

    multi_data = MultiAquariumZoneData(
        aquariums=[
            AquariumData(id=0, polygon=[(10, 10), (110, 10), (110, 210), (10, 210)]),
            AquariumData(id=1, polygon=[(120, 10), (220, 10), (220, 210), (120, 210)]),
        ],
        video_width=864,
        video_height=480,
        sequential_processing=True,
    )

    eligible_videos = [
        {
            "path": str(tmp_path / "video.mp4"),
            "results_dir": str(tmp_path / "results"),
            "zone_data": ZoneManager.multi_aquarium_zone_data_to_dict(multi_data),
        }
    ]

    tasks = coordinator._explode_sequential_tasks(eligible_videos)

    assert len(tasks) == 2
    for task in tasks:
        metadata = task["zone_data"].get("metadata", {})
        assert metadata.get("source_video_width") == 864
        assert metadata.get("source_video_height") == 480

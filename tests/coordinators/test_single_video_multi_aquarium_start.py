"""Reproduction + regression for the offline single-video, 2-aquarium TEST flow.

Scenario (no project saved on disk, ``project_path is None``):

1. User picks a single video with ``num_aquariums = 2``.
2. Auto-detect finds 2 aquariums → ``on_multi_auto_detect_success`` persists a
   ``MultiAquariumZoneData`` (2 polygons) into ``multi_aquarium_zones``.
3. The assignment dialog confirms group/subject/day per aquarium →
   ``MultiAquariumCoordinator._on_aquarium_assignment_completed``.
4. User clicks "Iniciar Análise de Vídeo Único" → ``VIDEO_START_SINGLE_PROCESSING``
   → ``VideoProcessingCoordinator.start_single_video_processing``.

Regression target: the flow was dying silently because several ``save_project()``
calls in the multi-aquarium/sequential path raised ``ProjectInvalidError`` when
``project_path is None`` and the EventBus swallowed the exception. These tests
drive the *real* coordinator chain (real ``ProjectManager`` without a project)
and assert the analysis reaches the ``ProcessingWorker`` instead of "nada acontece".
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator
from zebtrack.coordinators.sequential_processing_coordinator import (
    SequentialProcessingCoordinator,
)
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import EventBusV2


@pytest.fixture
def detected_multi_data() -> MultiAquariumZoneData:
    """Mimic what ``on_multi_auto_detect_success`` builds after detection.

    Fresh auto-detect: no metadata yet, ``sequential_processing`` keeps its
    dataclass default (True), source dimensions populated.
    """
    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(id=0, polygon=[(0, 0), (10, 0), (10, 10), (0, 10)]),
            AquariumData(id=1, polygon=[(20, 0), (30, 0), (30, 10), (20, 10)]),
        ],
        video_width=640,
        video_height=480,
    )


def _assignment_configs() -> list[dict]:
    return [
        {"aquarium_id": 0, "group": "Controle", "subject_id": "S01", "day": 1},
        {"aquarium_id": 1, "group": "Tratamento", "subject_id": "S02", "day": 1},
    ]


def _build_chain(project_manager, settings, *, captured_workers, monkeypatch):
    """Wire a real VideoProcessingCoordinator with real sub-coordinators.

    Only ``ProcessingWorker`` and ``detector_service`` are mocked.
    """
    state_manager = StateManager()
    event_bus = EventBusV2()
    cancel_event = threading.Event()

    class DummyWorker:
        def __init__(self, context=None, callbacks=None):
            captured_workers.append(self)
            self.context = context
            self.callbacks = callbacks

        def start_in_thread(self):
            return MagicMock(name="worker_thread")

    monkeypatch.setattr(
        "zebtrack.core.video.processing_worker.ProcessingWorker",
        DummyWorker,
    )

    detector_service = MagicMock()

    multi_coord = MultiAquariumCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=cancel_event,
        video_classification_service=MagicMock(),
        weight_manager=MagicMock(),
        event_bus=event_bus,
    )
    seq_coord = SequentialProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        settings_obj=settings,
        ui_coordinator=MagicMock(),
        cancel_event=cancel_event,
        recorder_factory=None,
        event_bus=event_bus,
    )
    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        weight_manager=MagicMock(),
        settings_obj=settings,
        ui_coordinator=MagicMock(),
        ui_state_controller=MagicMock(),
        cancel_event=cancel_event,
        video_selection_service=MagicMock(),
        video_validation_service=MagicMock(),
        video_classification_service=MagicMock(),
        recorder_factory=None,
        event_bus=event_bus,
        view=None,
        root=None,
        detector=None,
    )
    coordinator._multi_aquarium_coordinator = multi_coord
    coordinator._sequential_coordinator = seq_coord
    seq_coord._video_processing_coordinator = coordinator
    return coordinator, multi_coord, seq_coord


def test_assignment_without_project_persists_subjects(
    tmp_path, test_settings, detected_multi_data, monkeypatch
):
    """Assignment must persist subjects (and not raise) when there is no project."""
    video_path = str(tmp_path / "exp_2aq.mp4")
    Path(video_path).touch()

    pm = ProjectManager()  # no project_path
    pm.save_multi_aquarium_zone_data(video_path, detected_multi_data, persist=False)

    captured: list = []
    _coord, multi_coord, _seq = _build_chain(
        pm, test_settings, captured_workers=captured, monkeypatch=monkeypatch
    )

    # Must not raise ProjectInvalidError (was swallowed by the bus → silent).
    multi_coord._on_aquarium_assignment_completed(
        payloads.ZoneAquariumAssignmentCompletedPayload(
            configs=_assignment_configs(),
            apply_to_all=False,
            video_path=video_path,
        )
    )

    persisted = pm.get_multi_aquarium_zone_data(video_path)
    assert persisted is not None
    subjects = {aq.id: aq.subject_id for aq in persisted.aquariums}
    assert subjects == {0: "S01", 1: "S02"}, "subjects must reach multi_aquarium_zones"


def test_single_video_two_aquariums_starts_without_project(
    tmp_path, test_settings, detected_multi_data, monkeypatch
):
    """Full no-project flow must reach the ProcessingWorker (was 'nada acontece')."""
    video_path = str(tmp_path / "exp_2aq.mp4")
    Path(video_path).touch()

    pm = ProjectManager()  # no project_path
    test_settings.analysis_config.num_aquariums = 2

    captured: list = []
    coordinator, multi_coord, _seq = _build_chain(
        pm, test_settings, captured_workers=captured, monkeypatch=monkeypatch
    )

    # Step 2: detection persists multi-aquarium zones (+ defensive registration).
    pm.save_multi_aquarium_zone_data(video_path, detected_multi_data)
    pm.set_active_zone_video(video_path)

    # Step 3: assignment confirms subjects.
    multi_coord._on_aquarium_assignment_completed(
        payloads.ZoneAquariumAssignmentCompletedPayload(
            configs=_assignment_configs(),
            apply_to_all=False,
            video_path=video_path,
        )
    )

    # Step 4: start. Call directly so any exception surfaces (the bus swallows them).
    zone_data = pm.get_multi_aquarium_zone_data(video_path)
    coordinator.start_single_video_processing(
        video_path=video_path,
        config={
            "num_aquariums": 2,
            "analysis_interval_frames": 10,
            "display_interval_frames": 10,
        },
        zone_data=zone_data,
    )

    assert captured, "processing never reached the ProcessingWorker (silent failure)"


def test_sequential_advances_to_second_aquarium_without_project(
    tmp_path, test_settings, detected_multi_data, monkeypatch
):
    """Both aquariums must process sequentially with distinct output dirs.

    Simulates the worker completing aquarium 0 and asserts the chain advances to
    aquarium 1 (the per-aquarium ``save_project`` no longer raises with no project)
    and that each aquarium gets its own results directory (so reports don't clash).
    """
    video_path = str(tmp_path / "exp_2aq.mp4")
    Path(video_path).touch()

    pm = ProjectManager()  # no project_path
    test_settings.analysis_config.num_aquariums = 2

    captured: list = []
    coordinator, multi_coord, seq = _build_chain(
        pm, test_settings, captured_workers=captured, monkeypatch=monkeypatch
    )

    pm.save_multi_aquarium_zone_data(video_path, detected_multi_data)
    pm.set_active_zone_video(video_path)
    multi_coord._on_aquarium_assignment_completed(
        payloads.ZoneAquariumAssignmentCompletedPayload(
            configs=_assignment_configs(), apply_to_all=False, video_path=video_path
        )
    )

    zone_data = pm.get_multi_aquarium_zone_data(video_path)
    coordinator.start_single_video_processing(
        video_path=video_path,
        config={"num_aquariums": 2, "analysis_interval_frames": 10, "display_interval_frames": 10},
        zone_data=zone_data,
    )

    assert len(captured) == 1, "first aquarium should have started"
    out_dir_0 = captured[0].context.output_base_dir

    # Simulate the worker finishing aquarium 0 → triggers advancement to aquarium 1.
    captured[0].callbacks.on_completed(True, "", {})

    assert len(captured) == 2, "sequential flow must advance to the second aquarium"
    out_dir_1 = captured[1].context.output_base_dir
    assert out_dir_0 != out_dir_1, "each aquarium needs its own results directory"

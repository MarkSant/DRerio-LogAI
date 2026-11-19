"""Shared harness for the end-to-end flow tests (``tests/integration/test_flow_e2e_*``).

The pre-recorded flows (project and single video) both end in the same
production machinery: ``VideoProcessingCoordinator`` builds a
``ProcessingContext``, ``ProcessingWorker`` spawns a ``_WorkerProcess`` and a
monitor thread, and the completion callbacks register outputs and hand the
video to ``ReportGenerationCoordinator``. This module keeps all of that real and
replaces only what a headless test cannot cross:

* the PROCESS boundary: ``_WorkerProcess.start`` runs ``run()`` in the test
  process (``is_alive``/``join`` follow suit). A spawned child re-imports the
  module tree and could not see the deterministic detector;
* the MODEL: the YOLO plugin class the worker imports is replaced by
  ``GoldenDeterministicPlugin`` (no weights, no inference variance). The rest of
  ``_initialize_detector`` stays real: zone scaler, single-subject mode from the
  settings snapshot the coordinator handed over, and the restoration of the
  context's zone data into the worker's default zones (which the single-video
  flow depends on: its task descriptor carries no ``zone_data``);
* the worker's ``configure_logging``, which would reconfigure structlog for the
  whole session and write ``analysis_worker.log`` into the cwd.
"""

from __future__ import annotations

import threading
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from tests.helpers.prerecorded_pipeline import (
    HEIGHT,
    WIDTH,
    GoldenDeterministicPlugin,
    load_pristine_settings,
)
from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.core.video import processing_worker as processing_worker_module
from zebtrack.core.video.video_classification_service import VideoClassificationService
from zebtrack.core.video.video_selection_service import VideoSelectionService
from zebtrack.core.video.video_validation_service import VideoValidationService
from zebtrack.settings import Settings

__all__ = [
    "build_processing_coordinator",
    "flow_settings",
    "make_zone",
    "run_worker_in_process",
    "wait_for_processing",
]


def make_zone(
    arena: list[tuple[int, int]],
    roi: list[tuple[int, int]],
    roi_name: str,
    *,
    source_size: tuple[int, int] | None = None,
) -> ZoneData:
    """Arena + one ROI in RAW VIDEO PIXELS, the shape the Zones tab saves.

    The canvas converts clicks to the video frame's own pixels, so the
    points are in those pixels. For a single aquarium nothing in
    production writes ``source_video_width``/``source_video_height`` into the
    zone metadata (only the multi-aquarium paths do), so the default here is NO
    metadata, exactly what a user's zones look like; the worker then reads the
    points as the video's own pixels (A8-001). ``source_size`` exists for the
    A8-002 test, which checks that a zone that DOES carry it keeps it on the way
    to the project worker.
    """
    metadata: dict[str, Any] = {}
    if source_size is not None:
        metadata = {"source_video_width": source_size[0], "source_video_height": source_size[1]}
    return ZoneData(
        polygon=[list(p) for p in arena],
        roi_polygons=[[list(p) for p in roi]],
        roi_names=[roi_name],
        roi_colors=[(255, 0, 0)],
        metadata=metadata,
    )


def flow_settings(*, camera_matches_video: bool = True) -> Settings:
    """``config.yaml`` settings (no machine-local override) for a flow run.

    ``camera_matches_video=True`` sets ``camera.desired_width/height`` to the
    fixture video's size (640x480). ``False`` keeps the shipped 1280x720, under
    which a pre-recorded run must give the same result: since A8-001 a zone
    without a stated source size is scaled from the VIDEO's size, never from the
    camera reference that ``_initialize_detector`` seeds the ``ZoneScaler`` with.
    """
    settings = load_pristine_settings()
    if camera_matches_video:
        settings.camera.desired_width = WIDTH
        settings.camera.desired_height = HEIGHT
    return settings


def run_worker_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the real ``_WorkerProcess`` loop, minus the process and the model."""
    worker_cls = processing_worker_module._WorkerProcess

    def _start(self: Any) -> None:
        self.run()

    def _plugin_factory(model_path: Any = "", settings_obj: Any = None) -> Any:
        return GoldenDeterministicPlugin(str(model_path or ""))

    monkeypatch.setattr(worker_cls, "start", _start)
    monkeypatch.setattr(worker_cls, "is_alive", lambda self: False)
    monkeypatch.setattr(worker_cls, "join", lambda self, timeout=None: None)
    monkeypatch.setattr(
        "zebtrack.plugins.ultralytics_detector.UltralyticsDetectorPlugin", _plugin_factory
    )
    monkeypatch.setattr("zebtrack.logging_config.configure_logging", lambda *args, **kwargs: None)


def build_processing_coordinator(
    project_manager: ProjectManager, settings: Any
) -> VideoProcessingCoordinator:
    """A ``VideoProcessingCoordinator`` wired like ``di_registrations`` does.

    Real: selection / validation / classification services and the report
    coordinator with a real ``AnalysisService``. Absent (``None``), as in a
    headless app: the view, the event bus, the progress and multi-aquarium
    coordinators. ``weight_manager=None`` resolves the weight from the settings;
    the detector is replaced at the model boundary anyway.
    """
    state_manager = StateManager()
    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=MagicMock(name="detector_service"),
        weight_manager=cast(Any, None),
        settings_obj=settings,
        settings_baseline=settings,
        ui_coordinator=MagicMock(name="ui_coordinator"),
        ui_state_controller=MagicMock(name="ui_state_controller"),
        cancel_event=threading.Event(),
        video_selection_service=VideoSelectionService(),
        video_validation_service=VideoValidationService(),
        video_classification_service=VideoClassificationService(),
        event_bus=None,
        view=None,
        root=None,
    )
    coordinator._report_coordinator = ReportGenerationCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        settings_obj=settings,
        settings_baseline=settings,
        analysis_service=AnalysisService(settings_obj=settings),
    )
    return coordinator


def wait_for_processing(coordinator: VideoProcessingCoordinator, timeout: float = 300) -> None:
    """Join the monitor thread the coordinator started; fail if it never started."""
    thread = coordinator.processing_thread
    assert thread is not None, "the coordinator never started the worker"
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "the processing monitor did not finish"

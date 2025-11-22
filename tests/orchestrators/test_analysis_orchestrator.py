"""Unit tests for :mod:`zebtrack.orchestrators.analysis_orchestrator`."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.orchestrators.analysis_orchestrator import AnalysisOrchestrator
from zebtrack.ui.events import Events


class DummyEventBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, event: str, payload: dict):
        self.events.append((event, payload))


class DummyRoot:
    def __init__(self):
        self.after_calls: list[tuple[int, Callable[[], None]]] = []

    def after(self, delay: int, callback: Callable[[], None]):
        self.after_calls.append((delay, callback))
        callback()


class DummyWeightManager:
    def __init__(self):
        self.weight_path: str | None = None
        self.calls: list[tuple[str, str]] = []

    def get_weight_path_by_method(self, method: str, domain: str):
        self.calls.append((method, domain))
        return self.weight_path


class DummySettings:
    def __init__(self):
        class ModelSelection:
            aquarium_method = "det"

        class VideoProcessing:
            fps = 30
            sharp_turn_threshold_deg_s = 45
            freezing_velocity_threshold = 0.5
            freezing_min_duration_s = 1.0

        class TrajectorySmoothing:
            window_length = 5
            polyorder = 2

        self.model_selection = ModelSelection()
        self.video_processing = VideoProcessing()
        self.trajectory_smoothing = TrajectorySmoothing()


class DummyProjectManager:
    def __init__(self):
        self.next_video: Path | str | None = None
        self.active_zone_calls: list[Path | str | None] = []
        self.saved_projects = 0
        self.project_data = {
            "calibration": {
                "aquarium_width_cm": 30,
                "aquarium_height_cm": 20,
            }
        }
        self.results_dir = "results"
        self.metadata_by_experiment: dict[str, dict] = {}
        self.zone_data = self._build_default_zone()
        self.zone_data_lookup: dict[str | Path, ZoneData] = {}
        self.resolve_calls: list[tuple[str, str | Path | None]] = []

    def get_next_video(self):
        return self.next_video

    def set_active_zone_video(self, video):
        self.active_zone_calls.append(video)

    def save_project(self):
        self.saved_projects += 1

    def resolve_results_directory(self, experiment_id, video_path=None, metadata=None):
        self.resolve_calls.append((experiment_id, video_path))
        return self.results_dir

    def get_zone_data(self, video_path=None):
        if video_path and video_path in self.zone_data_lookup:
            return self.zone_data_lookup[video_path]
        return self.zone_data

    def get_metadata_for_experiment(self, experiment_id):
        return self.metadata_by_experiment.get(experiment_id)

    @staticmethod
    def _build_default_zone() -> ZoneData:
        zone = ZoneData()
        zone.polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
        zone.roi_polygons = []
        zone.roi_names = []
        zone.roi_colors = []
        return zone


class DummyMainViewModel:
    def __init__(self):
        self.view = MagicMock()
        self.state_manager = MagicMock()
        self.project_manager = DummyProjectManager()
        self.ui_event_bus = DummyEventBus()
        self.root = DummyRoot()
        self.settings = DummySettings()
        self.weight_manager = DummyWeightManager()
        self.processing_mode_calls: list[dict] = []
        self.refresh_calls: list[dict] = []
        self.processing_thread = None

        # Mock ui_state_controller and route refresh_project_views to capture calls
        self.ui_state_controller = MagicMock()
        self.ui_state_controller.refresh_project_views = self.refresh_project_views

    def _publish_processing_mode(self, **kwargs):
        self.processing_mode_calls.append(kwargs)

    def refresh_project_views(self, **kwargs):
        self.refresh_calls.append(kwargs)


def _build_orchestrator():
    vm = DummyMainViewModel()
    orchestrator = AnalysisOrchestrator(vm)
    return orchestrator, vm


@pytest.fixture()
def analysis_orchestrator_setup():
    return _build_orchestrator()


def test_run_aquarium_detection_warns_when_no_video(analysis_orchestrator_setup):
    orchestrator, vm = analysis_orchestrator_setup
    vm.project_manager.next_video = None

    orchestrator.run_aquarium_detection()

    warning_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_WARNING]
    assert warning_events, "should warn when there is no video"
    assert "Nenhum vídeo" in warning_events[0][1]["message"]
    assert vm.project_manager.active_zone_calls == []
    assert len(vm.processing_mode_calls) == 2
    assert vm.processing_mode_calls[0]["source"] == "calibration.aquarium.start"
    assert vm.processing_mode_calls[1]["source"] == "calibration.aquarium.complete"


def test_run_aquarium_detection_emits_polygon_on_success(monkeypatch):
    orchestrator, vm = _build_orchestrator()
    vm.project_manager.next_video = Path("/tmp/video.mp4")
    vm.weight_manager.weight_path = "weights/best.pt"
    captured = {}

    class FakeDetector:
        def __init__(self, model_path, mode):
            captured["init"] = {"model_path": model_path, "mode": mode}

        def detect_aquariums(self, video_path, stabilization_frames):
            captured["detect"] = {
                "video_path": video_path,
                "stabilization_frames": stabilization_frames,
            }
            return [[[0, 0], [1, 0], [1, 1]]]

    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.AquariumDetector",
        FakeDetector,
    )

    orchestrator.run_aquarium_detection()

    polygon_events = [
        evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SETUP_INTERACTIVE_POLYGON
    ]
    assert polygon_events, "expected polygon event on success"
    assert captured["init"]["model_path"] == "weights/best.pt"
    assert captured["detect"]["video_path"] == Path("/tmp/video.mp4")
    status_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SET_STATUS]
    assert status_events[-1][1]["message"] == "Pronto."


def test_run_aquarium_detection_errors_when_weight_missing(monkeypatch):
    orchestrator, vm = _build_orchestrator()
    vm.project_manager.next_video = Path("/tmp/video.mp4")
    vm.weight_manager.weight_path = None

    class ShouldNotInstantiate:
        def __init__(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("Detector should not be created when there is no weight")

    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.AquariumDetector",
        ShouldNotInstantiate,
    )

    orchestrator.run_aquarium_detection()

    error_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_ERROR]
    assert error_events, "should show error when weight path is missing"
    assert "Não foi possível encontrar" in error_events[0][1]["message"]


def test_generate_parquet_summaries_worker_reports_results(monkeypatch):
    orchestrator, vm = _build_orchestrator()
    vm.processing_thread = object()
    vm.project_manager.next_video = None

    outcomes = iter(
        [
            ("completed", "VideoA", "summary_a.parquet", True),
            ("skipped", "VideoB: trajectory missing.", None, False),
        ]
    )

    def fake_process(self, video, settings_obj):
        return next(outcomes)

    monkeypatch.setattr(
        AnalysisOrchestrator,
        "_process_summary_video",
        fake_process,
    )

    orchestrator._generate_parquet_summaries_worker([{"path": "a"}, {"path": "b"}], object())

    assert vm.project_manager.saved_projects == 1
    info_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_INFO]
    assert info_events, "should show summary info"
    warning_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SHOW_WARNING]
    assert warning_events, "should warn about skipped videos"
    status_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_SET_STATUS]
    assert "Σ Sumários atualizados" in status_events[-1][1]["message"]
    assert vm.refresh_calls[-1]["append_summary"] is True
    assert vm.processing_thread is None


def test_process_summary_video_returns_skipped_without_path():
    orchestrator, vm = _build_orchestrator()

    state, message, path, changed = orchestrator._process_summary_video({}, vm.settings)

    assert state == "skipped"
    assert "Caminho do vídeo" in message
    assert path is None
    assert changed is False


def test_process_summary_video_generates_summary_when_data_available(monkeypatch, tmp_path):
    orchestrator, vm = _build_orchestrator()
    video_path = tmp_path / "foo.mp4"
    vm.project_manager.results_dir = str(tmp_path / "results")
    vm.project_manager.metadata_by_experiment["foo"] = {"experiment_id": "foo"}
    vm.project_manager.zone_data_lookup[str(video_path)] = vm.project_manager._build_default_zone()

    candidate = Path(vm.project_manager.results_dir) / "3_CoordMovimento_foo.parquet"

    def fake_exists(path):
        return str(path) == str(candidate)

    class DummyFrame:
        empty = False

    reporter_calls: dict[str, object] = {}

    class FakeReporter:
        def __init__(self, **kwargs):
            reporter_calls["kwargs"] = kwargs

        def export_summary_data(self, path, format):
            reporter_calls["export"] = (path, format)

    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.os.path.exists",
        fake_exists,
    )
    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.pd.read_parquet",
        lambda path: DummyFrame(),
    )
    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.Reporter",
        FakeReporter,
    )
    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.os.makedirs",
        lambda *args, **kwargs: None,
    )

    video = {"path": str(video_path), "parquet_files": {}, "metadata": {}}

    state, info, parquet_path, changed = orchestrator._process_summary_video(video, vm.settings)

    assert state == "completed"
    assert info == "foo"
    assert parquet_path.endswith("foo_summary.parquet")
    assert changed is True
    assert video["parquet_files"]["summary"] == parquet_path
    assert reporter_calls["export"][0] == parquet_path


def test_process_summary_video_skips_when_calibration_missing(monkeypatch):
    orchestrator, vm = _build_orchestrator()
    vm.project_manager.project_data["calibration"] = {}

    class DummyFrame:
        empty = False

    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.os.path.exists",
        lambda path: True,
    )
    monkeypatch.setattr(
        "zebtrack.orchestrators.analysis_orchestrator.pd.read_parquet",
        lambda path: DummyFrame(),
    )

    video = {"path": "foo.mp4", "parquet_files": {"trajectory": "existing.parquet"}}
    state, message, _, changed = orchestrator._process_summary_video(video, vm.settings)

    assert state == "skipped"
    assert "calibração" in message
    assert changed is False

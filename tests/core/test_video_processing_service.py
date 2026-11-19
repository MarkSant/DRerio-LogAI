"""
Test VideoProcessingService - FASE 3 Validation.

This module validates:
- Service instantiation with mocked dependencies
- Error handling and state management
- Processing workflow coordination

Note: VideoProcessingService has many UI dependencies (root, view, ui_coordinator).
These tests focus on validating the service layer logic with mocked components.
"""

import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.paths = Mock()
    settings.paths.output_dir = "/fake/output"
    settings.yolo_model = Mock()
    settings.yolo_model.confidence_threshold = 0.25
    return settings


@pytest.fixture
def mock_detector():
    """Create mock detector."""
    detector = Mock()
    detector.detect = Mock(
        return_value=[{"bbox": [100, 100, 200, 200], "confidence": 0.95, "track_id": 1}]
    )
    return detector


@pytest.fixture
def mock_recorder():
    """Create mock recorder."""
    recorder = Mock()
    recorder.write_detection = Mock()
    recorder.finalize = Mock()
    return recorder


@pytest.fixture
def mock_project_manager():
    """Create mock project manager."""
    pm = Mock()
    pm.get_project_data = Mock(return_value={"videos": []})
    return pm


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    sm = Mock()
    sm.update_state = Mock()
    sm.get_project_state = Mock(return_value={})
    return sm


@pytest.fixture
def mock_ui_coordinator():
    """Create mock UI coordinator."""
    return Mock()


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    eb = Mock()
    eb.emit = Mock()
    return eb


@pytest.fixture
def mock_root():
    """Create mock Tkinter root."""
    root = Mock()
    root.after = Mock()
    return root


@pytest.fixture
def mock_view():
    """Create mock ApplicationGUI."""
    return Mock()


@pytest.fixture
def cancel_event():
    """Create threading cancel event."""
    return threading.Event()


@pytest.fixture
def video_processing_service(
    mock_settings,
    mock_detector,
    mock_recorder,
    mock_project_manager,
    mock_state_manager,
    mock_ui_coordinator,
    mock_event_bus,
    cancel_event,
):
    """Create VideoProcessingService with mocked dependencies."""
    from zebtrack.core.video.video_processing_service import VideoProcessingService

    service = VideoProcessingService(
        detector=mock_detector,
        recorder=mock_recorder,
        project_manager=mock_project_manager,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        ui_event_bus=mock_event_bus,
        cancel_event=cancel_event,
        settings_obj=mock_settings,
    )
    return service


@pytest.mark.unit
def test_service_instantiation_with_all_dependencies(video_processing_service):
    """Test that VideoProcessingService can be instantiated with all dependencies."""
    assert video_processing_service is not None
    assert video_processing_service.detector is not None
    assert video_processing_service.recorder is not None
    assert video_processing_service.settings is not None


@pytest.mark.unit
def test_service_has_required_dependencies(video_processing_service):
    """Test that service has all required dependency attributes."""
    assert hasattr(video_processing_service, "detector")
    assert hasattr(video_processing_service, "recorder")
    assert hasattr(video_processing_service, "project_manager")
    assert hasattr(video_processing_service, "state_manager")
    assert hasattr(video_processing_service, "settings")


def test_service_with_null_detector_allowed(
    mock_settings,
    mock_recorder,
    mock_project_manager,
    mock_state_manager,
    mock_ui_coordinator,
    mock_event_bus,
    cancel_event,
):
    """Test that service can be instantiated with None detector (lazy initialization)."""
    from zebtrack.core.video.video_processing_service import VideoProcessingService

    service = VideoProcessingService(
        detector=None,  # Lazy initialization pattern
        recorder=mock_recorder,
        project_manager=mock_project_manager,
        state_manager=mock_state_manager,
        ui_coordinator=mock_ui_coordinator,
        ui_event_bus=mock_event_bus,
        cancel_event=cancel_event,
        settings_obj=mock_settings,
    )

    assert service is not None
    assert service.detector is None  # Allowed for lazy initialization


def test_service_state_manager_integration(video_processing_service, mock_state_manager):
    """Test that service can update state via StateManager."""
    # Act: Simulate state update
    video_processing_service.state_manager.update_state(
        processing_status="running", current_video="test.mp4"
    )

    # Assert
    mock_state_manager.update_state.assert_called_with(
        processing_status="running", current_video="test.mp4"
    )


def test_service_event_bus_integration(video_processing_service, mock_event_bus):
    """Test that service can emit events via EventBus."""
    # Act: Simulate event emission
    video_processing_service.ui_event_bus.emit("processing.started", data={"video": "test.mp4"})

    # Assert
    mock_event_bus.emit.assert_called_with("processing.started", data={"video": "test.mp4"})


def test_service_cancel_event_integration(video_processing_service, cancel_event):
    """Test that service respects cancel_event."""
    # Arrange
    assert not cancel_event.is_set()

    # Act: Set cancel event
    cancel_event.set()

    # Assert: Service should detect cancellation
    assert video_processing_service.cancel_event.is_set()


def test_service_settings_injection(video_processing_service, mock_settings):
    """Test that settings are properly injected."""
    assert video_processing_service.settings is mock_settings
    assert video_processing_service.settings.paths.output_dir == "/fake/output"


@pytest.mark.parametrize(
    "attribute",
    [
        "detector",
        "recorder",
        "project_manager",
        "state_manager",
        "ui_coordinator",
        "ui_event_bus",
        "settings",
    ],
)
def test_service_has_injected_dependency(video_processing_service, attribute):
    """Parameterized test: Verify all dependencies are injected."""
    assert hasattr(video_processing_service, attribute)
    assert getattr(video_processing_service, attribute) is not None or attribute == "detector"


def test_service_detector_detection_call(video_processing_service, mock_detector):
    """Test that service can call detector.detect()."""
    # Arrange
    fake_frame = Mock()

    # Act
    detections = video_processing_service.detector.detect(fake_frame)

    # Assert
    mock_detector.detect.assert_called_once_with(fake_frame)
    assert len(detections) == 1
    assert detections[0]["confidence"] == 0.95


def test_service_recorder_write_call(video_processing_service, mock_recorder):
    """Test that service can call recorder.write_detection()."""
    # Arrange
    detection = {"bbox": [100, 100, 200, 200], "confidence": 0.95, "track_id": 1}

    # Act
    video_processing_service.recorder.write_detection(
        frame_number=1, timestamp=0.033, detection=detection
    )

    # Assert
    mock_recorder.write_detection.assert_called_once()


def test_service_ui_coordinator_integration(video_processing_service, mock_ui_coordinator):
    """Test that service can schedule UI updates via UIScheduler."""
    # Act: Simulate UI update
    video_processing_service.ui_coordinator.schedule_update(lambda: None)

    # Assert
    mock_ui_coordinator.schedule_update.assert_called_once()


def test_service_project_manager_integration(video_processing_service, mock_project_manager):
    """Test that service can access project data."""
    # Act
    project_data = video_processing_service.project_manager.get_project_data()

    # Assert
    mock_project_manager.get_project_data.assert_called_once()
    assert "videos" in project_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# process_single_video: the orchestration (TASK-087)
# ---------------------------------------------------------------------------


class _Bus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class _Scheduler:
    def __init__(self):
        self.delays = []

    def schedule_after(self, delay_ms, fn):
        self.delays.append(delay_ms)
        fn()


class _Project:
    def __init__(self, entry=None):
        self.entry = entry
        self.active_zone_videos = []
        self.find_calls = []

    def find_video_entry(self, *, path=None, experiment_id=None):
        self.find_calls.append((path, experiment_id))
        return self.entry

    def derive_processing_metadata(self, experiment_id, video_path):
        return {"day": 2, "derived_for": video_path}

    def set_active_zone_video(self, path):
        self.active_zone_videos.append(path)


class _Ctx:
    first_frame = "FIRST"

    def __init__(self):
        self.released = 0

    def release(self):
        self.released += 1


class _Detector:
    def __init__(self):
        self.cleared = 0

    def clear_cache(self):
        self.cleared += 1


class _Rig:
    """A real ``VideoProcessingService`` with its heavy steps scripted."""

    def __init__(self, tmp_path, monkeypatch, *, entry=None, context=True):
        from zebtrack.core.video.video_processing_service import VideoProcessingService

        self.cancel = threading.Event()
        self.bus = _Bus()
        self.scheduler = _Scheduler()
        self.project = _Project(entry)
        self.calls: list[tuple] = []
        self.ctx: Any = _Ctx() if context else None
        self.results = tmp_path / "results"
        self.tracking: tuple[bool, Any] = (True, [[0, 0], [1, 0], [1, 1]])
        self.analysis = True
        self.service = VideoProcessingService(
            project_manager=cast(Any, self.project),
            state_manager=cast(Any, SimpleNamespace()),
            ui_coordinator=cast(Any, self.scheduler),
            ui_event_bus=cast(Any, self.bus),
            cancel_event=self.cancel,
            settings_obj=cast(Any, SimpleNamespace()),
        )
        svc = self.service

        def create(video_path):
            self.calls.append(("context", video_path))
            return self.ctx

        def display(video_path, frame=None):
            self.calls.append(("display", video_path, frame))

        def resolve(**kw):
            self.calls.append(("resolve", kw))
            return self.results, "unused"

        def track(*args, **kw):
            self.calls.append(("track", args, kw))
            return self.tracking

        def analyse(**kw):
            self.calls.append(("analysis", kw))
            return self.analysis

        def cleanup(results_dir, baseline):
            self.calls.append(("cleanup", results_dir, baseline))

        monkeypatch.setattr(svc, "_create_video_context", create)
        monkeypatch.setattr(svc, "display_initial_frame", display)
        monkeypatch.setattr(svc, "resolve_results_path", resolve)
        monkeypatch.setattr(svc, "run_tracking_if_needed", track)
        monkeypatch.setattr(svc, "_run_analysis_pipeline", analyse)
        monkeypatch.setattr(svc, "_cleanup_cancelled_results", cleanup)

    def names(self):
        return [call[0] for call in self.calls]

    def call(self, name):
        (found,) = [c for c in self.calls if c[0] == name]
        return found

    def process(self, **overrides):
        kwargs = {
            "index": 1,
            "total_videos": 3,
            "video_info": {"path": "/v/Dia_2/CECT_4/CECT_4.mp4"},
            "single_video_config": None,
            "analysis_interval_frames": 4,
            "display_interval_frames": 2,
            "output_base_dir": "/out",
            "experiment_id": "CECT_4",
            "metadata_context": None,
            "analysis_profile": None,
            "detector": _Detector(),
        }
        kwargs.update(overrides)
        self.kwargs = kwargs
        return self.service.process_single_video(**cast(Any, kwargs))


class TestProcessSingleVideoOrchestration:
    def test_a_completed_run_returns_the_results_dir_and_hands_each_stage_its_inputs(
        self, tmp_path, monkeypatch
    ):
        from zebtrack.ui.event_bus_v2 import UIEvents

        rig = _Rig(tmp_path, monkeypatch, entry={"metadata": {"group": "G"}, "subject": "S3"})

        ok, results_dir = rig.process()

        assert (ok, results_dir) == (True, str(rig.results))
        path = "/v/Dia_2/CECT_4/CECT_4.mp4"
        assert rig.names() == ["context", "display", "resolve", "track", "analysis"]
        # The entry is looked up by PATH first: two days share the stem CECT_4.
        assert rig.project.find_calls == [(path, "CECT_4")]
        assert rig.project.active_zone_videos == [path]
        assert rig.call("display") == ("display", path, "FIRST")
        resolve = rig.call("resolve")[1]
        assert resolve["video_path"] == path
        assert resolve["experiment_id"] == "CECT_4"
        assert resolve["output_base_dir"] == "/out"
        # Derived metadata (the day) reaches the results-path resolution.
        assert resolve["metadata_context"] == {"derived_for": path, "day": 2}
        _, args, kw = rig.call("track")
        detector = rig.kwargs["detector"]
        # The worker builds its own detector/recorder and opens the video itself;
        # it never receives a calibration (the trajectory stays in raw pixels).
        assert args[:3] == (path, str(rig.results), "CECT_4")
        assert len(args) == 4
        assert callable(args[3])
        assert kw == {
            "analysis_interval_frames": 4,
            "display_interval_frames": 2,
        }
        analysis = rig.call("analysis")[1]
        assert analysis["arena_polygon_px"] == [[0, 0], [1, 0], [1, 1]]
        assert analysis["results_dir"] == str(rig.results)
        assert analysis["video_context"] is rig.ctx
        assert analysis["progress_callback"] is args[3]
        # Released once, and the detector cache cleared once.
        assert rig.ctx.released == 1
        assert cast(Any, detector).cleared == 1
        # The analysis view is told who is being processed, on the main thread.
        assert rig.scheduler.delays == [0]
        events = rig.bus.events
        metadata_events = [e for e in events if e.type == UIEvents.UI_UPDATE_ANALYSIS_METADATA]
        assert metadata_events[0].data.metadata["experiment_id"] == "CECT_4"
        assert metadata_events[0].data.metadata["group"] == "G"
        assert metadata_events[0].data.metadata["subject"] == "S3"
        start = next(e for e in events if e.type == UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS)
        assert (start.data.index, start.data.total, start.data.experiment_id) == (1, 3, "CECT_4")

    def test_a_given_metadata_context_is_used_as_is(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        given = {"group": "Given"}

        rig.process(metadata_context=given)

        assert rig.call("resolve")[1]["metadata_context"] is given
        assert rig.call("analysis")[1]["metadata_context"] is given

    def test_a_single_video_config_skips_derived_metadata(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        config = {"group_label": "Single"}

        rig.process(single_video_config=config)

        assert rig.call("resolve")[1]["metadata_context"] is None
        # The config shapes the analysis, never the tracking: no calibration
        # reaches the worker, so the trajectory stays in raw video pixels.
        assert "calibration_data" not in rig.call("track")[2]
        assert rig.call("analysis")[1]["single_video_config"] is config

    @pytest.mark.parametrize("info", [{}, {"path": ""}, {"path": None}])
    def test_a_video_without_a_path_is_refused_before_any_work(self, tmp_path, monkeypatch, info):
        rig = _Rig(tmp_path, monkeypatch)
        detector = _Detector()

        assert rig.process(video_info=info, detector=detector) == (False, None)

        assert rig.calls == []
        assert cast(Any, detector).cleared == 1

    def test_an_unreadable_video_is_refused_and_nothing_is_released(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch, context=False)

        assert rig.process() == (False, None)

        assert rig.names() == ["context"]
        assert rig.bus.events == []

    def test_a_failed_tracking_stops_before_the_analysis_without_cleanup(
        self, tmp_path, monkeypatch
    ):
        rig = _Rig(tmp_path, monkeypatch)
        rig.tracking = (False, None)

        assert rig.process() == (False, str(rig.results))

        assert "analysis" not in rig.names()
        assert "cleanup" not in rig.names()
        assert rig.ctx.released == 1

    def test_a_cancel_during_tracking_removes_what_the_run_created(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        rig.results.mkdir()
        (rig.results / "kept_from_before.txt").write_text("old")
        original_track = rig.service.run_tracking_if_needed

        def track_then_cancel(*args, **kw):
            rig.cancel.set()
            return original_track(*args, **kw)

        monkeypatch.setattr(rig.service, "run_tracking_if_needed", track_then_cancel)

        assert rig.process() == (False, str(rig.results))

        _, cleaned, baseline = rig.call("cleanup")
        assert cleaned == str(rig.results)
        # The earlier file was archived under history/ before the run started, so
        # the cleanup snapshot knows it and never deletes it.
        assert baseline == {"history"}
        assert not (rig.results / "kept_from_before.txt").exists()
        assert "analysis" not in rig.names()
        assert rig.ctx.released == 1

    def test_a_cancel_during_the_analysis_wins_over_its_success(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        original = rig.service._run_analysis_pipeline

        def analyse_then_cancel(**kw):
            rig.cancel.set()
            return original(**kw)

        monkeypatch.setattr(rig.service, "_run_analysis_pipeline", analyse_then_cancel)

        assert rig.process() == (False, str(rig.results))

        assert rig.names().count("cleanup") == 1

    def test_a_failed_analysis_is_reported_with_its_results_dir(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        rig.analysis = False

        assert rig.process() == (False, str(rig.results))
        assert "cleanup" not in rig.names()

    def test_an_error_still_releases_the_capture_and_clears_the_cache(self, tmp_path, monkeypatch):
        rig = _Rig(tmp_path, monkeypatch)
        detector = _Detector()

        def boom(*_a, **_k):
            raise RuntimeError("worker died")

        monkeypatch.setattr(rig.service, "run_tracking_if_needed", boom)

        with pytest.raises(RuntimeError, match="worker died"):
            rig.process(detector=detector)

        assert rig.ctx.released == 1
        assert cast(Any, detector).cleared == 1

    @pytest.mark.parametrize("detector", [None, object()])
    def test_a_detector_without_a_cache_is_left_alone(self, tmp_path, monkeypatch, detector):
        rig = _Rig(tmp_path, monkeypatch)
        assert rig.process(detector=detector) == (True, str(rig.results))

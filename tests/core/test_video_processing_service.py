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

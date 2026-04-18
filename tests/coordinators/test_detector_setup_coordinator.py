"""Tests for DetectorSetupCoordinator - Phase 4.9.

Comprehensive test coverage for detector setup and configuration orchestration.
"""

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.base_coordinator import CoordinatorValidationError
from zebtrack.coordinators.detector_setup_coordinator import (
    DetectorSetupCoordinator,
    DetectorSetupCoordinatorError,
)
from zebtrack.core.detection import ZoneData
from zebtrack.core.state_manager import StateCategory, StateManager

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_detector_service():
    """Create mock DetectorService."""
    service = MagicMock()
    service.initialize_detector.return_value = (True, None)
    service.configure_zones.return_value = True
    service.update_tracking_parameters.return_value = True
    service.reset_tracking_state.return_value = None
    service.set_single_subject_mode.return_value = None
    service.get_detector_parameters.return_value = {
        "track_threshold": 0.3,
        "match_threshold": 0.2,
        "track_buffer": 30,
    }
    service.get_factory_detector_parameters.return_value = {
        "track_threshold": 0.25,
        "match_threshold": 0.15,
        "track_buffer": 30,
    }
    service.restore_detector_settings.return_value = None
    service.settings = MagicMock()
    service.settings.detection.animal_method = "det"
    return service


@pytest.fixture
def mock_model_service():
    """Create mock ModelService."""
    return MagicMock()


@pytest.fixture
def mock_weight_manager():
    """Create mock WeightManager."""
    manager = MagicMock()
    manager.get_weight_details.return_value = {
        "path": "/path/to/weight.pt",
        "name": "yolo11n",
    }
    return manager


@pytest.fixture
def mock_event_bus():
    """Create mock EventBus."""
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    manager = MagicMock()
    manager.get_state.return_value = {}
    manager.prefer_unified_state_api = True
    return manager


@pytest.fixture
def detector_setup_coordinator(
    mock_state_manager,
    mock_detector_service,
    mock_model_service,
    mock_weight_manager,
    mock_event_bus,
):
    """Create DetectorSetupCoordinator with mocked dependencies."""
    return DetectorSetupCoordinator(
        state_manager=mock_state_manager,
        detector_service=mock_detector_service,
        model_service=mock_model_service,
        weight_manager=mock_weight_manager,
        event_bus=mock_event_bus,
    )


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


class TestDetectorSetupCoordinatorInitialization:
    """Test DetectorSetupCoordinator initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_detector_service,
        mock_model_service,
        mock_weight_manager,
        mock_event_bus,
    ):
        """Test initialization with all dependencies."""
        coordinator = DetectorSetupCoordinator(
            state_manager=mock_state_manager,
            detector_service=mock_detector_service,
            model_service=mock_model_service,
            weight_manager=mock_weight_manager,
            event_bus=mock_event_bus,
        )

        assert coordinator.state_manager == mock_state_manager
        assert coordinator.detector_service == mock_detector_service
        assert coordinator.model_service == mock_model_service
        assert coordinator.weight_manager == mock_weight_manager
        assert coordinator.event_bus == mock_event_bus

    def test_init_without_optional_dependencies(
        self,
        mock_state_manager,
        mock_detector_service,
    ):
        """Test initialization without optional dependencies."""
        coordinator = DetectorSetupCoordinator(
            state_manager=mock_state_manager,
            detector_service=mock_detector_service,
        )

        assert coordinator.model_service is None
        assert coordinator.weight_manager is None
        assert coordinator.event_bus is None

    def test_validate_dependencies_passes(self, detector_setup_coordinator):
        """Test that validate_dependencies returns True with valid dependencies."""
        assert detector_setup_coordinator.validate_dependencies() is True

    def test_validate_dependencies_fails_without_detector_service(
        self,
        mock_state_manager,
    ):
        """Test that validate_dependencies raises error without detector_service."""
        coordinator = DetectorSetupCoordinator(
            state_manager=mock_state_manager,
            detector_service=cast(Any, None),
        )

        with pytest.raises(CoordinatorValidationError) as exc_info:
            coordinator.validate_dependencies()

        assert "DetectorService is required" in str(exc_info.value)
        assert exc_info.value.context["missing_dependency"] == "detector_service"


# =============================================================================
# DETECTOR SETUP TESTS
# =============================================================================


class TestDetectorSetup:
    """Test detector setup workflows."""

    def test_setup_detector_success(self, detector_setup_coordinator, mock_detector_service):
        """Test successful detector setup."""
        success, error = detector_setup_coordinator.setup_detector(
            animal_method="det",
            use_openvino=True,
            active_weight_name="yolo11n",
        )

        assert success is True
        assert error is None
        mock_detector_service.initialize_detector.assert_called_once_with(
            animal_method="det",
            use_openvino=True,
            active_weight_name="yolo11n",
            detector_plugins=None,
            perspective=None,
        )

    def test_setup_detector_with_plugins(self, detector_setup_coordinator, mock_detector_service):
        """Test detector setup with custom plugins."""
        plugins = {"custom": MagicMock()}
        success, _error = detector_setup_coordinator.setup_detector(
            detector_plugins=plugins,
        )

        assert success is True
        mock_detector_service.initialize_detector.assert_called_once()
        call_kwargs = mock_detector_service.initialize_detector.call_args[1]
        assert call_kwargs["detector_plugins"] == plugins

    def test_setup_detector_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that setup_detector updates StateManager."""
        detector_setup_coordinator.setup_detector(
            animal_method="seg",
            use_openvino=False,
        )

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[0][0] == StateCategory.DETECTOR
        assert "is_detector_initialized" in call_args[1]
        assert call_args[1]["is_detector_initialized"] is True

    def test_setup_detector_updates_state_on_success(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that setup_detector updates state on success."""
        detector_setup_coordinator.setup_detector(animal_method="det")

        # Verify state was updated (setup_detector calls _update_state, not publish_event)
        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[0][0] == StateCategory.DETECTOR
        assert call_args[1].get("is_detector_initialized") is True

    def test_setup_detector_invalid_animal_method(self, detector_setup_coordinator):
        """Test setup_detector with invalid animal_method."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.setup_detector(animal_method="invalid")

        assert "Invalid animal_method" in str(exc_info.value)

    def test_setup_detector_service_fails(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test setup_detector when service returns failure."""
        mock_detector_service.initialize_detector.return_value = (False, "Test error")

        success, error = detector_setup_coordinator.setup_detector()

        assert success is False
        assert error == "Test error"

    def test_setup_detector_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test setup_detector when service raises exception."""
        mock_detector_service.initialize_detector.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.setup_detector()

        assert "Failed to setup detector" in str(exc_info.value)
        assert "animal_method" in exc_info.value.context

    def test_setup_detector_with_none_dependencies(
        self,
        mock_state_manager,
    ):
        """Test setup_detector fails validation with None detector_service."""
        coordinator = DetectorSetupCoordinator(
            state_manager=mock_state_manager,
            detector_service=cast(Any, None),
        )

        with pytest.raises(CoordinatorValidationError):
            coordinator.setup_detector()

    def test_setup_detector_invalid_weight_name_type(self, detector_setup_coordinator):
        """Test setup_detector with invalid active_weight_name type."""
        with pytest.raises(TypeError):
            detector_setup_coordinator.setup_detector(active_weight_name=123)

    def test_setup_detector_invalid_use_openvino_type(self, detector_setup_coordinator):
        """Test setup_detector with invalid use_openvino type."""
        with pytest.raises(TypeError):
            detector_setup_coordinator.setup_detector(use_openvino="true")


# =============================================================================
# ZONE CONFIGURATION TESTS
# =============================================================================


class TestZoneConfiguration:
    """Test zone configuration workflows."""

    def test_configure_zones_success(self, detector_setup_coordinator, mock_detector_service):
        """Test successful zone configuration."""
        zones = [{"name": "Zone1", "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]]}]
        success = detector_setup_coordinator.configure_zones(
            zones_data=zones,
            video_width=1920,
            video_height=1080,
        )

        assert success is True
        mock_detector_service.configure_zones.assert_called_once()
        call_kwargs = mock_detector_service.configure_zones.call_args.kwargs
        assert call_kwargs["video_width"] == 1920
        assert call_kwargs["video_height"] == 1080
        zones_arg = call_kwargs["zones_data"]
        assert isinstance(zones_arg, ZoneData)
        assert zones_arg.roi_names == ["Zone1"]
        assert zones_arg.roi_polygons == [[[0, 0], [100, 0], [100, 100], [0, 100]]]

    def test_configure_zones_without_dimensions(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test zone configuration without video dimensions."""
        zones = [{"name": "Zone1"}]
        success = detector_setup_coordinator.configure_zones(zones_data=zones)

        assert success is True
        mock_detector_service.configure_zones.assert_called_once()

    def test_configure_zones_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that configure_zones updates StateManager."""
        zones = [{"name": "Zone1"}, {"name": "Zone2"}]
        detector_setup_coordinator.configure_zones(zones_data=zones)

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args
        assert call_args[1]["zones_configured"] is True
        assert call_args[1]["zones_count"] == 2

    def test_configure_zones_publishes_event(
        self,
        detector_setup_coordinator,
        mock_event_bus,
    ):
        """Test that configure_zones publishes event."""
        zones = [{"name": "Zone1"}]
        detector_setup_coordinator.configure_zones(zones_data=zones)

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "ZONES_CONFIGURED"

    def test_configure_zones_invalid_width(self, detector_setup_coordinator):
        """Test configure_zones with invalid video_width."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.configure_zones(video_width=0)

        assert "video_width must be > 0" in str(exc_info.value)

    def test_configure_zones_invalid_height(self, detector_setup_coordinator):
        """Test configure_zones with invalid video_height."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.configure_zones(video_height=-10)

        assert "video_height must be > 0" in str(exc_info.value)

    def test_configure_zones_service_fails(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test configure_zones when service returns failure."""
        mock_detector_service.configure_zones.return_value = False

        success = detector_setup_coordinator.configure_zones()

        assert success is False

    def test_configure_zones_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test configure_zones when service raises exception."""
        mock_detector_service.configure_zones.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.configure_zones()

        assert "Failed to configure zones" in str(exc_info.value)

    def test_configure_zones_invalid_zones_data_type(self, detector_setup_coordinator):
        """Test configure_zones with invalid zones_data type."""
        with pytest.raises(TypeError):
            detector_setup_coordinator.configure_zones(zones_data="invalid")


# =============================================================================
# TRACKING PARAMETER TESTS
# =============================================================================


class TestTrackingParameters:
    """Test tracking parameter management."""

    def test_update_tracking_parameters_success(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test successful tracking parameter update."""
        success = detector_setup_coordinator.update_tracking_parameters(
            track_threshold=0.3,
            match_threshold=0.2,
            track_buffer=30,
        )

        assert success is True
        mock_detector_service.update_tracking_parameters.assert_called_once_with(
            track_threshold=0.3,
            match_threshold=0.2,
            track_buffer=30,
            max_center_distance=None,
            iou_threshold=None,
            use_bytetrack=None,
        )

    def test_update_tracking_parameters_partial(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test updating only some tracking parameters."""
        success = detector_setup_coordinator.update_tracking_parameters(track_threshold=0.4)

        assert success is True
        mock_detector_service.update_tracking_parameters.assert_called_once()
        call_kwargs = mock_detector_service.update_tracking_parameters.call_args[1]
        assert call_kwargs["track_threshold"] == 0.4
        assert call_kwargs["match_threshold"] is None
        assert call_kwargs["track_buffer"] is None

    def test_update_tracking_parameters_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that update_tracking_parameters updates StateManager."""
        detector_setup_coordinator.update_tracking_parameters(
            track_threshold=0.3,
            match_threshold=0.2,
        )

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args[1]
        assert call_args["tracking_parameters_updated"] is True
        assert call_args["track_threshold"] == 0.3
        assert call_args["match_threshold"] == 0.2

    def test_update_tracking_parameters_publishes_event(
        self,
        detector_setup_coordinator,
        mock_event_bus,
    ):
        """Test that update_tracking_parameters publishes event."""
        detector_setup_coordinator.update_tracking_parameters(track_threshold=0.3)

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "TRACKING_PARAMETERS_UPDATED"

    def test_update_tracking_parameters_invalid_track_threshold_range(
        self,
        detector_setup_coordinator,
    ):
        """Test update with track_threshold out of range."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.update_tracking_parameters(track_threshold=1.5)

        assert "track_threshold must be between 0.0 and 1.0" in str(exc_info.value)

    def test_update_tracking_parameters_invalid_match_threshold_range(
        self,
        detector_setup_coordinator,
    ):
        """Test update with match_threshold out of range."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.update_tracking_parameters(match_threshold=-0.1)

        assert "match_threshold must be between 0.0 and 1.0" in str(exc_info.value)

    def test_update_tracking_parameters_invalid_track_buffer(
        self,
        detector_setup_coordinator,
    ):
        """Test update with negative track_buffer."""
        with pytest.raises(ValueError) as exc_info:
            detector_setup_coordinator.update_tracking_parameters(track_buffer=-5)

        assert "track_buffer must be >= 0" in str(exc_info.value)

    def test_update_tracking_parameters_service_fails(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test update when service returns failure."""
        mock_detector_service.update_tracking_parameters.return_value = False

        success = detector_setup_coordinator.update_tracking_parameters(track_threshold=0.3)

        assert success is False

    def test_update_tracking_parameters_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test update when service raises exception."""
        mock_detector_service.update_tracking_parameters.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.update_tracking_parameters()

        assert "Failed to update tracking parameters" in str(exc_info.value)

    def test_get_detector_parameters_success(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test getting current detector parameters."""
        params = detector_setup_coordinator.get_detector_parameters()

        assert params["track_threshold"] == 0.3
        assert params["match_threshold"] == 0.2
        assert params["track_buffer"] == 30
        mock_detector_service.get_detector_parameters.assert_called_once()

    def test_get_factory_detector_parameters_success(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test getting factory default parameters."""
        params = detector_setup_coordinator.get_factory_detector_parameters()

        assert params["track_threshold"] == 0.25
        assert params["match_threshold"] == 0.15
        mock_detector_service.get_factory_detector_parameters.assert_called_once()


# =============================================================================
# TRACKING STATE TESTS
# =============================================================================


class TestTrackingState:
    """Test tracking state management."""

    def test_reset_tracking_state_success(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test successful tracking state reset."""
        success = detector_setup_coordinator.reset_tracking_state()

        assert success is True
        mock_detector_service.reset_tracking_state.assert_called_once()

    def test_reset_tracking_state_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that reset_tracking_state updates StateManager."""
        detector_setup_coordinator.reset_tracking_state()

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args[1]
        assert call_args["tracking_state_reset"] is True

    def test_reset_tracking_state_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test reset when service raises exception."""
        mock_detector_service.reset_tracking_state.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.reset_tracking_state()

        assert "Failed to reset tracking state" in str(exc_info.value)


# =============================================================================
# SINGLE SUBJECT MODE TESTS
# =============================================================================


class TestSingleSubjectMode:
    """Test single subject mode management."""

    def test_set_single_subject_mode_enabled(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test enabling single subject mode."""
        success = detector_setup_coordinator.set_single_subject_mode(enabled=True)

        assert success is True
        mock_detector_service.set_single_subject_mode.assert_called_once_with(enabled=True)

    def test_set_single_subject_mode_disabled(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test disabling single subject mode."""
        success = detector_setup_coordinator.set_single_subject_mode(enabled=False)

        assert success is True
        mock_detector_service.set_single_subject_mode.assert_called_once_with(enabled=False)

    def test_set_single_subject_mode_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that set_single_subject_mode updates StateManager."""
        detector_setup_coordinator.set_single_subject_mode(enabled=True)

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args[1]
        assert call_args["single_subject_mode"] is True

    def test_set_single_subject_mode_publishes_event(
        self,
        detector_setup_coordinator,
        mock_event_bus,
    ):
        """Test that set_single_subject_mode publishes event."""
        detector_setup_coordinator.set_single_subject_mode(enabled=True)

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "SINGLE_SUBJECT_MODE_CHANGED"

    def test_set_single_subject_mode_invalid_type(self, detector_setup_coordinator):
        """Test set_single_subject_mode with invalid type."""
        with pytest.raises(TypeError):
            detector_setup_coordinator.set_single_subject_mode(enabled="true")

    def test_set_single_subject_mode_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test set mode when service raises exception."""
        mock_detector_service.set_single_subject_mode.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.set_single_subject_mode(enabled=True)

        assert "Failed to set single subject mode" in str(exc_info.value)


# =============================================================================
# SETTINGS RESTORATION TESTS
# =============================================================================


class TestSettingsRestoration:
    """Test detector settings restoration."""

    def test_restore_detector_settings_success(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test successful settings restoration."""
        config = {"track_threshold": 0.3, "match_threshold": 0.2}
        success = detector_setup_coordinator.restore_detector_settings(config)

        assert success is True
        mock_detector_service.restore_detector_settings.assert_called_once_with(config)

    def test_restore_detector_settings_updates_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test that restore_detector_settings updates StateManager."""
        config = {"track_threshold": 0.3}
        detector_setup_coordinator.restore_detector_settings(config)

        mock_state_manager.update_state.assert_called()
        call_args = mock_state_manager.update_state.call_args[1]
        assert call_args["settings_restored"] is True

    def test_restore_detector_settings_publishes_event(
        self,
        detector_setup_coordinator,
        mock_event_bus,
    ):
        """Test that restore_detector_settings publishes event."""
        config = {"track_threshold": 0.3}
        detector_setup_coordinator.restore_detector_settings(config)

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "DETECTOR_SETTINGS_RESTORED"

    def test_restore_detector_settings_invalid_type(self, detector_setup_coordinator):
        """Test restore with invalid config type."""
        with pytest.raises(TypeError):
            detector_setup_coordinator.restore_detector_settings("invalid")

    def test_restore_detector_settings_service_raises_exception(
        self,
        detector_setup_coordinator,
        mock_detector_service,
    ):
        """Test restore when service raises exception."""
        mock_detector_service.restore_detector_settings.side_effect = RuntimeError("Test error")

        with pytest.raises(DetectorSetupCoordinatorError) as exc_info:
            detector_setup_coordinator.restore_detector_settings({})

        assert "Failed to restore detector settings" in str(exc_info.value)


# =============================================================================
# STATE QUERY TESTS
# =============================================================================


class TestStateQueries:
    """Test detector state query methods."""

    def test_is_detector_initialized_returns_true(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test is_detector_initialized when detector is initialized."""
        mock_state_manager.get_state.return_value = {"is_detector_initialized": True}

        assert detector_setup_coordinator.is_detector_initialized() is True

    def test_is_detector_initialized_returns_false(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test is_detector_initialized when detector is not initialized."""
        mock_state_manager.get_state.return_value = {}

        assert detector_setup_coordinator.is_detector_initialized() is False

    def test_get_detector_info_when_initialized(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test get_detector_info when detector is initialized."""
        mock_state_manager.get_state.return_value = {
            "is_detector_initialized": True,
            "animal_method": "det",
            "use_openvino": True,
            "zones_configured": True,
            "zones_count": 3,
            "single_subject_mode": True,
        }

        info = detector_setup_coordinator.get_detector_info()

        assert info["initialized"] is True
        assert info["animal_method"] == "det"
        assert info["use_openvino"] is True
        assert info["zones_configured"] is True
        assert info["zones_count"] == 3
        assert info["single_subject_mode"] is True
        assert "tracking_parameters" in info

    def test_get_detector_info_when_not_initialized(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test get_detector_info when detector is not initialized."""
        mock_state_manager.get_state.return_value = {}

        info = detector_setup_coordinator.get_detector_info()

        assert info["initialized"] is False
        assert info["zones_count"] == 0
        assert info["use_openvino"] is False

    def test_repr_shows_detector_state(
        self,
        detector_setup_coordinator,
        mock_state_manager,
    ):
        """Test __repr__ shows detector state."""
        mock_state_manager.get_state.return_value = {
            "is_detector_initialized": True,
            "animal_method": "seg",
            "use_openvino": False,
            "zones_count": 2,
        }

        repr_str = repr(detector_setup_coordinator)

        assert "DetectorSetupCoordinator" in repr_str
        assert "initialized=True" in repr_str
        assert "method=seg" in repr_str
        assert "zones=2" in repr_str


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestDetectorSetupCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_detector_workflow(
        self,
        mock_detector_service,
        mock_model_service,
        mock_weight_manager,
        mock_event_bus,
    ):
        """Test complete detector setup workflow."""
        # Use real StateManager
        state_manager = StateManager()

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
            model_service=mock_model_service,
            weight_manager=mock_weight_manager,
            event_bus=mock_event_bus,
        )

        # Setup detector
        success, _error = coordinator.setup_detector(
            animal_method="det",
            use_openvino=True,
        )
        assert success is True

        # Configure zones
        zones = [{"name": "Zone1"}, {"name": "Zone2"}]
        success = coordinator.configure_zones(zones_data=zones)
        assert success is True

        # Update tracking parameters
        success = coordinator.update_tracking_parameters(
            track_threshold=0.3,
            match_threshold=0.2,
        )
        assert success is True

        # Check state
        assert coordinator.is_detector_initialized() is True
        info = coordinator.get_detector_info()
        assert info["initialized"] is True
        assert info["zones_count"] == 2

    def test_state_history_tracks_changes(
        self,
        mock_detector_service,
    ):
        """Test that StateManager tracks detector state changes."""
        state_manager = StateManager(enable_history=True)

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Perform multiple operations
        coordinator.setup_detector()
        coordinator.update_tracking_parameters(track_threshold=0.3)
        coordinator.set_single_subject_mode(enabled=True)

        # Check history
        history = state_manager.get_history(StateCategory.DETECTOR)
        assert len(history) >= 3  # At least 3 state changes

    def test_error_recovery_on_setup_failure(
        self,
        mock_detector_service,
    ):
        """Test error recovery when detector setup fails."""
        state_manager = StateManager()
        mock_detector_service.initialize_detector.side_effect = RuntimeError("Setup failed")

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Attempt setup (should fail)
        with pytest.raises(DetectorSetupCoordinatorError):
            coordinator.setup_detector()

        # Verify detector is still not initialized
        assert coordinator.is_detector_initialized() is False

    def test_multiple_parameter_updates(
        self,
        mock_detector_service,
    ):
        """Test multiple tracking parameter updates."""
        state_manager = StateManager()

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Update parameters multiple times
        coordinator.update_tracking_parameters(track_threshold=0.3)
        coordinator.update_tracking_parameters(match_threshold=0.2)
        coordinator.update_tracking_parameters(track_buffer=40)

        # Verify all calls were made
        assert mock_detector_service.update_tracking_parameters.call_count == 3

    def test_zone_reconfiguration(
        self,
        mock_detector_service,
    ):
        """Test reconfiguring zones multiple times."""
        state_manager = StateManager()

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Configure zones initially
        zones1 = [{"name": "Zone1"}]
        coordinator.configure_zones(zones_data=zones1)

        # Reconfigure with different zones
        zones2 = [{"name": "Zone1"}, {"name": "Zone2"}, {"name": "Zone3"}]
        coordinator.configure_zones(zones_data=zones2)

        # Verify latest state
        info = coordinator.get_detector_info()
        assert info["zones_count"] == 3

    def test_settings_restoration_workflow(
        self,
        mock_detector_service,
    ):
        """Test complete settings save/restore workflow."""
        state_manager = StateManager()

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Get current parameters
        current = coordinator.get_detector_parameters()

        # Change parameters
        coordinator.update_tracking_parameters(track_threshold=0.5)

        # Restore original settings
        success = coordinator.restore_detector_settings(current)
        assert success is True

    def test_single_subject_mode_toggle(
        self,
        mock_detector_service,
    ):
        """Test toggling single subject mode on/off."""
        state_manager = StateManager()

        coordinator = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        # Enable
        coordinator.set_single_subject_mode(enabled=True)
        info = coordinator.get_detector_info()
        assert info["single_subject_mode"] is True

        # Disable
        coordinator.set_single_subject_mode(enabled=False)
        info = coordinator.get_detector_info()
        assert info["single_subject_mode"] is False

    def test_parallel_coordinator_instances(
        self,
        mock_detector_service,
    ):
        """Test that multiple coordinators can share StateManager."""
        state_manager = StateManager()

        coordinator1 = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=mock_detector_service,
        )

        coordinator2 = DetectorSetupCoordinator(
            state_manager=state_manager,
            detector_service=MagicMock(),
        )

        # Setup with coordinator1
        coordinator1.setup_detector()

        # Both coordinators should see the same state
        assert coordinator1.is_detector_initialized() is True
        assert coordinator2.is_detector_initialized() is True

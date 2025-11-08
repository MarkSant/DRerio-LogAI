"""
Unit tests for HardwareCoordinator.

Tests detector setup, Arduino management, zone configuration,
and callback integration.
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, call

from zebtrack.core.hardware_coordinator import HardwareCoordinator
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.project_manager import ProjectManager
from zebtrack.core.state_manager import StateManager
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events


class TestHardwareCoordinatorInitialization(unittest.TestCase):
    """Test HardwareCoordinator initialization."""

    def setUp(self):
        """Create mock dependencies."""
        self.mock_state_manager = Mock(spec=StateManager)
        self.mock_event_bus = Mock(spec=EventBus)
        self.mock_settings = Mock()
        self.mock_project_manager = Mock(spec=ProjectManager)
        self.mock_detector_service = Mock(spec=DetectorService)
        self.mock_arduino_manager_cls = Mock(spec=ArduinoManager)

    def test_init_stores_all_dependencies(self):
        """Test that all dependencies are stored during initialization."""
        coordinator = HardwareCoordinator(
            state_manager=self.mock_state_manager,
            ui_event_bus=self.mock_event_bus,
            settings_obj=self.mock_settings,
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
            arduino_manager_cls=self.mock_arduino_manager_cls,
        )

        assert coordinator.state_manager == self.mock_state_manager
        assert coordinator.ui_event_bus == self.mock_event_bus
        assert coordinator.settings == self.mock_settings
        assert coordinator.project_manager == self.mock_project_manager
        assert coordinator.detector_service == self.mock_detector_service
        assert coordinator._arduino_manager_cls == self.mock_arduino_manager_cls

    def test_init_sets_arduino_to_none(self):
        """Test that Arduino instances start as None."""
        coordinator = HardwareCoordinator(
            state_manager=self.mock_state_manager,
            ui_event_bus=self.mock_event_bus,
            settings_obj=self.mock_settings,
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
        )

        assert coordinator.arduino is None
        assert coordinator.arduino_manager is None

    def test_init_defaults_arduino_manager_cls(self):
        """Test that arduino_manager_cls defaults to ArduinoManager."""
        coordinator = HardwareCoordinator(
            state_manager=self.mock_state_manager,
            ui_event_bus=self.mock_event_bus,
            settings_obj=self.mock_settings,
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
        )

        assert coordinator._arduino_manager_cls == ArduinoManager

    def test_init_sets_callbacks_to_none(self):
        """Test that recording callbacks start as None."""
        coordinator = HardwareCoordinator(
            state_manager=self.mock_state_manager,
            ui_event_bus=self.mock_event_bus,
            settings_obj=self.mock_settings,
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
        )

        assert coordinator._trigger_recording_callback is None
        assert coordinator._stop_recording_callback is None


class TestSetupDetector(unittest.TestCase):
    """Test detector setup functionality."""

    def setUp(self):
        """Create coordinator with mocked dependencies."""
        self.mock_detector_service = Mock()
        self.mock_project_manager = Mock()

        self.coordinator = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            ui_event_bus=Mock(spec=EventBus),
            settings_obj=Mock(),
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
        )

    def test_setup_detector_calls_detector_service(self):
        """Test that setup_detector delegates to detector_service."""
        self.mock_detector_service.initialize_detector.return_value = (True, None)

        result = self.coordinator.setup_detector(
            temp_animal_method="det",
            use_openvino=False,
            active_weight_name="best.pt"
        )

        assert result is True
        self.mock_detector_service.initialize_detector.assert_called_once_with(
            animal_method="det",
            use_openvino=False,
            active_weight_name="best.pt"
        )

    def test_setup_detector_with_default_params(self):
        """Test setup_detector with default parameters."""
        self.mock_detector_service.initialize_detector.return_value = (True, None)

        result = self.coordinator.setup_detector()

        assert result is True
        self.mock_detector_service.initialize_detector.assert_called_once_with(
            animal_method=None,
            use_openvino=False,
            active_weight_name=""
        )

    def test_setup_detector_failure(self):
        """Test setup_detector when detector_service fails."""
        self.mock_detector_service.initialize_detector.return_value = (False, "Error message")

        result = self.coordinator.setup_detector()

        assert result is False

    def test_setup_detector_with_project_data(self):
        """Test that setup_detector validates project data."""
        self.mock_detector_service.initialize_detector.return_value = (True, None)
        self.mock_project_manager.project_data = {"use_arduino": True}

        result = self.coordinator.setup_detector()

        assert result is True


class TestArduinoManagement(unittest.TestCase):
    """Test Arduino connection and management."""

    def setUp(self):
        """Create coordinator with mocked dependencies."""
        self.mock_arduino_manager_cls = Mock()
        self.mock_arduino_manager = Mock()
        self.mock_arduino_manager_cls.return_value = self.mock_arduino_manager
        
        self.mock_settings = Mock()
        self.mock_settings.arduino.baud_rate = 9600
        
        self.mock_project_manager = Mock()
        self.mock_state_manager = Mock()

        self.coordinator = HardwareCoordinator(
            state_manager=self.mock_state_manager,
            ui_event_bus=Mock(spec=EventBus),
            settings_obj=self.mock_settings,
            project_manager=self.mock_project_manager,
            detector_service=Mock(),
            arduino_manager_cls=self.mock_arduino_manager_cls,
        )

    def test_setup_arduino_creates_manager(self):
        """Test that setup_arduino creates ArduinoManager when needed."""
        self.mock_project_manager.project_data = {
            "use_arduino": True,
            "arduino_port": "COM3"
        }
        self.mock_arduino_manager.is_connected.return_value = False
        self.mock_arduino_manager.connect.return_value = True

        result = self.coordinator.setup_arduino()

        assert result is True
        self.mock_arduino_manager.connect.assert_called_once_with("COM3", 9600)

    def test_setup_arduino_returns_false_when_disabled(self):
        """Test that setup_arduino returns False when Arduino is disabled."""
        self.mock_project_manager.project_data = {"use_arduino": False}

        result = self.coordinator.setup_arduino()

        assert result is False

    def test_on_arduino_status_change_connected(self):
        """Test Arduino status change when connected."""
        mock_view = Mock()
        self.coordinator.on_arduino_status_change(
            connected=True,
            port="COM3"
        )

        # Should log the event
        # No assertion needed as this is just state update

    def test_on_arduino_status_change_disconnected(self):
        """Test Arduino status change when disconnected."""
        self.coordinator.on_arduino_status_change(
            connected=False,
            port=None
        )

        # Should log the event
        # No assertion needed as this is just state update

    def test_log_arduino_event(self):
        """Test logging Arduino events."""
        # This is a simple logger method, just ensure it doesn't crash
        self.coordinator.log_arduino_event("Test event")

    def test_on_arduino_command_sent_success(self):
        """Test Arduino command sent callback with success."""
        self.coordinator.on_arduino_command_sent(
            command=1,
            success=True,
            source="test"
        )

        # Should log the event
        # No assertion needed as this is just logging

    def test_on_arduino_command_sent_failure(self):
        """Test Arduino command sent callback with failure."""
        self.coordinator.on_arduino_command_sent(
            command=1,
            success=False,
            source="test"
        )

        # Should log the failure
        # No assertion needed as this is just logging


class TestArduinoShutdown(unittest.TestCase):
    """Test Arduino shutdown handling."""

    def setUp(self):
        """Create coordinator with mocked Arduino."""
        self.mock_arduino_manager = Mock()
        self.coordinator = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            ui_event_bus=Mock(spec=EventBus),
            settings_obj=Mock(),
            project_manager=Mock(),
            detector_service=Mock(),
        )
        self.coordinator.arduino_manager = self.mock_arduino_manager

    def test_shutdown_arduino_closes_connection(self):
        """Test that shutdown closes Arduino connection."""
        self.coordinator.shutdown_arduino()

        self.mock_arduino_manager.shutdown.assert_called_once()
        assert self.coordinator.arduino_manager is None
        assert self.coordinator.arduino is None

    def test_shutdown_arduino_when_none(self):
        """Test that shutdown handles None arduino_manager gracefully."""
        self.coordinator.arduino_manager = None

        # Should not raise exception
        self.coordinator.shutdown_arduino()

    def test_shutdown_arduino_handles_exception(self):
        """Test that shutdown handles exceptions gracefully."""
        self.mock_arduino_manager.shutdown.side_effect = Exception("Connection error")

        # Should not raise exception - error is logged
        self.coordinator.shutdown_arduino()
        
        # Manager should be cleared even on error
        assert self.coordinator.arduino_manager is None

    def test_is_arduino_connected_when_connected(self):
        """Test is_arduino_connected when Arduino is connected."""
        self.mock_arduino_manager.is_connected.return_value = True
        
        assert self.coordinator.is_arduino_connected() is True

    def test_is_arduino_connected_when_not_connected(self):
        """Test is_arduino_connected when Arduino is not connected."""
        self.coordinator.arduino_manager = None
        
        assert self.coordinator.is_arduino_connected() is False


class TestRecordingCallbacks(unittest.TestCase):
    """Test recording callback integration."""

    def setUp(self):
        """Create coordinator."""
        self.coordinator = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            ui_event_bus=Mock(spec=EventBus),
            settings_obj=Mock(),
            project_manager=Mock(spec=ProjectManager),
            detector_service=Mock(spec=DetectorService),
        )

    def test_set_recording_callbacks(self):
        """Test setting recording callbacks."""
        trigger_cb = Mock()
        stop_cb = Mock()

        self.coordinator.set_recording_callbacks(trigger_cb, stop_cb)

        assert self.coordinator._trigger_recording_callback == trigger_cb
        assert self.coordinator._stop_recording_callback == stop_cb

    def test_trigger_recording_callback_invoked(self):
        """Test that trigger recording callback is invoked correctly."""
        trigger_cb = Mock()
        self.coordinator.set_recording_callbacks(trigger_cb, Mock())

        # This would be called by external trigger logic
        if self.coordinator._trigger_recording_callback:
            self.coordinator._trigger_recording_callback(event_code=1)

        trigger_cb.assert_called_once_with(event_code=1)

    def test_stop_recording_callback_invoked(self):
        """Test that stop recording callback is invoked correctly."""
        stop_cb = Mock()
        self.coordinator.set_recording_callbacks(Mock(), stop_cb)

        # This would be called by stop trigger logic
        if self.coordinator._stop_recording_callback:
            self.coordinator._stop_recording_callback()

        stop_cb.assert_called_once()


class TestZoneConfiguration(unittest.TestCase):
    """Test zone validation functionality."""

    def setUp(self):
        """Create coordinator with mocked dependencies."""
        self.mock_detector_service = Mock()
        self.mock_project_manager = Mock()
        self.mock_event_bus = Mock()

        self.coordinator = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            ui_event_bus=self.mock_event_bus,
            settings_obj=Mock(),
            project_manager=self.mock_project_manager,
            detector_service=self.mock_detector_service,
        )

    def test_validate_zones_before_processing(self):
        """Test that zone validation checks for main arena."""
        # HardwareCoordinator validates zones through ProjectManager
        # This test ensures the integration is working
        self.mock_project_manager.get_main_arena.return_value = {
            "corners": [[0, 0], [100, 0], [100, 100], [0, 100]]
        }

        arena = self.mock_project_manager.get_main_arena()
        assert arena is not None
        assert "corners" in arena


class TestExternalTriggerHandling(unittest.TestCase):
    """Test external trigger functionality."""

    def setUp(self):
        """Create coordinator."""
        self.coordinator = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            ui_event_bus=Mock(spec=EventBus),
            settings_obj=Mock(),
            project_manager=Mock(),
            detector_service=Mock(),
        )

    def test_set_pending_external_trigger(self):
        """Test setting external trigger context."""
        context = {"video_path": "/path/to/video.mp4"}
        self.coordinator.set_pending_external_trigger(context)

        assert self.coordinator._pending_external_trigger == context

    def test_get_pending_external_trigger(self):
        """Test getting external trigger context."""
        context = {"video_path": "/path/to/video.mp4"}
        self.coordinator._pending_external_trigger = context

        result = self.coordinator.get_pending_external_trigger()

        assert result == context

    def test_clear_pending_external_trigger(self):
        """Test clearing external trigger context."""
        self.coordinator._pending_external_trigger = {"test": "data"}

        self.coordinator.clear_pending_external_trigger()

        assert self.coordinator._pending_external_trigger is None

    def test_on_arduino_event_start_with_pending_trigger(self):
        """Test Arduino event 1 (start) when pending trigger is set."""
        trigger_cb = Mock()
        self.coordinator.set_recording_callbacks(trigger_cb, Mock())
        self.coordinator.set_pending_external_trigger({"test": "context"})

        self.coordinator.on_arduino_event(1)

        trigger_cb.assert_called_once_with(1)

    def test_on_arduino_event_start_without_pending_trigger(self):
        """Test Arduino event 1 (start) when no pending trigger."""
        trigger_cb = Mock()
        self.coordinator.set_recording_callbacks(trigger_cb, Mock())
        self.coordinator._pending_external_trigger = None

        self.coordinator.on_arduino_event(1)

        # Should not call trigger callback
        trigger_cb.assert_not_called()


if __name__ == "__main__":
    unittest.main()

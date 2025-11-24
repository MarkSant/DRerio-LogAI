"""
Integration tests for HardwareCoordinator with other components (Phase 3).

Verifies that HardwareCoordinator integrates properly with StateManager,
EventBus, DetectorService, and other Phase 3 components.

Migrated from Task 2.2 legacy API to Phase 3 architecture.
"""

import unittest
from unittest.mock import Mock, MagicMock

from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
from zebtrack.core.detector_service import DetectorService
from zebtrack.core.model_service import ModelService
from zebtrack.core.state_manager import StateManager
from zebtrack.core.weight_manager import WeightManager
from zebtrack.ui.event_bus import EventBus


class TestHardwareCoordinatorIntegration(unittest.TestCase):
    """Test HardwareCoordinator integration with other components."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.event_bus = Mock(spec=EventBus)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)
        self.model_service = Mock(spec=ModelService)

    def test_coordinator_initialization_with_all_components(self):
        """Test that coordinator initializes with all Phase 3 components."""
        coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
            model_service=self.model_service,
            event_bus=self.event_bus,
        )

        assert coordinator.state_manager == self.state_manager
        assert coordinator.detector_service == self.detector_service
        assert coordinator.weight_manager == self.weight_manager
        assert coordinator.model_service == self.model_service
        assert coordinator.event_bus == self.event_bus

    def test_coordinator_shares_state_manager(self):
        """Test that multiple coordinators can share StateManager."""
        coordinator1 = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        mock_detector2 = Mock(spec=DetectorService)
        mock_detector2.settings = Mock()
        coordinator2 = HardwareCoordinator(
            state_manager=self.state_manager,  # Same instance
            detector_service=mock_detector2,
            weight_manager=Mock(spec=WeightManager),
        )

        # Both should reference same state manager
        assert coordinator1.state_manager is coordinator2.state_manager

    def test_coordinator_shares_event_bus(self):
        """Test that multiple coordinators can share EventBus."""
        coordinator1 = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
            event_bus=self.event_bus,
        )

        mock_detector2 = Mock(spec=DetectorService)
        mock_detector2.settings = Mock()
        coordinator2 = HardwareCoordinator(
            state_manager=Mock(spec=StateManager),
            detector_service=mock_detector2,
            weight_manager=Mock(spec=WeightManager),
            event_bus=self.event_bus,  # Same instance
        )

        # Both should reference same event bus
        assert coordinator1.event_bus is coordinator2.event_bus

    def test_recording_callbacks_integration(self):
        """Test that recording callbacks integrate with session coordinator."""
        coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        # Simulate session coordinator setting callbacks
        trigger_callback = Mock()
        stop_callback = Mock()

        coordinator.set_recording_callbacks(
            trigger_callback=trigger_callback,
            stop_callback=stop_callback,
        )

        # Verify callbacks are stored
        assert coordinator._trigger_recording_callback == trigger_callback
        assert coordinator._stop_recording_callback == stop_callback

    def test_detector_setup_delegates_to_service(self):
        """Test that detector setup is properly delegated to DetectorService."""
        coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        self.detector_service.initialize_detector.return_value = (True, None)

        success, error = coordinator.setup_detector(
            animal_method="det",
            use_openvino=False,
            active_weight_name="best.pt",
        )

        assert success is True
        assert error is None
        self.detector_service.initialize_detector.assert_called_once_with(
            animal_method="det",
            use_openvino=False,
            active_weight_name="best.pt",
            detector_plugins=None,
        )


class TestDetectorServiceIntegration(unittest.TestCase):
    """Test integration between HardwareCoordinator and DetectorService."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

    def test_detector_methods_delegated_to_service(self):
        """Test that detector methods are delegated to DetectorService."""
        # Test setup_detector delegation
        self.detector_service.initialize_detector.return_value = (True, None)
        success, error = self.coordinator.setup_detector()
        assert success is True
        assert error is None
        self.detector_service.initialize_detector.assert_called_once()

    def test_settings_cached_from_detector_service(self):
        """Test that settings are properly cached from DetectorService."""
        mock_settings = Mock()
        self.detector_service.settings = mock_settings

        coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        assert coordinator.settings is mock_settings


class TestStateManagerIntegration(unittest.TestCase):
    """Test integration between HardwareCoordinator and StateManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

    def test_coordinator_has_access_to_state_manager(self):
        """Test that coordinator can access StateManager."""
        assert self.coordinator.state_manager is self.state_manager

    def test_coordinator_inherits_base_coordinator_state_methods(self):
        """Test that coordinator inherits state update methods from BaseCoordinator."""
        # BaseCoordinator provides _update_state and _publish_event
        # These should be available on HardwareCoordinator
        assert hasattr(self.coordinator, "_update_state")
        assert hasattr(self.coordinator, "_publish_event")


class TestEventBusIntegration(unittest.TestCase):
    """Test integration between HardwareCoordinator and EventBus."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.event_bus = Mock(spec=EventBus)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
            event_bus=self.event_bus,
        )

    def test_coordinator_has_access_to_event_bus(self):
        """Test that coordinator can access EventBus."""
        assert self.coordinator.event_bus is self.event_bus

    def test_coordinator_can_publish_events(self):
        """Test that coordinator can publish events via EventBus."""
        # BaseCoordinator provides _publish_event method
        assert hasattr(self.coordinator, "_publish_event")


class TestWeightManagerIntegration(unittest.TestCase):
    """Test integration between HardwareCoordinator and WeightManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = HardwareCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

    def test_coordinator_has_access_to_weight_manager(self):
        """Test that coordinator can access WeightManager."""
        assert self.coordinator.weight_manager is self.weight_manager


if __name__ == "__main__":
    unittest.main()

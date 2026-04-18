"""
Integration tests for DetectorSetupCoordinator with other components (Phase 4.9).

Verifies that DetectorSetupCoordinator integrates properly with StateManager,
EventBusV2, DetectorService, and other components.

Migrated from DetectorSetupCoordinator to DetectorSetupCoordinator in Phase 4.9.
"""

import unittest
from unittest.mock import Mock

from zebtrack.coordinators.detector_setup_coordinator import DetectorSetupCoordinator
from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.model_service import ModelService
from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.core.state_manager import StateManager
from zebtrack.ui.event_bus_v2 import EventBusV2


class TestDetectorSetupCoordinatorIntegration(unittest.TestCase):
    """Test DetectorSetupCoordinator integration with other components."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.event_bus = Mock(spec=EventBusV2)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)
        self.model_service = Mock(spec=ModelService)

    def test_coordinator_initialization_with_all_components(self):
        """Test that coordinator initializes with all components."""
        coordinator = DetectorSetupCoordinator(
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
        coordinator1 = DetectorSetupCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        mock_detector2 = Mock(spec=DetectorService)
        mock_detector2.settings = Mock()
        coordinator2 = DetectorSetupCoordinator(
            state_manager=self.state_manager,  # Same instance
            detector_service=mock_detector2,
            weight_manager=Mock(spec=WeightManager),
        )

        # Both should reference same state manager
        assert coordinator1.state_manager is coordinator2.state_manager

    def test_coordinator_shares_event_bus(self):
        """Test that multiple coordinators can share EventBus."""
        coordinator1 = DetectorSetupCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
            event_bus=self.event_bus,
        )

        mock_detector2 = Mock(spec=DetectorService)
        mock_detector2.settings = Mock()
        coordinator2 = DetectorSetupCoordinator(
            state_manager=Mock(spec=StateManager),
            detector_service=mock_detector2,
            weight_manager=Mock(spec=WeightManager),
            event_bus=self.event_bus,  # Same instance
        )

        # Both should reference same event bus
        assert coordinator1.event_bus is coordinator2.event_bus

    def test_detector_setup_delegates_to_service(self):
        """Test that detector setup is properly delegated to DetectorService."""
        coordinator = DetectorSetupCoordinator(
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
            perspective=None,
        )


class TestDetectorServiceIntegration(unittest.TestCase):
    """Test integration between DetectorSetupCoordinator and DetectorService."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = DetectorSetupCoordinator(
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

        coordinator = DetectorSetupCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

        assert coordinator.settings is mock_settings


class TestStateManagerIntegration(unittest.TestCase):
    """Test integration between DetectorSetupCoordinator and StateManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = DetectorSetupCoordinator(
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
        # These should be available on DetectorSetupCoordinator
        assert hasattr(self.coordinator, "_update_state")
        assert hasattr(self.coordinator, "_publish_event")


class TestEventBusIntegration(unittest.TestCase):
    """Test integration between DetectorSetupCoordinator and EventBusV2."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.event_bus = Mock(spec=EventBusV2)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = DetectorSetupCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
            event_bus=self.event_bus,
        )

    def test_coordinator_has_access_to_event_bus(self):
        """Test that coordinator can access EventBusV2."""
        assert self.coordinator.event_bus is self.event_bus

    def test_coordinator_can_publish_events(self):
        """Test that coordinator can publish events via EventBusV2."""
        # BaseCoordinator provides _publish_event method
        assert hasattr(self.coordinator, "_publish_event")


class TestWeightManagerIntegration(unittest.TestCase):
    """Test integration between DetectorSetupCoordinator and WeightManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = Mock(spec=StateManager)
        self.detector_service = Mock(spec=DetectorService)
        self.detector_service.settings = Mock()
        self.weight_manager = Mock(spec=WeightManager)

        self.coordinator = DetectorSetupCoordinator(
            state_manager=self.state_manager,
            detector_service=self.detector_service,
            weight_manager=self.weight_manager,
        )

    def test_coordinator_has_access_to_weight_manager(self):
        """Test that coordinator can access WeightManager."""
        assert self.coordinator.weight_manager is self.weight_manager


if __name__ == "__main__":
    unittest.main()

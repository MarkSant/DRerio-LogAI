"""Tests for BaseCoordinator abstract class.

This module tests the base functionality that all coordinators inherit,
ensuring that the foundation for the refactored architecture is solid.

Test Coverage:
- Initialization and dependency injection
- State management integration
- Event bus integration
- Validation methods
- Error handling
- Abstract method enforcement
"""

from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory, StateManager


class ConcreteCoordinator(BaseCoordinator):
    """Concrete implementation of BaseCoordinator for testing."""

    def __init__(self, state_manager, event_bus=None):
        super().__init__(state_manager, event_bus)
        self.validate_called = False

    def validate_dependencies(self) -> bool:
        """Implement abstract method."""
        self.validate_called = True
        return True


class TestBaseCoordinatorInitialization:
    """Test BaseCoordinator initialization and setup."""

    def test_init_with_state_manager_only(self):
        """Should initialize with just state_manager."""
        state_manager = Mock(spec=StateManager)

        coordinator = ConcreteCoordinator(state_manager=state_manager)

        assert coordinator.state_manager is state_manager
        assert coordinator.event_bus is None

    def test_init_with_event_bus(self):
        """Should initialize with state_manager and event_bus."""
        state_manager = Mock(spec=StateManager)
        event_bus = Mock()

        coordinator = ConcreteCoordinator(
            state_manager=state_manager,
            event_bus=event_bus,
        )

        assert coordinator.state_manager is state_manager
        assert coordinator.event_bus is event_bus

    def test_init_logs_creation(self):
        """Should log coordinator creation."""
        state_manager = Mock(spec=StateManager)

        with patch("zebtrack.coordinators.base.log") as mock_log:
            ConcreteCoordinator(state_manager=state_manager)

            mock_log.info.assert_called_once()
            call_args = mock_log.info.call_args
            assert "coordinator.initialized" in call_args[0]


class TestBaseCoordinatorAbstractMethods:
    """Test that abstract methods must be implemented."""

    def test_cannot_instantiate_base_coordinator_directly(self):
        """Should not allow instantiating BaseCoordinator directly."""
        state_manager = Mock(spec=StateManager)

        with pytest.raises(TypeError) as exc_info:
            cast(Any, BaseCoordinator)(state_manager=state_manager)

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_class_must_implement_validate_dependencies(self):
        """Concrete classes must implement validate_dependencies."""

        class IncompleteCoordinator(BaseCoordinator):
            pass  # Missing validate_dependencies

        state_manager = Mock(spec=StateManager)

        with pytest.raises(TypeError):
            cast(Any, IncompleteCoordinator)(state_manager=state_manager)


class TestBaseCoordinatorStateMgmt:
    """Test state management integration."""

    def test_update_state_calls_state_manager(self):
        """Should delegate state updates to StateManager."""
        state_manager = Mock(spec=StateManager)
        state_manager.update_project_state = Mock()

        coordinator = ConcreteCoordinator(state_manager=state_manager)

        coordinator._update_state(
            StateCategory.PROJECT,
            project_path="/test/path",
            project_name="test_project",
        )

        state_manager.update_project_state.assert_called_once()
        call_kwargs = state_manager.update_project_state.call_args[1]
        assert call_kwargs["project_path"] == "/test/path"
        assert call_kwargs["project_name"] == "test_project"
        assert "source" in call_kwargs

    def test_update_state_includes_source_info(self):
        """Should include source information in state updates."""
        state_manager = Mock(spec=StateManager)
        state_manager.update_detector_state = Mock()

        coordinator = ConcreteCoordinator(state_manager=state_manager)

        coordinator._update_state(
            StateCategory.DETECTOR,
            detector_initialized=True,
        )

        call_kwargs = state_manager.update_detector_state.call_args[1]
        source = call_kwargs["source"]
        assert "ConcreteCoordinator" in source

    def test_update_state_handles_unknown_category(self):
        """Should log warning for unknown state categories."""
        state_manager = Mock(spec=StateManager)

        coordinator = ConcreteCoordinator(state_manager=state_manager)

        # Create a mock category that doesn't have update method
        mock_category = Mock()
        mock_category.name = "UNKNOWN"

        with patch("zebtrack.coordinators.base.log") as mock_log:
            coordinator._update_state(mock_category, test_field="value")

            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args[0]
            assert "state.category.unknown" in call_args


class TestBaseCoordinatorEventBus:
    """Test event bus integration."""

    def test_publish_event_with_event_bus(self):
        """Should publish events when event_bus is available."""
        state_manager = Mock(spec=StateManager)
        event_bus = Mock()

        coordinator = ConcreteCoordinator(
            state_manager=state_manager,
            event_bus=event_bus,
        )

        coordinator._publish_event("TEST_EVENT", {"key": "value"})

        event_bus.publish_event.assert_called_once_with(
            "TEST_EVENT",
            {"key": "value"},
        )

    def test_publish_event_without_event_bus(self):
        """Should log debug message when no event_bus."""
        state_manager = Mock(spec=StateManager)

        coordinator = ConcreteCoordinator(state_manager=state_manager)

        with patch("zebtrack.coordinators.base.log") as mock_log:
            coordinator._publish_event("TEST_EVENT", {"key": "value"})

            mock_log.debug.assert_called_once()
            assert "event.no_bus" in mock_log.debug.call_args[0]

    def test_publish_event_with_none_data(self):
        """Should handle None data by converting to empty dict."""
        state_manager = Mock(spec=StateManager)
        event_bus = Mock()

        coordinator = ConcreteCoordinator(
            state_manager=state_manager,
            event_bus=event_bus,
        )

        coordinator._publish_event("TEST_EVENT", None)

        event_bus.publish_event.assert_called_once_with("TEST_EVENT", {})


class TestBaseCoordinatorValidation:
    """Test validation helper methods."""

    def test_validate_not_none_passes_for_valid_value(self):
        """Should not raise error for non-None values."""
        state_manager = Mock(spec=StateManager)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        # Should not raise
        coordinator._validate_not_none("test_value", "test_param")

    def test_validate_not_none_raises_for_none(self):
        """Should raise ValueError for None values."""
        state_manager = Mock(spec=StateManager)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        with pytest.raises(ValueError) as exc_info:
            coordinator._validate_not_none(None, "test_param")

        assert "test_param" in str(exc_info.value)
        assert "cannot be None" in str(exc_info.value)

    def test_validate_type_passes_for_correct_type(self):
        """Should not raise error for correct types."""
        state_manager = Mock(spec=StateManager)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        # Should not raise
        coordinator._validate_type("test", str, "test_param")
        coordinator._validate_type(42, int, "number_param")
        coordinator._validate_type([], list, "list_param")

    def test_validate_type_raises_for_wrong_type(self):
        """Should raise TypeError for incorrect types."""
        state_manager = Mock(spec=StateManager)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        with pytest.raises(TypeError) as exc_info:
            coordinator._validate_type(42, str, "test_param")

        assert "test_param" in str(exc_info.value)
        assert "str" in str(exc_info.value)
        assert "int" in str(exc_info.value)


class TestBaseCoordinatorErrors:
    """Test coordinator error classes."""

    def test_coordinator_error_basic(self):
        """Should create basic CoordinatorError."""
        error = CoordinatorError("Test error")

        assert str(error) == "Test error"
        assert error.coordinator is None
        assert error.context == {}

    def test_coordinator_error_with_context(self):
        """Should create CoordinatorError with full context."""
        error = CoordinatorError(
            "Test error",
            coordinator="TestCoordinator",
            project_name="test_project",
            operation="create",
        )

        assert str(error) == "Test error"
        assert error.coordinator == "TestCoordinator"
        assert error.context["project_name"] == "test_project"
        assert error.context["operation"] == "create"

    def test_coordinator_validation_error_inheritance(self):
        """CoordinatorValidationError should inherit from CoordinatorError."""
        error = CoordinatorValidationError("Validation failed")

        assert isinstance(error, CoordinatorError)
        assert isinstance(error, CoordinatorValidationError)

    def test_coordinator_dependency_error_inheritance(self):
        """CoordinatorDependencyError should inherit from CoordinatorError."""
        error = CoordinatorDependencyError("Dependency missing")

        assert isinstance(error, CoordinatorError)
        assert isinstance(error, CoordinatorDependencyError)


class TestBaseCoordinatorRepr:
    """Test string representation."""

    def test_repr_shows_class_name_and_state_manager(self):
        """Should show useful debug information."""
        state_manager = Mock(spec=StateManager)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        repr_str = repr(coordinator)

        assert "ConcreteCoordinator" in repr_str
        assert "state_manager=" in repr_str


class TestBaseCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_workflow_with_real_state_manager(self):
        """Test complete workflow with actual StateManager."""
        # Create real StateManager
        state_manager = StateManager(enable_history=True)

        # Create coordinator
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        # Validate dependencies
        assert coordinator.validate_dependencies() is True
        assert coordinator.validate_called is True

        # Update state
        coordinator._update_state(
            StateCategory.PROJECT,
            project_path="/test/path",
        )

        # Verify state was updated
        project_state = state_manager.get_project_state()
        assert project_state.project_path == "/test/path"

    def test_state_history_tracking(self):
        """Should track state changes in history."""
        state_manager = StateManager(enable_history=True)
        coordinator = ConcreteCoordinator(state_manager=state_manager)

        # Make multiple state changes
        coordinator._update_state(
            StateCategory.DETECTOR,
            detector_initialized=True,
        )
        coordinator._update_state(
            StateCategory.DETECTOR,
            active_weight_name="yolo11n.pt",
        )

        # Check history
        history = state_manager.get_history(StateCategory.DETECTOR)
        assert len(history) >= 2

        # Verify source includes coordinator name
        assert any("ConcreteCoordinator" in h.source for h in history)

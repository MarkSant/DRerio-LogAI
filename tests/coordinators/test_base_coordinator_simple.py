"""Simplified standalone tests for BaseCoordinator (no GUI dependencies).

This test file can run without tkinter and the full test infrastructure.
It verifies the core functionality of BaseCoordinator.
"""

import sys
from pathlib import Path

# Add src to path for direct imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from unittest.mock import Mock

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorDependencyError,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory, StateManager


class ConcreteCoordinator(BaseCoordinator):
    """Concrete implementation for testing."""

    def __init__(self, state_manager, event_bus=None):
        super().__init__(state_manager, event_bus)
        self.validate_called = False

    def validate_dependencies(self) -> bool:
        """Override base default."""
        self.validate_called = True
        return True


def test_init_with_state_manager():
    """Should initialize with state_manager."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    assert coordinator.state_manager is state_manager
    assert coordinator.event_bus is None
    print("✓ test_init_with_state_manager passed")


def test_init_with_event_bus():
    """Should initialize with state_manager and event_bus."""
    state_manager = Mock(spec=StateManager)
    event_bus = Mock()

    coordinator = ConcreteCoordinator(
        state_manager=state_manager,
        event_bus=event_bus,
    )

    assert coordinator.state_manager is state_manager
    assert coordinator.event_bus is event_bus
    print("✓ test_init_with_event_bus passed")


def test_can_instantiate_base_coordinator_directly():
    """BaseCoordinator is now concrete and can be instantiated directly."""
    state_manager = Mock(spec=StateManager)

    coordinator = BaseCoordinator(state_manager=state_manager)

    assert coordinator.state_manager is state_manager
    assert coordinator.validate_dependencies() is True
    print("✓ test_can_instantiate_base_coordinator_directly passed")


def test_validate_dependencies_is_called():
    """Should be able to call validate_dependencies."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    result = coordinator.validate_dependencies()

    assert result is True
    assert coordinator.validate_called is True
    print("✓ test_validate_dependencies_is_called passed")


def test_update_state_calls_state_manager():
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
    print("✓ test_update_state_calls_state_manager passed")


def test_publish_event_with_event_bus():
    """Should publish events when event_bus is available."""
    state_manager = Mock(spec=StateManager)
    event_bus = Mock()

    coordinator = ConcreteCoordinator(
        state_manager=state_manager,
        event_bus=event_bus,
    )

    coordinator._publish_event("TEST_EVENT", {"key": "value"})

    event_bus.publish.assert_called_once()
    event_obj = event_bus.publish.call_args[0][0]
    assert event_obj.type == "TEST_EVENT"
    assert event_obj.data == {"key": "value"}
    print("✓ test_publish_event_with_event_bus passed")


def test_publish_event_without_event_bus():
    """Should handle None event_bus gracefully."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    # Should not raise error
    coordinator._publish_event("TEST_EVENT", {"key": "value"})
    print("✓ test_publish_event_without_event_bus passed")


def test_validate_not_none_passes():
    """Should not raise for non-None values."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    # Should not raise
    coordinator._validate_not_none("test_value", "test_param")
    print("✓ test_validate_not_none_passes passed")


def test_validate_not_none_raises():
    """Should raise ValueError for None values."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    try:
        coordinator._validate_not_none(None, "test_param")
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "test_param" in str(e)
        assert "cannot be None" in str(e)
        print("✓ test_validate_not_none_raises passed")


def test_validate_type_passes():
    """Should not raise for correct types."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    # Should not raise
    coordinator._validate_type("test", str, "test_param")
    coordinator._validate_type(42, int, "number_param")
    print("✓ test_validate_type_passes passed")


def test_validate_type_raises():
    """Should raise TypeError for incorrect types."""
    state_manager = Mock(spec=StateManager)
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    try:
        coordinator._validate_type(42, str, "test_param")
        raise AssertionError("Should have raised TypeError")
    except TypeError as e:
        assert "test_param" in str(e)
        assert "str" in str(e)
        print("✓ test_validate_type_raises passed")


def test_coordinator_error_basic():
    """Should create basic CoordinatorError."""
    error = CoordinatorError("Test error")

    assert str(error) == "Test error"
    assert error.coordinator is None
    assert error.context == {}
    print("✓ test_coordinator_error_basic passed")


def test_coordinator_error_with_context():
    """Should create CoordinatorError with context."""
    error = CoordinatorError(
        "Test error",
        coordinator="TestCoordinator",
        project_name="test_project",
    )

    assert str(error) == "Test error"
    assert error.coordinator == "TestCoordinator"
    assert error.context["project_name"] == "test_project"
    print("✓ test_coordinator_error_with_context passed")


def test_error_inheritance():
    """Should have proper error hierarchy."""
    validation_error = CoordinatorValidationError("Validation failed")
    dependency_error = CoordinatorDependencyError("Dependency missing")

    assert isinstance(validation_error, CoordinatorError)
    assert isinstance(dependency_error, CoordinatorError)
    print("✓ test_error_inheritance passed")


def test_integration_with_real_state_manager():
    """Test with actual StateManager instance."""
    # Create real StateManager
    state_manager = StateManager(enable_history=True)

    # Create coordinator
    coordinator = ConcreteCoordinator(state_manager=state_manager)

    # Validate dependencies
    assert coordinator.validate_dependencies() is True

    # Update state
    coordinator._update_state(
        StateCategory.PROJECT,
        project_path="/test/path",
    )

    # Verify state was updated
    project_state = state_manager.get_project_state()
    assert project_state.project_path == "/test/path"
    print("✓ test_integration_with_real_state_manager passed")


if __name__ == "__main__":
    """Run tests manually without pytest."""
    print("\n=== Running BaseCoordinator Standalone Tests ===\n")

    passed = 0
    failed = 0

    tests = [
        test_init_with_state_manager,
        test_init_with_event_bus,
        test_can_instantiate_base_coordinator_directly,
        test_validate_dependencies_is_called,
        test_update_state_calls_state_manager,
        test_publish_event_with_event_bus,
        test_publish_event_without_event_bus,
        test_validate_not_none_passes,
        test_validate_not_none_raises,
        test_validate_type_passes,
        test_validate_type_raises,
        test_coordinator_error_basic,
        test_coordinator_error_with_context,
        test_error_inheritance,
        test_integration_with_real_state_manager,
    ]

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed += 1

    print(f"\n=== Results: {passed} passed, {failed} failed ===\n")

    sys.exit(0 if failed == 0 else 1)

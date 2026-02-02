"""Tests for BaseUIComponent abstract class.

This module tests the base functionality for UI components that orchestrate
multiple widgets and manage complex layouts.

Test Coverage:
- Initialization and dependency injection
- Abstract method enforcement
- Lifecycle management (show, hide, cleanup)
- Event bus integration
- UI thread scheduling
- Dependency validation
- Error handling
"""

from copy import deepcopy
from tkinter import Frame
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.settings import Settings
from zebtrack.ui.components.base_component import BaseUIComponent, UIComponentError

MINIMAL_SETTINGS_DATA = {
    "camera": {
        "index": 0,
        "desired_width": 1280,
        "desired_height": 720,
        "max_reconnect_attempts": 3,
        "reconnect_timeout_seconds": 5.0,
        "max_frame_lag_ms": 100.0,
    },
    "arduino": {
        "port": "COM3",
        "baud_rate": 115200,
    },
    "yolo_model": {
        "path": "tests/fixtures/models/mock.pt",
        "confidence_threshold": 0.25,
        "nms_threshold": 0.45,
    },
    "video_processing": {
        "fps": 30,
        "processing_interval": 10,
        "processing_offset": 0,
    },
    "reproducibility": {
        "seed": 42,
    },
}


class ConcreteUIComponent(BaseUIComponent):
    """Concrete implementation of BaseUIComponent for testing."""

    def __init__(self, parent, controller, event_bus, settings_obj):
        super().__init__(parent, controller, event_bus, settings_obj)
        self.setup_called = False
        self.bind_called = False
        self.cleanup_called = False

    def setup_widgets(self):
        """Implement abstract method."""
        self.setup_called = True
        # Create a simple widget
        self.test_label = Frame(self.frame)
        self.test_label.pack()

    def bind_events(self):
        """Implement abstract method."""
        self.bind_called = True


@pytest.fixture
def tk_parent(tkinter_root):
    """Provide a Tkinter parent widget."""
    return tkinter_root


@pytest.fixture
def mock_controller():
    """Provide a mock controller."""
    controller = Mock()
    controller.state_manager = Mock()
    return controller


@pytest.fixture
def mock_event_bus():
    """Provide a mock event bus."""
    return Mock()


@pytest.fixture
def settings_obj():
    """Provide a validated Settings object for UI tests."""
    return Settings.model_validate(deepcopy(MINIMAL_SETTINGS_DATA))


class TestBaseUIComponentInitialization:
    """Test BaseUIComponent initialization and setup."""

    def test_init_with_all_dependencies(
        self, tk_parent, mock_controller, mock_event_bus, settings_obj
    ):
        """Should initialize with all dependencies."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=mock_event_bus,
            settings_obj=settings_obj,
        )

        assert component.parent is tk_parent
        assert component.controller is mock_controller
        assert component.event_bus is mock_event_bus
        assert component.settings is settings_obj
        assert isinstance(component.frame, Frame)
        assert component._initialized is False
        assert component._visible is False

    def test_init_without_event_bus(self, tk_parent, mock_controller, settings_obj):
        """Should initialize without event_bus."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        assert component.event_bus is None

    def test_init_creates_logger(self, tk_parent, mock_controller, settings_obj):
        """Should create a bound logger with component name."""
        with patch("zebtrack.ui.components.base_component.log") as mock_log:
            mock_logger = Mock()
            mock_log.bind.return_value = mock_logger

            component = ConcreteUIComponent(
                parent=tk_parent,
                controller=mock_controller,
                event_bus=None,
                settings_obj=settings_obj,
            )

            # Verify logger was bound with component name
            mock_log.bind.assert_called_once_with(component="ConcreteUIComponent")
            assert component._log is mock_logger

    def test_init_logs_initialization(
        self, tk_parent, mock_controller, mock_event_bus, settings_obj
    ):
        """Should log component initialization."""
        with patch("zebtrack.ui.components.base_component.log") as mock_log:
            mock_logger = Mock()
            mock_log.bind.return_value = mock_logger

            ConcreteUIComponent(
                parent=tk_parent,
                controller=mock_controller,
                event_bus=mock_event_bus,
                settings_obj=settings_obj,
            )

            mock_logger.info.assert_called_once_with("component.initialized", has_event_bus=True)


class TestBaseUIComponentAbstractMethods:
    """Test abstract method enforcement."""

    def test_cannot_instantiate_base_component_directly(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should not allow instantiating BaseUIComponent directly."""
        with pytest.raises(TypeError) as exc_info:
            cast(Any, BaseUIComponent)(
                parent=tk_parent,
                controller=mock_controller,
                event_bus=None,
                settings_obj=settings_obj,
            )

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_class_must_implement_setup_widgets(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Concrete classes must implement setup_widgets."""

        class IncompleteComponent(BaseUIComponent):
            def bind_events(self):
                pass

            # Missing setup_widgets

        with pytest.raises(TypeError):
            cast(Any, IncompleteComponent)(
                parent=tk_parent,
                controller=mock_controller,
                event_bus=None,
                settings_obj=settings_obj,
            )

    def test_concrete_class_must_implement_bind_events(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Concrete classes must implement bind_events."""

        class IncompleteComponent(BaseUIComponent):
            def setup_widgets(self):
                pass

            # Missing bind_events

        with pytest.raises(TypeError):
            cast(Any, IncompleteComponent)(
                parent=tk_parent,
                controller=mock_controller,
                event_bus=None,
                settings_obj=settings_obj,
            )


class TestBaseUIComponentLifecycle:
    """Test component lifecycle management."""

    def test_show_calls_setup_and_bind_on_first_call(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should call setup_widgets and bind_events on first show."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        assert not component.setup_called
        assert not component.bind_called

        component.show()

        assert component.setup_called
        assert component.bind_called
        assert component._initialized
        assert component._visible

    def test_show_does_not_call_setup_on_subsequent_calls(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should not call setup_widgets again after first show."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.show()
        component.setup_called = False  # Reset flag

        component.show()

        assert not component.setup_called  # Should not be called again

    def test_hide_makes_component_invisible(self, tk_parent, mock_controller, settings_obj):
        """Should hide the component."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.show()
        assert component.is_visible()

        component.hide()
        assert not component.is_visible()
        assert not component._visible

    def test_is_visible_reflects_state(self, tk_parent, mock_controller, settings_obj):
        """Should correctly report visibility state."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        assert not component.is_visible()

        component.show()
        assert component.is_visible()

        component.hide()
        assert not component.is_visible()

    def test_cleanup_logs_cleanup(self, tk_parent, mock_controller, settings_obj):
        """Should log cleanup."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        with patch.object(component._log, "info") as mock_info:
            component.cleanup()

            mock_info.assert_called_once_with("component.cleanup")


class TestBaseUIComponentEventBus:
    """Test event bus integration."""

    def test_emit_event_with_event_bus(
        self, tk_parent, mock_controller, mock_event_bus, settings_obj
    ):
        """Should emit events when event_bus is available."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=mock_event_bus,
            settings_obj=settings_obj,
        )

        component._emit_event("TEST_EVENT", {"key": "value"})

        mock_event_bus.publish_event.assert_called_once_with("TEST_EVENT", {"key": "value"})

    def test_emit_event_without_event_bus(self, tk_parent, mock_controller, settings_obj):
        """Should handle missing event_bus gracefully."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        # Should not raise error
        component._emit_event("TEST_EVENT", {"key": "value"})

    def test_emit_event_with_none_data(
        self, tk_parent, mock_controller, mock_event_bus, settings_obj
    ):
        """Should convert None data to empty dict."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=mock_event_bus,
            settings_obj=settings_obj,
        )

        component._emit_event("TEST_EVENT", None)

        mock_event_bus.publish_event.assert_called_once_with("TEST_EVENT", {})


class TestBaseUIComponentUIThreadScheduling:
    """Test UI thread scheduling."""

    def test_schedule_on_ui_calls_parent_after(self, tk_parent, mock_controller, settings_obj):
        """Should schedule function on UI thread via parent.after()."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        mock_func = Mock()

        with patch.object(tk_parent, "after") as mock_after:
            component._schedule_on_ui(mock_func, "arg1", kwarg1="kwarg1")

            mock_after.assert_called_once_with(0, mock_func, "arg1", kwarg1="kwarg1")

    def test_schedule_on_ui_without_arguments(self, tk_parent, mock_controller, settings_obj):
        """Should schedule function without arguments."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        mock_func = Mock()

        with patch.object(tk_parent, "after") as mock_after:
            component._schedule_on_ui(mock_func)

            mock_after.assert_called_once_with(0, mock_func)


class TestBaseUIComponentValidation:
    """Test dependency validation."""

    def test_validate_dependencies_passes_with_all_deps(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should pass validation when all dependencies present."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        assert component._validate_dependencies() is True

    def test_validate_dependencies_fails_without_parent(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should fail validation without parent."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.parent = None

        assert component._validate_dependencies() is False

    def test_validate_dependencies_fails_without_controller(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should fail validation without controller."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.controller = None

        assert component._validate_dependencies() is False

    def test_validate_dependencies_fails_without_settings(
        self, tk_parent, mock_controller, settings_obj
    ):
        """Should fail validation without settings."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.settings = None

        assert component._validate_dependencies() is False


class TestBaseUIComponentErrors:
    """Test UI component error class."""

    def test_ui_component_error_basic(self):
        """Should create basic UIComponentError."""
        error = UIComponentError("Test error")

        assert str(error) == "Test error"
        assert error.component is None
        assert error.context == {}

    def test_ui_component_error_with_context(self):
        """Should create UIComponentError with full context."""
        error = UIComponentError(
            "Test error",
            component="TestComponent",
            widget="button",
            action="click",
        )

        assert str(error) == "Test error"
        assert error.component == "TestComponent"
        assert error.context["widget"] == "button"
        assert error.context["action"] == "click"


class TestBaseUIComponentRepr:
    """Test string representation."""

    def test_repr_shows_useful_debug_info(self, tk_parent, mock_controller, settings_obj):
        """Should show visibility and initialization state."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        repr_str = repr(component)

        assert "ConcreteUIComponent" in repr_str
        assert "visible=False" in repr_str
        assert "initialized=False" in repr_str

        component.show()
        repr_str = repr(component)

        assert "visible=True" in repr_str
        assert "initialized=True" in repr_str


class TestBaseUIComponentIntegration:
    """Integration tests with real Tkinter widgets."""

    def test_full_lifecycle_workflow(self, tk_parent, mock_controller, settings_obj):
        """Test complete component lifecycle."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        # Initially hidden
        assert not component.is_visible()
        assert not component._initialized

        # Show component
        component.show()
        assert component.is_visible()
        assert component._initialized
        assert component.setup_called
        assert component.bind_called

        # Hide component
        component.hide()
        assert not component.is_visible()
        assert component._initialized  # Still initialized

        # Show again (should not re-initialize)
        component.setup_called = False
        component.show()
        assert component.is_visible()
        assert not component.setup_called  # Not called again

        # Cleanup
        component.cleanup()

    def test_with_event_bus_integration(
        self, tk_parent, mock_controller, mock_event_bus, settings_obj
    ):
        """Test integration with event bus."""
        component = ConcreteUIComponent(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=mock_event_bus,
            settings_obj=settings_obj,
        )

        component.show()

        # Emit event
        component._emit_event("COMPONENT_READY", {"component": "test"})

        mock_event_bus.publish_event.assert_called_once_with(
            "COMPONENT_READY", {"component": "test"}
        )

    def test_custom_cleanup_override(self, tk_parent, mock_controller, settings_obj):
        """Test that cleanup can be overridden."""

        class ComponentWithCleanup(ConcreteUIComponent):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.custom_cleanup_called = False

            def cleanup(self):
                self.custom_cleanup_called = True
                super().cleanup()

        component = ComponentWithCleanup(
            parent=tk_parent,
            controller=mock_controller,
            event_bus=None,
            settings_obj=settings_obj,
        )

        component.cleanup()

        assert component.custom_cleanup_called

"""
Test event bus implementation for Phase 1 refactoring.
"""

from unittest.mock import Mock

import pytest

from zebtrack.ui.event_bus import EventBus, EventType
from zebtrack.ui.events import Events


class TestEventBus:
    """Tests for the enhanced EventBus with named events."""

    def test_publish_named_event(self):
        """Test publishing a named event."""
        bus = EventBus()
        result = bus.publish_event("test:event", {"key": "value"})
        assert result is True
        assert bus.size() == 1

    def test_subscribe_and_dispatch(self):
        """Test subscribing to and dispatching named events."""
        bus = EventBus()
        handler_called = []

        def handler(data):
            handler_called.append(data)

        bus.subscribe("test:event", handler)
        bus.publish_event("test:event", {"value": 42})

        events = bus.drain()
        assert len(events) == 1
        assert events[0].type == EventType.NAMED

        bus.dispatch_named_event(events[0].payload)
        assert len(handler_called) == 1
        assert handler_called[0] == {"value": 42}

    def test_multiple_subscribers(self):
        """Test that multiple subscribers receive the same event."""
        bus = EventBus()
        calls = []

        def handler1(data):
            calls.append(("handler1", data))

        def handler2(data):
            calls.append(("handler2", data))

        bus.subscribe("test:event", handler1)
        bus.subscribe("test:event", handler2)
        bus.publish_event("test:event", {"id": 123})

        events = bus.drain()
        bus.dispatch_named_event(events[0].payload)

        assert len(calls) == 2
        assert ("handler1", {"id": 123}) in calls
        assert ("handler2", {"id": 123}) in calls

    def test_unsubscribe(self):
        """Test unsubscribing a handler."""
        bus = EventBus()
        handler_called = []

        def handler(data):
            handler_called.append(data)

        bus.subscribe("test:event", handler)
        bus.unsubscribe("test:event", handler)
        bus.publish_event("test:event", {"value": 42})

        events = bus.drain()
        bus.dispatch_named_event(events[0].payload)

        assert len(handler_called) == 0

    def test_get_subscribers(self):
        """Test retrieving subscribers for an event."""
        bus = EventBus()

        def handler1(data):
            pass

        def handler2(data):
            pass

        bus.subscribe("test:event", handler1)
        bus.subscribe("test:event", handler2)

        subscribers = bus.get_subscribers("test:event")
        assert len(subscribers) == 2
        assert handler1 in subscribers
        assert handler2 in subscribers

    def test_dispatch_event_without_handlers_doesnt_crash(self):
        """Test that dispatching an event with no handlers doesn't crash."""
        bus = EventBus()
        bus.publish_event("orphan:event", {"data": "nobody listening"})

        events = bus.drain()
        # Should not raise an exception
        bus.dispatch_named_event(events[0].payload)
        # Test passes if we get here without exception

    def test_handler_exception_handling(self, caplog):
        """Test that exceptions in handlers are caught and logged."""
        bus = EventBus()

        exception_caught = False

        def failing_handler(data):
            raise ValueError("Handler failed!")

        bus.subscribe("test:event", failing_handler)
        bus.publish_event("test:event", {"value": 42})

        events = bus.drain()

        # The test passes if dispatch_named_event doesn't raise an exception
        # (i.e., the exception is caught and logged internally)
        try:
            bus.dispatch_named_event(events[0].payload)
            exception_caught = True
        except ValueError:
            # If the exception bubbles up, the test should fail
            exception_caught = False

        # The event bus should have caught and logged the exception internally
        assert exception_caught, "EventBus should catch and log handler exceptions, not raise them"
class TestEventCatalog:
    """Tests for the Events catalog."""

    def test_event_constants_defined(self):
        """Test that event constants are properly defined."""
        assert hasattr(Events, "RECORDING_START")
        assert hasattr(Events, "RECORDING_STOP")
        assert hasattr(Events, "PROJECT_CREATE")
        assert hasattr(Events, "PROJECT_OPEN")
        assert hasattr(Events, "PROJECT_CLOSE")
        assert hasattr(Events, "MODEL_SET_WEIGHT")
        assert hasattr(Events, "VIDEO_ANALYZE_SINGLE")

    def test_event_naming_convention(self):
        """Test that events follow the 'domain:action' naming convention."""
        assert Events.RECORDING_START == "recording:start"
        assert Events.PROJECT_CLOSE == "project:close"
        assert Events.MODEL_SET_WEIGHT == "model:set_weight"
        assert Events.VIDEO_CANCEL_ANALYSIS == "video:cancel_analysis"


class TestControllerEventIntegration:
    """Integration tests for controller event handling."""

    def test_controller_registers_event_handlers(self, mock_tkinter_root, mock_application_gui, monkeypatch):
        """Test that controller registers all event handlers when event bus is enabled."""
        from zebtrack.core.controller import AppController
        import zebtrack.settings
        
        # Enable event bus for this test by patching the module-level settings object
        monkeypatch.setattr(zebtrack.settings.settings.ui_features, "enable_event_queue", True)

        # Create controller with event bus enabled
        controller = AppController(mock_tkinter_root)

        # Verify event bus was created
        assert controller.ui_event_bus is not None

        # Verify some key events have subscribers
        subscribers = controller.ui_event_bus.get_subscribers(Events.RECORDING_START)
        assert len(subscribers) > 0

        subscribers = controller.ui_event_bus.get_subscribers(Events.PROJECT_CLOSE)
        assert len(subscribers) > 0

        subscribers = controller.ui_event_bus.get_subscribers(Events.MODEL_SET_WEIGHT)
        assert len(subscribers) > 0

    def test_recording_start_event_invokes_handler(self, mock_tkinter_root, mock_application_gui, monkeypatch):
        """Test that publishing RECORDING_START event invokes the controller method."""
        from zebtrack.core.controller import AppController
        import zebtrack.settings
        
        # Enable event bus for this test
        monkeypatch.setattr(zebtrack.settings.settings.ui_features, "enable_event_queue", True)

        controller = AppController(mock_tkinter_root)

        # Mock the actual start_recording method
        start_recording_mock = Mock()
        monkeypatch.setattr(controller, "start_recording", start_recording_mock)

        # Publish the event
        controller.ui_event_bus.publish_event(
            Events.RECORDING_START, {"day": 1, "group": "A", "cobaia": "C1"}
        )

        # Drain and dispatch
        events = controller.ui_event_bus.drain()
        for event in events:
            if event.type == EventType.NAMED:
                controller.ui_event_bus.dispatch_named_event(event.payload)

        # Verify the method was called
        start_recording_mock.assert_called_once_with(day=1, group="A", cobaia="C1")

    def test_project_close_event_invokes_handler(self, mock_tkinter_root, mock_application_gui, monkeypatch):
        """Test that publishing PROJECT_CLOSE event invokes the controller method."""
        from zebtrack.core.controller import AppController
        import zebtrack.settings
        
        # Enable event bus for this test
        monkeypatch.setattr(zebtrack.settings.settings.ui_features, "enable_event_queue", True)

        controller = AppController(mock_tkinter_root)

        # Mock the actual close_project method
        close_project_mock = Mock()
        monkeypatch.setattr(controller, "close_project", close_project_mock)

        # Publish the event
        controller.ui_event_bus.publish_event(Events.PROJECT_CLOSE, {})

        # Drain and dispatch
        events = controller.ui_event_bus.drain()
        for event in events:
            if event.type == EventType.NAMED:
                controller.ui_event_bus.dispatch_named_event(event.payload)

        # Verify the method was called
        close_project_mock.assert_called_once()


@pytest.fixture
def mock_tkinter_root():
    """Create a real Tkinter root for testing controller integration."""
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()  # Hide the window
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass  # Already destroyed


@pytest.fixture
def mock_application_gui(monkeypatch):
    """Mock ApplicationGUI to avoid ttkbootstrap Style singleton issues in controller tests."""
    from zebtrack.ui.gui import ApplicationGUI
    from unittest.mock import MagicMock, PropertyMock
    
    # Replace ApplicationGUI class entirely with a factory that returns MagicMock
    def create_mock_gui(*args, **kwargs):
        mock_gui = MagicMock(spec=ApplicationGUI)
        
        # Mock methods that might be called
        mock_gui.ask_ok_cancel = MagicMock(return_value=True)
        mock_gui.update_openvino_status = MagicMock()
        mock_gui.update_detector_status = MagicMock()
        mock_gui.stop_event_bus_polling = MagicMock()
        
        # Mock properties with PropertyMock
        type(mock_gui).zone_controls = PropertyMock(return_value=None)
        type(mock_gui).toggle_view_btn = PropertyMock(return_value=None)
        type(mock_gui).draw_roi_button = PropertyMock(return_value=None)
        type(mock_gui).roi_template_combobox = PropertyMock(return_value=None)
        
        return mock_gui
    
    monkeypatch.setattr("zebtrack.ui.gui.ApplicationGUI", create_mock_gui)
    
    yield create_mock_gui

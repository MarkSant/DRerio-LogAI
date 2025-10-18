"""
Test event bus implementation for Phase 1 refactoring.
"""

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

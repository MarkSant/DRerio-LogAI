"""
Test EventBusV2 implementation (migrated from Phase 1 EventBus tests).
"""

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents


class TestEventBusV2:
    """Tests for the EventBusV2 synchronous pub/sub bus."""

    def test_publish_without_subscribers(self):
        """Test publishing an event with no subscribers doesn't crash."""
        bus = EventBusV2()
        # Should not raise
        bus.publish(Event(type=UIEvents.RECORDING_START, data={"key": "value"}))

    def test_subscribe_and_publish(self):
        """Test subscribing to and publishing events (synchronous dispatch)."""
        bus = EventBusV2()
        handler_called = []

        def handler(data):
            handler_called.append(data)

        bus.subscribe(UIEvents.RECORDING_START, handler)
        bus.publish(Event(type=UIEvents.RECORDING_START, data={"value": 42}))

        assert len(handler_called) == 1
        assert handler_called[0] == {"value": 42}

    def test_multiple_subscribers(self):
        """Test that multiple subscribers receive the same event."""
        bus = EventBusV2()
        calls = []

        def handler1(data):
            calls.append(("handler1", data))

        def handler2(data):
            calls.append(("handler2", data))

        bus.subscribe(UIEvents.RECORDING_START, handler1)
        bus.subscribe(UIEvents.RECORDING_START, handler2)
        bus.publish(Event(type=UIEvents.RECORDING_START, data={"id": 123}))

        assert len(calls) == 2
        assert ("handler1", {"id": 123}) in calls
        assert ("handler2", {"id": 123}) in calls

    def test_unsubscribe(self):
        """Test unsubscribing a handler."""
        bus = EventBusV2()
        handler_called = []

        def handler(data):
            handler_called.append(data)

        bus.subscribe(UIEvents.RECORDING_START, handler)
        bus.unsubscribe(UIEvents.RECORDING_START, handler)
        bus.publish(Event(type=UIEvents.RECORDING_START, data={"value": 42}))

        assert len(handler_called) == 0

    def test_different_event_types_isolated(self):
        """Test that subscribers only receive events they subscribed to."""
        bus = EventBusV2()
        calls = []

        def handler(data):
            calls.append(data)

        bus.subscribe(UIEvents.RECORDING_START, handler)
        bus.publish(Event(type=UIEvents.RECORDING_STOP, data={"wrong": True}))

        assert len(calls) == 0

    def test_publish_event_without_handlers_doesnt_crash(self):
        """Test that publishing an event with no handlers doesn't crash."""
        bus = EventBusV2()
        # Should not raise an exception
        bus.publish(Event(type=UIEvents.PROJECT_CREATE, data={"data": "nobody listening"}))

    def test_handler_exception_handling(self):
        """Test that exceptions in handlers are caught and logged."""
        bus = EventBusV2()

        def failing_handler(data):
            raise ValueError("Handler failed!")

        bus.subscribe(UIEvents.RECORDING_START, failing_handler)

        # EventBusV2 catches handler exceptions internally — should not raise
        bus.publish(Event(type=UIEvents.RECORDING_START, data={"value": 42}))

    def test_event_data_passed_correctly(self):
        """Test that event data dict is passed correctly to handlers."""
        bus = EventBusV2()
        received = []

        def handler(data):
            received.append(data)

        bus.subscribe(UIEvents.PROJECT_CREATE, handler)
        bus.publish(Event(type=UIEvents.PROJECT_CREATE, data={"name": "test", "path": "/tmp"}))

        assert len(received) == 1
        assert received[0] == {"name": "test", "path": "/tmp"}


class TestUIEventsCatalog:
    """Tests for the UIEvents enum catalog."""

    def test_event_constants_defined(self):
        """Test that event constants are properly defined."""
        assert hasattr(UIEvents, "RECORDING_START")
        assert hasattr(UIEvents, "RECORDING_STOP")
        assert hasattr(UIEvents, "PROJECT_CREATE")
        assert hasattr(UIEvents, "PROJECT_OPEN")
        assert hasattr(UIEvents, "PROJECT_CLOSE")
        assert hasattr(UIEvents, "MODEL_SET_WEIGHT")
        assert hasattr(UIEvents, "VIDEO_ANALYZE_SINGLE")

    def test_events_are_enum_members(self):
        """Test that events are proper UIEvents enum members."""
        assert isinstance(UIEvents.RECORDING_START, UIEvents)
        assert isinstance(UIEvents.PROJECT_CLOSE, UIEvents)
        assert isinstance(UIEvents.MODEL_SET_WEIGHT, UIEvents)
        assert isinstance(UIEvents.VIDEO_CANCEL_ANALYSIS, UIEvents)

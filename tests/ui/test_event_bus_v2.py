"""Unit tests for EventBusV2."""

import threading
import time
from unittest.mock import Mock

import pytest

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents


@pytest.fixture
def event_bus():
    """Fixture providing a fresh EventBusV2 instance."""
    return EventBusV2()


def test_subscribe_and_publish(event_bus):
    """Test basic subscription and publishing."""
    handler = Mock()
    event_bus.subscribe(UIEvents.ZONES_UPDATED, handler)

    payload = {"key": "value"}
    event = Event(type=UIEvents.ZONES_UPDATED, data=payload)
    event_bus.publish(event)

    handler.assert_called_once_with(payload)


def test_multiple_subscribers(event_bus):
    """Test that multiple handlers receive the same event."""
    handler1 = Mock()
    handler2 = Mock()

    event_bus.subscribe(UIEvents.VIDEO_LOADED, handler1)
    event_bus.subscribe(UIEvents.VIDEO_LOADED, handler2)

    event = Event(type=UIEvents.VIDEO_LOADED)
    event_bus.publish(event)

    handler1.assert_called_once()
    handler2.assert_called_once()


def test_unsubscribe(event_bus):
    """Test unsubscribing a handler."""
    handler = Mock()
    event_bus.subscribe(UIEvents.SHOW_ERROR, handler)
    event_bus.unsubscribe(UIEvents.SHOW_ERROR, handler)

    event = Event(type=UIEvents.SHOW_ERROR)
    event_bus.publish(event)

    handler.assert_not_called()


def test_unsubscribe_non_existent(event_bus):
    """Test unsubscribing a handler that wasn't subscribed (should handle gracefully)."""
    handler = Mock()
    # Should not raise exception
    event_bus.unsubscribe(UIEvents.SHOW_ERROR, handler)


def test_handler_exception_isolation(event_bus):
    """Test that one failing handler doesn't stop others."""
    failing_handler = Mock(side_effect=ValueError("Boom"))
    working_handler = Mock()

    event_bus.subscribe(UIEvents.ANALYSIS_STARTED, failing_handler)
    event_bus.subscribe(UIEvents.ANALYSIS_STARTED, working_handler)

    event = Event(type=UIEvents.ANALYSIS_STARTED)
    event_bus.publish(event)

    failing_handler.assert_called_once()
    working_handler.assert_called_once()


def test_thread_safety(event_bus):
    """Test concurrent subscriptions and publishing."""

    received_counts = {"t1": 0, "t2": 0}
    lock = threading.Lock()

    def handler_t1(data):
        with lock:
            received_counts["t1"] += 1

    def handler_t2(data):
        with lock:
            received_counts["t2"] += 1

    def worker_subscribe_publish(thread_name, handler):
        # Subscribe
        event_bus.subscribe(UIEvents.PROCESSING_STATS_UPDATED, handler)

        # Publish 100 times
        for i in range(100):
            event_bus.publish(Event(UIEvents.PROCESSING_STATS_UPDATED, {"iter": i}))
            time.sleep(0.001)  # Small delay to encourage interleaving

    t1 = threading.Thread(target=worker_subscribe_publish, args=("t1", handler_t1))
    t2 = threading.Thread(target=worker_subscribe_publish, args=("t2", handler_t2))

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # We published 200 times total (100 each thread).
    # Since both subscribed, they both should have received events.
    # Note: Exact count depends on WHEN they subscribed relative to publishing.
    # But strictly speaking, if they subscribe first, they get their own events + others.
    # This test is mainly to ensure no Deadlock or Race Condition crashing the app.

    assert received_counts["t1"] > 0
    assert received_counts["t2"] > 0


def test_publish_no_subscribers(event_bus):
    """Test publishing with no subscribers."""
    # Should not crash
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED))


def test_event_dataclass_defaults():
    """Test Event dataclass defaults."""
    event = Event(type=UIEvents.ZONES_UPDATED)
    assert event.data == {}
    assert event.source is None

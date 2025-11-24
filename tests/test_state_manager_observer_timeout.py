"""
Tests for StateManager observer timeout protection.

Task 1.2: Validate that slow observers are properly timed out.
"""

import platform
import threading
import time

import pytest

from zebtrack.core.state_manager import StateCategory, StateManager


@pytest.mark.skipif(
    platform.system() == "Windows" or threading.current_thread() is not threading.main_thread(),
    reason="Timeout mechanism only works on Unix in main thread",
)
def test_observer_timeout():
    """Slow observer that exceeds timeout should be logged and not block."""
    mgr = StateManager()
    mgr._observer_timeout_seconds = 1  # Short timeout for testing

    normal_observer_called = []

    def slow_observer(category, key, old_value, new_value):
        """Observer that takes too long."""
        time.sleep(2)  # Exceed 1s timeout
        # This should not be reached if timeout works

    def normal_observer(category, key, old_value, new_value):
        """Observer that completes quickly."""
        normal_observer_called.append(True)

    # Subscribe both observers
    mgr.subscribe(StateCategory.RECORDING, slow_observer)
    mgr.subscribe(StateCategory.RECORDING, normal_observer)

    # Trigger update - slow observer should timeout, normal should complete
    start = time.time()
    mgr.update_recording_state(source="test", is_recording=True)
    elapsed = time.time() - start

    # Should complete reasonably fast (not 2 seconds)
    assert elapsed < 1.5, f"Should timeout after ~1s, took {elapsed:.2f}s"

    # Normal observer should have been called
    assert len(normal_observer_called) == 1, "Normal observer should complete"


def test_observer_timeout_on_windows_no_crash():
    """On Windows, timeout protection degrades gracefully (no crash)."""
    mgr = StateManager()
    mgr._observer_timeout_seconds = 1

    completed = []

    def observer(category, key, old_value, new_value):
        """Observer that would timeout on Unix but runs without timeout on Windows."""
        if platform.system() == "Windows":
            # Simulate slow observer on Windows to test graceful degradation
            time.sleep(2)  # Exceed 1s timeout
        # Skip actual sleep on Unix to avoid real timeout in tests
        completed.append(True)

    mgr.subscribe(StateCategory.RECORDING, observer)

    # Should not crash on any platform
    mgr.update_recording_state(source="test", is_recording=True)

    # Wait for async observers to complete (fire-and-forget pattern)
    time.sleep(2.5)

    assert len(completed) == 1, "Observer should complete on all platforms"


def test_observer_exception_handling_with_timeout():
    """Exceptions in observers should be caught even with timeout protection."""
    mgr = StateManager()

    other_observer_called = []

    def failing_observer(category, key, old_value, new_value):
        """Observer that raises an exception."""
        raise ValueError("Test exception")

    def normal_observer(category, key, old_value, new_value):
        """Observer that should still be called."""
        other_observer_called.append(True)

    mgr.subscribe(StateCategory.RECORDING, failing_observer)
    mgr.subscribe(StateCategory.RECORDING, normal_observer)

    # Should not crash, should call other observers
    mgr.update_recording_state(source="test", is_recording=True)

    # Wait for async observers to complete (fire-and-forget pattern)
    time.sleep(0.2)

    assert len(other_observer_called) == 1, "Other observers should still be notified"


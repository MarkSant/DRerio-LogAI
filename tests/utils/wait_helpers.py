"""Wait condition helpers for robust testing without time.sleep().

v2.2: Provides polling-based wait conditions to replace brittle time.sleep() calls
in threading tests, improving reliability and reducing flakiness.

Usage:
    from tests.utils.wait_helpers import wait_for_condition, wait_for_thread_exit

    # Instead of: time.sleep(1.0); assert thread.is_alive()
    # Use: assert not wait_for_thread_exit(thread, timeout=1.0)
"""

import threading
import time
from collections.abc import Callable


def wait_for_condition(
    condition_fn: Callable[[], bool],
    timeout: float = 2.0,
    interval: float = 0.01,
    error_msg: str | None = None,
) -> bool:
    """Poll a condition function until it returns True or timeout expires.

    Args:
        condition_fn: Callable that returns bool (True when condition met)
        timeout: Maximum time to wait in seconds (default 2.0)
        interval: Polling interval in seconds (default 0.01 = 10ms)
        error_msg: Custom error message (optional, for logging)

    Returns:
        bool: True if condition met, False if timeout

    Example:
        events = []
        def check(): return len(events) > 0
        assert wait_for_condition(check, timeout=1.0)
    """
    start = time.time()
    while time.time() - start < timeout:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


def wait_for_event(event: threading.Event, timeout: float = 2.0) -> bool:
    """Wait for a threading.Event to be set.

    Args:
        event: Threading event to wait for
        timeout: Maximum time to wait in seconds (default 2.0)

    Returns:
        bool: True if event was set, False if timeout

    Example:
        ready_event = threading.Event()
        assert wait_for_event(ready_event, timeout=1.0)
    """
    return event.wait(timeout)


def wait_for_thread_exit(thread: threading.Thread, timeout: float = 2.0) -> bool:
    """Wait for a thread to exit.

    Args:
        thread: Thread to wait for
        timeout: Maximum time to wait in seconds (default 2.0)

    Returns:
        bool: True if thread exited, False if still alive after timeout

    Example:
        worker = threading.Thread(target=work)
        worker.start()
        assert wait_for_thread_exit(worker, timeout=1.0)
    """
    thread.join(timeout)
    return not thread.is_alive()


def assert_condition_met(
    condition_fn: Callable[[], bool],
    timeout: float = 2.0,
    error_msg: str | None = None,
) -> None:
    """Assert that a condition is met within timeout, raising AssertionError if not.

    Args:
        condition_fn: Callable that returns bool
        timeout: Maximum time to wait in seconds (default 2.0)
        error_msg: Custom error message for AssertionError

    Raises:
        AssertionError: If condition not met within timeout

    Example:
        events = []
        assert_condition_met(lambda: len(events) > 0, timeout=1.0,
                           error_msg="No events received")
    """
    if not wait_for_condition(condition_fn, timeout):
        msg = error_msg or f"Condition not met within {timeout}s"
        raise AssertionError(msg)

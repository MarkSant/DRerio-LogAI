"""
Stress tests for StateManager under high concurrency.

Task 1.3: Comprehensive concurrency tests to validate deadlock fixes
and threading improvements.

Run with: pytest tests/test_state_manager_stress.py -v
"""
import threading
import time
from unittest.mock import MagicMock

import pytest

from zebtrack.core.state_manager import StateCategory, StateManager


@pytest.mark.slow
def test_1000_concurrent_updates_no_deadlock():
    """1000 threads updating state simultaneously."""
    mgr = StateManager()
    results = []

    def update_worker(i):
        mgr.update_processing_state(
            source=f"worker_{i}", current_frame=i, total_frames=i * 10
        )
        results.append(i)

    threads = [
        threading.Thread(target=update_worker, args=(i,)) for i in range(1000)
    ]
    start = time.time()

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)  # 10s max

    elapsed = time.time() - start

    assert len(results) == 1000, "All updates should complete"
    assert elapsed < 10.0, f"Updates took {elapsed:.2f}s (should be <10s)"


@pytest.mark.slow
def test_observers_do_not_block_state_updates():
    """Slow observer should not block other state updates."""
    mgr = StateManager()

    slow_observer_called = threading.Event()
    fast_updates_completed = []

    def slow_observer(category, key, old_value, new_value):
        time.sleep(0.5)  # Simulate slow callback
        slow_observer_called.set()

    def fast_update_worker():
        for i in range(10):
            mgr.update_processing_state(source="fast", current_frame=i)
            fast_updates_completed.append(i)
            time.sleep(0.01)

    mgr.subscribe(StateCategory.PROCESSING, slow_observer)

    # Trigger slow observer
    mgr.update_processing_state(source="initial", current_frame=0)

    # Start fast updates immediately
    fast_thread = threading.Thread(target=fast_update_worker)
    fast_thread.start()
    fast_thread.join(timeout=5)

    assert len(fast_updates_completed) == 10, "Fast updates should not be blocked"
    assert slow_observer_called.wait(timeout=2), "Slow observer should complete"


@pytest.mark.slow
def test_100_observers_registered_concurrently():
    """100 threads registering observers simultaneously."""
    mgr = StateManager()
    observers = []

    def register_observer_worker():
        obs = MagicMock()
        observers.append(obs)
        mgr.subscribe(StateCategory.RECORDING, obs)

    threads = [
        threading.Thread(target=register_observer_worker) for _ in range(100)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert mgr.get_observer_count(StateCategory.RECORDING) == 100


@pytest.mark.slow
def test_subscribe_unsubscribe_race_condition():
    """Subscribe/unsubscribe happening concurrently with notifications."""
    mgr = StateManager()
    observers = [MagicMock() for _ in range(20)]
    errors = []

    def subscribe_unsubscribe_worker(obs):
        for _ in range(10):
            mgr.subscribe(StateCategory.RECORDING, obs)
            time.sleep(0.001)
            mgr.unsubscribe(StateCategory.RECORDING, obs)

    def update_worker():
        for i in range(50):
            try:
                mgr.update_recording_state(source="test", is_recording=bool(i % 2))
                time.sleep(0.001)
            except Exception as e:
                errors.append(e)

    sub_threads = [
        threading.Thread(target=subscribe_unsubscribe_worker, args=(obs,))
        for obs in observers
    ]
    update_thread = threading.Thread(target=update_worker)

    for t in sub_threads:
        t.start()
    update_thread.start()

    for t in sub_threads:
        t.join()
    update_thread.join()

    assert len(errors) == 0, f"Race condition errors: {errors}"


@pytest.mark.slow
def test_memory_leak_with_many_subscriptions():
    """Verify no memory leak with repeated subscribe/unsubscribe."""
    import gc
    import sys

    mgr = StateManager()
    initial_refcount = sys.getrefcount(mgr)

    for _ in range(1000):
        obs = MagicMock()
        mgr.subscribe(StateCategory.RECORDING, obs)
        mgr.unsubscribe(StateCategory.RECORDING, obs)
        del obs

    gc.collect()
    final_refcount = sys.getrefcount(mgr)

    # Allow small increase but not 1000x
    assert final_refcount - initial_refcount < 10, "Memory leak detected"

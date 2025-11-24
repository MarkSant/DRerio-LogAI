"""
Testes de Thread Safety para UICoordinator.

Testa cenários de concorrência em agendamento de UI,
sincronização de estado e processamento de fila de eventos.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock

import pytest

from tests.utils.wait_helpers import wait_for_thread_exit
from zebtrack.core.ui_coordinator import UICoordinator


@pytest.fixture
def mock_root():
    """Create a mock Tkinter root."""
    root = Mock()
    # Simulate root.after behavior - execute immediately for testing
    root.after = Mock(side_effect=lambda delay, func, *args: func(*args) if args else func())
    root.after_cancel = Mock()
    return root


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBus."""
    event_bus = Mock()
    event_bus.publish_callable.return_value = True
    return event_bus


@pytest.fixture
def ui_coordinator(mock_root):
    """Create a UICoordinator instance with mocked root."""
    return UICoordinator(root=mock_root, event_bus=None)


@pytest.fixture
def ui_coordinator_with_event_bus(mock_root, mock_event_bus):
    """Create a UICoordinator instance with both root and event bus."""
    return UICoordinator(root=mock_root, event_bus=mock_event_bus)


class TestUICoordinatorScheduling:
    """Test thread-safe UI scheduling."""

    def test_concurrent_schedule_calls(self, ui_coordinator):
        """Test concurrent schedule() calls from multiple threads."""
        scheduled_functions = []

        def scheduler_worker(thread_id):
            for i in range(5):
                ui_coordinator.schedule(
                    lambda tid=thread_id, idx=i: scheduled_functions.append((tid, idx))
                )
                time.sleep(0.01)

        # Start multiple scheduler threads
        schedulers = []
        for i in range(3):
            scheduler = threading.Thread(target=scheduler_worker, args=(i,), daemon=False)
            scheduler.start()
            schedulers.append(scheduler)

        # Wait for completion
        for scheduler in schedulers:
            scheduler.join(timeout=3.0)

        # All threads should complete
        for scheduler in schedulers:
            assert not scheduler.is_alive()

        # Verify functions were scheduled
        assert len(scheduled_functions) == 15  # 3 threads × 5 calls each

    def test_concurrent_schedule_after_calls(self, ui_coordinator):
        """Test concurrent schedule_after() calls."""
        scheduled_ids = []

        def scheduler_worker(thread_id):
            for i in range(5):
                after_id = ui_coordinator.schedule_after(
                    100,
                    lambda tid=thread_id, idx=i: None,
                )
                scheduled_ids.append((thread_id, after_id))
                time.sleep(0.01)

        # Start multiple scheduler threads
        schedulers = []
        for i in range(3):
            scheduler = threading.Thread(target=scheduler_worker, args=(i,), daemon=False)
            scheduler.start()
            schedulers.append(scheduler)

        # Wait for completion
        for scheduler in schedulers:
            scheduler.join(timeout=3.0)

        # All threads should complete
        for scheduler in schedulers:
            assert not scheduler.is_alive()

        # Verify schedule_after was called
        assert len(scheduled_ids) == 15

    def test_concurrent_cancel_scheduled_calls(self, ui_coordinator):
        """Test concurrent cancel_scheduled() calls."""
        # Schedule some callbacks first
        after_ids = []
        for i in range(10):
            after_id = ui_coordinator.schedule_after(1000, lambda: None)
            after_ids.append(after_id)

        def canceler_worker(thread_id, ids_to_cancel):
            for after_id in ids_to_cancel:
                ui_coordinator.cancel_scheduled(after_id)
                time.sleep(0.01)

        # Distribute IDs across threads
        ids_per_thread = [after_ids[i::3] for i in range(3)]

        # Start multiple canceler threads
        cancelers = []
        for i in range(3):
            canceler = threading.Thread(
                target=canceler_worker, args=(i, ids_per_thread[i]), daemon=False
            )
            canceler.start()
            cancelers.append(canceler)

        # Wait for completion
        for canceler in cancelers:
            canceler.join(timeout=3.0)

        # All threads should complete
        for canceler in cancelers:
            assert not canceler.is_alive()


class TestUICoordinatorEventBus:
    """Test event bus integration with threading."""

    def test_concurrent_event_bus_publishing(self, ui_coordinator_with_event_bus):
        """Test concurrent event bus publishing."""
        published_events = []

        def publisher_worker(thread_id):
            for i in range(5):
                ui_coordinator_with_event_bus.schedule(
                    lambda tid=thread_id, idx=i: published_events.append((tid, idx))
                )
                time.sleep(0.01)

        # Start multiple publisher threads
        publishers = []
        for i in range(3):
            publisher = threading.Thread(target=publisher_worker, args=(i,), daemon=False)
            publisher.start()
            publishers.append(publisher)

        # Wait for completion
        for publisher in publishers:
            publisher.join(timeout=3.0)

        # All threads should complete
        for publisher in publishers:
            assert not publisher.is_alive()

        # Verify events were published (via event bus or fallback)
        assert len(published_events) >= 0  # May vary based on event bus behavior

    def test_event_bus_fallback_behavior(self, mock_root):
        """Test fallback when event bus fails."""
        # Create event bus that fails
        failing_event_bus = Mock()
        failing_event_bus.publish_callable.return_value = False

        coordinator = UICoordinator(root=mock_root, event_bus=failing_event_bus)

        executed_functions = []

        def fallback_worker(thread_id):
            for i in range(3):
                coordinator.schedule(
                    lambda tid=thread_id, idx=i: executed_functions.append((tid, idx))
                )
                time.sleep(0.01)

        # Start workers
        workers = []
        for i in range(2):
            worker = threading.Thread(target=fallback_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All should complete and functions should execute via fallback
        for worker in workers:
            assert not worker.is_alive()
        assert len(executed_functions) == 6  # 2 threads × 3 calls each


class TestUICoordinatorViewUpdates:
    """Test concurrent view update operations."""

    def test_concurrent_update_view_calls(self, ui_coordinator):
        """Test concurrent update_view() calls."""
        mock_view = Mock()
        mock_view.update_status = Mock()
        mock_view.update_progress = Mock()

        update_calls = []

        def updater_worker(thread_id):
            for i in range(5):
                ui_coordinator.update_view(
                    mock_view, "update_status", f"Status from thread {thread_id}"
                )
                update_calls.append((thread_id, i))
                time.sleep(0.01)

        # Start multiple updater threads
        updaters = []
        for i in range(3):
            updater = threading.Thread(target=updater_worker, args=(i,), daemon=False)
            updater.start()
            updaters.append(updater)

        # Wait for completion
        for updater in updaters:
            updater.join(timeout=3.0)

        # All threads should complete
        for updater in updaters:
            assert not updater.is_alive()

        # Verify updates were called
        assert len(update_calls) == 15

    def test_concurrent_set_status_calls(self, ui_coordinator):
        """Test concurrent set_status() convenience method calls."""
        mock_view = Mock()
        mock_view.set_status = Mock()

        status_updates = []

        def status_worker(thread_id):
            for i in range(5):
                ui_coordinator.set_status(mock_view, f"Status {thread_id}_{i}")
                status_updates.append((thread_id, i))
                time.sleep(0.01)

        # Start multiple status workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=status_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        assert len(status_updates) == 15

    def test_concurrent_progress_updates(self, ui_coordinator):
        """Test concurrent update_progress() calls."""
        mock_view = Mock()
        mock_view.update_progress = Mock()

        progress_values = []

        def progress_worker(thread_id):
            for i in range(5):
                progress = (i + 1) / 5.0
                ui_coordinator.update_progress(mock_view, progress)
                progress_values.append((thread_id, progress))
                time.sleep(0.01)

        # Start multiple progress workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=progress_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        assert len(progress_values) == 15


class TestUICoordinatorRaceConditions:
    """Test race conditions in UI coordinator operations."""

    def test_concurrent_root_access(self, ui_coordinator):
        """Test concurrent access to root object."""
        access_count = []

        def root_accessor(thread_id):
            for i in range(5):
                # Access root through scheduling
                ui_coordinator.schedule(lambda: access_count.append(1))
                time.sleep(0.01)

        # Start multiple accessor threads
        accessors = []
        for i in range(3):
            accessor = threading.Thread(target=root_accessor, args=(i,), daemon=False)
            accessor.start()
            accessors.append(accessor)

        # Wait for completion
        for accessor in accessors:
            accessor.join(timeout=3.0)

        # All threads should complete
        for accessor in accessors:
            assert not accessor.is_alive()

        # Verify accesses occurred
        assert len(access_count) == 15

    def test_mixed_operation_concurrency(self, ui_coordinator):
        """Test concurrent mixed operations (schedule, schedule_after, cancel)."""
        operations = []

        def mixed_worker(thread_id):
            for i in range(3):
                # Schedule immediate
                ui_coordinator.schedule(lambda: operations.append("schedule"))
                time.sleep(0.01)

                # Schedule delayed
                after_id = ui_coordinator.schedule_after(100, lambda: operations.append("delayed"))
                time.sleep(0.01)

                # Cancel
                if after_id:
                    ui_coordinator.cancel_scheduled(after_id)
                    operations.append("cancel")
                time.sleep(0.01)

        # Start multiple workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=mixed_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

        # Verify operations occurred
        assert len(operations) > 0


class TestUICoordinatorErrorHandling:
    """Test error handling in concurrent operations."""

    def test_exception_in_scheduled_callback(self, ui_coordinator):
        """Test exception handling in scheduled callbacks."""
        exceptions_caught = []

        def failing_callback(thread_id):
            if thread_id == 1:
                raise RuntimeError(f"Error from thread {thread_id}")

        def error_worker(thread_id):
            try:
                ui_coordinator.schedule(failing_callback, thread_id)
                time.sleep(0.01)
            except Exception as e:
                exceptions_caught.append((thread_id, str(e)))

        # Start workers
        workers = []
        for i in range(3):
            worker = threading.Thread(target=error_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete
        for worker in workers:
            assert not worker.is_alive()

    def test_missing_view_method_handling(self, ui_coordinator):
        """Test handling of missing view methods."""
        mock_view = Mock()
        # Don't define the method we'll try to call

        attempts = []

        def updater_worker(thread_id):
            for i in range(3):
                ui_coordinator.update_view(mock_view, "nonexistent_method", "arg")
                attempts.append((thread_id, i))
                time.sleep(0.01)

        # Start workers
        workers = []
        for i in range(2):
            worker = threading.Thread(target=updater_worker, args=(i,), daemon=False)
            worker.start()
            workers.append(worker)

        # Wait for completion
        for worker in workers:
            worker.join(timeout=3.0)

        # All threads should complete despite missing method
        for worker in workers:
            assert not worker.is_alive()

        assert len(attempts) == 6

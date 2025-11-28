"""
Tests for StateManager Observer Pattern enhancements.

Phase 3, Step 2.2: Test coverage for explicit Observer pattern,
BaseStateObserver, ObserverAdapter, and formal registration methods.
"""

from unittest.mock import MagicMock

from zebtrack.core.state_manager import (
    BaseStateObserver,
    ObserverAdapter,
    StateCategory,
    StateManager,
)


class TestObserverProtocol:
    """Test formal Observer protocol and base class."""

    def test_base_observer_subclass(self):
        """BaseStateObserver subclass receives notifications."""
        state_mgr = StateManager()
        notifications = []

        class TestObserver(BaseStateObserver):
            def on_state_changed(self, category, key, old_value, new_value):
                notifications.append((category, key, old_value, new_value))

        observer = TestObserver()
        # BaseStateObserver instances need to be wrapped for StateManager
        state_mgr.subscribe(StateCategory.RECORDING, observer.on_state_changed)

        # Trigger state change
        state_mgr.update_recording_state(source="test", is_recording=True)

        assert len(notifications) == 1
        assert notifications[0][0] == StateCategory.RECORDING
        assert notifications[0][1] == "is_recording"
        assert notifications[0][2] is False
        assert notifications[0][3] is True

    def test_observer_adapter_category_filter(self):
        """ObserverAdapter filters by category."""
        state_mgr = StateManager()
        callback = MagicMock()

        # Create adapter that only observes RECORDING category
        adapter = ObserverAdapter(
            callback=callback,
            categories={StateCategory.RECORDING},
        )

        state_mgr.subscribe(StateCategory.RECORDING, adapter)
        state_mgr.subscribe(StateCategory.DETECTOR, adapter)

        # Trigger changes in both categories
        state_mgr.update_recording_state(source="test", is_recording=True)
        state_mgr.update_detector_state(source="test", detector_initialized=True)

        # Only RECORDING change should be notified
        assert callback.call_count == 1
        call_args = callback.call_args[0]
        assert call_args[0] == StateCategory.RECORDING

    def test_observer_adapter_key_filter(self):
        """ObserverAdapter filters by specific keys."""
        state_mgr = StateManager()
        callback = MagicMock()

        # Create adapter that only observes specific keys
        adapter = ObserverAdapter(
            callback=callback,
            keys={"is_recording", "output_path"},
        )

        state_mgr.subscribe(StateCategory.RECORDING, adapter)

        # Trigger changes to different keys
        state_mgr.update_recording_state(source="test", is_recording=True)
        state_mgr.update_recording_state(source="test", arduino_connected=True)

        # Only is_recording should be notified
        assert callback.call_count == 1
        call_args = callback.call_args[0]
        assert call_args[1] == "is_recording"

    def test_observer_adapter_combined_filter(self):
        """ObserverAdapter filters by both category and keys."""
        state_mgr = StateManager()
        callback = MagicMock()

        # Create adapter with both filters
        adapter = ObserverAdapter(
            callback=callback,
            categories={StateCategory.RECORDING},
            keys={"is_recording"},
        )

        state_mgr.subscribe(StateCategory.RECORDING, adapter)
        state_mgr.subscribe(StateCategory.DETECTOR, adapter)

        # Trigger various changes
        state_mgr.update_recording_state(source="test", is_recording=True)
        state_mgr.update_recording_state(source="test", arduino_connected=True)
        state_mgr.update_detector_state(source="test", detector_initialized=True)

        # Only RECORDING.is_recording should be notified
        assert callback.call_count == 1
        call_args = callback.call_args[0]
        assert call_args[0] == StateCategory.RECORDING
        assert call_args[1] == "is_recording"


class TestExplicitRegistration:
    """Test explicit observer registration methods."""

    def test_register_observer_alias(self):
        """register_observer() is alias for subscribe()."""
        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.register_observer(StateCategory.RECORDING, observer)

        state_mgr.update_recording_state(source="test", is_recording=True)

        observer.assert_called_once()

    def test_register_global_observer_alias(self):
        """register_global_observer() is alias for subscribe_all()."""
        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.register_global_observer(observer)

        state_mgr.update_recording_state(source="test", is_recording=True)

        observer.assert_called_once()

    def test_multiple_observers_same_category(self):
        """Multiple observers can be registered for same category."""
        state_mgr = StateManager()
        observer1 = MagicMock()
        observer2 = MagicMock()
        observer3 = MagicMock()

        state_mgr.register_observer(StateCategory.RECORDING, observer1)
        state_mgr.register_observer(StateCategory.RECORDING, observer2)
        state_mgr.register_observer(StateCategory.RECORDING, observer3)

        state_mgr.update_recording_state(source="test", is_recording=True)

        observer1.assert_called_once()
        observer2.assert_called_once()
        observer3.assert_called_once()


class TestObserverCount:
    """Test observer counting utilities."""

    def test_get_observer_count_specific_category(self):
        """get_observer_count() returns count for specific category."""
        state_mgr = StateManager()

        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 0

        state_mgr.subscribe(StateCategory.RECORDING, MagicMock())
        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 1

        state_mgr.subscribe(StateCategory.RECORDING, MagicMock())
        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 2

    def test_get_observer_count_all(self):
        """get_observer_count() returns total count when no category specified."""
        state_mgr = StateManager()

        assert state_mgr.get_observer_count() == 0

        state_mgr.subscribe(StateCategory.RECORDING, MagicMock())
        state_mgr.subscribe(StateCategory.DETECTOR, MagicMock())
        state_mgr.subscribe_all(MagicMock())

        assert state_mgr.get_observer_count() == 3

    def test_unsubscribe_decrements_count(self):
        """Unsubscribing decrements observer count."""
        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.subscribe(StateCategory.RECORDING, observer)
        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 1

        state_mgr.unsubscribe(StateCategory.RECORDING, observer)
        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 0


class TestStateIntegrity:
    """Test state integrity verification."""

    def test_verify_state_integrity_initial(self):
        """verify_state_integrity() returns diagnostic info for initial state."""
        state_mgr = StateManager()

        integrity = state_mgr.verify_state_integrity()

        assert integrity["state_valid"] is True
        assert integrity["project"]["has_path"] is False
        assert integrity["detector"]["initialized"] is False
        assert integrity["recording"]["is_recording"] is False
        assert integrity["processing"]["is_processing"] is False

    def test_verify_state_integrity_with_data(self):
        """verify_state_integrity() reflects actual state."""
        from pathlib import Path

        state_mgr = StateManager()

        state_mgr.update_project_state(
            source="test",
            project_path=Path("/test/project"),
            project_data={"videos": []},
        )
        state_mgr.update_detector_state(
            source="test",
            detector_initialized=True,
            frame_width=1920,
            frame_height=1080,
        )

        integrity = state_mgr.verify_state_integrity()

        assert integrity["project"]["has_path"] is True
        assert integrity["project"]["has_data"] is True
        assert integrity["detector"]["initialized"] is True
        assert integrity["detector"]["has_dimensions"] is True

    def test_verify_state_integrity_includes_observers(self):
        """verify_state_integrity() includes observer counts."""
        state_mgr = StateManager()

        state_mgr.subscribe(StateCategory.RECORDING, MagicMock())
        state_mgr.subscribe(StateCategory.DETECTOR, MagicMock())
        state_mgr.subscribe_all(MagicMock())

        integrity = state_mgr.verify_state_integrity()

        assert integrity["observers"]["total"] == 3
        assert integrity["observers"]["by_category"]["RECORDING"] == 1
        assert integrity["observers"]["by_category"]["DETECTOR"] == 1
        assert integrity["observers"]["global"] == 1


class TestObserverExceptionHandling:
    """Test that observer exceptions don't break state updates."""

    def test_failing_observer_doesnt_prevent_update(self):
        """State updates succeed even if observer raises exception."""
        state_mgr = StateManager()
        working_calls = []

        def failing_observer(category, key, old_value, new_value):
            raise RuntimeError("Observer error")

        def working_observer(category, key, old_value, new_value):
            working_calls.append((category, key, old_value, new_value))

        state_mgr.subscribe(StateCategory.RECORDING, failing_observer)
        state_mgr.subscribe(StateCategory.RECORDING, working_observer)

        # Update should succeed despite failing observer
        state_mgr.update_recording_state(source="test", is_recording=True)

        # Verify state was updated
        state = state_mgr.get_recording_state()
        assert state.is_recording is True

        # Wait for async observers to complete (they run in ThreadPoolExecutor)
        from tests.utils.wait_helpers import wait_for_condition

        wait_for_condition(lambda: len(working_calls) > 0, timeout=1.0)

        # Verify working observer was called
        assert len(working_calls) == 1
        assert working_calls[0][1] == "is_recording"

    def test_failing_global_observer_doesnt_prevent_update(self):
        """Global observer exceptions don't prevent state updates."""
        state_mgr = StateManager()

        def failing_global_observer(category, key, old_value, new_value):
            raise RuntimeError("Global observer error")

        state_mgr.subscribe_all(failing_global_observer)

        # Update should succeed
        state_mgr.update_recording_state(source="test", is_recording=True)

        # Verify state was updated
        state = state_mgr.get_recording_state()
        assert state.is_recording is True


class TestUnidirectionalDataFlow:
    """Test that state changes flow only through official methods."""

    def test_state_updates_go_through_update_methods(self):
        """Verify all state changes use update_*_state() methods."""
        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.subscribe(StateCategory.RECORDING, observer)

        # State change via official method
        state_mgr.update_recording_state(source="test", is_recording=True)

        # Observer should be notified
        observer.assert_called_once()

        # Verify state was actually updated
        state = state_mgr.get_recording_state()
        assert state.is_recording is True

    def test_direct_state_access_not_recommended(self):
        """Direct access to _state bypasses observers (anti-pattern)."""
        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.subscribe(StateCategory.RECORDING, observer)

        # ANTI-PATTERN: Direct access bypasses observers
        # This is what we want to prevent with proper architecture
        state_mgr._state.recording.is_recording = True

        # Observer NOT notified (demonstrates why direct access is bad)
        observer.assert_not_called()

        # But state WAS changed (inconsistent!)
        assert state_mgr._state.recording.is_recording is True


class TestThreadSafety:
    """Test thread-safe observer registration and notification."""

    def test_concurrent_observer_registration(self):
        """Multiple threads can register observers safely."""
        import threading

        state_mgr = StateManager()
        observers = []

        def register_observer():
            observer = MagicMock()
            observers.append(observer)
            state_mgr.subscribe(StateCategory.RECORDING, observer)

        threads = [threading.Thread(target=register_observer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert state_mgr.get_observer_count(StateCategory.RECORDING) == 10

    def test_concurrent_state_updates_notify_all(self):
        """State updates from multiple threads notify all observers."""
        import threading

        state_mgr = StateManager()
        observer = MagicMock()

        state_mgr.subscribe(StateCategory.PROCESSING, observer)

        # Use unique values to ensure all updates trigger notifications
        # (updates with same value are skipped)
        def update_state(value):
            # Use different state key to avoid value deduplication
            # Start from 1 to avoid matching initial state (current_frame=0)
            state_mgr.update_processing_state(
                source=f"test-{value}",
                current_frame=value + 1,
                total_frames=(value + 1) * 10,
            )

        threads = [threading.Thread(target=update_state, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Wait for async observers to complete (they run in ThreadPoolExecutor)
        from tests.utils.wait_helpers import wait_for_condition

        wait_for_condition(lambda: observer.call_count >= 10, timeout=2.0)

        # Observer should be called twice per update (current_frame + total_frames)
        assert observer.call_count == 10

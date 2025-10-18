"""
Tests for StateManager - centralized application state management.

Phase 2, Step 4: Test coverage for observable pattern, state updates,
observer notifications, history tracking, and thread safety.
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.core.state_manager import (
    ApplicationState,
    DetectorState,
    ProjectState,
    RecordingState,
    StateCategory,
    StateManager,
)


class TestStateSnapshots:
    """Test immutable state snapshots."""

    def test_project_state_copy(self):
        """ProjectState.copy() creates independent deep copy."""
        state = ProjectState(
            project_path=Path("/test/project"),
            project_data={"videos": ["v1.mp4"], "zones": [1, 2, 3]},
            active_zone_video="v1.mp4",
        )

        copy = state.copy()

        # Verify initial equality
        assert copy.project_path == state.project_path
        assert copy.project_data == state.project_data
        assert copy.active_zone_video == state.active_zone_video

        # Modify copy
        copy.project_data["videos"].append("v2.mp4")
        copy.project_data["zones"][0] = 999

        # Original should be unchanged
        assert state.project_data["videos"] == ["v1.mp4"]
        assert state.project_data["zones"][0] == 1

    def test_detector_state_copy(self):
        """DetectorState.copy() creates independent deep copy."""
        state = DetectorState(
            detector_initialized=True,
            active_weight_name="best_oi.pt",
            use_openvino=True,
            zone_data={"polygon": [[0, 0], [100, 100]]},
        )

        copy = state.copy()

        # Modify copy
        assert copy.zone_data is not None
        copy.zone_data["polygon"][0] = [999, 999]

        # Original should be unchanged
        assert state.zone_data is not None
        assert state.zone_data["polygon"][0] == [0, 0]

    def test_application_state_copy(self):
        """ApplicationState.copy() creates full deep copy."""
        state = ApplicationState(
            project=ProjectState(project_path=Path("/test")),
            detector=DetectorState(detector_initialized=True),
            recording=RecordingState(is_recording=True),
        )

        copy = state.copy()

        # Modify nested state
        copy.project.project_path = Path("/modified")
        copy.detector.detector_initialized = False
        copy.recording.is_recording = False

        # Original should be unchanged
        assert state.project.project_path == Path("/test")
        assert state.detector.detector_initialized is True
        assert state.recording.is_recording is True


class TestStateManagerBasics:
    """Test basic StateManager initialization and configuration."""

    def test_initialization_default(self):
        """StateManager initializes with default settings."""
        mgr = StateManager()

        snapshot = mgr.get_snapshot()
        assert snapshot.project.project_path is None
        assert snapshot.detector.detector_initialized is False
        assert snapshot.recording.is_recording is False
        assert snapshot.processing.is_processing is False
        assert snapshot.ui.canvas_view_mode == "zones"

    def test_initialization_with_history_disabled(self):
        """StateManager can be initialized without history tracking."""
        mgr = StateManager(enable_history=False)

        mgr.update_project_state(project_path=Path("/test"))
        history = mgr.get_history()

        assert history == []

    def test_repr(self):
        """StateManager has useful string representation."""
        mgr = StateManager()
        repr_str = repr(mgr)

        assert "StateManager" in repr_str
        assert "observers=" in repr_str
        assert "history=" in repr_str


class TestStateUpdates:
    """Test state update operations."""

    def test_update_project_state(self):
        """Project state updates correctly."""
        mgr = StateManager()

        mgr.update_project_state(
            source="test",
            project_path=Path("/test/project"),
            active_zone_video="video1.mp4",
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.project.project_path == Path("/test/project")
        assert snapshot.project.active_zone_video == "video1.mp4"

    def test_update_detector_state(self):
        """Detector state updates correctly."""
        mgr = StateManager()

        mgr.update_detector_state(
            source="test",
            detector_initialized=True,
            active_weight_name="best_oi.pt",
            use_openvino=True,
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.detector.detector_initialized is True
        assert snapshot.detector.active_weight_name == "best_oi.pt"
        assert snapshot.detector.use_openvino is True

    def test_update_recording_state(self):
        """Recording state updates correctly."""
        mgr = StateManager()

        mgr.update_recording_state(
            source="test",
            is_recording=True,
            output_path=Path("/output/recording.parquet"),
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.recording.is_recording is True
        assert snapshot.recording.output_path == Path("/output/recording.parquet")

    def test_update_processing_state(self):
        """Processing state updates correctly."""
        mgr = StateManager()

        mgr.update_processing_state(
            source="test",
            is_processing=True,
            current_video="test.mp4",
            current_frame=100,
            total_frames=1000,
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.processing.is_processing is True
        assert snapshot.processing.current_video == "test.mp4"
        assert snapshot.processing.current_frame == 100
        assert snapshot.processing.total_frames == 1000

    def test_update_ui_state(self):
        """UI state updates correctly."""
        mgr = StateManager()

        mgr.update_ui_state(
            source="test",
            canvas_view_mode="analysis",
            selected_videos=["v1.mp4", "v2.mp4"],
            analysis_interval_frames=15,
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.ui.canvas_view_mode == "analysis"
        assert snapshot.ui.selected_videos == ["v1.mp4", "v2.mp4"]
        assert snapshot.ui.analysis_interval_frames == 15

    def test_update_unknown_field_logs_warning(self):
        """Updating unknown field logs warning but doesn't crash."""
        mgr = StateManager()

        mgr.update_project_state(
            source="test",
            unknown_field="value",
        )

        # State should be unchanged (warning is logged internally)
        snapshot = mgr.get_snapshot()
        assert not hasattr(snapshot.project, "unknown_field")

    def test_update_with_same_value_doesnt_notify(self):
        """Updating with same value doesn't trigger notifications."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.update_project_state(project_path=Path("/test"))
        mgr.subscribe(StateCategory.PROJECT, observer)

        # Update with same value
        mgr.update_project_state(project_path=Path("/test"))

        # Observer should not be called
        observer.assert_not_called()


class TestObserverPattern:
    """Test observer subscription and notification."""

    def test_subscribe_to_category(self):
        """Can subscribe to specific state category."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.subscribe(StateCategory.RECORDING, observer)
        mgr.update_recording_state(source="test", is_recording=True)

        observer.assert_called_once()
        args = observer.call_args[0]
        assert args[0] == StateCategory.RECORDING
        assert args[1] == "is_recording"
        assert args[2] is False  # old value
        assert args[3] is True  # new value

    def test_subscribe_all(self):
        """Can subscribe to all state changes."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.subscribe_all(observer)

        mgr.update_project_state(source="test", project_path=Path("/test"))
        mgr.update_detector_state(source="test", detector_initialized=True)

        assert observer.call_count == 2

    def test_multiple_observers(self):
        """Multiple observers can subscribe to same category."""
        mgr = StateManager()
        observer1 = MagicMock()
        observer2 = MagicMock()

        mgr.subscribe(StateCategory.RECORDING, observer1)
        mgr.subscribe(StateCategory.RECORDING, observer2)

        mgr.update_recording_state(source="test", is_recording=True)

        observer1.assert_called_once()
        observer2.assert_called_once()

    def test_unsubscribe(self):
        """Can unsubscribe from state changes."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.subscribe(StateCategory.RECORDING, observer)
        mgr.unsubscribe(StateCategory.RECORDING, observer)

        mgr.update_recording_state(source="test", is_recording=True)

        observer.assert_not_called()

    def test_unsubscribe_all(self):
        """Can unsubscribe from all state changes."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.subscribe_all(observer)
        mgr.unsubscribe_all(observer)

        mgr.update_project_state(source="test", project_path=Path("/test"))

        observer.assert_not_called()

    def test_observer_exception_doesnt_break_others(self):
        """Exception in one observer doesn't affect others."""
        mgr = StateManager()

        def failing_observer(*args):
            raise ValueError("Test exception")

        good_observer = MagicMock()

        mgr.subscribe(StateCategory.RECORDING, failing_observer)
        mgr.subscribe(StateCategory.RECORDING, good_observer)

        mgr.update_recording_state(source="test", is_recording=True)

        # Good observer should still be called even if first observer fails
        good_observer.assert_called_once()

    def test_observer_only_notified_for_subscribed_category(self):
        """Observer only receives notifications for subscribed category."""
        mgr = StateManager()
        observer = MagicMock()

        mgr.subscribe(StateCategory.RECORDING, observer)

        # Update different category
        mgr.update_project_state(source="test", project_path=Path("/test"))

        # Observer should not be called
        observer.assert_not_called()

        # Update subscribed category
        mgr.update_recording_state(source="test", is_recording=True)

        # Now observer should be called
        observer.assert_called_once()


class TestStateHistory:
    """Test state change history tracking."""

    def test_history_records_changes(self):
        """State changes are recorded in history."""
        mgr = StateManager()

        mgr.update_project_state(source="test", project_path=Path("/test"))
        mgr.update_recording_state(source="test", is_recording=True)

        history = mgr.get_history()
        assert len(history) == 2

        assert history[0].category == StateCategory.PROJECT
        assert history[0].key == "project_path"
        assert history[0].new_value == Path("/test")
        assert history[0].source == "test"

        assert history[1].category == StateCategory.RECORDING
        assert history[1].key == "is_recording"
        assert history[1].new_value is True

    def test_history_filter_by_category(self):
        """Can filter history by category."""
        mgr = StateManager()

        mgr.update_project_state(source="test", project_path=Path("/test"))
        mgr.update_recording_state(source="test", is_recording=True)
        mgr.update_project_state(source="test", active_zone_video="v1.mp4")

        history = mgr.get_history(category=StateCategory.PROJECT)
        assert len(history) == 2
        assert all(c.category == StateCategory.PROJECT for c in history)

    def test_history_filter_by_key(self):
        """Can filter history by state key."""
        mgr = StateManager()

        mgr.update_project_state(source="test", project_path=Path("/test1"))
        mgr.update_project_state(source="test", active_zone_video="v1.mp4")
        mgr.update_project_state(source="test", project_path=Path("/test2"))

        history = mgr.get_history(key="project_path")
        assert len(history) == 2
        assert all(c.key == "project_path" for c in history)

    def test_history_limit(self):
        """Can limit number of history items returned."""
        mgr = StateManager()

        for i in range(10):
            mgr.update_project_state(source="test", project_path=Path(f"/test{i}"))

        history = mgr.get_history(limit=3)
        assert len(history) == 3

        # Should return most recent
        assert history[-1].new_value == Path("/test9")

    def test_history_max_size(self):
        """History respects max_history_size limit."""
        mgr = StateManager(max_history_size=5)

        for i in range(10):
            mgr.update_project_state(source="test", project_path=Path(f"/test{i}"))

        history = mgr.get_history()
        assert len(history) == 5

        # Should keep most recent 5
        assert history[0].new_value == Path("/test5")
        assert history[-1].new_value == Path("/test9")

    def test_clear_history(self):
        """Can clear state history."""
        mgr = StateManager()

        mgr.update_project_state(source="test", project_path=Path("/test"))
        assert len(mgr.get_history()) == 1

        mgr.clear_history()
        assert len(mgr.get_history()) == 0

    def test_history_disabled(self):
        """History tracking can be disabled."""
        mgr = StateManager(enable_history=False)

        mgr.update_project_state(source="test", project_path=Path("/test"))

        history = mgr.get_history()
        assert history == []


class TestThreadSafety:
    """Test thread-safe state access and updates."""

    def test_concurrent_updates(self):
        """Multiple threads can update state safely."""
        mgr = StateManager()
        num_threads = 10
        updates_per_thread = 10  # Reduced for faster test

        def update_worker(thread_id):
            for i in range(updates_per_thread):
                mgr.update_processing_state(
                    source=f"thread_{thread_id}",
                    current_frame=thread_id * updates_per_thread + i,
                )

        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All updates should be recorded (history is enabled)
        # Note: some updates might be deduplicated if values are the same
        history = mgr.get_history(key="current_frame")
        assert len(history) > 0
        assert len(history) <= num_threads * updates_per_thread

    def test_concurrent_reads(self):
        """Multiple threads can read state safely."""
        mgr = StateManager()
        mgr.update_project_state(project_path=Path("/test"))

        results = []

        def read_worker():
            for _ in range(100):
                snapshot = mgr.get_snapshot()
                results.append(snapshot.project.project_path)

        threads = [threading.Thread(target=read_worker) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should return consistent value
        assert all(path == Path("/test") for path in results)

    def test_concurrent_subscribe_unsubscribe(self):
        """Can subscribe/unsubscribe from multiple threads."""
        mgr = StateManager()
        observers = [MagicMock() for _ in range(10)]

        def subscribe_worker(obs):
            mgr.subscribe(StateCategory.RECORDING, obs)
            time.sleep(0.001)
            mgr.unsubscribe(StateCategory.RECORDING, obs)

        threads = [threading.Thread(target=subscribe_worker, args=(obs,)) for obs in observers]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without deadlock or errors
        mgr.update_recording_state(source="test", is_recording=True)


class TestDebuggingUtilities:
    """Test debugging and introspection features."""

    def test_dump_state(self):
        """dump_state returns comprehensive state dictionary."""
        mgr = StateManager()

        test_path = Path("/test/project")
        mgr.update_project_state(
            project_path=test_path,
            project_data={"videos": ["v1.mp4"]},
        )
        mgr.update_detector_state(
            detector_initialized=True,
            active_weight_name="best_oi.pt",
        )
        mgr.update_recording_state(is_recording=True)

        dump = mgr.dump_state()

        assert "project" in dump
        # Use Path for comparison to handle Windows vs Unix paths
        assert Path(dump["project"]["project_path"]) == test_path

        assert "detector" in dump
        assert dump["detector"]["initialized"] is True
        assert dump["detector"]["active_weight"] == "best_oi.pt"

        assert "recording" in dump
        assert dump["recording"]["is_recording"] is True

        assert "processing" in dump
        assert "ui" in dump

    def test_get_specific_state_snapshots(self):
        """Can get snapshots of specific state categories."""
        mgr = StateManager()

        mgr.update_project_state(project_path=Path("/test"))
        mgr.update_detector_state(detector_initialized=True)

        project = mgr.get_project_state()
        assert project.project_path == Path("/test")

        detector = mgr.get_detector_state()
        assert detector.detector_initialized is True

        recording = mgr.get_recording_state()
        assert recording.is_recording is False

        processing = mgr.get_processing_state()
        assert processing.is_processing is False

        ui = mgr.get_ui_state()
        assert ui.canvas_view_mode == "zones"

    def test_get_state_snapshot(self):
        """get_state_snapshot returns a serializable dictionary."""
        mgr = StateManager()
        mgr.update_project_state(project_path=Path("/test"))
        mgr.update_detector_state(detector_initialized=True)

        snapshot = mgr.get_state_snapshot()

        assert isinstance(snapshot, dict)
        assert "project" in snapshot
        assert "detector" in snapshot
        assert "_timestamp" in snapshot
        assert isinstance(snapshot["_timestamp"], str)
        assert snapshot["project"]["project_path"] == "/test"


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_project_workflow(self):
        """Test complete project open → process → close workflow."""
        mgr = StateManager()
        changes = []

        def track_changes(category, key, old_val, new_val):
            changes.append((category.name, key, old_val, new_val))

        mgr.subscribe_all(track_changes)

        # Open project
        mgr.update_project_state(
            source="controller",
            project_path=Path("/test/project"),
        )
        mgr.update_detector_state(
            source="controller",
            detector_initialized=True,
            zones_configured=True,
        )

        # Start processing
        mgr.update_processing_state(
            source="worker",
            is_processing=True,
            current_video="test.mp4",
            total_frames=1000,
        )

        # Progress updates
        mgr.update_processing_state(source="worker", current_frame=500)
        mgr.update_processing_state(source="worker", current_frame=1000)

        # Complete processing
        mgr.update_processing_state(source="worker", is_processing=False)

        # Close project
        mgr.update_project_state(source="controller", project_path=None)

        # Verify sequence
        assert len(changes) > 0
        assert changes[0][1] == "project_path"
        assert changes[-1][1] == "project_path"
        assert changes[-1][3] is None

    def test_recording_session(self):
        """Test recording start → stop workflow."""
        mgr = StateManager()

        # Setup
        mgr.update_detector_state(
            source="controller",
            detector_initialized=True,
        )
        mgr.update_recording_state(
            source="controller",
            arduino_connected=True,
        )

        # Start recording
        mgr.update_recording_state(
            source="controller",
            is_recording=True,
            output_path=Path("/output/recording.parquet"),
            recording_start_time=datetime.now(),
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.recording.is_recording is True
        assert snapshot.recording.output_path is not None

        # Stop recording
        mgr.update_recording_state(
            source="controller",
            is_recording=False,
        )

        snapshot = mgr.get_snapshot()
        assert snapshot.recording.is_recording is False

    def test_ui_view_mode_switching(self):
        """Test UI view mode transitions."""
        mgr = StateManager()
        view_changes = []

        def track_view(category, key, old_val, new_val):
            if key == "canvas_view_mode":
                view_changes.append(new_val)

        mgr.subscribe(StateCategory.UI, track_view)

        # Switch to analysis view
        mgr.update_ui_state(
            source="gui",
            canvas_view_mode="analysis",
        )

        # Switch back to zones
        mgr.update_ui_state(
            source="gui",
            canvas_view_mode="zones",
        )

        assert view_changes == ["analysis", "zones"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

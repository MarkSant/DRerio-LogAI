"""
Extended unit tests for StateManager immutable snapshots and category updates.
"""

from __future__ import annotations

from pathlib import Path

from zebtrack.core.state_manager import (
    DetectorState,
    ProcessingState,
    ProjectState,
    RecordingState,
    StateCategory,
    StateManager,
    UIState,
)


class TestStateManagerExtended:
    """Test StateManager get/update methods across all state categories."""

    def test_initial_state_categories_typed_accessors(self):
        sm = StateManager()
        # Use typed getters - get_state() returns a dict snapshot, not dataclass
        assert isinstance(sm.get_project_state(), ProjectState)
        assert isinstance(sm.get_detector_state(), DetectorState)
        assert isinstance(sm.get_recording_state(), RecordingState)
        assert isinstance(sm.get_processing_state(), ProcessingState)
        assert isinstance(sm.get_ui_state(), UIState)

    def test_get_state_returns_dict_snapshot(self):
        sm = StateManager()
        snap = sm.get_state(StateCategory.PROJECT)
        assert isinstance(snap, dict)
        assert "is_loaded" in snap

    def test_update_project_state(self):
        sm = StateManager(enable_history=True)
        sm.update_project_state(is_loaded=True, project_path=Path("/path/to/proj"))
        proj_state = sm.get_project_state()
        assert proj_state.is_loaded is True
        assert proj_state.project_path == Path("/path/to/proj")

        history = sm.get_history(StateCategory.PROJECT)
        assert len(history) >= 1

    def test_update_detector_state(self):
        sm = StateManager()
        sm.update_detector_state(detector_initialized=True, animal_method="seg")
        det_state = sm.get_detector_state()
        assert det_state.detector_initialized is True
        assert det_state.animal_method == "seg"

    def test_update_recording_state(self):
        sm = StateManager()
        sm.update_recording_state(is_recording=True, arduino_connected=True)
        rec_state = sm.get_recording_state()
        assert rec_state.is_recording is True
        assert rec_state.arduino_connected is True

    def test_update_processing_state(self):
        sm = StateManager()
        sm.update_processing_state(is_processing=True, current_frame=150, total_frames=300)
        proc_state = sm.get_processing_state()
        assert proc_state.is_processing is True
        assert proc_state.current_frame == 150
        assert proc_state.total_frames == 300

    def test_update_ui_state(self):
        sm = StateManager()
        sm.update_ui_state(canvas_view_mode="analysis", current_tab="reports")
        ui_state = sm.get_ui_state()
        assert ui_state.canvas_view_mode == "analysis"
        assert ui_state.current_tab == "reports"

    def test_subscribe_and_unsubscribe_observer(self):
        sm = StateManager()
        received_changes = []

        def observer(category, key, old_val, new_val):
            received_changes.append((category, key, new_val))

        sm.subscribe(StateCategory.UI, observer)
        sm.update_ui_state(canvas_view_mode="analysis")

        # Check synchronous or queued delivery
        sm.unsubscribe(StateCategory.UI, observer)

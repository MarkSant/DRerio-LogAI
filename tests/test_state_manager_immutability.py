"""
Tests for StateManager immutability.

This module verifies that state retrieved from the StateManager is a deep
copy and that modifying it does not affect the internal state.
"""

from unittest.mock import MagicMock

import pytest

from zebtrack.core.state_manager import StateCategory, StateManager


@pytest.fixture
def state_manager() -> StateManager:
    """Fixture for a clean StateManager instance."""
    return StateManager()


def test_get_project_state_is_immutable(state_manager: StateManager):
    """Verify that modifying the project state object doesn't affect the internal state."""
    # Arrange
    state_manager.update_project_state(
        source="test",
        project_data={"videos": ["v1.mp4"]},
    )
    project_state = state_manager.get_project_state()
    assert project_state.project_data is not None
    observer = MagicMock()
    state_manager.subscribe(StateCategory.PROJECT, observer)

    # Act
    project_state.project_data["videos"].append("v2.mp4")

    # Assert
    current_project_state = state_manager.get_project_state()
    assert current_project_state.project_data is not None
    assert current_project_state.project_data["videos"] == ["v1.mp4"]
    observer.assert_not_called()


def test_get_detector_state_is_immutable(state_manager: StateManager):
    """Verify that modifying the detector state object doesn't affect the internal state."""
    # Arrange
    state_manager.update_detector_state(
        source="test",
        zone_data={"polygons": [[0, 0]]},
    )
    detector_state = state_manager.get_detector_state()
    assert detector_state.zone_data is not None
    observer = MagicMock()
    state_manager.subscribe(StateCategory.DETECTOR, observer)

    # Act
    detector_state.zone_data["polygons"].append([1, 1])

    # Assert
    current_detector_state = state_manager.get_detector_state()
    assert current_detector_state.zone_data is not None
    assert current_detector_state.zone_data["polygons"] == [[0, 0]]
    observer.assert_not_called()


def test_get_ui_state_is_immutable(state_manager: StateManager):
    """Verify that modifying the UI state object doesn't affect the internal state."""
    # Arrange
    state_manager.update_ui_state(
        source="test",
        selected_videos=["v1.mp4"],
    )
    ui_state = state_manager.get_ui_state()
    assert ui_state.selected_videos is not None
    observer = MagicMock()
    state_manager.subscribe(StateCategory.UI, observer)

    # Act
    ui_state.selected_videos.append("v2.mp4")

    # Assert
    current_ui_state = state_manager.get_ui_state()
    assert current_ui_state.selected_videos is not None
    assert current_ui_state.selected_videos == ["v1.mp4"]
    observer.assert_not_called()


def test_get_snapshot_is_immutable(state_manager: StateManager):
    """Verify that modifying the full snapshot object doesn't affect the internal state."""
    # Arrange
    state_manager.update_project_state(
        source="test",
        project_data={"videos": ["v1.mp4"]},
    )
    snapshot = state_manager.get_snapshot()
    assert snapshot.project.project_data is not None
    observer = MagicMock()
    state_manager.subscribe(StateCategory.PROJECT, observer)

    # Act
    snapshot.project.project_data["videos"].append("v2.mp4")

    # Assert
    current_snapshot = state_manager.get_snapshot()
    assert current_snapshot.project.project_data is not None
    assert current_snapshot.project.project_data["videos"] == ["v1.mp4"]
    observer.assert_not_called()

"""Unit tests for UICoordinator (Event-Driven Architecture v4.0).

Tests the Mediator pattern implementation that coordinates UI component
communication via EventBusV2.
"""

from unittest.mock import Mock, call

import numpy as np
import pytest

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents
from zebtrack.ui.ui_coordinator import UICoordinator


@pytest.fixture
def event_bus():
    """Fixture providing a fresh EventBusV2 instance."""
    return EventBusV2()


@pytest.fixture
def canvas_manager_mock():
    """Fixture providing a mock CanvasManager."""
    mock = Mock()
    mock.update_zone_listbox = Mock()
    mock.load_video_frame = Mock()
    mock.setup_interactive_polygon = Mock()
    return mock


@pytest.fixture
def validation_manager_mock():
    """Fixture providing a mock ValidationManager."""
    mock = Mock()
    mock.validate_zones = Mock()
    mock.has_zones = Mock(return_value=False)
    return mock


@pytest.fixture
def project_view_manager_mock():
    """Fixture providing a mock ProjectViewManager."""
    mock = Mock()
    mock.refresh_if_needed = Mock()
    mock._populate_video_selector_tree = Mock()
    mock.apply_pending_readiness_snapshot = Mock()
    mock._build_video_hierarchy_snapshot = Mock()
    mock.refresh_project_views = Mock()
    return mock


@pytest.fixture
def dialog_manager_mock():
    """Fixture providing a mock DialogManager."""
    mock = Mock()
    mock.offer_zone_reuse = Mock()
    return mock


@pytest.fixture
def root_mock():
    """Fixture providing a mock Tkinter root."""
    mock = Mock()
    mock.after = Mock(side_effect=lambda delay, func: func())  # Execute immediately in tests
    return mock


@pytest.fixture
def ui_coordinator(
    event_bus,
    canvas_manager_mock,
    validation_manager_mock,
    project_view_manager_mock,
    dialog_manager_mock,
    root_mock,
):
    """Fixture providing a fully configured UICoordinator."""
    return UICoordinator(
        event_bus,
        canvas_manager=canvas_manager_mock,
        validation_manager=validation_manager_mock,
        project_view_manager=project_view_manager_mock,
        dialog_manager=dialog_manager_mock,
        root=root_mock,
    )


# ===========================
# Initialization Tests
# ===========================


def test_ui_coordinator_initialization(ui_coordinator, event_bus):
    """Test UICoordinator initializes correctly."""
    assert ui_coordinator.event_bus is event_bus
    assert ui_coordinator.canvas_manager is not None
    assert ui_coordinator.validation_manager is not None
    assert ui_coordinator.project_view_manager is not None
    assert ui_coordinator.dialog_manager is not None
    assert ui_coordinator._events_handled == 0
    assert ui_coordinator._errors_count == 0


def test_ui_coordinator_subscriptions_setup(ui_coordinator, event_bus):
    """Test that UICoordinator sets up all subscriptions."""
    # Verify subscriptions were created (internal state check)
    # EventBusV2 stores subscribers in _subscribers dict
    assert UIEvents.ZONES_UPDATED in event_bus._subscribers
    assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in event_bus._subscribers
    assert UIEvents.READINESS_SNAPSHOT_UPDATED in event_bus._subscribers
    assert UIEvents.POLYGON_EDIT_REQUESTED in event_bus._subscribers
    assert UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED in event_bus._subscribers
    assert UIEvents.VIDEO_LOADED in event_bus._subscribers
    assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_bus._subscribers
    assert UIEvents.ANALYSIS_STARTED in event_bus._subscribers
    assert UIEvents.ANALYSIS_COMPLETED in event_bus._subscribers
    assert UIEvents.PROCESSING_STATS_UPDATED in event_bus._subscribers


# ===========================
# Workflow Tests
# ===========================


def test_workflow_1_zones_updated(ui_coordinator, event_bus, canvas_manager_mock, validation_manager_mock, project_view_manager_mock):
    """Test Workflow 1: ZONES_UPDATED event coordination."""
    # Arrange
    zone_data = Mock()
    zone_data.polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]

    # Act
    event_bus.publish(
        Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": zone_data}, source="DialogManager")
    )

    # Assert
    canvas_manager_mock.update_zone_listbox.assert_called_once_with(zone_data)
    validation_manager_mock.validate_zones.assert_called_once()
    project_view_manager_mock.refresh_if_needed.assert_called_once_with(reason="zones_updated")
    assert ui_coordinator._events_handled == 1


def test_workflow_1_zones_updated_no_zone_data(ui_coordinator, event_bus, canvas_manager_mock):
    """Test ZONES_UPDATED with None zone_data."""
    # Act
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": None}))

    # Assert
    canvas_manager_mock.update_zone_listbox.assert_called_once_with(None)
    assert ui_coordinator._events_handled == 1


def test_workflow_2_video_tree_refresh_requested(ui_coordinator, event_bus, project_view_manager_mock):
    """Test Workflow 2: VIDEO_TREE_REFRESH_REQUESTED event coordination."""
    # Arrange
    filter_text = "test_filter"

    # Act
    event_bus.publish(
        Event(
            type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
            data={"filter_text": filter_text},
            source="ZoneControlBuilder",
        )
    )

    # Assert
    project_view_manager_mock._populate_video_selector_tree.assert_called_once_with(filter_text)
    assert ui_coordinator._events_handled == 1


def test_workflow_2_video_tree_refresh_no_filter(ui_coordinator, event_bus, project_view_manager_mock):
    """Test VIDEO_TREE_REFRESH_REQUESTED with no filter."""
    # Act
    event_bus.publish(
        Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": None})
    )

    # Assert
    project_view_manager_mock._populate_video_selector_tree.assert_called_once_with(None)


def test_workflow_3_readiness_snapshot_updated(ui_coordinator, event_bus, project_view_manager_mock):
    """Test Workflow 3: READINESS_SNAPSHOT_UPDATED event coordination."""
    # Arrange
    snapshot_data = {
        "ready_with_trajectory": [{"video": "test1.mp4"}],
        "ready_with_zones": [{"video": "test2.mp4"}],
        "arena_only": [{"video": "test3.mp4"}],
        "without_arena": [{"video": "test4.mp4"}],
    }

    # Act
    event_bus.publish(
        Event(type=UIEvents.READINESS_SNAPSHOT_UPDATED, data=snapshot_data, source="DialogManager")
    )

    # Assert
    project_view_manager_mock.apply_pending_readiness_snapshot.assert_called_once_with(
        ready_with_trajectory=snapshot_data["ready_with_trajectory"],
        ready_with_zones=snapshot_data["ready_with_zones"],
        arena_only=snapshot_data["arena_only"],
        without_arena=snapshot_data["without_arena"],
    )
    assert ui_coordinator._events_handled == 1


def test_workflow_3_readiness_snapshot_empty_data(ui_coordinator, event_bus, project_view_manager_mock):
    """Test READINESS_SNAPSHOT_UPDATED with empty data."""
    # Act
    event_bus.publish(Event(type=UIEvents.READINESS_SNAPSHOT_UPDATED, data={}))

    # Assert - should handle missing keys gracefully with defaults
    project_view_manager_mock.apply_pending_readiness_snapshot.assert_called_once_with(
        ready_with_trajectory=[],
        ready_with_zones=[],
        arena_only=[],
        without_arena=[],
    )


def test_workflow_4_polygon_edit_requested(ui_coordinator, event_bus, canvas_manager_mock):
    """Test Workflow 4: POLYGON_EDIT_REQUESTED event coordination."""
    # Arrange
    polygon = np.array([[100, 100], [200, 100], [200, 200], [100, 200]])

    # Act
    event_bus.publish(
        Event(
            type=UIEvents.POLYGON_EDIT_REQUESTED,
            data={"polygon": polygon},
            source="CanvasManager",
        )
    )

    # Assert
    canvas_manager_mock.setup_interactive_polygon.assert_called_once()
    # Verify the polygon was passed (numpy array comparison)
    call_args = canvas_manager_mock.setup_interactive_polygon.call_args[0][0]
    np.testing.assert_array_equal(call_args, polygon)
    assert ui_coordinator._events_handled == 1


def test_workflow_4_polygon_edit_no_polygon(ui_coordinator, event_bus, canvas_manager_mock):
    """Test POLYGON_EDIT_REQUESTED with None polygon (should not call setup)."""
    # Act
    event_bus.publish(Event(type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": None}))

    # Assert - should not call setup if polygon is None
    canvas_manager_mock.setup_interactive_polygon.assert_not_called()


def test_workflow_5_video_hierarchy_snapshot_requested(ui_coordinator, event_bus, project_view_manager_mock):
    """Test Workflow 5: VIDEO_HIERARCHY_SNAPSHOT_REQUESTED event coordination."""
    # Act
    event_bus.publish(Event(type=UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED, data={}))

    # Assert
    project_view_manager_mock._build_video_hierarchy_snapshot.assert_called_once()
    assert ui_coordinator._events_handled == 1


def test_workflow_6_video_loaded(ui_coordinator, event_bus, canvas_manager_mock, dialog_manager_mock, validation_manager_mock):
    """Test Workflow 6: VIDEO_LOADED event coordination."""
    # Arrange
    video_path = "/path/to/video.mp4"
    validation_manager_mock.has_zones.return_value = False  # No zones exist

    # Act
    event_bus.publish(
        Event(type=UIEvents.VIDEO_LOADED, data={"video_path": video_path}, source="CanvasManager")
    )

    # Assert
    canvas_manager_mock.load_video_frame.assert_called_once_with(video_path)
    validation_manager_mock.has_zones.assert_called_once_with(video_path)
    dialog_manager_mock.offer_zone_reuse.assert_called_once_with(video_path)
    assert ui_coordinator._events_handled == 1


def test_workflow_6_video_loaded_has_zones(ui_coordinator, event_bus, canvas_manager_mock, dialog_manager_mock, validation_manager_mock):
    """Test VIDEO_LOADED when video already has zones (should not offer reuse)."""
    # Arrange
    video_path = "/path/to/video.mp4"
    validation_manager_mock.has_zones.return_value = True  # Zones exist

    # Act
    event_bus.publish(Event(type=UIEvents.VIDEO_LOADED, data={"video_path": video_path}))

    # Assert
    canvas_manager_mock.load_video_frame.assert_called_once_with(video_path)
    dialog_manager_mock.offer_zone_reuse.assert_not_called()  # Should not offer reuse


def test_workflow_7_project_views_refresh_requested(ui_coordinator, event_bus, project_view_manager_mock):
    """Test Workflow 7: PROJECT_VIEWS_REFRESH_REQUESTED event coordination."""
    # Arrange
    data = {"reason": "zones_changed", "append_summary": True, "immediate": False}

    # Act
    event_bus.publish(Event(type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED, data=data))

    # Assert
    project_view_manager_mock.refresh_project_views.assert_called_once_with(
        reason="zones_changed", append_summary=True, immediate=False
    )
    assert ui_coordinator._events_handled == 1


def test_workflow_7_project_views_refresh_defaults(ui_coordinator, event_bus, project_view_manager_mock):
    """Test PROJECT_VIEWS_REFRESH_REQUESTED with default values."""
    # Act
    event_bus.publish(Event(type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED, data={}))

    # Assert
    project_view_manager_mock.refresh_project_views.assert_called_once_with(
        reason=None, append_summary=False, immediate=False
    )


def test_workflow_8_analysis_started(ui_coordinator, event_bus):
    """Test Workflow 8: ANALYSIS_STARTED event coordination."""
    # Arrange
    data = {"video_path": "/path/to/video.mp4", "analysis_type": "tracking"}

    # Act
    event_bus.publish(Event(type=UIEvents.ANALYSIS_STARTED, data=data))

    # Assert - Currently a placeholder, just verify no error and event counted
    assert ui_coordinator._events_handled == 1
    assert ui_coordinator._errors_count == 0


def test_workflow_9_analysis_completed(ui_coordinator, event_bus):
    """Test Workflow 9: ANALYSIS_COMPLETED event coordination."""
    # Arrange
    data = {"video_path": "/path/to/video.mp4", "success": True, "error": None}

    # Act
    event_bus.publish(Event(type=UIEvents.ANALYSIS_COMPLETED, data=data))

    # Assert - Currently a placeholder
    assert ui_coordinator._events_handled == 1
    assert ui_coordinator._errors_count == 0


def test_workflow_10_processing_stats_updated(ui_coordinator, event_bus):
    """Test Workflow 10: PROCESSING_STATS_UPDATED event coordination."""
    # Arrange
    data = {
        "processed_frames": 100,
        "total_frames": 1000,
        "detected_frames": 95,
        "start_time": 12345.67,
    }

    # Act
    event_bus.publish(Event(type=UIEvents.PROCESSING_STATS_UPDATED, data=data))

    # Assert - Currently a placeholder
    assert ui_coordinator._events_handled == 1
    assert ui_coordinator._errors_count == 0


# ===========================
# Error Handling Tests
# ===========================


def test_error_handling_zones_updated(ui_coordinator, event_bus, canvas_manager_mock):
    """Test error handling when canvas_manager raises exception."""
    # Arrange
    canvas_manager_mock.update_zone_listbox.side_effect = ValueError("Canvas error")

    # Act
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))

    # Assert - Error should be caught and logged, not propagate
    assert ui_coordinator._events_handled == 1
    assert ui_coordinator._errors_count == 1


def test_error_handling_video_tree_refresh(ui_coordinator, event_bus, project_view_manager_mock):
    """Test error handling when project_view_manager raises exception."""
    # Arrange
    project_view_manager_mock._populate_video_selector_tree.side_effect = RuntimeError(
        "Tree error"
    )

    # Act
    event_bus.publish(Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": "test"}))

    # Assert
    assert ui_coordinator._events_handled == 1
    assert ui_coordinator._errors_count == 1


def test_error_handling_multiple_workflows(ui_coordinator, event_bus, canvas_manager_mock, project_view_manager_mock):
    """Test error counting across multiple workflows."""
    # Arrange
    canvas_manager_mock.update_zone_listbox.side_effect = ValueError("Error 1")
    project_view_manager_mock._populate_video_selector_tree.side_effect = ValueError("Error 2")

    # Act
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))
    event_bus.publish(Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": "test"}))

    # Assert
    assert ui_coordinator._events_handled == 2
    assert ui_coordinator._errors_count == 2


# ===========================
# Helper Method Tests
# ===========================


def test_safe_ui_call_with_root(root_mock):
    """Test _safe_ui_call schedules on main thread when root is available."""
    # Arrange
    event_bus = EventBusV2()
    coordinator = UICoordinator(event_bus, root=root_mock)
    callback = Mock()

    # Act
    coordinator._safe_ui_call(callback)

    # Assert
    root_mock.after.assert_called_once()
    callback.assert_called_once()  # Mock after executes immediately


def test_safe_ui_call_without_root():
    """Test _safe_ui_call executes directly when root is not available."""
    # Arrange
    event_bus = EventBusV2()
    coordinator = UICoordinator(event_bus, root=None)
    callback = Mock()

    # Act
    coordinator._safe_ui_call(callback)

    # Assert
    callback.assert_called_once()


# ===========================
# Statistics Tests
# ===========================


def test_get_statistics(ui_coordinator, event_bus):
    """Test get_statistics returns correct counts."""
    # Act - Trigger some events
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))
    event_bus.publish(Event(type=UIEvents.VIDEO_LOADED, data={"video_path": "/test.mp4"}))

    # Get statistics
    stats = ui_coordinator.get_statistics()

    # Assert
    assert stats["events_handled"] == 2
    assert stats["errors_count"] == 0


def test_reset_statistics(ui_coordinator, event_bus):
    """Test reset_statistics clears counts."""
    # Arrange - Trigger some events
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))
    assert ui_coordinator._events_handled == 1

    # Act
    ui_coordinator.reset_statistics()

    # Assert
    stats = ui_coordinator.get_statistics()
    assert stats["events_handled"] == 0
    assert stats["errors_count"] == 0


# ===========================
# Integration Tests
# ===========================


def test_multiple_events_in_sequence(ui_coordinator, event_bus, canvas_manager_mock, project_view_manager_mock):
    """Test handling multiple different events in sequence."""
    # Act
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))
    event_bus.publish(Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": "test"}))
    event_bus.publish(Event(type=UIEvents.ANALYSIS_STARTED, data={"video_path": "/test.mp4"}))

    # Assert
    assert ui_coordinator._events_handled == 3
    assert ui_coordinator._errors_count == 0
    canvas_manager_mock.update_zone_listbox.assert_called_once()
    project_view_manager_mock._populate_video_selector_tree.assert_called_once()


def test_coordinator_without_optional_components():
    """Test UICoordinator works with None components (graceful degradation)."""
    # Arrange
    event_bus = EventBusV2()
    coordinator = UICoordinator(
        event_bus,
        canvas_manager=None,
        validation_manager=None,
        project_view_manager=None,
        dialog_manager=None,
        root=None,
    )

    # Act - Publish events (should not crash)
    event_bus.publish(Event(type=UIEvents.ZONES_UPDATED, data={"zone_data": Mock()}))
    event_bus.publish(Event(type=UIEvents.VIDEO_LOADED, data={"video_path": "/test.mp4"}))

    # Assert - Events handled but no operations performed
    assert coordinator._events_handled == 2
    assert coordinator._errors_count == 0

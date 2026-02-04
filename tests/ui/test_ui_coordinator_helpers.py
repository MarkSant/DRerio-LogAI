"""Tests for UICoordinator helper behaviors."""

from unittest.mock import MagicMock

from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.ui.ui_coordinator import UICoordinator


def test_safe_ui_call_uses_root_after():
    event_bus = MagicMock()
    root = MagicMock()
    func = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, root=root)

    coordinator._safe_ui_call(func)

    root.after.assert_called_once_with(0, func)
    func.assert_not_called()


def test_safe_ui_call_without_root_calls_directly():
    event_bus = MagicMock()
    func = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, root=None)

    coordinator._safe_ui_call(func)

    func.assert_called_once()


def test_get_statistics_returns_counts():
    event_bus = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus)

    coordinator._events_handled = 5
    coordinator._errors_count = 2

    assert coordinator.get_statistics() == {"events_handled": 5, "errors_count": 2}


def test_setup_subscriptions_registers_key_events():
    event_bus = MagicMock()

    UICoordinator(event_bus=event_bus)

    subscribed_events = [call.args[0] for call in event_bus.subscribe.call_args_list]
    assert UIEvents.ZONES_UPDATED in subscribed_events
    assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in subscribed_events
    assert UIEvents.ANALYSIS_TASK_STATUS_UPDATED in subscribed_events
    assert UIEvents.ZONE_DISPLAY_CLEARED in subscribed_events


def test_on_video_tree_refresh_requests_population():
    event_bus = MagicMock()
    project_view_manager = MagicMock()

    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    coordinator._on_video_tree_refresh_requested({"filter_text": "fish"})

    project_view_manager._populate_video_selector_tree.assert_called_once_with("fish")


def test_on_readiness_snapshot_updated_applies_snapshot():
    event_bus = MagicMock()
    project_view_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    payload = {
        "ready_with_trajectory": [{"path": "a"}],
        "ready_with_zones": [{"path": "b"}],
        "arena_only": [{"path": "c"}],
        "without_arena": [{"path": "d"}],
    }

    coordinator._on_readiness_snapshot_updated(payload)

    project_view_manager.apply_pending_readiness_snapshot.assert_called_once_with(**payload)


def test_on_project_views_refresh_requested_delegates():
    event_bus = MagicMock()
    project_view_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, project_view_manager=project_view_manager)

    coordinator._on_project_views_refresh_requested(
        {"reason": "zones", "append_summary": True, "immediate": True}
    )

    project_view_manager.refresh_project_views.assert_called_once_with(
        reason="zones", append_summary=True, immediate=True
    )


def test_on_processing_stats_updated_delegates():
    event_bus = MagicMock()
    state_synchronizer = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, state_synchronizer=state_synchronizer)

    coordinator._on_processing_stats_updated({"fps": 30})

    state_synchronizer.update_processing_stats.assert_called_once_with(fps=30)


def test_on_external_trigger_notice_calls_dialog():
    event_bus = MagicMock()
    dialog_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, dialog_manager=dialog_manager)

    coordinator._on_external_trigger_notice({"session_label": "S1", "source": "io"})

    dialog_manager.show_external_trigger_notice.assert_called_once_with(
        "S1", session_label="S1", source="io"
    )


def test_on_external_trigger_notice_cleared_calls_dialog():
    event_bus = MagicMock()
    dialog_manager = MagicMock()
    coordinator = UICoordinator(event_bus=event_bus, dialog_manager=dialog_manager)

    coordinator._on_external_trigger_notice_cleared({})

    dialog_manager.clear_external_trigger_notice.assert_called_once()

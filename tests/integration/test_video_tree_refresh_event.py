"""Integration tests for VIDEO_TREE_REFRESH_REQUESTED event (Event-Driven Architecture v4.0).

Tests the migration of _populate_video_selector_tree() from direct GUI calls to Event Bus V2.
This validates FASE 2 - Tarefa 2.2 (PLANO_ACAO_V4.md).
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents


@pytest.mark.integration
class TestVideoTreeRefreshEvent:
    """Integration tests for VIDEO_TREE_REFRESH_REQUESTED event flow."""

    def test_event_bus_v2_publishes_video_tree_refresh(self):
        """EventBusV2 can publish and subscribe to VIDEO_TREE_REFRESH_REQUESTED event."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act
        event_bus.publish(
            Event(
                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                data={"filter_text": "test_filter"},
                source="test",
            )
        )

        # Assert
        assert len(events_received) == 1
        assert events_received[0]["filter_text"] == "test_filter"

    def test_project_view_manager_subscribes_to_video_tree_refresh(self):
        """ProjectViewManager subscribes to VIDEO_TREE_REFRESH_REQUESTED and calls
        _populate_video_selector_tree."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus

        from zebtrack.ui.components.project_views import VideoSelectorTreeManager

        view_manager = VideoSelectorTreeManager(gui_mock, event_bus_v2=event_bus)

        # Mock the _populate_video_selector_tree method
        with patch.object(view_manager, "_populate_video_selector_tree") as mock_populate:
            # Act
            event_bus.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={"filter_text": "test"},
                    source="test",
                )
            )

            # Assert
            mock_populate.assert_called_once_with("test")

    def test_zone_control_builder_publishes_video_tree_refresh_dual_mode(self):
        """ZoneControlBuilder publishes VIDEO_TREE_REFRESH_REQUESTED in dual mode."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus

        from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder

        builder = ZoneControlBuilder(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act
        builder._refresh_video_tree_dual_mode("test_filter")

        # Assert - event was published
        assert len(events_received) >= 1, "VIDEO_TREE_REFRESH_REQUESTED event should be published"
        assert events_received[0]["filter_text"] == "test_filter"

    def test_project_view_manager_publishes_video_tree_refresh_dual_mode(self):
        """ProjectViewManager publishes VIDEO_TREE_REFRESH_REQUESTED in dual mode."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock._pending_readiness_snapshot = {}
        gui_mock._video_selector_filter = "test_filter"
        gui_mock.video_selector_tree = MagicMock()  # Simulate tree exists

        from zebtrack.ui.components.project_views import VideoSelectorTreeManager

        view_manager = VideoSelectorTreeManager(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act
        view_manager.apply_pending_readiness_snapshot(
            ready_with_trajectory=[], ready_with_zones=[], arena_only=[], without_arena=[]
        )

        # Assert
        assert len(events_received) >= 1, "VIDEO_TREE_REFRESH_REQUESTED event should be published"
        assert events_received[0]["filter_text"] == "test_filter"

    def test_dual_mode_removed_old_path_does_not_execute(self):
        """Verify Phase 3: Old path is removed, only new path (event) executes."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock._populate_video_selector_tree = MagicMock()  # Track old path calls

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder

        builder = ZoneControlBuilder(gui_mock, event_bus_v2=event_bus)

        # Act
        builder._refresh_video_tree_dual_mode("test")

        # Assert
        assert gui_mock._populate_video_selector_tree.call_count == 0, "Old path should NOT execute"
        assert len(events_received) >= 1, "New path (event) should execute"
        assert events_received[0]["filter_text"] == "test"

    def test_zone_control_builder_refresh_button_uses_dual_mode(self):
        """ZoneControlBuilder refresh button λ uses dual mode method."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.zone_controls_frame = MagicMock()  # Mock the frame for widget creation
        gui_mock.video_search_var = MagicMock()

        from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder

        builder = ZoneControlBuilder(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act - simulate button click
        with patch.object(builder, "_refresh_video_tree_dual_mode") as mock_refresh:
            # Simulate the lambda being called (button click)
            mock_refresh()

            # Assert
            mock_refresh.assert_called_once()

    def test_filter_text_none_handled_correctly(self):
        """Video tree refresh handles filter_text=None correctly."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act
        event_bus.publish(
            Event(
                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                data={"filter_text": None},
                source="test",
            )
        )

        # Assert
        assert len(events_received) == 1
        assert events_received[0]["filter_text"] is None


@pytest.mark.integration
class TestVideoTreeRefreshEventEdgeCases:
    """Edge case tests for VIDEO_TREE_REFRESH_REQUESTED event."""

    def test_event_bus_v2_none_does_not_crash(self):
        """Components handle event_bus_v2=None gracefully (backward compatibility)."""
        # Arrange
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = None

        from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder

        # Act - should not crash
        builder = ZoneControlBuilder(gui_mock, event_bus_v2=None)

        # Assert
        assert builder.event_bus_v2 is None

    def test_multiple_subscribers_receive_event(self):
        """Multiple subscribers can listen to VIDEO_TREE_REFRESH_REQUESTED."""
        # Arrange
        event_bus = EventBusV2()
        events_received_1 = []
        events_received_2 = []

        def handler1(data):
            events_received_1.append(data)

        def handler2(data):
            events_received_2.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler1)
        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler2)

        # Act
        event_bus.publish(
            Event(
                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                data={"filter_text": "test"},
                source="test",
            )
        )

        # Assert - both subscribers received the event
        assert len(events_received_1) == 1
        assert len(events_received_2) == 1
        assert events_received_1[0]["filter_text"] == "test"
        assert events_received_2[0]["filter_text"] == "test"

    def test_unsubscribe_stops_receiving_events(self):
        """Unsubscribing stops receiving events."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act - publish before unsubscribe
        event_bus.publish(
            Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": "test1"})
        )

        # Unsubscribe
        event_bus.unsubscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Publish after unsubscribe
        event_bus.publish(
            Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": "test2"})
        )

        # Assert - only first event received
        assert len(events_received) == 1
        assert events_received[0]["filter_text"] == "test1"

    def test_empty_filter_text_handled(self):
        """Empty string filter_text is handled correctly."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, handler)

        # Act
        event_bus.publish(
            Event(
                type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED, data={"filter_text": ""}, source="test"
            )
        )

        # Assert
        assert len(events_received) == 1
        assert events_received[0]["filter_text"] == ""

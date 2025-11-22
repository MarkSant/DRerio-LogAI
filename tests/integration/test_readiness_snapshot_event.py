"""Integration tests for READINESS_SNAPSHOT_UPDATED event (Event-Driven Architecture v4.0).

Tests the migration of apply_pending_readiness_snapshot() from direct GUI calls to Event Bus V2.
This validates FASE 2 - Tarefa 2.3 (PLANO_ACAO_V4.md).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents


@pytest.mark.integration
class TestReadinessSnapshotEvent:
    """Integration tests for READINESS_SNAPSHOT_UPDATED event flow."""

    def test_event_bus_v2_publishes_readiness_snapshot(self):
        """EventBusV2 can publish and subscribe to READINESS_SNAPSHOT_UPDATED event."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Act
        snapshot_data = {
            'ready_with_trajectory': [{'path': '/video1.mp4'}],
            'ready_with_zones': [{'path': '/video2.mp4'}],
            'arena_only': [{'path': '/video3.mp4'}],
            'without_arena': [{'path': '/video4.mp4'}]
        }
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data=snapshot_data,
            source='test'
        ))

        # Assert
        assert len(events_received) == 1
        assert events_received[0]['ready_with_trajectory'] == [{'path': '/video1.mp4'}]
        assert events_received[0]['ready_with_zones'] == [{'path': '/video2.mp4'}]
        assert events_received[0]['arena_only'] == [{'path': '/video3.mp4'}]
        assert events_received[0]['without_arena'] == [{'path': '/video4.mp4'}]

    def test_project_view_manager_subscribes_to_readiness_snapshot(self):
        """ProjectViewManager subscribes to READINESS_SNAPSHOT_UPDATED and calls apply_pending_readiness_snapshot."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus

        from zebtrack.ui.components.project_view_manager import ProjectViewManager

        view_manager = ProjectViewManager(gui_mock, event_bus_v2=event_bus)

        # Mock the apply_pending_readiness_snapshot method
        with patch.object(view_manager, 'apply_pending_readiness_snapshot') as mock_apply:
            # Act
            snapshot_data = {
                'ready_with_trajectory': [{'path': '/video1.mp4'}],
                'ready_with_zones': [{'path': '/video2.mp4'}],
                'arena_only': [],
                'without_arena': []
            }
            event_bus.publish(Event(
                type=UIEvents.READINESS_SNAPSHOT_UPDATED,
                data=snapshot_data,
                source='test'
            ))

            # Assert
            mock_apply.assert_called_once()
            call_args = mock_apply.call_args
            assert call_args.kwargs['ready_with_trajectory'] == [{'path': '/video1.mp4'}]
            assert call_args.kwargs['ready_with_zones'] == [{'path': '/video2.mp4'}]
            assert call_args.kwargs['arena_only'] == []
            assert call_args.kwargs['without_arena'] == []

    def test_dialog_manager_publishes_readiness_snapshot_dual_mode(self):
        """DialogManager publishes READINESS_SNAPSHOT_UPDATED in dual mode."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.root = MagicMock()
        gui_mock._build_video_hierarchy_snapshot = MagicMock(return_value=[])
        gui_mock.apply_pending_readiness_snapshot = MagicMock()  # Mock OLD PATH

        from zebtrack.ui.components.dialog_manager import DialogManager

        dialog_manager = DialogManager(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Mock PendingVideosDialog to avoid GUI creation
        with patch('zebtrack.ui.components.dialog_manager.PendingVideosDialog') as mock_dialog_class:
            mock_dialog = MagicMock()
            mock_dialog.result = None
            mock_dialog_class.return_value = mock_dialog

            # Act
            snapshot_lists = {
                'ready_with_trajectory': [{'path': '/video1.mp4'}],
                'ready_with_zones': [{'path': '/video2.mp4'}],
                'arena_only': [],
                'without_arena': [{'path': '/video4.mp4'}]
            }

            try:
                result = dialog_manager.ask_reuse_zones(**snapshot_lists)
            except Exception as e:
                # If method fails due to missing dependencies, that's OK - we're testing event publishing
                pass

        # Assert - event was published
        assert len(events_received) >= 1, "READINESS_SNAPSHOT_UPDATED event should be published"
        assert events_received[0]['ready_with_trajectory'] == [{'path': '/video1.mp4'}]
        assert events_received[0]['ready_with_zones'] == [{'path': '/video2.mp4'}]
        assert events_received[0]['without_arena'] == [{'path': '/video4.mp4'}]

    def test_dual_mode_both_paths_execute(self):
        """Dual mode: both old path (direct call) and new path (event) execute."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.apply_pending_readiness_snapshot = MagicMock()  # Track old path calls
        gui_mock.root = MagicMock()
        gui_mock._build_video_hierarchy_snapshot = MagicMock(return_value=[])

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        from zebtrack.ui.components.dialog_manager import DialogManager

        dialog_manager = DialogManager(gui_mock, event_bus_v2=event_bus)

        # Mock PendingVideosDialog
        with patch('zebtrack.ui.components.dialog_manager.PendingVideosDialog') as mock_dialog_class:
            mock_dialog = MagicMock()
            mock_dialog.result = {'selected_videos': []}
            mock_dialog_class.return_value = mock_dialog

            # Act
            snapshot_data = {
                'ready_with_trajectory': [{'path': '/video1.mp4'}],
                'ready_with_zones': [],
                'arena_only': [],
                'without_arena': []
            }
            dialog_manager.ask_reuse_zones(**snapshot_data)

        # Assert both paths executed
        assert gui_mock.apply_pending_readiness_snapshot.call_count >= 1, "Old path should execute"
        assert len(events_received) >= 1, "New path (event) should execute"

    def test_empty_lists_handled_correctly(self):
        """Readiness snapshot handles empty lists for all categories."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Act
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data={
                'ready_with_trajectory': [],
                'ready_with_zones': [],
                'arena_only': [],
                'without_arena': []
            },
            source='test'
        ))

        # Assert
        assert len(events_received) == 1
        assert events_received[0]['ready_with_trajectory'] == []
        assert events_received[0]['ready_with_zones'] == []
        assert events_received[0]['arena_only'] == []
        assert events_received[0]['without_arena'] == []

    def test_multiple_videos_in_each_category(self):
        """Readiness snapshot handles multiple videos in each category."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Act
        snapshot_data = {
            'ready_with_trajectory': [
                {'path': '/video1.mp4'},
                {'path': '/video2.mp4'}
            ],
            'ready_with_zones': [
                {'path': '/video3.mp4'},
                {'path': '/video4.mp4'},
                {'path': '/video5.mp4'}
            ],
            'arena_only': [
                {'path': '/video6.mp4'}
            ],
            'without_arena': [
                {'path': '/video7.mp4'},
                {'path': '/video8.mp4'},
                {'path': '/video9.mp4'},
                {'path': '/video10.mp4'}
            ]
        }
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data=snapshot_data,
            source='test'
        ))

        # Assert
        assert len(events_received) == 1
        assert len(events_received[0]['ready_with_trajectory']) == 2
        assert len(events_received[0]['ready_with_zones']) == 3
        assert len(events_received[0]['arena_only']) == 1
        assert len(events_received[0]['without_arena']) == 4


@pytest.mark.integration
class TestReadinessSnapshotEventEdgeCases:
    """Edge case tests for READINESS_SNAPSHOT_UPDATED event."""

    def test_event_bus_v2_none_does_not_crash(self):
        """Components handle event_bus_v2=None gracefully (backward compatibility)."""
        # Arrange
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = None

        from zebtrack.ui.components.dialog_manager import DialogManager

        # Act - should not crash
        dialog_manager = DialogManager(gui_mock, event_bus_v2=None)

        # Assert
        assert dialog_manager.event_bus_v2 is None

    def test_multiple_subscribers_receive_event(self):
        """Multiple subscribers can listen to READINESS_SNAPSHOT_UPDATED."""
        # Arrange
        event_bus = EventBusV2()
        events_received_1 = []
        events_received_2 = []

        def handler1(data):
            events_received_1.append(data)

        def handler2(data):
            events_received_2.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler1)
        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler2)

        # Act
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data={
                'ready_with_trajectory': [],
                'ready_with_zones': [],
                'arena_only': [],
                'without_arena': []
            },
            source='test'
        ))

        # Assert - both subscribers received the event
        assert len(events_received_1) == 1
        assert len(events_received_2) == 1

    def test_unsubscribe_stops_receiving_events(self):
        """Unsubscribing stops receiving events."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Act - publish before unsubscribe
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data={
                'ready_with_trajectory': [],
                'ready_with_zones': [],
                'arena_only': [],
                'without_arena': []
            }
        ))

        # Unsubscribe
        event_bus.unsubscribe(UIEvents.READINESS_SNAPSHOT_UPDATED, handler)

        # Publish after unsubscribe
        event_bus.publish(Event(
            type=UIEvents.READINESS_SNAPSHOT_UPDATED,
            data={
                'ready_with_trajectory': [{'path': '/video.mp4'}],
                'ready_with_zones': [],
                'arena_only': [],
                'without_arena': []
            }
        ))

        # Assert - only first event received
        assert len(events_received) == 1

    def test_event_with_missing_keys_uses_defaults(self):
        """Event handler uses empty list defaults when keys are missing."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus

        from zebtrack.ui.components.project_view_manager import ProjectViewManager

        view_manager = ProjectViewManager(gui_mock, event_bus_v2=event_bus)

        # Mock the apply_pending_readiness_snapshot method
        with patch.object(view_manager, 'apply_pending_readiness_snapshot') as mock_apply:
            # Act - publish event with missing keys
            event_bus.publish(Event(
                type=UIEvents.READINESS_SNAPSHOT_UPDATED,
                data={},  # Empty data - should use defaults
                source='test'
            ))

            # Assert - method called with default empty lists
            mock_apply.assert_called_once()
            call_args = mock_apply.call_args
            assert call_args.kwargs['ready_with_trajectory'] == []
            assert call_args.kwargs['ready_with_zones'] == []
            assert call_args.kwargs['arena_only'] == []
            assert call_args.kwargs['without_arena'] == []

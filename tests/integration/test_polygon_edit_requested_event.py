"""Integration tests for POLYGON_EDIT_REQUESTED event (Event-Driven Architecture v4.0).

Tests the migration of setup_interactive_polygon() from direct GUI calls to Event Bus V2.
This validates FASE 2 - Tarefa 2.4 (PLANO_ACAO_V4.md).

IMPORTANT: This migration also fixes a critical bug where the method setup_interactive_polygon()
was calling a non-existent method in EventDispatcher, making polygon editing non-functional.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents


@pytest.fixture(autouse=True)
def mock_tkinter_vars():
    """Mock tkinter variables to avoid root window requirement."""
    with patch("tkinter.StringVar") as mock_string_var:
        mock_var_instance = MagicMock()
        mock_var_instance.get.return_value = ""
        mock_string_var.return_value = mock_var_instance

        with patch("tkinter.BooleanVar"):
            with patch("tkinter.IntVar"):
                yield


@pytest.mark.integration
class TestPolygonEditRequestedEvent:
    """Integration tests for POLYGON_EDIT_REQUESTED event flow."""

    def test_event_bus_v2_publishes_polygon_edit_requested(self):
        """EventBusV2 can publish and subscribe to POLYGON_EDIT_REQUESTED event."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        # Act
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        event_bus.publish(
            Event(type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon}, source="test")
        )

        # Assert
        assert len(events_received) == 1
        assert np.array_equal(events_received[0]["polygon"], polygon)

    def test_canvas_manager_subscribes_to_polygon_edit_requested(self):
        """CanvasManager subscribes to POLYGON_EDIT_REQUESTED and sets up polygon editing."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.edited_polygon_points = []  # Start empty
        gui_mock.video_display = MagicMock()
        gui_mock.video_display.canvas = MagicMock()

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        # Mock the renderer.draw_interactive_polygon method
        with patch.object(canvas_manager.renderer, "draw_interactive_polygon") as mock_draw:
            # Act
            polygon = np.array([[10, 20], [30, 40], [50, 60]])
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon}, source="test"
                )
            )

            # Assert
            # 1. edited_polygon_points should be populated
            assert len(gui_mock.edited_polygon_points) == 3
            assert gui_mock.edited_polygon_points == [[10, 20], [30, 40], [50, 60]]

            # 2. draw_interactive_polygon should be called
            mock_draw.assert_called_once()

    def test_canvas_manager_publishes_polygon_edit_requested_dual_mode_arena(self):
        """CanvasManager publishes POLYGON_EDIT_REQUESTED in dual mode when editing arena."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.setup_interactive_polygon = MagicMock()  # Mock OLD PATH
        gui_mock.zone_controls = MagicMock()
        gui_mock.drawing_state_manager.mode = None  # Not in drawing mode

        # Mock zone data
        zone_data_mock = MagicMock()
        zone_data_mock.polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        gui_mock._get_zone_data_for_active_context = MagicMock(return_value=zone_data_mock)

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        # Mock zone listbox selection
        listbox_mock = MagicMock()
        item_mock = {"values": ["Arena Principal"]}
        listbox_mock.selection.return_value = ["item_1"]
        listbox_mock.item.return_value = item_mock
        gui_mock.zone_controls.zone_listbox = listbox_mock

        # Act
        canvas_manager.edit_selected_zone_vertices()

        # Assert - event was published
        assert len(events_received) >= 1, "POLYGON_EDIT_REQUESTED event should be published"
        assert events_received[0]["polygon"] is not None
        assert len(events_received[0]["polygon"]) == 4  # 4 vertices for arena

    def test_canvas_manager_publishes_polygon_edit_requested_dual_mode_roi(self):
        """CanvasManager publishes POLYGON_EDIT_REQUESTED in dual mode when editing ROI."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.setup_interactive_polygon = MagicMock()  # Mock OLD PATH
        gui_mock.zone_controls = MagicMock()
        gui_mock.drawing_state_manager.mode = None

        # Mock zone data with ROI
        zone_data_mock = MagicMock()
        zone_data_mock.polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        zone_data_mock.roi_names = ["ROI 1", "ROI 2"]
        zone_data_mock.roi_polygons = [
            [[10, 10], [20, 10], [20, 20], [10, 20]],
            [[30, 30], [40, 30], [40, 40], [30, 40]],
        ]
        gui_mock._get_zone_data_for_active_context = MagicMock(return_value=zone_data_mock)

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        # Mock zone listbox selection for ROI 1
        listbox_mock = MagicMock()
        item_mock = {"values": ["📍 ROI 1"]}
        listbox_mock.selection.return_value = ["item_1"]
        listbox_mock.item.return_value = item_mock
        gui_mock.zone_controls.zone_listbox = listbox_mock

        # Act
        canvas_manager.edit_selected_zone_vertices()

        # Assert - event was published
        assert len(events_received) >= 1, "POLYGON_EDIT_REQUESTED event should be published for ROI"
        assert events_received[0]["polygon"] is not None
        assert len(events_received[0]["polygon"]) == 4  # 4 vertices for ROI

    def test_dual_mode_removed_old_path_does_not_execute(self):
        """Verify Phase 3: Old path is removed, only new path (event) executes."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.setup_interactive_polygon = MagicMock()  # Track old path calls
        gui_mock.zone_controls = MagicMock()
        gui_mock.drawing_state_manager.mode = None

        zone_data_mock = MagicMock()
        zone_data_mock.polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        gui_mock._get_zone_data_for_active_context = MagicMock(return_value=zone_data_mock)

        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        listbox_mock = MagicMock()
        item_mock = {"values": ["Arena Principal"]}
        listbox_mock.selection.return_value = ["item_1"]
        listbox_mock.item.return_value = item_mock
        gui_mock.zone_controls.zone_listbox = listbox_mock

        # Act
        canvas_manager.edit_selected_zone_vertices()

        # Assert
        assert gui_mock.setup_interactive_polygon.call_count == 0, "Old path should NOT execute"
        assert len(events_received) >= 1, "New path (event) should execute"

    def test_polygon_with_different_shapes(self):
        """POLYGON_EDIT_REQUESTED handles polygons with different number of vertices."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.edited_polygon_points = []
        gui_mock.video_display = MagicMock()
        gui_mock.video_display.canvas = MagicMock()

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        with patch.object(canvas_manager.renderer, "draw_interactive_polygon"):
            # Test triangle (3 vertices)
            polygon_3 = np.array([[0, 0], [10, 0], [5, 10]])
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon_3}, source="test"
                )
            )
            assert len(gui_mock.edited_polygon_points) == 3

            # Test hexagon (6 vertices)
            polygon_6 = np.array([[0, 0], [10, 0], [15, 10], [10, 20], [0, 20], [-5, 10]])
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon_6}, source="test"
                )
            )
            assert len(gui_mock.edited_polygon_points) == 6

    def test_polygon_coordinates_preserved_correctly(self):
        """Polygon coordinates are preserved exactly when converting to list."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.edited_polygon_points = []
        gui_mock.video_display = MagicMock()
        gui_mock.video_display.canvas = MagicMock()

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        with patch.object(canvas_manager.renderer, "draw_interactive_polygon"):
            # Act
            polygon = np.array([[123.5, 456.7], [789.1, 234.5], [567.8, 901.2]])
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon}, source="test"
                )
            )

            # Assert - coordinates preserved with float precision
            assert gui_mock.edited_polygon_points[0] == [123.5, 456.7]
            assert gui_mock.edited_polygon_points[1] == [789.1, 234.5]
            assert gui_mock.edited_polygon_points[2] == [567.8, 901.2]


@pytest.mark.integration
class TestPolygonEditRequestedEventEdgeCases:
    """Edge case tests for POLYGON_EDIT_REQUESTED event."""

    def test_event_bus_v2_none_does_not_crash(self):
        """Components handle event_bus_v2=None gracefully (backward compatibility)."""
        # Arrange
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = None

        from zebtrack.ui.components.canvas_manager import CanvasManager

        # Act - should not crash
        canvas_manager = CanvasManager(gui_mock, event_bus_v2=None)

        # Assert
        assert canvas_manager.event_bus_v2 is None

    def test_multiple_subscribers_receive_event(self):
        """Multiple subscribers can listen to POLYGON_EDIT_REQUESTED."""
        # Arrange
        event_bus = EventBusV2()
        events_received_1 = []
        events_received_2 = []

        def handler1(data):
            events_received_1.append(data)

        def handler2(data):
            events_received_2.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler1)
        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler2)

        # Act
        polygon = np.array([[0, 0], [10, 10], [20, 0]])
        event_bus.publish(
            Event(type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon}, source="test")
        )

        # Assert - both subscribers received the event
        assert len(events_received_1) == 1
        assert len(events_received_2) == 1
        assert np.array_equal(events_received_1[0]["polygon"], polygon)
        assert np.array_equal(events_received_2[0]["polygon"], polygon)

    def test_unsubscribe_stops_receiving_events(self):
        """Unsubscribing stops receiving events."""
        # Arrange
        event_bus = EventBusV2()
        events_received = []

        def handler(data):
            events_received.append(data)

        event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        # Act - publish before unsubscribe
        polygon_1 = np.array([[0, 0], [10, 10]])
        event_bus.publish(Event(type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon_1}))

        # Unsubscribe
        event_bus.unsubscribe(UIEvents.POLYGON_EDIT_REQUESTED, handler)

        # Publish after unsubscribe
        polygon_2 = np.array([[20, 20], [30, 30]])
        event_bus.publish(Event(type=UIEvents.POLYGON_EDIT_REQUESTED, data={"polygon": polygon_2}))

        # Assert - only first event received
        assert len(events_received) == 1
        assert np.array_equal(events_received[0]["polygon"], polygon_1)

    def test_event_with_missing_polygon_uses_none(self):
        """Event handler handles missing polygon gracefully."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.edited_polygon_points = ["previous", "data"]  # Pre-existing data
        gui_mock.video_display = MagicMock()

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        with patch.object(canvas_manager.renderer, "draw_interactive_polygon") as mock_draw:
            # Act - publish event with missing polygon
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED,
                    data={},  # Empty data - no polygon key
                    source="test",
                )
            )

            # Assert - edited_polygon_points should NOT be modified (no polygon provided)
            assert gui_mock.edited_polygon_points == ["previous", "data"]
            # draw should NOT be called since polygon is missing
            mock_draw.assert_not_called()

    def test_polygon_as_list_of_lists_handled_correctly(self):
        """Event handler handles polygon as list of lists (not numpy array)."""
        # Arrange
        event_bus = EventBusV2()
        gui_mock = MagicMock()
        gui_mock.event_bus_v2 = event_bus
        gui_mock.edited_polygon_points = []
        gui_mock.video_display = MagicMock()
        gui_mock.video_display.canvas = MagicMock()

        from zebtrack.ui.components.canvas_manager import CanvasManager

        canvas_manager = CanvasManager(gui_mock, event_bus_v2=event_bus)

        with patch.object(canvas_manager.renderer, "draw_interactive_polygon") as mock_draw:
            # Act - polygon as list (not numpy array)
            polygon_list = [[0, 0], [100, 0], [100, 100], [0, 100]]
            event_bus.publish(
                Event(
                    type=UIEvents.POLYGON_EDIT_REQUESTED,
                    data={"polygon": polygon_list},
                    source="test",
                )
            )

            # Assert
            assert gui_mock.edited_polygon_points == polygon_list
            mock_draw.assert_called_once()

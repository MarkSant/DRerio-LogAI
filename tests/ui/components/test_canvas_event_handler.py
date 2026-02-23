"""Tests for CanvasEventHandler helpers."""

from types import SimpleNamespace
from unittest.mock import ANY, Mock

from zebtrack.ui.components.canvas.event_handler import CanvasEventHandler
from zebtrack.ui.event_bus_v2 import Event, UIEvents


def _make_handler():
    canvas = Mock()
    canvas.winfo_width.return_value = 800
    canvas.winfo_height.return_value = 600
    canvas.after.return_value = "debounce-id"

    drawing_state_manager = SimpleNamespace(
        mode="polygon",
        drawing_type="arena",
        current_points=[],
        canvas_points=[],
        video_points=[],
        vertex_hover_tolerance=5.0,
        dragging_vertex_index=None,
        has_points=Mock(return_value=False),
        add_point=Mock(),
        undo=Mock(return_value=True),
        redo=Mock(return_value=True),
        point_count=Mock(return_value=2),
    )

    zone_ctx = Mock()
    zone_ctx.get_zone_data_for_active_context.return_value = SimpleNamespace(polygon=[])

    dialog_mgr = Mock()

    gui = SimpleNamespace(
        video_display=SimpleNamespace(canvas=canvas),
        drawing_state_manager=drawing_state_manager,
        polygon_drawing_service=Mock(),
        set_status=Mock(),
        show_info=Mock(),
        show_error=Mock(),
        root=Mock(),
        _zone_context_service=zone_ctx,
        dialog_manager=dialog_mgr,
    )

    manager = SimpleNamespace(
        gui=gui,
        apply_snapping=Mock(return_value=None),
        _canvas_to_video=Mock(return_value=(10.0, 20.0)),
        _video_to_canvas=Mock(return_value=(10.0, 20.0)),
        renderer=SimpleNamespace(
            draw_interactive_polygon=Mock(),
            redraw_polygon_in_progress=Mock(),
        ),
        event_bus_v2=Mock(),
        stop_drawing=Mock(),
        _redraw_polygon_in_progress=Mock(),
        _check_prompt_second_aquarium=Mock(),
    )
    return CanvasEventHandler(manager)


def test_on_canvas_click_ignores_when_not_polygon():
    handler = _make_handler()
    handler.gui.drawing_state_manager.mode = "view"

    handler.on_canvas_click(SimpleNamespace(x=10, y=20))

    handler.gui.drawing_state_manager.add_point.assert_not_called()


def test_on_canvas_click_adds_point_and_draws_marker():
    handler = _make_handler()
    handler.gui.drawing_state_manager.has_points.return_value = False

    handler.on_canvas_click(SimpleNamespace(x=10, y=20))

    handler.gui.drawing_state_manager.add_point.assert_called_once_with(
        (10.0, 20.0), (10.0, 20.0), (10.0, 20.0)
    )
    handler.gui.video_display.canvas.create_oval.assert_called_once()


def test_on_canvas_click_hover_existing_vertex_starts_drag():
    handler = _make_handler()
    handler.gui.drawing_state_manager.current_points = [(10.0, 20.0)]
    handler.gui.drawing_state_manager.has_points.return_value = True

    handler.on_canvas_click(SimpleNamespace(x=12, y=21))

    assert handler.gui.drawing_state_manager.dragging_vertex_index == 0
    handler.gui.video_display.canvas.config.assert_called_once_with(cursor="hand2")
    handler.gui.drawing_state_manager.add_point.assert_not_called()


def test_on_canvas_double_click_success_publishes_and_stops():
    handler = _make_handler()
    handler.gui.drawing_state_manager.drawing_type = None
    handler.gui.drawing_state_manager.video_points = [(1, 2), (3, 4), (5, 6)]
    handler.gui.polygon_drawing_service.complete_polygon.return_value = True

    handler.on_canvas_double_click(SimpleNamespace(x=0, y=0))

    handler.gui.set_status.assert_called_once()
    handler.gui.dialog_manager.show_info.assert_called_once()
    handler.manager.event_bus_v2.publish.assert_called_once()
    published_event = handler.manager.event_bus_v2.publish.call_args.args[0]
    assert isinstance(published_event, Event)
    assert published_event.type == UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED
    handler.manager.stop_drawing.assert_called_once()
    handler.gui.root.after.assert_called_once_with(
        100,
        handler.manager._check_prompt_second_aquarium,
    )


def test_on_canvas_double_click_failure_reports_error():
    handler = _make_handler()
    handler.gui.drawing_state_manager.drawing_type = "roi"
    handler.gui.drawing_state_manager.video_points = [(1, 2), (3, 4)]
    handler.gui.polygon_drawing_service.complete_polygon.return_value = False

    handler.on_canvas_double_click(SimpleNamespace(x=0, y=0))

    handler.gui.dialog_manager.show_error.assert_called_once()
    handler.manager.stop_drawing.assert_called_once()


def test_on_drawing_undo_updates_status_and_redraws():
    handler = _make_handler()
    handler.gui.drawing_state_manager.mode = "polygon"
    handler.gui.drawing_state_manager.has_points.return_value = True

    assert handler.on_drawing_undo(SimpleNamespace()) == "break"

    handler.manager._redraw_polygon_in_progress.assert_called_once()
    handler.gui.set_status.assert_called_once()


def test_on_drawing_redo_updates_status_and_redraws():
    handler = _make_handler()
    handler.gui.drawing_state_manager.mode = "polygon"

    assert handler.on_drawing_redo(SimpleNamespace()) == "break"

    handler.manager._redraw_polygon_in_progress.assert_called_once()
    handler.gui.set_status.assert_called_once()


def test_on_handle_press_sets_drag_state_and_binds():
    handler = _make_handler()
    handler.gui.edited_polygon_points = [(5.0, 6.0)]

    handler.on_handle_press(SimpleNamespace(x=3, y=4), handle_index=0)

    assert handler.gui._dragged_handle_index == 0
    assert handler.gui._drag_start_mouse == (3.0, 4.0)
    handler.gui.video_display.canvas.bind.assert_any_call(
        "<B1-Motion>", handler.on_handle_drag_global
    )
    handler.gui.video_display.canvas.bind.assert_any_call(
        "<ButtonRelease-1>", handler.on_handle_release_global
    )


def test_on_handle_drag_ignores_without_drag_index():
    handler = _make_handler()
    handler.gui._dragged_handle_index = None

    handler.on_handle_drag(SimpleNamespace(x=10, y=20))

    handler.manager.renderer.draw_interactive_polygon.assert_not_called()


def test_on_handle_drag_updates_polygon_and_clamps():
    handler = _make_handler()
    handler.gui._dragged_handle_index = 0
    handler.gui._drag_offset = (0.0, 0.0)
    handler.gui.edited_polygon_points = [[0.0, 0.0]]
    handler.gui.current_editing_zone = None
    handler.manager.apply_snapping.return_value = None
    handler.manager._canvas_to_video.side_effect = lambda x, y: (x, y)
    handler.gui.video_display.canvas.winfo_width.return_value = 100
    handler.gui.video_display.canvas.winfo_height.return_value = 80

    handler.on_handle_drag(SimpleNamespace(x=200, y=200))

    assert handler.gui.edited_polygon_points[0] == [100, 80]
    handler.manager.renderer.draw_interactive_polygon.assert_called_once()


def test_on_canvas_motion_debounces_updates():
    handler = _make_handler()
    handler.gui.drawing_state_manager.mode = "polygon"
    handler._motion_debounce_id = "old-id"

    handler.on_canvas_motion(SimpleNamespace(x=1, y=2))

    handler.gui.video_display.canvas.after_cancel.assert_called_once_with("old-id")
    handler.gui.video_display.canvas.after.assert_called_once_with(
        handler.MOTION_DEBOUNCE_MS,
        ANY,
    )


def test_handle_canvas_motion_shows_snap_indicator_without_points():
    handler = _make_handler()
    handler.gui.drawing_state_manager.mode = "polygon"
    handler.gui.drawing_state_manager.current_points = []
    handler.manager.apply_snapping.return_value = (5.0, 6.0)

    handler._handle_canvas_motion(SimpleNamespace(x=1, y=2))

    handler.gui.video_display.canvas.create_oval.assert_called_once()
    handler.gui.video_display.canvas.create_line.assert_not_called()

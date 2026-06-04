"""Tests for ZoneEditor multi-vertex selection / deletion (issues 1 & 2)."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

from zebtrack.ui.components.canvas.zone_editor import ZoneEditor


def _make_editor(points):
    """Build a ZoneEditor with mocked canvas_manager + gui for selection tests."""
    gui = SimpleNamespace(
        edited_polygon_points=list(points),
        set_status=Mock(),
    )
    renderer = SimpleNamespace(draw_interactive_polygon=Mock())
    canvas_manager = SimpleNamespace(
        gui=gui,
        renderer=renderer,
        selected_vertex_indices=set(),
        dragged_handle_index=None,
    )
    dialog_manager = Mock()
    editor = ZoneEditor(cast(Any, canvas_manager), dialog_manager=dialog_manager)
    return editor, canvas_manager, gui, dialog_manager


def test_select_all_vertices_marks_every_index():
    editor, cm, _gui, _dm = _make_editor([[0, 0], [1, 0], [1, 1], [0, 1]])
    editor.select_all_vertices()
    assert cm.selected_vertex_indices == {0, 1, 2, 3}
    cm.renderer.draw_interactive_polygon.assert_called_once()


def test_select_no_vertices_clears_selection():
    editor, cm, _gui, _dm = _make_editor([[0, 0], [1, 0], [1, 1]])
    cm.selected_vertex_indices = {0, 2}
    editor.select_no_vertices()
    assert cm.selected_vertex_indices == set()


def test_toggle_vertex_selection_add_and_remove():
    editor, cm, _gui, _dm = _make_editor([[0, 0], [1, 0], [1, 1]])
    editor.toggle_vertex_selection(1, selected=True)
    assert cm.selected_vertex_indices == {1}
    editor.toggle_vertex_selection(1, selected=False)
    assert cm.selected_vertex_indices == set()


def test_delete_vertices_removes_selected_indices():
    # 5 vertices so deleting 2 still leaves 3 (the minimum).
    editor, cm, gui, _dm = _make_editor([[0, 0], [1, 0], [2, 0], [2, 2], [0, 2]])
    cm.selected_vertex_indices = {1, 3}
    editor.delete_vertices({1, 3})
    assert gui.edited_polygon_points == [[0, 0], [2, 0], [0, 2]]
    assert cm.selected_vertex_indices == set()
    cm.renderer.draw_interactive_polygon.assert_called_once()


def test_delete_vertices_uses_current_selection_when_none_passed():
    editor, cm, gui, _dm = _make_editor([[0, 0], [1, 0], [1, 1], [0, 1]])
    cm.selected_vertex_indices = {0}
    editor.delete_vertices()
    assert gui.edited_polygon_points == [[1, 0], [1, 1], [0, 1]]


def test_delete_vertices_refuses_below_minimum():
    editor, cm, gui, dm = _make_editor([[0, 0], [1, 0], [1, 1]])
    editor.delete_vertices({0})
    # Polygon would drop to 2 vertices → rejected, nothing removed.
    assert gui.edited_polygon_points == [[0, 0], [1, 0], [1, 1]]
    dm.show_warning.assert_called_once()
    cm.renderer.draw_interactive_polygon.assert_not_called()


def test_delete_vertices_ignores_out_of_range_indices():
    editor, _cm, gui, _dm = _make_editor([[0, 0], [1, 0], [1, 1], [0, 1]])
    editor.delete_vertices({99})
    assert gui.edited_polygon_points == [[0, 0], [1, 0], [1, 1], [0, 1]]


def test_save_arena_arena_branch_persists_directly():
    """O ramo 'arena' do save_arena deve PERSISTIR direto via
    analysis_vm.save_manual_arena (com os vértices editados), e NÃO publicar
    ZONE_SAVE_MANUAL_ARENA — esse evento é EmptyPayload e o bus descarta o
    polygon_points, fazendo a edição nunca salvar (auto-detecção reaparecia)."""
    editor, cm, gui, _dm = _make_editor([[10, 10], [20, 10], [20, 20], [10, 20]])
    cm.current_editing_zone = "arena"
    gui.current_editing_zone = "arena"
    gui.zone_controls = SimpleNamespace(aquarium_count_var=SimpleNamespace(get=lambda: 1))
    save_mock = Mock(return_value=True)
    gui.controller = SimpleNamespace(analysis_vm=SimpleNamespace(save_manual_arena=save_mock))
    gui.root = SimpleNamespace(after=Mock())
    cm.event_bus_v2 = None
    cm.redraw_zones_from_project_data = Mock()
    cm.multi_aquarium = SimpleNamespace(_check_prompt_second_aquarium=Mock())
    editor.update_roi_button_state = Mock()  # type: ignore[method-assign]
    editor.clear_interactive_polygon = Mock()  # type: ignore[method-assign]
    # event_dispatcher NÃO deve ser usado para persistir o arena.
    gui.event_dispatcher = SimpleNamespace(publish_event=Mock())

    editor.save_arena()

    save_mock.assert_called_once_with([[10, 10], [20, 10], [20, 20], [10, 20]])
    gui.event_dispatcher.publish_event.assert_not_called()

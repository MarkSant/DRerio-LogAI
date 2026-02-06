"""Tests for ProcessingReportsWidget."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.processing_reports import ProcessingReportsWidget


@pytest.fixture
def widget(tkinter_root):
    event_bus = Mock()
    return ProcessingReportsWidget(parent=tkinter_root, event_bus=event_bus)


def _insert_video_item(widget: ProcessingReportsWidget, item_id: str, video_path: str) -> None:
    widget.add_tree_item(
        item_id,
        text=item_id,
        values=("✓", "✓", "✓", "✓", "OK", video_path),
        tags=("status_complete",),
    )


@pytest.mark.gui
def test_open_unified_no_project_path(widget, monkeypatch):
    widget._project_path = None
    startfile = Mock()
    monkeypatch.setattr("os.startfile", startfile, raising=False)

    widget._open_latest_unified_file(".xlsx")

    startfile.assert_not_called()


@pytest.mark.gui
def test_open_unified_missing_dir(widget, tmp_path, monkeypatch):
    widget._project_path = str(tmp_path)
    startfile = Mock()
    monkeypatch.setattr("os.startfile", startfile, raising=False)

    widget._open_latest_unified_file(".xlsx")

    startfile.assert_not_called()


@pytest.mark.gui
def test_open_unified_opens_latest(widget, tmp_path, monkeypatch):
    widget._project_path = str(tmp_path)
    unified_dir = tmp_path / "unified_reports"
    unified_dir.mkdir()

    first = unified_dir / "report1.xlsx"
    second = unified_dir / "report2.xlsx"
    first.write_text("one")
    second.write_text("two")

    first.touch()
    second.touch()
    first_time = 1_000_000
    second_time = 1_000_100
    first_utime = (first_time, first_time)
    second_utime = (second_time, second_time)
    import os

    os.utime(first, first_utime)
    os.utime(second, second_utime)

    startfile = Mock()
    monkeypatch.setattr("os.startfile", startfile, raising=False)

    widget._open_latest_unified_file(".xlsx")

    startfile.assert_called_once_with(str(second))


@pytest.mark.gui
def test_delete_unified_confirm_true(widget):
    widget.btn_open_unified_word.config(state="normal")
    widget.btn_open_unified_excel.config(state="normal")
    widget.btn_open_unified_parquet.config(state="normal")
    widget.btn_delete_unified.config(state="normal")

    with patch("tkinter.messagebox.askyesno", return_value=True):
        widget._on_delete_unified_clicked()

    widget.event_bus.publish_event.assert_called_once_with(
        event_name="reports.delete_unified", data={}
    )
    assert str(widget.btn_open_unified_word.cget("state")) == "disabled"
    assert str(widget.btn_open_unified_excel.cget("state")) == "disabled"
    assert str(widget.btn_open_unified_parquet.cget("state")) == "disabled"
    assert str(widget.btn_delete_unified.cget("state")) == "disabled"


@pytest.mark.gui
def test_delete_unified_confirm_false(widget):
    widget.btn_open_unified_word.config(state="normal")

    with patch("tkinter.messagebox.askyesno", return_value=False):
        widget._on_delete_unified_clicked()

    widget.event_bus.publish_event.assert_not_called()
    assert str(widget.btn_open_unified_word.cget("state")) == "normal"


@pytest.mark.gui
def test_update_button_states_with_selection(widget):
    _insert_video_item(widget, "video1", "/path/to/video1.mp4")
    widget.tree.selection_set("video1")

    widget._update_button_states()

    assert str(widget.btn_generate_trajectories.cget("state")) == "normal"
    assert str(widget.btn_export_summaries.cget("state")) == "normal"
    assert str(widget.btn_generate_partial.cget("state")) == "normal"
    assert "vídeo(s) selecionado(s)" in widget.selection_label.cget("text")


@pytest.mark.gui
def test_update_button_states_no_selection(widget):
    widget._update_button_states()

    assert str(widget.btn_generate_trajectories.cget("state")) == "disabled"
    assert str(widget.btn_export_summaries.cget("state")) == "disabled"
    assert str(widget.btn_generate_partial.cget("state")) == "disabled"
    assert widget.selection_label.cget("text") == "Nenhum vídeo selecionado"


@pytest.mark.gui
def test_update_button_states_with_unified_reports(widget, tmp_path):
    reports_dir = tmp_path / "unified_reports"
    reports_dir.mkdir()
    (reports_dir / "report.docx").write_text("doc")
    (reports_dir / "report.xlsx").write_text("xls")

    widget._update_button_states(project_path=str(tmp_path))

    assert str(widget.btn_open_unified_word.cget("state")) == "normal"
    assert str(widget.btn_open_unified_excel.cget("state")) == "normal"
    assert str(widget.btn_open_unified_parquet.cget("state")) == "disabled"
    assert str(widget.btn_delete_unified.cget("state")) == "normal"


@pytest.mark.gui
def test_expand_collapse_toggles(widget):
    _insert_video_item(widget, "parent", "/path/to/video.mp4")
    widget.add_tree_item(
        "child",
        text="child",
        parent="parent",
        values=("", "", "", "", "", "/path/to/video.mp4"),
    )

    widget._on_expand_collapse_clicked()
    assert widget._tree_expanded is True
    assert widget.btn_expand_collapse.cget("text") == "⊟ Colapsar Tudo"

    widget._on_expand_collapse_clicked()
    assert widget._tree_expanded is False
    assert widget.btn_expand_collapse.cget("text") == "⊞ Expandir Tudo"


@pytest.mark.gui
def test_right_click_emits_event(widget):
    _insert_video_item(widget, "video1", "/path/to/video1.mp4")
    bbox = widget.tree.bbox("video1")
    if not bbox:
        pytest.skip("Tree item not visible in this environment.")

    event = Mock()
    event.y = bbox[1] + 1
    event.x = bbox[0] + 1
    event.x_root = 100
    event.y_root = 200

    widget._on_item_right_click(event)

    widget.event_bus.publish_event.assert_called_once()
    call_args = widget.event_bus.publish_event.call_args
    assert call_args[1]["event_name"] == "processing_reports.item_right_click"


@pytest.mark.gui
def test_action_callbacks_invoked(widget):
    on_traj = Mock()
    on_export = Mock()
    on_partial = Mock()
    on_unified = Mock()

    widget._on_generate_trajectories = on_traj
    widget._on_export_summaries = on_export
    widget._on_generate_partial_report = on_partial
    widget._on_generate_unified_report = on_unified

    _insert_video_item(widget, "video1", "/path/to/video1.mp4")
    widget.tree.selection_set("video1")

    widget._on_generate_trajectories_clicked()
    on_traj.assert_called_once_with(("video1",))

    widget._on_export_summaries_clicked()
    on_export.assert_called_once()

    widget._on_generate_partial_clicked()
    on_partial.assert_called_once()

    widget._on_generate_unified_clicked()
    on_unified.assert_called_once()

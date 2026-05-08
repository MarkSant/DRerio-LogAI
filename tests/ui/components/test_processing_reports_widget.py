"""Tests for ProcessingReportsWidget."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.components.processing_reports import ProcessingReportsWidget
from zebtrack.ui.event_bus_v2 import UIEvents


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
    mock_open = Mock()
    monkeypatch.setattr("zebtrack.utils.os_opener.open_path", mock_open)

    widget._open_latest_unified_file(".xlsx")

    mock_open.assert_not_called()


@pytest.mark.gui
def test_open_unified_missing_dir(widget, tmp_path, monkeypatch):
    widget._project_path = str(tmp_path)
    mock_open = Mock()
    monkeypatch.setattr("zebtrack.utils.os_opener.open_path", mock_open)

    widget._open_latest_unified_file(".xlsx")

    mock_open.assert_not_called()


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

    mock_open = Mock()
    monkeypatch.setattr("zebtrack.utils.os_opener.open_path", mock_open)

    widget._open_latest_unified_file(".xlsx")

    mock_open.assert_called_once_with(str(second))


@pytest.mark.gui
def test_open_unified_prefers_latest_manifest_artifact(widget, tmp_path, monkeypatch):
    widget._project_path = str(tmp_path)
    unified_dir = tmp_path / "unified_reports"
    unified_dir.mkdir()

    older = unified_dir / "report_old.xlsx"
    latest_by_time = unified_dir / "report_latest.xlsx"
    from_manifest = unified_dir / "report_from_manifest.xlsx"

    older.write_text("older")
    latest_by_time.write_text("latest")
    from_manifest.write_text("manifest")

    import os

    os.utime(older, (1_000_000, 1_000_000))
    os.utime(from_manifest, (1_000_050, 1_000_050))
    os.utime(latest_by_time, (1_000_100, 1_000_100))

    manifest = {
        "run_id": "run_123",
        "artifacts": {
            "excel": str(from_manifest),
            "word": "",
            "parquet": "",
        },
    }
    (unified_dir / "latest_unified_run.json").write_text(json.dumps(manifest), encoding="utf-8")

    mock_open = Mock()
    monkeypatch.setattr("zebtrack.utils.os_opener.open_path", mock_open)

    widget._open_latest_unified_file(".xlsx")

    mock_open.assert_called_once_with(str(from_manifest))


@pytest.mark.gui
def test_open_unified_manifest_missing_artifact_falls_back_to_latest(widget, tmp_path, monkeypatch):
    widget._project_path = str(tmp_path)
    unified_dir = tmp_path / "unified_reports"
    unified_dir.mkdir()

    older = unified_dir / "report_old.xlsx"
    latest = unified_dir / "report_latest.xlsx"
    older.write_text("older")
    latest.write_text("latest")

    import os

    os.utime(older, (1_000_000, 1_000_000))
    os.utime(latest, (1_000_100, 1_000_100))

    manifest = {
        "run_id": "run_124",
        "artifacts": {
            "excel": str(unified_dir / "missing.xlsx"),
        },
    }
    (unified_dir / "latest_unified_run.json").write_text(json.dumps(manifest), encoding="utf-8")

    mock_open = Mock()
    monkeypatch.setattr("zebtrack.utils.os_opener.open_path", mock_open)

    widget._open_latest_unified_file(".xlsx")

    mock_open.assert_called_once_with(str(latest))


@pytest.mark.gui
def test_delete_unified_confirm_true(widget):
    widget.btn_open_unified_word.config(state="normal")
    widget.btn_open_unified_excel.config(state="normal")
    widget.btn_open_unified_parquet.config(state="normal")
    widget.btn_delete_unified.config(state="normal")

    with patch("tkinter.messagebox.askyesno", return_value=True):
        widget._on_delete_unified_clicked()

    widget.event_bus.publish.assert_called_once_with(
        UIEvents.REPORTS_DELETE_UNIFIED,
        payloads.ReportsDeleteUnifiedPayload(),
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

    widget.event_bus.publish.assert_not_called()
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

    widget.event_bus.publish.assert_called_once()
    call_args = widget.event_bus.publish.call_args
    event_obj = call_args[0][0]  # First positional arg
    assert event_obj.type == UIEvents.PROCESSING_REPORTS_ITEM_RIGHT_CLICK
    assert event_obj.data.item_id == "video1"
    assert event_obj.data.column_id == "#1"
    assert event_obj.data.x == 100
    assert event_obj.data.y == 200


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

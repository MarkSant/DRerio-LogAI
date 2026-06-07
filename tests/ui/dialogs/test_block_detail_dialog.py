"""Tests for ``BlockDetailDialog.start_session``.

Focused on the "deferred for zone confirmation" vs "genuine failure"
distinction so the user no longer sees a spurious
"Falha ao iniciar sessão para Animal X" popup after approving the
auto-detect polygon — that path returns False from
``start_live_project_session`` because the session is waiting for zone
confirmation, not because anything failed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pandas as pd
from docx import Document

from zebtrack.ui.dialogs.block_detail_dialog import BlockDetailDialog


def _build_dialog(
    *,
    start_session_return: bool,
    pending_zone_confirmation: bool,
) -> tuple[BlockDetailDialog, MagicMock]:
    """Construct a BlockDetailDialog bypassing Toplevel init.

    Returns (dialog, session_coordinator_mock) so callers can assert on
    the session_coordinator's call history.
    """
    dialog = cast(Any, BlockDetailDialog.__new__(BlockDetailDialog))
    dialog.day_num = 1
    dialog.group_name = "Controle"
    dialog._camera_index_override = None
    dialog._camera_friendly_name_override = None
    dialog.subjects_per_group = 3
    dialog.completed_sessions = set()
    dialog.destroy = MagicMock()  # Skip real Tk teardown

    session_coordinator = MagicMock()
    session_coordinator.start_live_project_session.return_value = start_session_return
    session_coordinator.live_calibration_coordinator = SimpleNamespace(
        pending_zone_confirmation=pending_zone_confirmation,
    )
    dialog.session_coordinator = session_coordinator

    return cast(BlockDetailDialog, dialog), session_coordinator


def _build_partial_report_dialog(tmp_path) -> BlockDetailDialog:
    dialog = cast(Any, BlockDetailDialog.__new__(BlockDetailDialog))
    dialog.day_num = 1
    dialog.group_name = "Controle"
    dialog.subjects_per_group = 1
    dialog.completed_sessions = {(1, "Controle", "1")}
    dialog.project_manager = SimpleNamespace(project_path=str(tmp_path))
    dialog._find_session_folder = MagicMock(return_value=tmp_path / "session_1")
    return cast(BlockDetailDialog, dialog)


def test_start_session_does_not_show_error_when_deferred_for_zones():
    """When ``start_live_project_session`` returns False because zones are
    pending confirmation, the user is on the zone tab seeing the
    "Iniciar Gravação" banner — no error popup should appear."""
    dialog, _ = _build_dialog(start_session_return=False, pending_zone_confirmation=True)

    with patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showerror") as mock_error:
        dialog.start_session("1")

    mock_error.assert_not_called()


def test_start_session_shows_error_on_genuine_failure():
    """A return of False with ``pending_zone_confirmation=False`` is a real
    failure (camera missing, wrong project type, etc.) — the popup must
    still surface so the user knows the session didn't start."""
    dialog, _ = _build_dialog(start_session_return=False, pending_zone_confirmation=False)

    with patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showerror") as mock_error:
        dialog.start_session("1")

    mock_error.assert_called_once()
    args, _kwargs = mock_error.call_args
    # Body must reference the subject + day/group so the user can act on it.
    assert "Animal 1" in args[1]
    assert "Dia 1" in args[1]
    assert "Controle" in args[1]


def test_start_session_shows_no_error_on_success():
    """Happy path: success=True → no error popup regardless of pending flag."""
    dialog, _ = _build_dialog(start_session_return=True, pending_zone_confirmation=False)

    with patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showerror") as mock_error:
        dialog.start_session("1")

    mock_error.assert_not_called()


def test_start_session_handles_missing_live_calibration_coordinator():
    """Older session_coordinator builds may not expose
    ``live_calibration_coordinator``. The deferred-detection probe must
    tolerate that and fall back to showing the error popup."""
    dialog, session_coordinator = _build_dialog(
        start_session_return=False, pending_zone_confirmation=False
    )
    # Strip the attribute to simulate a legacy build.
    del session_coordinator.live_calibration_coordinator

    with patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showerror") as mock_error:
        dialog.start_session("1")

    mock_error.assert_called_once()


def test_get_session_files_status_detects_relatorio_excel(tmp_path):
    dialog = _build_partial_report_dialog(tmp_path)
    session_folder = tmp_path / "session_1"
    session_folder.mkdir()
    (session_folder / "4_Relatorio_live_exp.xlsx").touch()

    status = dialog._get_session_files_status(session_folder)

    assert status["summary"] is True


def test_generate_partial_report_accepts_relatorio_excel(tmp_path):
    dialog = _build_partial_report_dialog(tmp_path)
    session_folder = tmp_path / "session_1"
    session_folder.mkdir()
    pd.DataFrame({"total_distance_cm": [10.0]}).to_excel(
        session_folder / "4_Relatorio_live_exp.xlsx",
        index=False,
    )
    dialog.session_coordinator = cast(Any, SimpleNamespace(event_bus=None))
    dialog.live_batch_coordinator = cast(Any, SimpleNamespace(event_bus=None))

    with (
        patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showwarning") as mock_warning,
        patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showinfo") as mock_info,
        patch("zebtrack.ui.dialogs.block_detail_dialog.messagebox.showerror") as mock_error,
        patch(
            "zebtrack.ui.dialogs.block_detail_dialog.messagebox.askyesno",
            side_effect=[False, False],
        ),
    ):
        dialog.generate_partial_report()

    mock_warning.assert_not_called()
    mock_error.assert_not_called()
    mock_info.assert_called_once()
    assert (tmp_path / "partial_reports" / "PartialReport_Dia1_Controle.xlsx").exists()
    assert (tmp_path / "partial_reports" / "PartialReport_Dia1_Controle.docx").exists()


def test_get_partial_report_stats_columns_ignores_non_numeric_time_fields(tmp_path):
    dialog = _build_partial_report_dialog(tmp_path)
    df = pd.DataFrame(
        {
            "analysis_timestamp": ["2026-06-07 10:00:00"],
            "total_time_seconds": [12.5],
            "total_roi_entries": [3],
            "time_label": ["baseline"],
            "animal": ["1"],
        }
    )

    stats_cols = dialog._get_partial_report_stats_columns(df)

    assert stats_cols == ["total_time_seconds", "total_roi_entries"]


def test_write_partial_report_word_lists_only_successfully_parsed_sessions(tmp_path):
    dialog = _build_partial_report_dialog(tmp_path)
    session_folder = tmp_path / "session_1"
    session_folder.mkdir()

    valid_summary = session_folder / "4_Relatorio_live_exp.xlsx"
    invalid_summary = session_folder / "4_Relatorio_corrompido.xlsx"

    pd.DataFrame({"total_distance_cm": [10.0]}).to_excel(valid_summary, index=False)
    invalid_summary.write_text("not an excel file", encoding="utf-8")

    all_data, unified_df, parsed_summary_files = dialog._build_partial_report_dataset(
        [("1", valid_summary), ("2", invalid_summary)]
    )

    output_path = tmp_path / "partial.docx"
    dialog._write_partial_report_word(
        output_path,
        "partial.xlsx",
        parsed_summary_files,
        all_data,
        unified_df,
    )

    document = Document(output_path)
    session_rows = document.tables[0].rows

    assert len(session_rows) == 2
    assert session_rows[1].cells[0].text == "1"
    assert session_rows[1].cells[1].text == valid_summary.name

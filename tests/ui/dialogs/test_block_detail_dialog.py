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

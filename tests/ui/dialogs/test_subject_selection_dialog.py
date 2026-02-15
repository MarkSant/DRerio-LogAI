"""Tests for SubjectSelectionDialog helpers."""

from collections.abc import Iterable
from typing import Any, cast
from unittest.mock import MagicMock

from zebtrack.ui.dialogs.subject_selection_dialog import SubjectSelectionDialog


def _build_dialog(
    subjects_per_group: int = 2, completed_subjects: Iterable[int] | None = None
) -> SubjectSelectionDialog:
    dialog = cast(Any, SubjectSelectionDialog.__new__(SubjectSelectionDialog))
    dialog.subjects_per_group = subjects_per_group
    dialog.completed_subjects = set(completed_subjects or set())
    dialog.result = None
    dialog.ok = MagicMock()
    return cast(SubjectSelectionDialog, dialog)


def test_select_subject_sets_result_and_closes():
    dialog = _build_dialog()

    dialog.select_subject(2)

    assert dialog.result == 2
    cast(MagicMock, dialog.ok).assert_called_once()


def test_body_builds_labels_with_completion_status(monkeypatch):
    master = MagicMock()
    dialog = _build_dialog(subjects_per_group=2, completed_subjects={1})

    label_completed = MagicMock()
    label_pending = MagicMock()
    label_factory = MagicMock(side_effect=[label_completed, label_pending])
    monkeypatch.setattr("zebtrack.ui.dialogs.subject_selection_dialog.ttk.Label", label_factory)

    dialog.body(master)

    label_factory.assert_any_call(
        master,
        text="Cobaia 1: Concluído",
        foreground="darkgreen",
        font=("Helvetica", 10),
    )
    label_factory.assert_any_call(
        master,
        text="Cobaia 2: Pendente",
        foreground="black",
        font=("Helvetica", 10),
    )
    label_completed.pack.assert_called_once()
    label_pending.pack.assert_called_once()
    label_pending.config.assert_called_once_with(cursor="hand2")
    cast(MagicMock, label_pending.bind).assert_called_once()
    cast(MagicMock, label_completed.bind).assert_not_called()

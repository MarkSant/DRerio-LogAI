"""Tests for ReportGeneratorActions (unified report generation and deletion).

Collaborators are small fakes: what the researcher is told (dialog titles and
texts), the event published to start generation (a typed payload) and what ends
up on disk are asserted. Folder deletion runs on real temp folders; the only
patched pieces are the ones that would make a test slow (``time.sleep``) or that
need a locked file (``shutil.rmtree``).
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from tests.utils.deferring_tk import bind_deferring_tk

from zebtrack.ui import payloads
from zebtrack.ui.components.project_views.report_generator_actions import (
    ReportGeneratorActions,
)
from zebtrack.ui.event_bus_v2 import UIEvents

VIDEO_A = {"path": "D:/exp/Dia_1/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"}
VIDEO_B = {"path": "D:/exp/Dia_2/CECT_4/CECT_4.mp4", "experiment_id": "CECT_4"}
VIDEO_C = {"path": "D:/exp/Dia_1/CECT_5/CECT_5.mp4", "experiment_id": "CECT_5"}


class _Dialogs:
    def __init__(self, yes_no_cancel: bool | None = True) -> None:
        self.answer = yes_no_cancel
        self.warnings: list[tuple[str, str]] = []
        self.infos: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.questions: list[tuple[str, str, str]] = []

    def show_warning(self, title: str, message: str) -> None:
        self.warnings.append((title, message))

    def show_info(self, title: str, message: str) -> None:
        self.infos.append((title, message))

    def show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))

    def ask_yes_no_cancel(self, title: str, message: str, *, icon: str = "question") -> Any:
        self.questions.append((title, message, icon))
        return self.answer


class _Project:
    def __init__(self, project_path: Path | None, videos: list[dict]) -> None:
        self.project_path = str(project_path) if project_path else None
        self._videos = videos

    def get_all_videos(self) -> list[dict]:
        return list(self._videos)


class _Dispatcher:
    def __init__(self) -> None:
        self.events: list[tuple[Any, Any]] = []

    def publish_event(self, event: Any, payload: Any) -> None:
        self.events.append((event, payload))


class _ProcessingWidget:
    def __init__(self, selection: tuple[str, ...] = ()) -> None:
        self._selection = selection
        self.refreshed: list[Any] = []

    def get_selection(self) -> tuple[str, ...]:
        return self._selection

    def _update_button_states(self, project_path: Any) -> None:
        self.refreshed.append(project_path)


class _LegacyTree:
    def __init__(self, selection: tuple[str, ...], existing: set[str]) -> None:
        self._selection = selection
        self._existing = existing

    def selection(self) -> tuple[str, ...]:
        return self._selection

    def exists(self, item_id: str) -> bool:
        return item_id in self._existing


def _actions(
    project_path: Path | None = None,
    videos: list[dict] | None = None,
    *,
    answer: bool | None = True,
    widget: _ProcessingWidget | None = None,
    tree_metadata: dict | None = None,
    report_tree_metadata: dict | None = None,
    reports_tree: _LegacyTree | None = None,
) -> tuple[ReportGeneratorActions, _Dialogs, _Dispatcher, list[str]]:
    dialogs = _Dialogs(answer)
    dispatcher = _Dispatcher()
    status: list[str] = []
    project = _Project(project_path, videos if videos is not None else [])
    actions = ReportGeneratorActions(
        project_manager_getter=lambda: project,
        event_dispatcher=dispatcher,
        dialog_manager=dialogs,  # type: ignore[arg-type]
        processing_reports_widget=widget,
        set_status=status.append,
        tree_metadata=tree_metadata,
        report_tree_metadata=report_tree_metadata,
        reports_tree_getter=(lambda: reports_tree) if reports_tree is not None else None,
    )
    return actions, dialogs, dispatcher, status


def _make_reports(project: Path, scope_dir: str, *names: str) -> Path:
    folder = project / "unified_reports" / scope_dir
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_bytes(b"x")
    return folder


def _generate_payload(dispatcher: _Dispatcher) -> payloads.ReportGeneratePayload:
    assert len(dispatcher.events) == 1
    event, payload = dispatcher.events[0]
    assert event == UIEvents.REPORT_GENERATE
    assert isinstance(payload, payloads.ReportGeneratePayload)
    return payload


class TestGenerateUnifiedReport:
    def test_without_videos_it_warns_and_publishes_nothing(self, tmp_path):
        actions, dialogs, dispatcher, _status = _actions(tmp_path, [])

        actions.generate_unified_report()

        assert dialogs.warnings == [
            ("No Data", "There are no processed videos in this project to build a report from.")
        ]
        assert dispatcher.events == []

    def test_a_fresh_project_publishes_the_total_report_request_without_replacing(self, tmp_path):
        actions, dialogs, dispatcher, _status = _actions(tmp_path, [VIDEO_A, VIDEO_B])

        actions.generate_unified_report()

        payload = _generate_payload(dispatcher)
        assert list(payload.videos or []) == [VIDEO_A, VIDEO_B]
        assert payload.report_type == "unified"
        assert payload.report_scope == "all"
        assert payload.replace_existing is False
        assert dialogs.questions == []

    def test_a_project_without_a_path_never_asks_and_never_replaces(self):
        actions, dialogs, dispatcher, _status = _actions(None, [VIDEO_A])

        actions.generate_unified_report()

        assert _generate_payload(dispatcher).replace_existing is False
        assert dialogs.questions == []

    @pytest.mark.parametrize(("answer", "replace"), [(True, True), (False, False)])
    def test_existing_reports_ask_and_the_answer_decides_replacement(
        self, tmp_path, answer, replace
    ):
        _make_reports(tmp_path, "total", "relatorio.docx")
        actions, dialogs, dispatcher, _status = _actions(tmp_path, [VIDEO_A], answer=answer)

        actions.generate_unified_report()

        assert _generate_payload(dispatcher).replace_existing is replace
        assert len(dialogs.questions) == 1
        title, message, icon = dialogs.questions[0]
        assert title == "Existing Unified Reports"
        assert "Yes: delete the previous ones" in message
        assert "Cancel: abort generation" in message
        assert icon == "warning"

    def test_cancelling_the_question_aborts_and_says_so_in_the_status_bar(self, tmp_path):
        _make_reports(tmp_path, "total", "relatorio.docx")
        actions, _dialogs, dispatcher, status = _actions(tmp_path, [VIDEO_A], answer=None)

        actions.generate_unified_report()

        assert dispatcher.events == []
        assert status == ["Unified report generation cancelled by the user."]

    @pytest.mark.parametrize("name", ["sumario.parquet", "sumario.xlsx", "relatorio.docx"])
    def test_each_report_format_counts_as_an_existing_report(self, tmp_path, name):
        _make_reports(tmp_path, "total", name)
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, [VIDEO_A])

        actions.generate_unified_report()

        assert len(dialogs.questions) == 1

    def test_other_files_in_the_folder_are_not_reports(self, tmp_path):
        _make_reports(tmp_path, "total", "notes.txt", "manifest.json")
        actions, dialogs, dispatcher, _status = _actions(tmp_path, [VIDEO_A])

        actions.generate_unified_report()

        assert dialogs.questions == []
        assert _generate_payload(dispatcher).replace_existing is False

    def test_an_empty_total_folder_does_not_ask(self, tmp_path):
        _make_reports(tmp_path, "total")
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, [VIDEO_A])

        actions.generate_unified_report()

        assert dialogs.questions == []

    def test_partial_reports_do_not_trigger_the_question_for_the_total_report(self, tmp_path):
        _make_reports(tmp_path, "selecionados", "parcial.docx")
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, [VIDEO_A])

        actions.generate_unified_report()

        assert dialogs.questions == []


class TestPartialReportFromTheUnifiedTab:
    def _tab(self, tmp_path, selection, metadata, **kwargs):
        return _actions(
            tmp_path,
            [VIDEO_A, VIDEO_B, VIDEO_C],
            widget=_ProcessingWidget(selection),
            tree_metadata=metadata,
            **kwargs,
        )

    def test_the_selected_videos_are_published_in_selection_order(self, tmp_path):
        metadata = {
            "i1": {"type": "video", "video_path": VIDEO_C["path"]},
            "i2": {"type": "video", "video_path": VIDEO_A["path"]},
        }
        actions, _dialogs, dispatcher, _status = self._tab(tmp_path, ("i1", "i2"), metadata)

        actions.on_processing_reports_generate_partial()

        payload = _generate_payload(dispatcher)
        assert list(payload.videos or []) == [VIDEO_C, VIDEO_A]
        assert payload.report_scope == "selected"
        assert payload.report_type == "unified"
        assert payload.replace_existing is False

    def test_the_same_experiment_id_on_two_days_is_told_apart_by_path(self, tmp_path):
        metadata = {"i1": {"type": "video", "video_path": VIDEO_B["path"]}}
        actions, _dialogs, dispatcher, _status = self._tab(tmp_path, ("i1",), metadata)

        actions.on_processing_reports_generate_partial()

        assert list(_generate_payload(dispatcher).videos or []) == [VIDEO_B]

    def test_group_day_and_unknown_nodes_are_ignored(self, tmp_path):
        metadata = {
            "g": {"type": "group"},
            "d": {"type": "day"},
            "nopath": {"type": "video"},
            "unknown": {"type": "video", "video_path": "D:/elsewhere/other.mp4"},
            "ok": {"type": "video", "video_path": VIDEO_A["path"]},
        }
        actions, _dialogs, dispatcher, _status = self._tab(
            tmp_path, ("g", "d", "missing", "nopath", "unknown", "ok"), metadata
        )

        actions.on_processing_reports_generate_partial()

        assert list(_generate_payload(dispatcher).videos or []) == [VIDEO_A]

    def test_when_nothing_selectable_is_selected_nothing_happens(self, tmp_path):
        actions, dialogs, dispatcher, _status = self._tab(
            tmp_path, ("g",), {"g": {"type": "group"}}
        )

        actions.on_processing_reports_generate_partial()

        assert dispatcher.events == []
        assert dialogs.questions == []

    def test_an_empty_selection_does_nothing(self, tmp_path):
        actions, _dialogs, dispatcher, _status = self._tab(tmp_path, (), {})

        actions.on_processing_reports_generate_partial()

        assert dispatcher.events == []

    def test_without_the_tab_widget_nothing_happens(self, tmp_path):
        actions, _dialogs, dispatcher, _status = _actions(tmp_path, [VIDEO_A], widget=None)

        actions.on_processing_reports_generate_partial()

        assert dispatcher.events == []

    def test_existing_partial_reports_are_checked_in_the_selected_folder(self, tmp_path):
        _make_reports(tmp_path, "selecionados", "parcial.xlsx")
        metadata = {"i1": {"type": "video", "video_path": VIDEO_A["path"]}}
        actions, dialogs, dispatcher, _status = self._tab(tmp_path, ("i1",), metadata, answer=True)

        actions.on_processing_reports_generate_partial()

        assert len(dialogs.questions) == 1
        assert _generate_payload(dispatcher).replace_existing is True

    def test_total_reports_do_not_trigger_the_question_for_a_partial_report(self, tmp_path):
        _make_reports(tmp_path, "total", "total.xlsx")
        metadata = {"i1": {"type": "video", "video_path": VIDEO_A["path"]}}
        actions, dialogs, _dispatcher, _status = self._tab(tmp_path, ("i1",), metadata)

        actions.on_processing_reports_generate_partial()

        assert dialogs.questions == []

    def test_cancelling_the_question_publishes_nothing(self, tmp_path):
        _make_reports(tmp_path, "selecionados", "parcial.xlsx")
        metadata = {"i1": {"type": "video", "video_path": VIDEO_A["path"]}}
        actions, _dialogs, dispatcher, status = self._tab(tmp_path, ("i1",), metadata, answer=None)

        actions.on_processing_reports_generate_partial()

        assert dispatcher.events == []
        assert status == ["Unified report generation cancelled by the user."]


class TestPartialReportFromTheLegacyTree:
    def test_selected_video_nodes_still_in_the_tree_are_published(self, tmp_path):
        tree = _LegacyTree(("a", "gone", "c"), existing={"a", "c"})
        metadata = {
            "a": {"type": "video", "video_path": VIDEO_A["path"]},
            "gone": {"type": "video", "video_path": VIDEO_B["path"]},
            "c": {"type": "folder"},
        }
        actions, _dialogs, dispatcher, _status = _actions(
            tmp_path, [VIDEO_A, VIDEO_B], report_tree_metadata=metadata, reports_tree=tree
        )

        actions.generate_partial_report()

        payload = _generate_payload(dispatcher)
        assert list(payload.videos or []) == [VIDEO_A]
        assert payload.report_scope == "selected"
        assert payload.report_type == "unified"

    def test_without_a_tree_or_selection_nothing_happens(self, tmp_path):
        no_tree, _d1, dispatcher1, _s1 = _actions(tmp_path, [VIDEO_A])
        no_selection, _d2, dispatcher2, _s2 = _actions(
            tmp_path, [VIDEO_A], reports_tree=_LegacyTree((), set())
        )

        no_tree.generate_partial_report()
        no_selection.generate_partial_report()

        assert dispatcher1.events == []
        assert dispatcher2.events == []

    def test_cancelling_the_question_publishes_nothing(self, tmp_path):
        _make_reports(tmp_path, "selecionados", "parcial.docx")
        tree = _LegacyTree(("a",), existing={"a"})
        actions, _dialogs, dispatcher, status = _actions(
            tmp_path,
            [VIDEO_A],
            answer=None,
            report_tree_metadata={"a": {"type": "video", "video_path": VIDEO_A["path"]}},
            reports_tree=tree,
        )

        actions.generate_partial_report()

        assert dispatcher.events == []
        assert status == ["Unified report generation cancelled by the user."]


class TestDeleteAllUnifiedReports:
    def test_without_a_project_path_nothing_happens(self):
        actions, dialogs, _dispatcher, _status = _actions(None)

        actions.delete_all_unified_reports()

        assert dialogs.infos == [] and dialogs.errors == []

    def test_the_whole_folder_is_removed_and_the_user_is_told_once(self, tmp_path):
        _make_reports(tmp_path, "total", "a.docx", "b.xlsx")
        _make_reports(tmp_path, "selecionados", "c.parquet")
        widget = _ProcessingWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()

        assert not (tmp_path / "unified_reports").exists()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]
        assert dialogs.errors == []
        assert widget.refreshed == [str(tmp_path)]

    def test_without_the_tab_widget_the_success_message_is_not_followed_by_a_contradiction(
        self, tmp_path
    ):
        """ "No reports to delete" belongs to a missing folder, not to a missing widget."""
        _make_reports(tmp_path, "total", "a.docx")
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=None)

        actions.delete_all_unified_reports()

        assert not (tmp_path / "unified_reports").exists()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]

    @pytest.mark.parametrize("with_widget", [True, False])
    def test_a_missing_folder_says_there_was_nothing_to_delete(self, tmp_path, with_widget):
        widget = _ProcessingWidget() if with_widget else None
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()

        assert dialogs.infos == [("Warning", "There were no unified reports to delete.")]
        assert dialogs.errors == []
        if widget is not None:
            assert widget.refreshed == [str(tmp_path)]

    def test_read_only_files_do_not_stop_the_deletion(self, tmp_path):
        folder = _make_reports(tmp_path, "total", "locked.docx")
        os.chmod(folder / "locked.docx", stat.S_IREAD)
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=_ProcessingWidget())

        actions.delete_all_unified_reports()

        assert not (tmp_path / "unified_reports").exists()
        assert dialogs.errors == []

    @staticmethod
    def _locked_rmtree(monkeypatch, sleeps: list[float]):
        """rmtree that cannot remove one file: it reports to ``onerror`` and goes on."""

        def rmtree(path: Any, onerror: Any = None, **_kw: Any) -> None:
            def locked(_target: Any) -> None:
                raise PermissionError("file is being used by another process")

            onerror(locked, str(Path(path) / "total" / "a.docx"), sys.exc_info())

        monkeypatch.setattr(shutil, "rmtree", rmtree)
        monkeypatch.setattr(time, "sleep", sleeps.append)

    def test_a_locked_file_is_reported_as_a_failure_not_as_a_success(self, tmp_path, monkeypatch):
        """The onerror handler swallows the failure, so rmtree "returns normally"."""
        _make_reports(tmp_path, "total", "a.docx")
        sleeps: list[float] = []
        self._locked_rmtree(monkeypatch, sleeps)
        widget = _ProcessingWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()

        assert (tmp_path / "unified_reports").exists()
        assert dialogs.infos == []
        assert len(dialogs.errors) == 1
        title, message = dialogs.errors[0]
        assert title == "Deletion Error"
        assert message.startswith(
            "Could not delete the folder.\nCheck whether a file is still open.\n\nError: "
        )
        assert "OneDrive" not in message
        # Three attempts, a pause BETWEEN them: no pause after the last one, which
        # only delayed the error dialog (audit A6-02).
        assert sleeps == [0.5, 0.5]
        assert widget.refreshed == [str(tmp_path)]

    def test_a_folder_under_onedrive_adds_the_lock_hint(self, tmp_path, monkeypatch):
        project = tmp_path / "OneDrive" / "Experimento"
        _make_reports(project, "total", "a.docx")
        self._locked_rmtree(monkeypatch, [])
        actions, dialogs, _dispatcher, _status = _actions(project)

        actions.delete_all_unified_reports()

        assert "OneDrive may be locking files. Try again in a few moments." in dialogs.errors[0][1]

    def test_a_transient_error_is_retried_and_then_succeeds(self, tmp_path, monkeypatch):
        _make_reports(tmp_path, "total", "a.docx")
        sleeps: list[float] = []
        real_rmtree = shutil.rmtree
        attempts: list[int] = []

        def flaky(path: Any, onerror: Any = None, **kw: Any) -> None:
            attempts.append(1)
            if len(attempts) == 1:
                raise PermissionError("antivirus scan in progress")
            real_rmtree(path, onerror=onerror, **kw)

        monkeypatch.setattr(shutil, "rmtree", flaky)
        monkeypatch.setattr(time, "sleep", sleeps.append)
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=_ProcessingWidget())

        actions.delete_all_unified_reports()

        assert len(attempts) == 2
        assert sleeps == [0.5]
        assert not (tmp_path / "unified_reports").exists()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]
        assert dialogs.errors == []


class _TkWidget(_ProcessingWidget):
    """The reports tab widget with a deferring Tk loop (``after`` is queued)."""

    def __init__(self) -> None:
        super().__init__()
        self.tk_loop = bind_deferring_tk(self)


class TestDeleteAllUnifiedReportsOffTk:
    """A6-02: the deletion runs on a worker; dialogs and buttons stay on Tk."""

    def test_deletion_runs_off_tk_and_the_dialog_waits_for_the_tk_loop(self, tmp_path, monkeypatch):
        _make_reports(tmp_path, "total", "a.docx")
        real_rmtree = shutil.rmtree
        threads: list = []

        def rmtree(path: Any, onerror: Any = None, **kw: Any) -> None:
            threads.append(threading.current_thread())
            real_rmtree(path, onerror=onerror, **kw)

        monkeypatch.setattr(shutil, "rmtree", rmtree)
        widget = _TkWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()
        assert dialogs.infos == []
        assert widget.refreshed == []

        widget.tk_loop.run_until_idle()

        assert len(threads) == 1
        assert threads[0] is not threading.main_thread()
        assert not (tmp_path / "unified_reports").exists()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]
        assert widget.refreshed == [str(tmp_path)]

    def test_a_second_request_while_deleting_is_ignored(self, tmp_path, monkeypatch):
        _make_reports(tmp_path, "total", "a.docx")
        release = threading.Event()
        calls: list = []
        real_rmtree = shutil.rmtree

        def slow_rmtree(path: Any, onerror: Any = None, **kw: Any) -> None:
            calls.append(1)
            release.wait(5)
            real_rmtree(path, onerror=onerror, **kw)

        monkeypatch.setattr(shutil, "rmtree", slow_rmtree)
        widget = _TkWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()
        actions.delete_all_unified_reports()
        release.set()
        widget.tk_loop.run_until_idle()

        assert calls == [1]
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]
        assert dialogs.errors == []

    def test_failure_is_reported_on_tk_and_a_new_attempt_is_allowed(self, tmp_path, monkeypatch):
        _make_reports(tmp_path, "total", "a.docx")
        TestDeleteAllUnifiedReports._locked_rmtree(monkeypatch, [])
        widget = _TkWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()
        widget.tk_loop.run_until_idle()

        assert [title for title, _msg in dialogs.errors] == ["Deletion Error"]
        assert widget.refreshed == [str(tmp_path)]

        actions.delete_all_unified_reports()
        widget.tk_loop.run_until_idle()
        assert len(dialogs.errors) == 2

    def test_an_unexpected_worker_error_still_ends_in_the_error_dialog(self, tmp_path, monkeypatch):
        _make_reports(tmp_path, "total", "a.docx")
        from zebtrack.ui.components.project_views import report_generator_actions as module

        def explode(_dir: str):
            raise ValueError("bad path")

        monkeypatch.setattr(module, "delete_unified_reports_dir", explode)
        widget = _TkWidget()
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=widget)

        actions.delete_all_unified_reports()
        widget.tk_loop.run_until_idle()

        assert len(dialogs.errors) == 1
        assert dialogs.errors[0][1].endswith("Error: bad path")
        assert widget.refreshed == [str(tmp_path)]

        # Not stuck: the next click runs again.
        monkeypatch.setattr(module, "delete_unified_reports_dir", lambda _d: (True, None))
        actions.delete_all_unified_reports()
        widget.tk_loop.run_until_idle()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]

    def test_the_gui_root_is_used_when_the_tab_widget_is_missing(self, tmp_path):
        _make_reports(tmp_path, "total", "a.docx")
        root = SimpleNamespace()
        tk_loop = bind_deferring_tk(root)
        actions, dialogs, _dispatcher, _status = _actions(tmp_path, widget=None)
        cast(Any, dialogs).gui = SimpleNamespace(root=root)

        actions.delete_all_unified_reports()
        assert dialogs.infos == []

        tk_loop.run_until_idle()
        assert dialogs.infos == [("Success", "All unified reports have been deleted.")]

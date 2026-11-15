"""Tests for ReportAssetActions (video asset deletion and report file opening).

Collaborators are small fakes. What is asserted is what the researcher gets: the
dialogs shown (title and text), the file or folder handed to the operating system
opener, the removal request sent to the menu manager, the refresh that follows a
reset, and the rows added to the legacy reports tree.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.components.project_views.report_asset_actions import ReportAssetActions
from zebtrack.ui.event_bus_v2 import UIEvents
from zebtrack.utils import os_opener

VIDEO = "D:/exp/Dia_1/CECT_4/CECT_4.mp4"


class _Dialogs:
    def __init__(
        self,
        mode: str | None = None,
        confirm: tuple[bool, bool] = (True, False),
    ) -> None:
        self.mode = mode
        self.confirm = confirm
        self.mode_asked: list[tuple[str, str]] = []
        self.confirm_asked: list[tuple[str, int, list[str]]] = []
        self.warnings: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []

    def choose_processing_reports_delete_mode(self, name: str, *, target_kind: str) -> Any:
        self.mode_asked.append((name, target_kind))
        return self.mode

    def confirm_delete_processing_data(
        self, label: str, count: int, names: list[str]
    ) -> tuple[bool, bool]:
        self.confirm_asked.append((label, count, names))
        return self.confirm

    def show_warning(self, title: str, message: str) -> None:
        self.warnings.append((title, message))

    def show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))


class _Menu:
    def __init__(self) -> None:
        self.removals: list[tuple[Any, str]] = []

    def handle_overview_asset_removal(self, path: Any, asset: str) -> None:
        self.removals.append((path, asset))


class _Project:
    def __init__(
        self,
        project_path: Path | None = None,
        entry: dict | None = None,
        resets: dict[str, bool] | None = None,
        results_dir: Path | None = None,
    ) -> None:
        self.project_path = str(project_path) if project_path else None
        self.entry = entry
        self.resets = resets or {}
        self.reset_calls: list[tuple[str, bool]] = []
        self.results_dir = results_dir
        self.resolve_calls: list[tuple[str, Any, Any]] = []

    def reset_analysis_data(self, path: str, *, delete_files: bool) -> bool:
        self.reset_calls.append((path, delete_files))
        return self.resets.get(path, True)

    def find_video_entry(self, *, path: str) -> dict | None:
        return self.entry

    def resolve_results_directory(self, experiment_id: str, *, video_path: Any, metadata: Any):
        self.resolve_calls.append((experiment_id, video_path, metadata))
        return self.results_dir


class _Selector:
    def __init__(self) -> None:
        self.refreshes: list[dict[str, Any]] = []

    def refresh_project_views(self, **kwargs: Any) -> None:
        self.refreshes.append(kwargs)


class _Dispatcher:
    def __init__(self) -> None:
        self.events: list[tuple[Any, Any]] = []

    def publish_event(self, event: Any, payload: Any) -> None:
        self.events.append((event, payload))


class _Tree:
    """Stands for the processing-reports tree and the legacy reports tree."""

    def __init__(self, rows: dict[int, str] | None = None, selection: tuple[str, ...] = ()):
        self.rows = rows or {}
        self._selection = selection
        self.inserted: list[dict[str, Any]] = []
        self.opened: list[tuple[str, bool]] = []

    def identify_row(self, y: int) -> str:
        return self.rows.get(y, "")

    def selection(self) -> tuple[str, ...]:
        return self._selection

    def insert(self, parent: str, index: str, **kwargs: Any) -> str:
        child = f"child{len(self.inserted) + 1}"
        self.inserted.append({"parent": parent, "index": index, "id": child, **kwargs})
        return child

    def item(self, item_id: str, **kwargs: Any) -> None:
        self.opened.append((item_id, bool(kwargs.get("open"))))


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the operating-system opener; records what would have been opened."""
    calls: list[str] = []
    monkeypatch.setattr(os_opener, "open_path", lambda path: calls.append(str(path)))
    return calls


def _actions(
    project: _Project | None = None,
    dialogs: _Dialogs | None = None,
    **kwargs: Any,
) -> tuple[ReportAssetActions, _Dialogs, _Menu]:
    dialogs = dialogs or _Dialogs()
    menu = _Menu()
    project = project or _Project()
    actions = ReportAssetActions(
        project_manager_getter=lambda: project,
        dialog_manager=dialogs,  # type: ignore[arg-type]
        menu_manager=menu,
        **kwargs,
    )
    return actions, dialogs, menu


class TestMenuDelegation:
    def test_delete_video_asset_forwards_path_and_asset(self):
        actions, _dialogs, menu = _actions()

        actions.delete_video_asset(VIDEO, "roi")

        assert menu.removals == [(VIDEO, "roi")]

    def test_delete_video_from_project_asks_the_menu_to_remove_the_video(self):
        actions, _dialogs, menu = _actions()

        actions.delete_video_from_project(VIDEO)

        assert menu.removals == [(VIDEO, "video")]


class TestChooseVideoDeleteAction:
    def test_the_question_names_the_file_not_the_path(self):
        actions, dialogs, _menu = _actions(dialogs=_Dialogs(mode=None))

        actions.choose_video_delete_action(VIDEO)

        assert dialogs.mode_asked == [("CECT_4.mp4", "video")]

    def test_cancelling_does_nothing(self):
        project = _Project()
        actions, dialogs, menu = _actions(project, _Dialogs(mode=None))

        actions.choose_video_delete_action(VIDEO)

        assert menu.removals == []
        assert dialogs.confirm_asked == []
        assert project.reset_calls == []

    def test_choosing_project_removes_the_video_from_the_project(self):
        actions, dialogs, menu = _actions(dialogs=_Dialogs(mode="project"))

        actions.choose_video_delete_action(VIDEO)

        assert menu.removals == [(VIDEO, "video")]
        assert dialogs.confirm_asked == []

    def test_choosing_data_resets_the_analysis_of_that_video_only(self):
        project = _Project()
        actions, dialogs, menu = _actions(project, _Dialogs(mode="data", confirm=(True, True)))

        actions.choose_video_delete_action(VIDEO)

        assert menu.removals == []
        assert dialogs.confirm_asked == [("CECT_4.mp4", 1, ["CECT_4.mp4"])]
        assert project.reset_calls == [(VIDEO, True)]


class TestResetAnalysisData:
    def test_nothing_to_reset_returns_false_without_asking(self):
        actions, dialogs, _menu = _actions()

        assert actions.reset_analysis_data_for_videos([], target_label="x") is False
        assert actions.reset_analysis_data_for_videos(["", ""], target_label="x") is False

        assert dialogs.confirm_asked == []

    def test_duplicates_are_collapsed_keeping_the_first_occurrence(self):
        project = _Project()
        actions, dialogs, _menu = _actions(project)

        actions.reset_analysis_data_for_videos(
            ["D:/a/b.mp4", "D:/a/c.mp4", "D:/a/b.mp4", ""], target_label="2 videos"
        )

        assert dialogs.confirm_asked == [("2 videos", 2, ["b.mp4", "c.mp4"])]
        assert [path for path, _flag in project.reset_calls] == ["D:/a/b.mp4", "D:/a/c.mp4"]

    def test_declining_the_confirmation_resets_nothing(self):
        project = _Project()
        selector = _Selector()
        actions, _dialogs, _menu = _actions(
            project, _Dialogs(confirm=(False, False)), video_selector_manager=selector
        )

        assert actions.reset_analysis_data_for_videos([VIDEO], target_label="x") is False

        assert project.reset_calls == []
        assert selector.refreshes == []

    @pytest.mark.parametrize("delete_files", [True, False])
    def test_the_delete_files_choice_reaches_every_reset(self, delete_files):
        project = _Project()
        actions, _dialogs, _menu = _actions(project, _Dialogs(confirm=(True, delete_files)))

        actions.reset_analysis_data_for_videos(["D:/a.mp4", "D:/b.mp4"], target_label="x")

        assert project.reset_calls == [("D:/a.mp4", delete_files), ("D:/b.mp4", delete_files)]

    def test_a_reset_refreshes_the_views_once_through_the_selector_manager(self):
        selector = _Selector()
        actions, _dialogs, _menu = _actions(_Project(), video_selector_manager=selector)

        result = actions.reset_analysis_data_for_videos(["D:/a.mp4", "D:/b.mp4"], target_label="x")

        assert result is True
        assert selector.refreshes == [
            {"reason": "Analyses reset (drawings preserved)", "append_summary": True}
        ]

    def test_one_successful_reset_among_failures_is_enough_to_refresh(self):
        project = _Project(resets={"D:/a.mp4": False, "D:/b.mp4": True})
        selector = _Selector()
        actions, _dialogs, _menu = _actions(project, video_selector_manager=selector)

        result = actions.reset_analysis_data_for_videos(["D:/a.mp4", "D:/b.mp4"], target_label="x")

        assert result is True
        assert len(selector.refreshes) == 1

    def test_when_no_reset_changed_anything_nothing_is_refreshed(self):
        project = _Project(resets={"D:/a.mp4": False})
        selector = _Selector()
        actions, _dialogs, _menu = _actions(project, video_selector_manager=selector)

        result = actions.reset_analysis_data_for_videos(["D:/a.mp4"], target_label="x")

        assert result is False
        assert selector.refreshes == []

    def test_the_selector_manager_may_be_given_as_a_getter(self):
        selector = _Selector()
        actions, _dialogs, _menu = _actions(_Project(), video_selector_manager=lambda: selector)

        actions.reset_analysis_data_for_videos([VIDEO], target_label="x")

        assert len(selector.refreshes) == 1

    def test_without_a_selector_manager_a_refresh_event_is_published(self):
        dispatcher = _Dispatcher()
        actions, _dialogs, _menu = _actions(_Project(), event_dispatcher=dispatcher)

        actions.reset_analysis_data_for_videos([VIDEO], target_label="x")

        assert dispatcher.events == [
            (
                UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                payloads.ProjectViewsRefreshRequestedPayload(
                    reason="Analyses reset (drawings preserved)",
                    append_summary=True,
                    immediate=True,
                ),
            )
        ]

    def test_with_neither_refresher_the_reset_still_succeeds(self):
        actions, _dialogs, _menu = _actions(_Project())

        assert actions.reset_analysis_data_for_videos([VIDEO], target_label="x") is True

    def test_delete_all_processing_data_labels_the_dialog_with_the_file_name(self):
        project = _Project()
        actions, dialogs, _menu = _actions(project)

        actions.delete_all_processing_data(VIDEO)

        assert dialogs.confirm_asked == [("CECT_4.mp4", 1, ["CECT_4.mp4"])]
        assert project.reset_calls == [(VIDEO, False)]


class TestLegacyTreeArtifacts:
    @staticmethod
    def _entry(tmp_path: Path, **parquet_files: str) -> dict:
        return {
            "path": str(tmp_path / "CECT_4.mp4"),
            "results_dir": str(tmp_path),
            "parquet_files": parquet_files,
        }

    def test_word_and_excel_reports_become_children_that_open_a_file(self, tmp_path):
        docx = tmp_path / "relatorio.docx"
        xlsx = tmp_path / "sumario.xlsx"
        docx.write_bytes(b"x")
        xlsx.write_bytes(b"x")
        tree = _Tree()
        metadata: dict = {}
        actions, _dialogs, _menu = _actions(
            reports_tree_getter=lambda: tree, report_tree_metadata=metadata
        )
        entry = self._entry(tmp_path, report_docx=str(docx), summary_excel=str(xlsx))

        actions.append_report_artifacts_from_entry("video1", entry)

        assert [(c["parent"], c["text"], c["values"], c["tags"]) for c in tree.inserted] == [
            ("video1", "📝 Word: relatorio.docx", ("", "", "", "", "Open"), ("report-file",)),
            ("video1", "📊 Excel: sumario.xlsx", ("", "", "", "", "Open"), ("report-file",)),
        ]
        assert metadata == {
            "child1": {"type": "file", "path": str(docx), "parent_video": entry["path"]},
            "child2": {"type": "file", "path": str(xlsx), "parent_video": entry["path"]},
        }
        assert tree.opened == [("video1", True)]

    def test_a_stale_recorded_path_falls_back_to_the_file_named_after_the_video(self, tmp_path):
        guessed = tmp_path / "CECT_4_report.docx"
        guessed.write_bytes(b"x")
        tree = _Tree()
        actions, _dialogs, _menu = _actions(reports_tree_getter=lambda: tree)
        entry = self._entry(tmp_path, report_docx=str(tmp_path / "moved" / "old.docx"))

        actions.append_report_artifacts_from_entry("video1", entry)

        assert [c["text"] for c in tree.inserted] == ["📝 Word: CECT_4_report.docx"]

    def test_the_excel_fallback_is_the_summary_workbook(self, tmp_path):
        (tmp_path / "CECT_4_summary.xlsx").write_bytes(b"x")
        tree = _Tree()
        actions, _dialogs, _menu = _actions(reports_tree_getter=lambda: tree)

        actions.append_report_artifacts_from_entry("video1", self._entry(tmp_path))

        assert [c["text"] for c in tree.inserted] == ["📊 Excel: CECT_4_summary.xlsx"]

    def test_without_reports_the_parent_is_left_alone(self, tmp_path):
        tree = _Tree()
        actions, _dialogs, _menu = _actions(reports_tree_getter=lambda: tree)

        actions.append_report_artifacts_from_entry("video1", self._entry(tmp_path))

        assert tree.inserted == []
        assert tree.opened == []

    def test_an_entry_without_a_path_is_ignored(self, tmp_path):
        tree = _Tree()
        actions, _dialogs, _menu = _actions(reports_tree_getter=lambda: tree)

        actions.append_report_artifacts_from_entry("video1", {"results_dir": str(tmp_path)})

        assert tree.inserted == []

    def test_without_a_tree_nothing_happens(self, tmp_path):
        actions, _dialogs, _menu = _actions()

        actions.append_report_artifacts_from_entry("video1", self._entry(tmp_path))


def _widget(tree: _Tree | None) -> SimpleNamespace:
    return SimpleNamespace(tree=tree)


class TestClicks:
    def test_a_single_click_on_a_report_file_opens_it(self, tmp_path, opened):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")
        tree = _Tree(rows={40: "row1"})
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree),
            tree_metadata={"row1": {"type": "file", "file_path": str(report)}},
        )

        actions.on_processing_reports_item_click(SimpleNamespace(num=1, y=40))

        assert opened == [str(report)]

    def test_a_single_click_on_a_video_row_opens_nothing(self, tmp_path, opened):
        tree = _Tree(rows={40: "row1"})
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree),
            tree_metadata={"row1": {"type": "video", "results_dir": str(tmp_path)}},
        )

        actions.on_processing_reports_item_click(SimpleNamespace(num=1, y=40))

        assert opened == []

    def test_a_right_or_middle_click_is_ignored(self, tmp_path, opened):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")
        tree = _Tree(rows={40: "row1"})
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree),
            tree_metadata={"row1": {"type": "file", "path": str(report)}},
        )

        actions.on_processing_reports_item_click(SimpleNamespace(num=3, y=40))

        assert opened == []

    def test_without_an_event_the_selected_row_is_used(self, tmp_path, opened):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")
        tree = _Tree(selection=("sel", "other"))
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree),
            tree_metadata={"sel": {"type": "file", "path": str(report)}},
        )

        actions.on_processing_reports_item_click()

        assert opened == [str(report)]

    def test_a_click_on_empty_space_with_no_selection_does_nothing(self, opened):
        tree = _Tree()
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree), tree_metadata={}
        )

        actions.on_processing_reports_item_click(SimpleNamespace(num=1, y=999))
        actions.on_processing_reports_item_double_click(SimpleNamespace(num=1, y=999))

        assert opened == []

    def test_a_row_without_metadata_does_nothing(self, opened):
        tree = _Tree(rows={40: "row1"})
        actions, _dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree), tree_metadata={}
        )

        actions.on_processing_reports_item_click(SimpleNamespace(num=1, y=40))
        actions.on_processing_reports_item_double_click(SimpleNamespace(num=1, y=40))

        assert opened == []

    def test_without_a_tab_widget_or_tree_nothing_happens(self, opened):
        none_widget, _d1, _m1 = _actions(processing_reports_widget=None)
        no_tree, _d2, _m2 = _actions(processing_reports_widget=_widget(None))

        for actions in (none_widget, no_tree):
            actions.on_processing_reports_item_click(SimpleNamespace(num=1, y=1))
            actions.on_processing_reports_item_double_click(SimpleNamespace(num=1, y=1))

        assert opened == []


class TestDoubleClicks:
    def _double_click(self, tmp_path, metadata: dict, opened: list[str]):
        tree = _Tree(rows={40: "row1"})
        actions, dialogs, _menu = _actions(
            processing_reports_widget=_widget(tree), tree_metadata={"row1": metadata}
        )
        actions.on_processing_reports_item_double_click(SimpleNamespace(num=1, y=40))
        return dialogs

    def test_a_file_node_opens_the_file(self, tmp_path, opened):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")

        self._double_click(tmp_path, {"type": "file", "path": str(report)}, opened)

        assert opened == [str(report)]

    def test_a_video_node_opens_its_results_folder(self, tmp_path, opened):
        self._double_click(tmp_path, {"type": "video", "results_dir": str(tmp_path)}, opened)

        assert opened == [str(tmp_path)]

    def test_an_aquarium_node_opens_its_results_folder(self, tmp_path, opened):
        self._double_click(
            tmp_path,
            {"type": "aquarium", "results_dir": str(tmp_path), "aquarium_id": 1},
            opened,
        )

        assert opened == [str(tmp_path)]

    @pytest.mark.parametrize("node_type", ["video", "aquarium"])
    def test_a_results_folder_that_does_not_exist_is_not_opened(self, tmp_path, opened, node_type):
        self._double_click(
            tmp_path, {"type": node_type, "results_dir": str(tmp_path / "gone")}, opened
        )

        assert opened == []

    @pytest.mark.parametrize("node_type", ["video", "aquarium"])
    def test_a_node_without_a_results_folder_opens_nothing(self, tmp_path, opened, node_type):
        self._double_click(tmp_path, {"type": node_type}, opened)

        assert opened == []

    def test_other_node_types_open_nothing(self, tmp_path, opened):
        self._double_click(tmp_path, {"type": "group", "results_dir": str(tmp_path)}, opened)

        assert opened == []


class TestOpeningReportFiles:
    def test_a_node_without_a_path_warns(self, opened):
        actions, dialogs, _menu = _actions()

        actions.open_report_file_from_metadata({"type": "file"})

        assert dialogs.warnings == [("File unavailable", "The report path was not found.")]
        assert opened == []

    def test_a_file_that_no_longer_exists_warns_with_its_path(self, tmp_path, opened):
        gone = tmp_path / "gone.docx"
        actions, dialogs, _menu = _actions()

        actions.open_report_file_from_metadata({"file_path": str(gone)})

        assert dialogs.warnings == [("File not found", f"The file no longer exists:\n{gone}")]
        assert opened == []

    def test_file_path_wins_over_path(self, tmp_path, opened):
        wanted = tmp_path / "wanted.docx"
        other = tmp_path / "other.docx"
        wanted.write_bytes(b"x")
        other.write_bytes(b"x")
        actions, _dialogs, _menu = _actions()

        actions.open_report_file_from_metadata({"file_path": str(wanted), "path": str(other)})

        assert opened == [str(wanted)]

    def test_an_os_failure_is_shown_to_the_user(self, tmp_path, monkeypatch):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")

        def refuse(_path: Any) -> None:
            raise OSError("no application is associated with the file")

        monkeypatch.setattr(os_opener, "open_path", refuse)
        actions, dialogs, _menu = _actions()

        actions.open_report_file_from_metadata({"path": str(report)})

        assert dialogs.errors == [
            ("Error", "Could not open: no application is associated with the file")
        ]

    def test_the_parent_folder_of_a_report_is_opened(self, tmp_path, opened):
        report = tmp_path / "relatorio.docx"
        report.write_bytes(b"x")
        actions, _dialogs, _menu = _actions()

        actions.open_report_parent_folder_from_metadata({"path": str(report)})

        assert opened == [str(tmp_path)]

    def test_a_parent_folder_that_is_gone_is_not_opened(self, tmp_path, opened):
        actions, dialogs, _menu = _actions()

        actions.open_report_parent_folder_from_metadata({"path": str(tmp_path / "gone" / "r.docx")})
        actions.open_report_parent_folder_from_metadata({})

        assert opened == []
        assert dialogs.warnings == []


class TestOpenUnifiedReport:
    @staticmethod
    def _stamp(path: Path, mtime: float) -> Path:
        path.write_bytes(b"x")
        os.utime(path, (mtime, mtime))
        return path

    def test_without_a_project_path_nothing_happens(self, opened):
        actions, dialogs, _menu = _actions(_Project(None))

        actions.open_unified_report("word")

        assert opened == [] and dialogs.warnings == []

    def test_a_missing_folder_warns(self, tmp_path, opened):
        actions, dialogs, _menu = _actions(_Project(tmp_path))

        actions.open_unified_report("word")

        assert dialogs.warnings == [("Unavailable", "No unified report found.")]

    def test_an_unknown_type_opens_nothing(self, tmp_path, opened):
        (tmp_path / "unified_reports").mkdir()
        actions, dialogs, _menu = _actions(_Project(tmp_path))

        actions.open_unified_report("pdf")

        assert opened == [] and dialogs.warnings == []

    def test_a_folder_without_that_type_warns_with_the_type(self, tmp_path, opened):
        folder = tmp_path / "unified_reports"
        folder.mkdir()
        (folder / "sumario.xlsx").write_bytes(b"x")
        actions, dialogs, _menu = _actions(_Project(tmp_path))

        actions.open_unified_report("word")

        assert dialogs.warnings == [("Unavailable", "No word report found.")]
        assert opened == []

    @pytest.mark.parametrize(
        ("file_type", "suffix"), [("word", ".docx"), ("excel", ".xlsx"), ("parquet", ".parquet")]
    )
    def test_the_newest_report_of_the_requested_type_is_opened(
        self, tmp_path, opened, file_type, suffix
    ):
        folder = tmp_path / "unified_reports"
        folder.mkdir()
        self._stamp(folder / f"old{suffix}", 1_000_000)
        newest = self._stamp(folder / f"new{suffix}", 3_000_000)
        self._stamp(folder / f"mid{suffix}", 2_000_000)
        for other in (".docx", ".xlsx", ".parquet"):
            if other != suffix:
                self._stamp(folder / f"newer_but_other{other}", 9_000_000)
        actions, _dialogs, _menu = _actions(_Project(tmp_path))

        actions.open_unified_report(file_type)

        assert opened == [str(newest)]

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F2-UI-004: reports are written to unified_reports/total/ and "
            "unified_reports/selecionados/ (_unified_report_mixin), but "
            "open_unified_report globs only the top level of unified_reports/, so it "
            "answers 'No word report found.' for every current project. The live "
            "'Open' buttons use ProcessingReportsWidget._open_latest_unified_file, "
            "which walks the subfolders; this method has no production caller."
        ),
    )
    def test_a_report_in_the_total_subfolder_is_found(self, tmp_path, opened):
        total = tmp_path / "unified_reports" / "total"
        total.mkdir(parents=True)
        report = self._stamp(total / "relatorio.docx", 1_000_000)
        actions, _dialogs, _menu = _actions(_Project(tmp_path))

        actions.open_unified_report("word")

        assert opened == [str(report)]


class TestOpenResultsFolderOfAReportVideo:
    @staticmethod
    def _node(**extra: Any) -> dict:
        return {"video_path": VIDEO, **extra}

    def test_a_node_without_a_video_path_does_nothing(self, opened):
        actions, dialogs, _menu = _actions(_Project())

        actions.handle_report_video_node({})

        assert opened == [] and dialogs.warnings == []

    def test_with_a_recorded_summary_the_results_folder_opens(self, tmp_path, opened):
        summary = tmp_path / "CECT_4_summary.xlsx"
        summary.write_bytes(b"x")
        entry = {"results_dir": str(tmp_path), "parquet_files": {"summary_excel": str(summary)}}
        actions, _dialogs, _menu = _actions(_Project(entry=entry))

        actions.handle_report_video_node(self._node())

        assert opened == [str(tmp_path)]

    def test_results_found_next_to_the_expected_name_count_without_a_recorded_path(
        self, tmp_path, opened
    ):
        (tmp_path / "CECT_4_report.docx").write_bytes(b"x")
        actions, _dialogs, _menu = _actions(_Project(entry=None))

        actions.handle_report_video_node(self._node(results_dir=str(tmp_path)))

        assert opened == [str(tmp_path)]

    @pytest.mark.parametrize("name", ["CECT_4_summary.parquet", "CECT_4_summary.xlsx"])
    def test_each_summary_format_counts_as_results(self, tmp_path, opened, name):
        (tmp_path / name).write_bytes(b"x")
        actions, _dialogs, _menu = _actions(_Project(entry=None))

        actions.handle_report_video_node(self._node(results_dir=str(tmp_path)))

        assert opened == [str(tmp_path)]

    def test_a_folder_without_results_warns_and_is_not_opened(self, tmp_path, opened):
        (tmp_path / "3_CoordMovimento_CECT_4.parquet").write_bytes(b"x")
        actions, dialogs, _menu = _actions(_Project(entry=None))

        actions.handle_report_video_node(self._node(results_dir=str(tmp_path)))

        assert dialogs.warnings == [
            (
                "Reports unavailable",
                "Generate the report for this video before opening the results folder.",
            )
        ]
        assert opened == []

    def test_a_results_folder_that_is_gone_warns(self, tmp_path, opened):
        actions, dialogs, _menu = _actions(_Project(entry=None))

        actions.handle_report_video_node(self._node(results_dir=str(tmp_path / "gone")))

        assert len(dialogs.warnings) == 1
        assert opened == []

    def test_the_results_folder_is_resolved_from_the_entry_metadata(self, tmp_path, opened):
        (tmp_path / "CECT_4_report.docx").write_bytes(b"x")
        entry = {
            "metadata": {"group": "G1"},
            "group": "G2",
            "day": "Dia_1",
            "subject": None,
            "group_display_name": "Grupo 1",
            "results_dir": "",
        }
        project = _Project(entry=entry, results_dir=tmp_path)
        actions, _dialogs, _menu = _actions(project)

        actions.handle_report_video_node(self._node())

        # metadata wins over the entry's own group; None values are skipped.
        assert project.resolve_calls == [
            (
                "CECT_4",
                VIDEO,
                {"group": "G1", "group_display_name": "Grupo 1", "day": "Dia_1"},
            )
        ]
        assert opened == [str(tmp_path)]

    def test_the_folder_recorded_in_the_entry_is_used_when_the_node_has_none(
        self, tmp_path, opened
    ):
        (tmp_path / "CECT_4_report.docx").write_bytes(b"x")
        project = _Project(entry={"results_dir": str(tmp_path)})
        actions, _dialogs, _menu = _actions(project)

        actions.handle_report_video_node(self._node())

        assert project.resolve_calls == []
        assert opened == [str(tmp_path)]

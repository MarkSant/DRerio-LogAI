"""Tests for ProjectViewManager helper formatting methods (Phase 4.6 decomposition)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.components.project_views import (
    ReportsTreeManager,
    VideoSelectorTreeManager,
    format_status_label,
    format_status_ratio,
    format_status_summary,
    format_status_token,
    format_video_metadata,
    summarize_batch_data,
    video_sort_key,
)
from zebtrack.ui.event_bus_v2 import UIEvents

pytestmark = pytest.mark.gui


def _make_manager():
    pm = Mock()
    pm.has_arena_data.return_value = False
    pm.has_roi_data.return_value = False
    pm.has_trajectory_data.return_value = False
    pm.has_summary_data.return_value = False
    pm.get_all_videos.return_value = []

    controller = SimpleNamespace(project_manager=pm)
    validation_manager = Mock()
    validation_manager._build_day_title.return_value = "Dia 01"
    gui = SimpleNamespace(
        controller=controller,
        validation_manager=validation_manager,
        dialog_manager=Mock(),
        event_dispatcher=Mock(),
        set_status=Mock(),
    )

    vsm = VideoSelectorTreeManager(gui)
    rtm = ReportsTreeManager(gui)
    return vsm, rtm, gui, pm


def test_format_status_label_pluralization():
    assert format_status_label(1) == "1 vídeo"
    assert format_status_label(2) == "2 vídeos"


def test_format_status_summary_with_zero_total():
    assert format_status_summary(0, 0) == "0 vídeos (0%)"


def test_format_status_summary_percentage():
    assert format_status_summary(10, 3) == "3 vídeos (30%)"


def test_format_status_ratio():
    assert format_status_ratio(3, 7) == "3/7"


def test_summarize_batch_data_counts():
    _vsm, _rtm, _gui, pm = _make_manager()

    pm.has_arena_data.side_effect = [True, False]
    pm.has_roi_data.side_effect = [True, False]
    pm.has_trajectory_data.side_effect = [False, True]
    pm.has_summary_data.side_effect = [True, True]

    videos = [
        {"path": "/path/video1.mp4"},
        {"path": "/path/video2.mp4"},
    ]

    counts = summarize_batch_data(videos, pm)

    assert counts["total"] == 2
    assert counts["with_arena"] == 1
    assert counts["with_rois"] == 1
    assert counts["with_trajectory"] == 1
    assert counts["with_summary"] == 2


def test_format_data_badges_none():
    _vsm, _rtm, _gui, pm = _make_manager()

    pm.has_arena_data.return_value = False
    pm.has_roi_data.return_value = False
    pm.has_trajectory_data.return_value = False

    from zebtrack.ui.components.project_views.project_view_helpers import format_data_badges

    assert format_data_badges("/path/video.mp4", pm) == "—"


def test_format_data_badges_with_flags():
    _vsm, _rtm, _gui, pm = _make_manager()

    pm.has_arena_data.return_value = True
    pm.has_roi_data.return_value = True
    pm.has_trajectory_data.return_value = False

    from zebtrack.ui.components.project_views.project_view_helpers import format_data_badges

    result = format_data_badges("/path/video.mp4", pm)

    assert "🏟" in result
    assert "🎯" in result
    assert "🧭" not in result


def test_format_video_metadata_variants():
    assert format_video_metadata({}) == "Sem metadata"
    assert (
        format_video_metadata({"metadata": {"group": "G1", "day": 2, "subject": 3}})
        == "Grupo: G1 | Dia: 2 | Sujeito: 3"
    )


def test_format_status_token():
    assert format_status_token("pending") == "pending"
    assert format_status_token("") == "—"


def test_build_day_title_delegates():
    vsm, _rtm, gui, _pm = _make_manager()

    result = vsm._build_day_title(1, {"day": 1})

    gui.validation_manager._build_day_title.assert_called_once_with(1, {"day": 1})
    assert result == "Dia 01"


def test_video_sort_key_numeric_and_text():
    assert video_sort_key("5")[0] == 0
    assert video_sort_key("abc")[0] == 1


def test_resolve_unified_strategy_no_project_path_defaults_append():
    _vsm, rtm, _gui, pm = _make_manager()
    pm.project_path = None

    assert rtm._generator._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_yes_means_replace(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports" / "total"
    unified_dir.mkdir(parents=True)
    (unified_dir / "unified.parquet").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = True

    assert rtm._generator._resolve_unified_generation_strategy() is True


def test_resolve_unified_strategy_existing_no_means_append(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports" / "total"
    unified_dir.mkdir(parents=True)
    (unified_dir / "unified.xlsx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = False

    assert rtm._generator._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_cancel_returns_none(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports" / "total"
    unified_dir.mkdir(parents=True)
    (unified_dir / "unified.docx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = None

    assert rtm._generator._resolve_unified_generation_strategy() is None
    gui.set_status.assert_called_once()


def test_processing_reports_generate_partial_dispatches_unified_selected_payload():
    _vsm, rtm, gui, pm = _make_manager()
    selected_video = {"path": "/videos/v1.mp4", "status": "complete"}
    pm.get_all_videos.return_value = [selected_video]

    mock_widget = Mock()
    mock_widget.get_selection.return_value = ("video_item_1",)
    rtm._generator._processing_reports_widget = mock_widget
    rtm._generator._tree_metadata = {
        "video_item_1": {"type": "video", "video_path": "/videos/v1.mp4"}
    }

    rtm._generator._resolve_unified_generation_strategy = Mock(return_value=True)

    rtm.on_processing_reports_generate_partial()

    gui.event_dispatcher.publish_event.assert_called_once_with(
        UIEvents.REPORT_GENERATE,
        payloads.ReportGeneratePayload(
            videos=[selected_video],
            report_type="unified",
            report_scope="selected",
            replace_existing=True,
        ),
    )


def test_processing_reports_right_click_video_opens_context_menu():
    _vsm, rtm, gui, _pm = _make_manager()
    gui.menu_manager = Mock()
    rtm._tree_metadata["video_item_1"] = {
        "type": "video",
        "video_path": "/videos/v1.mp4",
    }

    rtm._on_processing_reports_right_click(
        payloads.ProjectContextMenuClickPayload(
            item_id="video_item_1",
            column_id="#3",
            x=120,
            y=220,
        )
    )

    gui.menu_manager.show_processing_reports_context_menu.assert_called_once()
    call_args = gui.menu_manager.show_processing_reports_context_menu.call_args
    assert call_args.args[:4] == ("/videos/v1.mp4", "#3", 120, 220)
    assert "delete_choice" in call_args.args[4]


def test_processing_reports_right_click_video_uses_aquarium_asset_availability():
    _vsm, rtm, gui, pm = _make_manager()
    gui.menu_manager = Mock()
    pm.find_video_entry.return_value = {
        "multi_aquarium_outputs": {
            "1": {
                "parquet_files": {
                    "trajectory": "/videos/v1_aq1_traj.parquet",
                    "report_docx": "/videos/v1_aq1_report.docx",
                }
            }
        }
    }
    pm.has_arena_data.return_value = True
    pm.has_roi_data.return_value = False
    pm.has_trajectory_data.return_value = False
    pm.has_summary_data.return_value = False

    rtm._tree_metadata["video_item_1"] = {
        "type": "video",
        "video_path": "/videos/v1.mp4",
        "aquarium_id": 1,
    }

    rtm._on_processing_reports_right_click(
        payloads.ProjectContextMenuClickPayload(
            item_id="video_item_1",
            column_id="#3",
            x=120,
            y=220,
        )
    )

    gui.menu_manager.show_processing_reports_context_menu.assert_called_once()
    kwargs = gui.menu_manager.show_processing_reports_context_menu.call_args.kwargs
    assert kwargs["asset_availability"] == {
        "arena": True,
        "rois": False,
        "trajectory": True,
        "summary": True,
    }


def test_processing_reports_right_click_file_routes_to_file_context_menu():
    _vsm, rtm, _gui, _pm = _make_manager()
    rtm._show_report_file_context_menu = Mock()
    rtm._tree_metadata["file_item_1"] = {
        "type": "file",
        "file_path": "/videos/v1_results/report.docx",
    }

    rtm._on_processing_reports_right_click(
        payloads.ProjectContextMenuClickPayload(
            item_id="file_item_1",
            column_id="#0",
            x=320,
            y=420,
        )
    )

    rtm._show_report_file_context_menu.assert_called_once_with(
        {"type": "file", "file_path": "/videos/v1_results/report.docx"},
        320,
        420,
    )


def test_processing_reports_item_click_ignores_right_click_events():
    _vsm, rtm, _gui, _pm = _make_manager()
    tree = Mock()
    tree.identify_row.return_value = "file_item_1"
    rtm._assets._processing_reports_widget = SimpleNamespace(tree=tree)
    rtm._assets._tree_metadata = {
        "file_item_1": {"type": "file", "file_path": "/videos/v1_results/report.docx"}
    }
    rtm._assets._handle_report_file_node = Mock()

    event = SimpleNamespace(y=12, num=3)
    rtm._assets.on_processing_reports_item_click(event)

    rtm._assets._handle_report_file_node.assert_not_called()


def test_processing_reports_hierarchy_delete_project_publishes_subject_event():
    _vsm, rtm, gui, _pm = _make_manager()
    tree = Mock()
    tree.item.return_value = "🐟 Sujeito C1"
    gui.processing_reports_widget = SimpleNamespace(tree=tree)
    gui.dialog_manager.choose_processing_reports_delete_mode.return_value = "project"
    gui.dialog_manager.confirm_delete_hierarchy_node.return_value = (True, False)

    rtm._collect_descendant_video_paths = Mock(return_value=["/videos/v1.mp4"])

    rtm._handle_hierarchy_delete_action(
        "subject_node",
        {"type": "subject", "group_id": "G1", "day_id": "1", "subject_id": "C1"},
    )

    gui.event_dispatcher.publish_event.assert_called_once_with(
        UIEvents.PROJECT_DELETE_SUBJECT,
        payloads.ProjectDeleteSubjectPayload(
            group_id="G1",
            day_id="1",
            subject_id="C1",
            delete_files=False,
        ),
    )


def test_processing_reports_hierarchy_delete_data_only_cleans_descendant_videos():
    _vsm, rtm, gui, _pm = _make_manager()
    tree = Mock()
    tree.item.return_value = "📅 Dia 01"
    gui.processing_reports_widget = SimpleNamespace(tree=tree)
    gui.dialog_manager.choose_processing_reports_delete_mode.return_value = "data"
    rtm._collect_descendant_video_paths = Mock(return_value=["/videos/v1.mp4", "/videos/v2.mp4"])
    rtm._assets.reset_analysis_data_for_videos = Mock()

    rtm._handle_hierarchy_delete_action(
        "day_node",
        {"type": "day", "group_id": "G1", "day_id": "1"},
    )

    rtm._assets.reset_analysis_data_for_videos.assert_called_once_with(
        ["/videos/v1.mp4", "/videos/v2.mp4"],
        target_label="Dia 01",
    )


def test_processing_reports_refresh_uses_late_video_selector_manager():
    _vsm, rtm, gui, _pm = _make_manager()
    gui.video_selector_manager = Mock()

    rtm._assets._refresh_project_views("refresh")

    gui.video_selector_manager.refresh_project_views.assert_called_once_with(
        reason="refresh",
        append_summary=True,
    )


def test_processing_reports_refresh_falls_back_to_refresh_event():
    _vsm, rtm, gui, _pm = _make_manager()

    rtm._assets._refresh_project_views("refresh")

    gui.event_dispatcher.publish_event.assert_called_once_with(
        UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
        payloads.ProjectViewsRefreshRequestedPayload(
            reason="refresh",
            append_summary=True,
            immediate=True,
        ),
    )


def test_project_overview_double_click_opens_partial_report_file(tmp_path):
    vsm, _rtm, gui, _pm = _make_manager()
    report_path = tmp_path / "PartialReport_Dia1_Controle.xlsx"
    report_path.write_text("x")

    gui.project_overview_tree = Mock()
    gui.project_overview_tree.item.return_value = ()
    gui.project_overview_widget = SimpleNamespace(
        _iid_to_report_path={"partial_item": str(report_path)}
    )
    gui.canvas_manager = Mock()

    with patch("zebtrack.utils.os_opener.open_path") as mock_open_path:
        vsm.handle_project_overview_double_click("partial_item")

    mock_open_path.assert_called_once_with(str(report_path))
    gui.canvas_manager.load_video_frame_to_canvas.assert_not_called()


def test_processing_reports_hierarchy_metadata_edit_updates_descendant_videos():
    _vsm, rtm, gui, pm = _make_manager()
    gui.root = Mock()
    gui.event_bus_v2 = Mock()
    tree = Mock()
    tree.item.return_value = "🐟 Sujeito C1"
    gui.processing_reports_widget = SimpleNamespace(tree=tree)
    pm.get_available_groups.return_value = ["G1", "G2"]
    pm.update_batch_video_metadata.return_value = 2
    rtm._collect_descendant_video_paths = Mock(return_value=["/videos/v1.mp4", "/videos/v2.mp4"])
    rtm.refresh_processing_reports_tab = Mock()

    from unittest.mock import patch

    with patch(
        "zebtrack.ui.components.project_views.reports_tree_manager.BatchVideoMetadataDialog"
    ) as mock_dialog:
        mock_dialog.return_value.result = {"group": "G2", "day": 2, "subject": "C9"}

        rtm._handle_hierarchy_metadata_edit_action(
            "subject_node",
            {"type": "subject", "group_id": "G1", "day_id": "1", "subject_id": "C1"},
        )

    pm.update_batch_video_metadata.assert_called_once_with(
        ["/videos/v1.mp4", "/videos/v2.mp4"],
        {"group": "G2", "day": 2, "subject": "C9"},
    )
    rtm.refresh_processing_reports_tab.assert_called_once()
    gui.set_status.assert_called_once()
    assert gui.event_bus_v2.publish.call_count == 2


def test_processing_reports_aquarium_delete_scope_publishes_event():
    _vsm, rtm, gui, _pm = _make_manager()
    gui.dialog_manager.ask_yes_no.side_effect = [True, False]

    rtm._handle_delete_aquarium_scope(
        {"type": "aquarium", "video_path": "/videos/v1.mp4", "aquarium_id": 1}
    )

    gui.event_dispatcher.publish_event.assert_called_once_with(
        UIEvents.PROJECT_DELETE_AQUARIUM,
        payloads.ProjectDeleteAquariumPayload(
            video_path="/videos/v1.mp4",
            aquarium_id=1,
            delete_files=False,
            delete_zone=True,
        ),
    )


def test_processing_reports_aquarium_reset_analysis_publishes_event():
    _vsm, rtm, gui, _pm = _make_manager()
    gui.dialog_manager.ask_yes_no.side_effect = [True, True]

    rtm._handle_reset_aquarium_analysis(
        {"type": "aquarium", "video_path": "/videos/v1.mp4", "aquarium_id": 0}
    )

    gui.event_dispatcher.publish_event.assert_called_once_with(
        UIEvents.PROJECT_RESET_ANALYSIS_DATA,
        payloads.ProjectResetAnalysisDataPayload(
            video_path="/videos/v1.mp4",
            aquarium_id=0,
            delete_files=True,
        ),
    )

"""Tests for ProjectViewManager helper formatting methods."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.project_view_manager import ProjectViewManager
from zebtrack.ui.events import Events

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

    return ProjectViewManager(gui), gui, pm


def test_format_status_label_pluralization():
    manager, _gui, _pm = _make_manager()

    assert manager.format_status_label(1) == "1 vídeo"
    assert manager.format_status_label(2) == "2 vídeos"


def test_format_status_summary_with_zero_total():
    manager, _gui, _pm = _make_manager()

    assert manager.format_status_summary(0, 0) == "0 vídeos (0%)"


def test_format_status_summary_percentage():
    manager, _gui, _pm = _make_manager()

    assert manager.format_status_summary(10, 3) == "3 vídeos (30%)"


def test_format_status_ratio():
    manager, _gui, _pm = _make_manager()

    assert manager.format_status_ratio(3, 7) == "3/7"


def test_summarize_batch_data_counts():
    manager, _gui, pm = _make_manager()

    pm.has_arena_data.side_effect = [True, False]
    pm.has_roi_data.side_effect = [True, False]
    pm.has_trajectory_data.side_effect = [False, True]
    pm.has_summary_data.side_effect = [True, True]

    videos = [
        {"path": "/path/video1.mp4"},
        {"path": "/path/video2.mp4"},
    ]

    counts = manager.summarize_batch_data(videos)

    assert counts["total"] == 2
    assert counts["with_arena"] == 1
    assert counts["with_rois"] == 1
    assert counts["with_trajectory"] == 1
    assert counts["with_summary"] == 2


def test_format_data_badges_none():
    manager, _gui, pm = _make_manager()

    pm.has_arena_data.return_value = False
    pm.has_roi_data.return_value = False
    pm.has_trajectory_data.return_value = False

    assert manager.format_data_badges("/path/video.mp4") == "—"


def test_format_data_badges_with_flags():
    manager, _gui, pm = _make_manager()

    pm.has_arena_data.return_value = True
    pm.has_roi_data.return_value = True
    pm.has_trajectory_data.return_value = False

    result = manager.format_data_badges("/path/video.mp4")

    assert "🏟" in result
    assert "🎯" in result
    assert "🧭" not in result


def test_format_video_metadata_variants():
    manager, _gui, _pm = _make_manager()

    assert manager.format_video_metadata({}) == "Sem metadata"
    assert (
        manager.format_video_metadata({"metadata": {"group": "G1", "day": 2, "subject": 3}})
        == "Grupo: G1 | Dia: 2 | Sujeito: 3"
    )


def test_format_status_token():
    assert ProjectViewManager.format_status_token("pending") == "pending"
    assert ProjectViewManager.format_status_token("") == "—"


def test_build_day_title_delegates():
    manager, gui, _pm = _make_manager()

    result = manager._build_day_title(1, {"day": 1})

    gui.validation_manager._build_day_title.assert_called_once_with(1, {"day": 1})
    assert result == "Dia 01"


def test_video_sort_key_numeric_and_text():
    assert ProjectViewManager._video_sort_key("5")[0] == 0
    assert ProjectViewManager._video_sort_key("abc")[0] == 1


def test_resolve_unified_strategy_no_project_path_defaults_append():
    manager, _gui, pm = _make_manager()
    pm.project_path = None

    assert manager._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_yes_means_replace(tmp_path):
    manager, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.parquet").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = True

    assert manager._resolve_unified_generation_strategy() is True


def test_resolve_unified_strategy_existing_no_means_append(tmp_path):
    manager, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.xlsx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = False

    assert manager._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_cancel_returns_none(tmp_path):
    manager, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.docx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = None

    assert manager._resolve_unified_generation_strategy() is None
    gui.set_status.assert_called_once()


def test_processing_reports_generate_partial_dispatches_unified_selected_payload():
    manager, gui, pm = _make_manager()
    pm.get_all_videos.return_value = [{"path": "/videos/v1.mp4", "status": "complete"}]

    gui.processing_reports_widget = Mock()
    gui.processing_reports_widget.get_selection.return_value = ("video_item_1",)
    gui._processing_reports_tree_metadata = {
        "video_item_1": {"type": "video", "video_path": "/videos/v1.mp4"}
    }

    manager._resolve_unified_generation_strategy = Mock(return_value=True)

    manager.on_processing_reports_generate_partial()

    gui.event_dispatcher.publish_event.assert_called_once_with(
        Events.REPORT_GENERATE,
        {
            "videos": [{"path": "/videos/v1.mp4", "status": "complete"}],
            "report_type": "unified",
            "report_scope": "selected",
            "replace_existing": True,
        },
    )

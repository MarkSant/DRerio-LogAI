"""Tests for ProjectViewManager helper formatting methods (Phase 4.6 decomposition)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
from zebtrack.ui.event_bus_v2 import Event, UIEvents

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

    assert rtm._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_yes_means_replace(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.parquet").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = True

    assert rtm._resolve_unified_generation_strategy() is True


def test_resolve_unified_strategy_existing_no_means_append(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.xlsx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = False

    assert rtm._resolve_unified_generation_strategy() is False


def test_resolve_unified_strategy_existing_cancel_returns_none(tmp_path):
    _vsm, rtm, gui, pm = _make_manager()
    pm.project_path = str(tmp_path)
    unified_dir = Path(tmp_path) / "unified_reports"
    unified_dir.mkdir()
    (unified_dir / "unified.docx").write_text("x")
    gui.dialog_manager.ask_yes_no_cancel.return_value = None

    assert rtm._resolve_unified_generation_strategy() is None
    gui.set_status.assert_called_once()


def test_processing_reports_generate_partial_dispatches_unified_selected_payload():
    _vsm, rtm, gui, pm = _make_manager()
    pm.get_all_videos.return_value = [{"path": "/videos/v1.mp4", "status": "complete"}]

    gui.processing_reports_widget = Mock()
    gui.processing_reports_widget.get_selection.return_value = ("video_item_1",)
    gui._processing_reports_tree_metadata = {
        "video_item_1": {"type": "video", "video_path": "/videos/v1.mp4"}
    }

    rtm._resolve_unified_generation_strategy = Mock(return_value=True)

    rtm.on_processing_reports_generate_partial()

    gui.event_dispatcher.publish.assert_called_once_with(
        Event(
            type=UIEvents.REPORT_GENERATE,
            data={
                "videos": [{"path": "/videos/v1.mp4", "status": "complete"}],
                "report_type": "unified",
                "report_scope": "selected",
                "replace_existing": True,
            },
        )
    )

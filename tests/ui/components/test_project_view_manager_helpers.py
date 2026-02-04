"""Tests for ProjectViewManager helper formatting methods."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.project_view_manager import ProjectViewManager

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
    gui = SimpleNamespace(controller=controller, validation_manager=validation_manager)

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

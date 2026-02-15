"""Tests for VideoSelectionService."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from zebtrack.core.video_selection_service import VideoSelectionService


def test_select_pending_filters_processed():
    service = VideoSelectionService()

    all_videos = [
        {"path": "a.mp4", "status": "pending"},
        {"path": "b.mp4", "status": "processed"},
        {"path": "c.mp4", "status": "complete"},
        {"path": "d.mp4", "status": "error"},
    ]

    result = service.select_candidates(all_videos)

    assert result.selection_mode == "pending"
    assert result.candidate_count == 2
    assert {v["path"] for v in result.candidate_entries} == {"a.mp4", "d.mp4"}
    assert result.missing_targets == []


def test_select_targeted_matches_normalized(monkeypatch):
    service = VideoSelectionService()

    def normalize(path: str) -> str | None:
        return path.lower()

    monkeypatch.setattr("zebtrack.core.video_manager.VideoManager.normalize_path", normalize)

    all_videos = [
        {"path": "A.MP4", "status": "pending"},
        {"path": "B.MP4", "status": "pending"},
    ]

    result = service.select_candidates(all_videos, target_paths=["a.mp4"])

    assert result.selection_mode == "targeted"
    assert result.candidate_count == 1
    assert result.candidate_entries[0]["path"] == "A.MP4"
    assert result.missing_targets == []


def test_select_targeted_tracks_missing(monkeypatch):
    service = VideoSelectionService()

    def normalize(path: str) -> str | None:
        return path.lower()

    monkeypatch.setattr("zebtrack.core.video_manager.VideoManager.normalize_path", normalize)

    all_videos = [{"path": "A.MP4", "status": "pending"}]

    result = service.select_candidates(all_videos, target_paths=["a.mp4", "missing.mp4"])

    assert result.selection_mode == "targeted"
    assert result.candidate_count == 1
    assert result.missing_targets == ["missing.mp4"]
    assert result.has_missing is True


def test_select_targeted_ignores_sub_entries(monkeypatch):
    service = VideoSelectionService()

    def normalize(path: str) -> str | None:
        return path

    monkeypatch.setattr("zebtrack.core.video_manager.VideoManager.normalize_path", normalize)

    all_videos = [{"path": "video.mp4", "status": "pending"}]

    result = service.select_candidates(all_videos, target_paths=["_sub_123"])

    assert result.selection_mode == "targeted"
    assert result.candidate_count == 0
    assert result.missing_targets == []


def test_select_candidates_handles_invalid_paths(monkeypatch):
    service = VideoSelectionService()

    normalize_mock = MagicMock(side_effect=lambda path: path if path else None)
    monkeypatch.setattr("zebtrack.core.video_manager.VideoManager.normalize_path", normalize_mock)

    all_videos: list[dict[str, object]] = [
        {"path": "video.mp4", "status": "pending"},
        {"path": None},
    ]

    result = service.select_candidates(all_videos, target_paths=[cast(str, None), "", "video.mp4"])

    assert result.candidate_count == 1
    assert result.candidate_entries[0]["path"] == "video.mp4"
    assert result.missing_targets == []


@pytest.mark.parametrize(
    "status,expected", [("processed", 0), ("complete", 0), ("pending", 1), ("error", 1)]
)
def test_select_pending_statuses(status, expected):
    service = VideoSelectionService()

    result = service.select_candidates([{"path": "x.mp4", "status": status}])

    assert result.candidate_count == expected

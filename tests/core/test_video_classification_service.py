"""Tests for VideoClassificationService."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.core.video.video_classification_service import VideoClassificationService

_NORMALIZE_ATTR = "zebtrack.core.project.video_manager.VideoManager.normalize_path"


def _normalize(path: str) -> str | None:
    return path.lower() if path else None


def test_classify_videos_buckets(monkeypatch):
    service = VideoClassificationService()

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    candidates: list[dict[str, object]] = [
        {"path": "A.MP4"},
        {"path": "B.MP4"},
        {"path": "C.MP4"},
        {"path": "D.MP4"},
    ]

    info_by_norm: dict[str, dict[str, Any]] = {
        "a.mp4": {"has_arena": True, "has_rois": True, "has_trajectory": True},
        "b.mp4": {"has_arena": True, "has_rois": True, "has_trajectory": False},
        "c.mp4": {"has_arena": True, "has_rois": False},
        "d.mp4": {"has_arena": False},
    }

    result = service.classify_videos(candidates, info_by_norm)

    assert [v["path"] for v in result.ready_with_trajectory] == ["A.MP4"]
    assert [v["path"] for v in result.ready_with_zones] == ["B.MP4"]
    assert [v["path"] for v in result.arena_only] == ["C.MP4"]
    assert [v["path"] for v in result.without_arena] == ["D.MP4"]
    assert result.data_changed is True


def test_classify_videos_copies_scan_data(monkeypatch):
    service = VideoClassificationService()

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    video = {"path": "A.MP4"}
    info_by_norm = {
        "a.mp4": {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": False,
            "parquet_files": {"arena": "arena.parquet"},
            "has_data": True,
        }
    }

    result = service.classify_videos([video], info_by_norm)

    assert result.ready_with_zones[0]["parquet_files"] == {"arena": "arena.parquet"}
    assert result.ready_with_zones[0]["has_data"] is True


def test_classify_videos_skips_invalid_entries(monkeypatch):
    service = VideoClassificationService()

    normalize_mock = MagicMock(side_effect=_normalize)
    monkeypatch.setattr(_NORMALIZE_ATTR, normalize_mock)

    candidates: list[dict[str, object]] = [
        {"path": ""},
        {"path": None},
        {"path": "A.MP4"},
    ]
    info_by_norm: dict[str, dict[str, Any]] = {"a.mp4": {"has_arena": False}}

    result = service.classify_videos(candidates, info_by_norm)

    assert len(result.without_arena) == 1
    assert result.without_arena[0]["path"] == "A.MP4"


def test_classify_videos_missing_info(monkeypatch):
    service = VideoClassificationService()

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    candidates: list[dict[str, object]] = [{"path": "A.MP4"}]
    info_by_norm: dict[str, dict[str, Any]] = {}

    result = service.classify_videos(candidates, info_by_norm)

    assert result.ready_with_trajectory == []
    assert result.without_arena == []

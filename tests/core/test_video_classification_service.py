"""Tests for VideoClassificationService."""

from __future__ import annotations

from typing import Any, ClassVar
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


def test_classify_videos_honors_aquarium_filter(monkeypatch):
    service = VideoClassificationService()

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    video = {"path": "VIDEO.MP4", "has_trajectory": True}
    info_by_norm = {
        "video.mp4": {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "aquarium_flags": {
                0: {
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                    "has_complete_data": True,
                },
                1: {
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                    "has_complete_data": False,
                },
            },
        }
    }

    result = service.classify_videos(
        [video],
        info_by_norm,
        aquarium_filter={"video.mp4": [1]},
    )

    assert result.ready_with_trajectory == []
    assert [entry["path"] for entry in result.ready_with_zones] == ["VIDEO.MP4"]
    assert result.ready_with_zones[0]["has_trajectory"] is False
    assert video["has_trajectory"] is True


# ---------------------------------------------------------------------------
# Selection-aware flags and unnormalisable paths (TASK-087)
# ---------------------------------------------------------------------------


class TestEffectiveFlagsForAquariumSelection:
    INFO: ClassVar[dict[str, Any]] = {
        "has_arena": True,
        "has_rois": True,
        "has_trajectory": True,
        "has_complete_data": True,
        "aquarium_flags": {
            0: {"has_arena": True, "has_rois": True, "has_trajectory": True},
            1: {"has_arena": True, "has_rois": False, "has_trajectory": False},
        },
    }

    def _flags(self, aquarium_filter, path="C:/Videos/A.mp4", info=None):
        from zebtrack.core.video.video_classification_service import (
            VideoClassificationService,
        )

        return VideoClassificationService._resolve_effective_flags(
            info or self.INFO, path, aquarium_filter
        )

    def test_without_a_filter_or_a_path_the_stored_flags_stand(self):
        stored = {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_complete_data": True,
        }
        assert self._flags(None) == stored
        assert self._flags({"C:/Videos/A.mp4": [1]}, path=None) == stored

    def test_the_selected_aquarium_alone_decides_and_completeness_is_recomputed(self):
        # Aquarium 1 has an arena but no ROIs and no trajectory: NOT complete,
        # whatever the video-level flag says.
        assert self._flags({"c:/videos/a.mp4": [1]}) == {
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": False,
            "has_complete_data": False,
        }

    def test_any_selected_aquarium_counts_and_all_three_assets_make_it_complete(self):
        assert self._flags({"C:/Videos/A.mp4": [0, 1]})["has_complete_data"] is True

    def test_selected_ids_the_video_has_no_flags_for_leave_nothing_ready(self):
        assert self._flags({"C:/Videos/A.mp4": [7]}) == {
            "has_arena": False,
            "has_rois": False,
            "has_trajectory": False,
            "has_complete_data": False,
        }

    def test_a_filter_for_another_video_or_an_empty_selection_changes_nothing(self):
        assert self._flags({"C:/Videos/B.mp4": [1]})["has_complete_data"] is True
        assert self._flags({"C:/Videos/A.mp4": []})["has_complete_data"] is True

    def test_a_video_without_per_aquarium_flags_keeps_its_stored_ones(self):
        info = {"has_arena": True, "has_rois": False, "has_trajectory": True}
        assert self._flags({"C:/Videos/A.mp4": [1]}, info=info) == {
            "has_arena": True,
            "has_rois": False,
            "has_trajectory": True,
            "has_complete_data": False,
        }

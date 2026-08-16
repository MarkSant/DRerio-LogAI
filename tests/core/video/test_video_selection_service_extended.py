"""
Extended unit tests for VideoSelectionService in core/video/video_selection_service.py.
"""

from __future__ import annotations

import pytest

from zebtrack.core.video.video_selection_service import (
    VideoSelectionResult,
    VideoSelectionService,
)


class TestVideoSelectionResultExtended:
    """Test VideoSelectionResult properties."""

    def test_properties(self):
        res = VideoSelectionResult(
            candidate_entries=[{"path": "/v1.mp4"}],
            missing_targets=["/v2.mp4"],
            selection_mode="targeted",
        )
        assert res.has_missing is True
        assert res.candidate_count == 1

        empty = VideoSelectionResult()
        assert empty.has_missing is False
        assert empty.candidate_count == 0


class TestVideoSelectionServiceExtended:
    """Test VideoSelectionService targeted and pending selection workflows."""

    @pytest.fixture
    def service(self) -> VideoSelectionService:
        return VideoSelectionService()

    def test_select_pending_mode(self, service: VideoSelectionService):
        all_videos = [
            {"path": "video1.mp4", "status": "pending"},
            {"path": "video2.mp4", "status": "processed"},
            {"path": "video3.mp4", "status": "complete"},
            {"path": "video4.mp4"},  # no status -> defaults to pending
        ]
        result = service.select_candidates(all_videos)
        assert result.selection_mode == "pending"
        assert result.candidate_count == 2
        paths = [v["path"] for v in result.candidate_entries]
        assert "video1.mp4" in paths
        assert "video4.mp4" in paths
        assert result.has_missing is False

    def test_select_targeted_mode(self, service: VideoSelectionService):
        all_videos = [
            {"path": "video1.mp4", "status": "processed"},
            {"path": "video2.mp4", "status": "pending"},
        ]
        result = service.select_candidates(
            all_videos, target_paths=["video1.mp4", "nonexistent.mp4"]
        )
        assert result.selection_mode == "targeted"
        assert result.candidate_count == 1
        assert result.candidate_entries[0]["path"] == "video1.mp4"
        assert result.has_missing is True
        assert "nonexistent.mp4" in result.missing_targets

    def test_select_targeted_ignores_sub_tree_ids(self, service: VideoSelectionService):
        all_videos = [{"path": "video1.mp4"}]
        result = service.select_candidates(
            all_videos, target_paths=["video1.mp4", "video1_sub_0.mp4"]
        )
        # video1_sub_0 contains "_sub_" so it is not listed in missing_targets
        assert result.candidate_count == 1
        assert result.missing_targets == []

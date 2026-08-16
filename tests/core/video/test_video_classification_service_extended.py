"""
Extended unit tests for VideoClassificationService in core/video/video_classification_service.py.
"""

from __future__ import annotations

import pytest

from zebtrack.core.project.video_manager import VideoManager
from zebtrack.core.video.video_classification_service import (
    VideoClassificationService,
)


class TestVideoClassificationServiceExtended:
    """Test VideoClassificationService categorization into processing buckets."""

    @pytest.fixture
    def service(self) -> VideoClassificationService:
        return VideoClassificationService()

    def test_classify_videos_all_categories(self, service: VideoClassificationService):
        v_traj = {"path": "v_traj.mp4"}
        v_zones = {"path": "v_zones.mp4"}
        v_arena = {"path": "v_arena.mp4"}
        v_no_arena = {"path": "v_none.mp4"}

        norm_traj = VideoManager.normalize_path("v_traj.mp4")
        norm_zones = VideoManager.normalize_path("v_zones.mp4")
        norm_arena = VideoManager.normalize_path("v_arena.mp4")
        norm_none = VideoManager.normalize_path("v_none.mp4")

        info_by_norm = {
            norm_traj: {
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
                "has_complete_data": True,
            },
            norm_zones: {
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False,
                "has_complete_data": False,
            },
            norm_arena: {
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            },
            norm_none: {
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            },
        }

        candidates = [v_traj, v_zones, v_arena, v_no_arena]
        result = service.classify_videos(candidates, info_by_norm)

        assert len(result.ready_with_trajectory) == 1
        assert result.ready_with_trajectory[0]["path"] == "v_traj.mp4"

        assert len(result.ready_with_zones) == 1
        assert result.ready_with_zones[0]["path"] == "v_zones.mp4"

        assert len(result.arena_only) == 1
        assert result.arena_only[0]["path"] == "v_arena.mp4"

        assert len(result.without_arena) == 1
        assert result.without_arena[0]["path"] == "v_none.mp4"

        assert result.data_changed is True

    def test_classify_videos_empty_or_invalid_entries(self, service: VideoClassificationService):
        result = service.classify_videos(
            [{"path": ""}, {"no_path_key": True}],
            info_by_norm={},
        )
        assert len(result.ready_with_trajectory) == 0
        assert len(result.ready_with_zones) == 0
        assert len(result.arena_only) == 0
        assert len(result.without_arena) == 0

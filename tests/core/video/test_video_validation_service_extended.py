"""
Extended unit tests for VideoValidationService in core/video/video_validation_service.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import AquariumData, MultiAquariumZoneData
from zebtrack.core.project.video_manager import VideoManager
from zebtrack.core.video.video_validation_service import (
    VideoScanResult,
    VideoValidationService,
)


class TestVideoScanResultExtended:
    """Test VideoScanResult value object properties."""

    def test_properties(self):
        res = VideoScanResult(
            info_by_norm={"/v1.mp4": {}},
            missing_files=["/v2.mp4"],
            scanned_videos=[{"path": "/v1.mp4"}],
        )
        assert res.has_missing is True
        assert res.scan_count == 1

        empty = VideoScanResult()
        assert empty.has_missing is False
        assert empty.scan_count == 0


class TestVideoValidationServiceExtended:
    """Test VideoValidationService path scanning and multi-aquarium enrichment."""

    @pytest.fixture
    def service(self) -> VideoValidationService:
        return VideoValidationService()

    def test_normalize_aquarium_key(self, service: VideoValidationService):
        assert service._normalize_aquarium_key(0) == 0
        assert service._normalize_aquarium_key("aquarium_1") == 1
        assert service._normalize_aquarium_key("AQ02") == 2
        assert service._normalize_aquarium_key("no_digits") is None

    def test_scan_and_validate_paths_single_aquarium(self, service: VideoValidationService):
        mock_pm = MagicMock()
        mock_pm.scan_input_paths.return_value = [
            {"path": "video1.mp4", "has_arena": False, "has_rois": False}
        ]
        mock_pm.find_video_entry.return_value = {
            "path": "video1.mp4",
            "has_arena": True,
            "has_rois": True,
        }
        mock_pm.get_multi_aquarium_zone_data.return_value = None

        result = service.scan_and_validate_paths(["video1.mp4", "missing.mp4"], mock_pm)

        assert result.scan_count == 1
        assert result.has_missing is True
        assert "missing.mp4" in result.missing_files

        norm_path = VideoManager.normalize_path("video1.mp4")
        info = result.info_by_norm[norm_path]
        assert info["has_arena"] is True
        assert info["has_rois"] is True

    def test_scan_and_validate_paths_multi_aquarium(self, service: VideoValidationService):
        mock_pm = MagicMock()
        mock_pm.scan_input_paths.return_value = [{"path": "multi_video.mp4"}]
        mock_pm.find_video_entry.return_value = {"path": "multi_video.mp4"}

        aq0 = AquariumData(id=0, polygon=[[0, 0], [10, 0], [10, 10]])
        aq1 = AquariumData(id=1, polygon=[[20, 20], [30, 20], [30, 30]])
        multi_data = MultiAquariumZoneData(aquariums=[aq0, aq1])
        mock_pm.get_multi_aquarium_zone_data.return_value = multi_data
        mock_pm.get_aquarium_asset_flags.side_effect = lambda path, aq_id: {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": aq_id == 0,
            "has_complete_data": aq_id == 0,
        }

        result = service.scan_and_validate_paths(["multi_video.mp4"], mock_pm)

        assert result.scan_count == 1
        norm_path = VideoManager.normalize_path("multi_video.mp4")
        info = result.info_by_norm[norm_path]
        assert info["is_multi_aquarium"] is True
        assert 0 in info["aquarium_flags"]
        assert 1 in info["aquarium_flags"]
        assert info["has_arena"] is True
        assert info["has_trajectory"] is True

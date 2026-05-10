"""Tests for VideoValidationService."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from zebtrack.core.video.video_validation_service import VideoValidationService

_NORMALIZE_ATTR = "zebtrack.core.project.video_manager.VideoManager.normalize_path"


@dataclass
class _Aquarium:
    id: int
    polygon: list
    roi_polygons: list


@dataclass
class _MultiZoneData:
    aquariums: list[_Aquarium]


def _normalize(path: str) -> str | None:
    return path.lower() if path else None


def test_scan_and_validate_basic(monkeypatch):
    service = VideoValidationService()

    project_manager = MagicMock()
    project_manager.scan_input_paths.return_value = [{"path": "VIDEO.MP4"}]
    project_manager.find_video_entry.return_value = {"has_arena": False, "has_rois": False}
    project_manager.get_multi_aquarium_zone_data.return_value = None

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["VIDEO.MP4"], project_manager)

    assert result.scan_count == 1
    assert result.has_missing is False
    assert "video.mp4" in result.info_by_norm


def test_scan_and_validate_multi_aquarium_flags(monkeypatch):
    service = VideoValidationService()

    project_manager = MagicMock()
    project_manager.scan_input_paths.return_value = [{"path": "VIDEO.MP4"}]
    project_manager.find_video_entry.return_value = {"has_arena": False, "has_rois": False}
    project_manager.get_multi_aquarium_zone_data.return_value = _MultiZoneData(
        aquariums=[_Aquarium(id=0, polygon=[(0, 0), (1, 0), (1, 1)], roi_polygons=[[1, 2, 3]])]
    )
    project_manager.get_aquarium_asset_flags.return_value = {
        "has_arena": True,
        "has_rois": True,
        "has_trajectory": False,
        "has_summary": False,
        "has_complete_data": False,
    }

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["VIDEO.MP4"], project_manager)

    info = result.info_by_norm["video.mp4"]
    assert info.get("has_arena") is True
    assert info.get("has_rois") is True
    assert info.get("is_multi_aquarium") is True


def test_scan_and_validate_multi_aquarium_outputs(monkeypatch):
    service = VideoValidationService()

    project_manager = MagicMock()
    project_manager.scan_input_paths.return_value = [{"path": "VIDEO.MP4"}]
    project_manager.find_video_entry.return_value = {
        "multi_aquarium_outputs": {"0": {"parquet_files": {"trajectory": "file.parquet"}}}
    }
    project_manager.get_multi_aquarium_zone_data.return_value = None
    project_manager.get_aquarium_asset_flags.side_effect = [
        {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_summary": False,
            "has_complete_data": True,
        }
    ]

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["VIDEO.MP4"], project_manager)

    info = result.info_by_norm["video.mp4"]
    assert info.get("has_trajectory") is True
    assert info.get("is_multi_aquarium") is True


def test_scan_and_validate_stores_per_aquarium_flags(monkeypatch):
    service = VideoValidationService()

    project_manager = MagicMock()
    project_manager.scan_input_paths.return_value = [{"path": "VIDEO.MP4"}]
    project_manager.find_video_entry.return_value = {
        "multi_aquarium_outputs": {
            "0": {"parquet_files": {"trajectory": "aq0.parquet"}},
            "1": {"parquet_files": {}},
        }
    }
    project_manager.get_multi_aquarium_zone_data.return_value = _MultiZoneData(
        aquariums=[
            _Aquarium(id=0, polygon=[(0, 0), (1, 0), (1, 1)], roi_polygons=[[1, 2, 3]]),
            _Aquarium(id=1, polygon=[(2, 0), (3, 0), (3, 1)], roi_polygons=[[4, 5, 6]]),
        ]
    )
    project_manager.get_aquarium_asset_flags.side_effect = [
        {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": True,
            "has_summary": False,
            "has_complete_data": True,
        },
        {
            "has_arena": True,
            "has_rois": True,
            "has_trajectory": False,
            "has_summary": False,
            "has_complete_data": False,
        },
    ]

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["VIDEO.MP4"], project_manager)

    info = result.info_by_norm["video.mp4"]
    assert info["aquarium_flags"][0]["has_trajectory"] is True
    assert info["aquarium_flags"][1]["has_trajectory"] is False


def test_scan_and_validate_missing_files(monkeypatch):
    service = VideoValidationService()

    project_manager = MagicMock()
    project_manager.scan_input_paths.return_value = []
    project_manager.find_video_entry.return_value = None
    project_manager.get_multi_aquarium_zone_data.return_value = None

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["missing.mp4"], project_manager)

    assert result.has_missing is True
    assert result.missing_files == ["missing.mp4"]

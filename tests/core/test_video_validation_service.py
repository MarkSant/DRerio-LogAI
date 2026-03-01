"""Tests for VideoValidationService."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from zebtrack.core.video.video_validation_service import VideoValidationService

_NORMALIZE_ATTR = "zebtrack.core.project.video_manager.VideoManager.normalize_path"


@dataclass
class _Aquarium:
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
        aquariums=[_Aquarium(polygon=[(0, 0), (1, 0), (1, 1)], roi_polygons=[[1, 2, 3]])]
    )

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

    monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)

    result = service.scan_and_validate_paths(["VIDEO.MP4"], project_manager)

    info = result.info_by_norm["video.mp4"]
    assert info.get("has_trajectory") is True
    assert info.get("is_multi_aquarium") is True


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

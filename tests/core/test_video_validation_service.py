"""Tests for VideoValidationService."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

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


# ---------------------------------------------------------------------------
# Edge cases of the scan enrichment (TASK-087)
# ---------------------------------------------------------------------------


class _Project:
    """Just enough ``ProjectManager`` for ``scan_and_validate_paths``."""

    def __init__(self, scanned, entries, flags=None, multi=None, multi_error=None):
        self.scanned = scanned
        self.entries = entries
        self.flags = flags or {}
        self.multi = multi
        self.multi_error = multi_error
        self.flag_calls: list[tuple[str, int]] = []

    def scan_input_paths(self, paths):
        return self.scanned

    def find_video_entry(self, *, path):
        return self.entries.get(path)

    def get_multi_aquarium_zone_data(self, path):
        if self.multi_error is not None:
            raise self.multi_error
        return self.multi

    def get_aquarium_asset_flags(self, path, aquarium_id):
        self.flag_calls.append((path, aquarium_id))
        return self.flags[aquarium_id]


def _flags(arena=False, rois=False, trajectory=False, complete=False):
    return {
        "has_arena": arena,
        "has_rois": rois,
        "has_trajectory": trajectory,
        "has_complete_data": complete,
    }


class TestAquariumKeyNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (3, 3),
            ("aquarium_2", 2),
            ("7", 7),
            ("none", None),
            ("", None),
            # A superscript is "a digit" for str.isdigit() but int() refuses it.
            ("²", None),
        ],
    )
    def test_keys_become_integers_when_they_carry_digits(self, raw, expected):
        assert VideoValidationService._normalize_aquarium_key(raw) == expected


class TestScanEnrichment:
    def test_stored_multi_aquarium_outputs_supply_the_per_aquarium_flags(self, monkeypatch):
        monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)
        project = _Project(
            scanned=[{"path": "/v/a.mp4"}],
            entries={"/v/a.mp4": {"multi_aquarium_outputs": {"aquarium_1": {}, 2: {}, "bad": {}}}},
            flags={1: _flags(arena=True, trajectory=True), 2: _flags(rois=True)},
            multi_error=RuntimeError("zone scan failed"),
        )

        result = VideoValidationService().scan_and_validate_paths(["/v/a.mp4"], cast(Any, project))

        info = result.info_by_norm["/v/a.mp4"]
        assert info["is_multi_aquarium"] is True
        assert info["multi_aquarium_outputs"] == {"aquarium_1": {}, 2: {}, "bad": {}}
        assert info["aquarium_flags"] == {
            1: _flags(arena=True, trajectory=True),
            2: _flags(rois=True),
        }
        # Aggregated with ANY across aquariums, complete only if some aquarium is.
        assert (info["has_arena"], info["has_rois"]) == (True, True)
        assert (info["has_trajectory"], info["has_complete_data"]) == (True, False)
        # The unparseable key never reached the project.
        assert sorted(project.flag_calls) == [("/v/a.mp4", 1), ("/v/a.mp4", 2)]

    def test_zone_data_aquariums_are_not_asked_twice_when_outputs_repeat_them(self, monkeypatch):
        monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)
        project = _Project(
            scanned=[{"path": "/v/a.mp4"}],
            entries={"/v/a.mp4": {"multi_aquarium_outputs": {"aquarium_1": {}}}},
            flags={1: _flags(arena=True)},
            multi=_MultiZoneData(aquariums=[_Aquarium(id=1, polygon=[], roi_polygons=[])]),
        )

        VideoValidationService().scan_and_validate_paths(["/v/a.mp4"], cast(Any, project))

        assert project.flag_calls == [("/v/a.mp4", 1)]

    def test_the_project_entry_fills_flags_the_scan_did_not_find(self, monkeypatch):
        monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)
        project = _Project(
            scanned=[{"path": "/v/b.mp4"}, {"path": "/v/c.mp4", "has_arena": True}],
            entries={
                "/v/b.mp4": _flags(arena=True, rois=True, trajectory=True, complete=True),
                "/v/c.mp4": _flags(rois=True),
            },
        )

        result = VideoValidationService().scan_and_validate_paths(
            ["/v/b.mp4", "/v/c.mp4"], cast(Any, project)
        )

        b = result.info_by_norm["/v/b.mp4"]
        assert (b["has_arena"], b["has_rois"], b["has_trajectory"], b["has_complete_data"]) == (
            True,
            True,
            True,
            True,
        )
        c = result.info_by_norm["/v/c.mp4"]
        assert c["has_arena"] is True  # the scan's own finding survives
        assert c["has_rois"] is True
        assert "has_trajectory" not in c

    def test_scan_results_without_a_path_or_a_project_entry_are_left_alone(self, monkeypatch):
        monkeypatch.setattr(_NORMALIZE_ATTR, _normalize)
        project = _Project(
            scanned=[{"name": "no path"}, {"path": "/v/unknown.mp4", "has_arena": False}],
            entries={},
        )

        result = VideoValidationService().scan_and_validate_paths(
            ["/v/unknown.mp4", "/v/gone.mp4"], cast(Any, project)
        )

        assert result.scanned_videos[0] == {"name": "no path"}
        assert result.info_by_norm["/v/unknown.mp4"] == {
            "path": "/v/unknown.mp4",
            "has_arena": False,
        }
        assert result.missing_files == ["/v/gone.mp4"]
        assert project.flag_calls == []

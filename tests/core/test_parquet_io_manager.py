"""Unit tests for ``zebtrack.core.project.ParquetIOManager``.

The manager is stateless: project state and lookups are injected as callables,
which makes it straightforward to test with ``tmp_path`` and small lambdas.

Focus is the zone-parquet **schema** (column names/order) and the canonical
filenames — both are part of the project's persisted data contract, so they are
pinned explicitly here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.parquet_io_manager import ParquetIOManager


@pytest.fixture
def manager():
    return ParquetIOManager()


@pytest.fixture
def zone_data():
    return ZoneData(
        polygon=[[0, 0], [100, 0], [100, 80], [0, 80]],
        roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
        roi_names=["Center"],
    )


class TestZoneParquetFilenames:
    def test_golden_filenames(self):
        names = ParquetIOManager._zone_parquet_filenames("myvideo")
        assert names == {
            "arena": "1_ProcessingArea_myvideo.parquet",
            "rois": "2_AreasOfInterest_myvideo.parquet",
        }


class TestExportZonesToParquet:
    def test_no_project_path_returns_empty(self, manager, zone_data):
        result = manager.export_zones_to_parquet(
            "video.mp4",
            zone_data,
            project_path=None,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: None,
        )
        assert result == {}

    def test_exports_arena_and_rois_with_expected_schema(self, manager, zone_data, tmp_path):
        result = manager.export_zones_to_parquet(
            "session/myvideo.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert set(result) == {"arena", "rois"}

        arena = pd.read_parquet(result["arena"])
        assert list(arena.columns) == ["x", "y"]
        assert arena.shape == (4, 2)
        assert [list(row) for row in arena.to_numpy()] == zone_data.polygon

        rois = pd.read_parquet(result["rois"])
        assert list(rois.columns) == ["roi_name", "point_index", "x", "y"]
        assert (rois["roi_name"] == "Center").all()
        assert list(rois["point_index"]) == [0, 1, 2, 3]

    def test_filenames_follow_canonical_pattern(self, manager, zone_data, tmp_path):
        result = manager.export_zones_to_parquet(
            "myvideo.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert result["arena"].endswith("1_ProcessingArea_myvideo.parquet")
        assert result["rois"].endswith("2_AreasOfInterest_myvideo.parquet")

    def test_polygon_only_exports_arena_only(self, manager, tmp_path):
        zone = ZoneData(polygon=[[0, 0], [10, 0], [10, 10]])
        result = manager.export_zones_to_parquet(
            "v.mp4",
            zone,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert set(result) == {"arena"}

    def test_empty_zone_exports_nothing(self, manager, tmp_path):
        result = manager.export_zones_to_parquet(
            "v.mp4",
            ZoneData(),
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )
        assert result == {}

    def test_video_entry_metadata_is_passed_to_resolver(self, manager, zone_data, tmp_path):
        captured = {}

        def resolver(stem, *, video_path, metadata):
            captured["metadata"] = metadata
            return tmp_path

        manager.export_zones_to_parquet(
            "v.mp4",
            zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: {"metadata": {"group": "control"}},
            resolve_results_directory_fn=resolver,
        )
        assert captured["metadata"] == {"group": "control"}


class TestResolveSourceZoneParquets:
    def test_finds_files_in_source_directory(self, manager, tmp_path):
        # Lay down an arena parquet next to the source video.
        (tmp_path / "1_ProcessingArea_clip.parquet").write_bytes(b"x")
        found = ParquetIOManager._resolve_source_zone_parquets(
            source_video_path=tmp_path / "clip.mp4",
            source_entry=None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            project_path=None,
        )
        assert "arena" in found
        assert found["arena"].endswith("1_ProcessingArea_clip.parquet")

    def test_returns_empty_when_nothing_on_disk(self, manager, tmp_path):
        found = ParquetIOManager._resolve_source_zone_parquets(
            source_video_path=tmp_path / "clip.mp4",
            source_entry=None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            project_path=None,
        )
        assert found == {}

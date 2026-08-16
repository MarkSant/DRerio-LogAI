"""
Extended unit tests for ParquetIOManager in core/project/parquet_io_manager.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.parquet_io_manager import ParquetIOManager


class TestParquetIOManagerExtended:
    """Test ParquetIOManager export and zone parquet importing."""

    @pytest.fixture
    def manager(self) -> ParquetIOManager:
        return ParquetIOManager()

    def test_import_zone_data_from_video_parquets_no_candidates(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        imported = manager.import_zone_data_from_video_parquets(
            video_path=tmp_path / "vid.mp4",
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            get_zone_data_fn=lambda **kw: ZoneData(),
            save_zone_data_fn=lambda *args, **kw: None,
        )
        assert imported is False

    def test_import_zone_data_from_video_parquets_success(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        video_stem = "sample_video"
        video_path = tmp_path / f"{video_stem}.mp4"

        # Create valid arena parquet
        arena_df = pd.DataFrame({"x": [10, 50, 50, 10], "y": [10, 10, 50, 50]})
        arena_file = tmp_path / f"1_ProcessingArea_{video_stem}.parquet"
        arena_df.to_parquet(arena_file)

        # Create valid ROIs parquet
        rois_df = pd.DataFrame(
            {
                "roi_name": ["Center", "Center", "Center", "Center"],
                "point_index": [0, 1, 2, 3],
                "x": [20, 30, 30, 20],
                "y": [20, 20, 30, 30],
            }
        )
        rois_file = tmp_path / f"2_AreasOfInterest_{video_stem}.parquet"
        rois_df.to_parquet(rois_file)

        target_zone_data = ZoneData()
        mock_save = MagicMock()

        imported = manager.import_zone_data_from_video_parquets(
            video_path=video_path,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: {
                "parquet_files": {
                    "arena": str(arena_file),
                    "rois": str(rois_file),
                }
            },
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
            get_zone_data_fn=lambda **kw: target_zone_data,
            save_zone_data_fn=mock_save,
        )

        assert imported is True
        mock_save.assert_called_once_with(target_zone_data, str(video_path), persist=False)
        assert len(target_zone_data.polygon) == 4
        assert target_zone_data.roi_names == ["Center"]
        assert len(target_zone_data.roi_polygons) == 1

    def test_export_zones_to_parquet_with_multiple_rois(
        self, manager: ParquetIOManager, tmp_path: Path
    ):
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[
                [[10, 10], [40, 10], [40, 40], [10, 40]],
                [[60, 60], [90, 60], [90, 90], [60, 90]],
            ],
            roi_names=["ZoneA", "ZoneB"],
        )

        exported = manager.export_zones_to_parquet(
            video_path="session/video123.mp4",
            zone_data=zone_data,
            project_path=tmp_path,
            find_video_entry_fn=lambda path: None,
            resolve_results_directory_fn=lambda stem, **kw: tmp_path,
        )

        assert "arena" in exported
        assert "rois" in exported

        df_arena = pd.read_parquet(exported["arena"])
        assert df_arena.shape == (4, 2)

        df_rois = pd.read_parquet(exported["rois"])
        assert df_rois.shape == (8, 4)
        assert set(df_rois["roi_name"].unique()) == {"ZoneA", "ZoneB"}

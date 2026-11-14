"""
Tests for granular parquet detection and zone import functionality.

This module tests the enhanced scan_input_paths() and load_zones_from_parquet()
methods that provide detailed information about existing parquet files.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import ProjectManager


class TestParquetImport(unittest.TestCase):
    """Tests for parquet file detection and zone import."""

    def setUp(self):
        """Create temporary directory and test fixtures."""
        self.test_dir = tempfile.mkdtemp(prefix="zebtrack_test_parquet_")
        self.video_dir = Path(self.test_dir) / "videos"
        self.video_dir.mkdir()

        # Create dummy video files
        self.video1 = self.video_dir / "test_video1.mp4"
        self.video2 = self.video_dir / "test_video2.mp4"
        self.video3 = self.video_dir / "test_video3.mp4"

        for video_file in [self.video1, self.video2, self.video3]:
            video_file.touch()

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _create_arena_parquet(self, video_path: Path):
        """Helper to create a mock arena parquet file."""
        base_name = video_path.stem
        arena_path = video_path.parent / f"1_ProcessingArea_{base_name}.parquet"

        # Create arena polygon (rectangle)
        arena_data = pd.DataFrame({"x": [0, 640, 640, 0], "y": [0, 0, 480, 480]})

        table = pa.Table.from_pandas(arena_data)
        pq.write_table(table, str(arena_path))
        return arena_path

    def _create_rois_parquet(self, video_path: Path, roi_names: list[str] | None = None) -> Path:
        """Helper to create a mock ROIs parquet file."""
        if roi_names is None:
            roi_names = ["Top", "Bottom"]

        base_name = video_path.stem
        rois_path = video_path.parent / f"2_AreasOfInterest_{base_name}.parquet"

        # Create ROI polygons
        roi_data = []
        for idx, roi_name in enumerate(roi_names):
            # Simple rectangular ROI
            y_offset = idx * 240
            roi_points = [
                (0, y_offset),
                (640, y_offset),
                (640, y_offset + 240),
                (0, y_offset + 240),
            ]
            for point_idx, (x, y) in enumerate(roi_points):
                roi_data.append({"roi_name": roi_name, "point_index": point_idx, "x": x, "y": y})

        rois_df = pd.DataFrame(roi_data)
        table = pa.Table.from_pandas(rois_df)
        pq.write_table(table, str(rois_path))
        return rois_path

    def _create_trajectory_parquet(self, video_path: Path):
        """Helper to create a mock trajectory parquet file."""
        base_name = video_path.stem
        trajectory_path = video_path.parent / f"3_CoordMovimento_{base_name}.parquet"

        # Create minimal trajectory data
        trajectory_data = pd.DataFrame(
            {
                "timestamp": [0.0, 0.033, 0.066],
                "frame": [0, 1, 2],
                "track_id": [1, 1, 1],
                "x1": [100, 110, 120],
                "y1": [200, 210, 220],
                "x2": [150, 160, 170],
                "y2": [250, 260, 270],
                "confidence": [0.95, 0.93, 0.94],
            }
        )

        table = pa.Table.from_pandas(trajectory_data)
        pq.write_table(table, str(trajectory_path))
        return trajectory_path

    def test_scan_detects_no_parquet_files(self):
        """Test that scan correctly identifies videos without parquet files."""
        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video_dir)])

        self.assertEqual(len(results), 3)
        for result in results:
            self.assertFalse(result["has_arena"])
            self.assertFalse(result["has_rois"])
            self.assertFalse(result["has_trajectory"])
            self.assertFalse(result["has_complete_data"])
            self.assertFalse(result["has_data"])  # Backward compatibility
            self.assertIsNone(result["parquet_files"]["arena"])
            self.assertIsNone(result["parquet_files"]["rois"])
            self.assertIsNone(result["parquet_files"]["trajectory"])

    def test_scan_detects_only_arena(self):
        """Test detection of arena parquet only."""
        self._create_arena_parquet(self.video1)

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video1)])

        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertTrue(result["has_arena"])
        self.assertFalse(result["has_rois"])
        self.assertFalse(result["has_trajectory"])
        self.assertFalse(result["has_complete_data"])
        # No trajectory, so backward compatibility should be False
        self.assertFalse(result["has_data"])
        self.assertIsNotNone(result["parquet_files"]["arena"])

    def test_scan_detects_arena_and_rois(self):
        """Test detection of arena and ROI parquet files."""
        self._create_arena_parquet(self.video1)
        self._create_rois_parquet(self.video1)

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video1)])

        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertTrue(result["has_arena"])
        self.assertTrue(result["has_rois"])
        self.assertFalse(result["has_trajectory"])
        self.assertFalse(result["has_complete_data"])
        self.assertIsNotNone(result["parquet_files"]["arena"])
        self.assertIsNotNone(result["parquet_files"]["rois"])

    def test_scan_detects_complete_data(self):
        """Test detection when all three parquet types exist."""
        self._create_arena_parquet(self.video1)
        self._create_rois_parquet(self.video1)
        self._create_trajectory_parquet(self.video1)

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video1)])

        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertTrue(result["has_arena"])
        self.assertTrue(result["has_rois"])
        self.assertTrue(result["has_trajectory"])
        self.assertTrue(result["has_complete_data"])
        self.assertTrue(result["has_data"])  # Backward compat
        self.assertIsNotNone(result["parquet_files"]["arena"])
        self.assertIsNotNone(result["parquet_files"]["rois"])
        self.assertIsNotNone(result["parquet_files"]["trajectory"])

    def test_scan_detects_mixed_scenarios(self):
        """Test scanning multiple videos with different parquet availability."""
        # Video 1: Complete data
        self._create_arena_parquet(self.video1)
        self._create_rois_parquet(self.video1)
        self._create_trajectory_parquet(self.video1)

        # Video 2: Only arena and ROIs
        self._create_arena_parquet(self.video2)
        self._create_rois_parquet(self.video2, ["Center"])

        # Video 3: No parquet files

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video_dir)])

        self.assertEqual(len(results), 3)

        # Find each video in results
        video1_result = next(r for r in results if "test_video1" in r["path"])
        video2_result = next(r for r in results if "test_video2" in r["path"])
        video3_result = next(r for r in results if "test_video3" in r["path"])

        # Video 1 assertions
        self.assertTrue(video1_result["has_complete_data"])

        # Video 2 assertions
        self.assertTrue(video2_result["has_arena"])
        self.assertTrue(video2_result["has_rois"])
        self.assertFalse(video2_result["has_trajectory"])
        self.assertFalse(video2_result["has_complete_data"])

        # Video 3 assertions
        self.assertFalse(video3_result["has_arena"])
        self.assertFalse(video3_result["has_rois"])
        self.assertFalse(video3_result["has_trajectory"])

    def test_scan_detects_in_results_subdirectory(self):
        """Test that scan finds parquet files in _results subdirectory."""
        # Create results subdirectory
        results_dir = self.video_dir / "test_video1_results"
        results_dir.mkdir()

        # Create parquet files in results subdirectory
        base_name = self.video1.stem
        arena_path = results_dir / f"1_ProcessingArea_{base_name}.parquet"
        arena_df = pd.DataFrame({"x": [0, 100, 100, 0], "y": [0, 0, 100, 100]})
        pq.write_table(pa.Table.from_pandas(arena_df), str(arena_path))

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video1)])

        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertTrue(result["has_arena"])
        self.assertIn("_results", result["parquet_files"]["arena"])

    def test_load_zones_from_parquet_arena_only(self):
        """Test loading only arena from parquet."""
        self._create_arena_parquet(self.video1)

        pm = ProjectManager()
        video_info = pm.scan_input_paths([str(self.video1)])[0]
        zone_data: ZoneData | None = pm.load_zones_from_parquet(video_info)

        self.assertIsNotNone(zone_data)
        assert zone_data is not None
        self.assertIsNotNone(zone_data.polygon)
        self.assertEqual(len(zone_data.polygon), 4)  # Rectangle has 4 points
        self.assertEqual(zone_data.polygon[0], [0, 0])
        self.assertEqual(zone_data.roi_polygons, [])

    def test_load_zones_from_parquet_with_rois(self):
        """Test loading arena and ROIs from parquet."""
        self._create_arena_parquet(self.video1)
        self._create_rois_parquet(self.video1, ["Top", "Bottom", "Center"])

        pm = ProjectManager()
        video_info = pm.scan_input_paths([str(self.video1)])[0]
        zone_data: ZoneData | None = pm.load_zones_from_parquet(video_info)

        self.assertIsNotNone(zone_data)
        assert zone_data is not None
        self.assertIsNotNone(zone_data.polygon)
        self.assertEqual(len(zone_data.roi_polygons), 3)
        self.assertEqual(len(zone_data.roi_names), 3)
        self.assertIn("Top", zone_data.roi_names)
        self.assertIn("Bottom", zone_data.roi_names)
        self.assertIn("Center", zone_data.roi_names)
        self.assertEqual(len(zone_data.roi_colors), 3)  # Default colors assigned

    def test_load_zones_with_no_files_returns_none(self):
        """Test that load_zones returns None when no parquet files exist."""
        pm = ProjectManager()
        video_info = pm.scan_input_paths([str(self.video1)])[0]
        zone_data: ZoneData | None = pm.load_zones_from_parquet(video_info)

        self.assertIsNone(zone_data)

    def test_load_zones_with_invalid_schema_returns_partial(self):
        """Test that load_zones handles invalid schemas gracefully."""
        # Create arena with valid schema
        self._create_arena_parquet(self.video1)

        # Create ROI with invalid schema (missing columns)
        base_name = self.video1.stem
        rois_path = self.video1.parent / f"2_AreasOfInterest_{base_name}.parquet"
        invalid_rois_df = pd.DataFrame({"only_x": [1, 2, 3]})
        pq.write_table(pa.Table.from_pandas(invalid_rois_df), str(rois_path))

        pm = ProjectManager()
        video_info = pm.scan_input_paths([str(self.video1)])[0]
        zone_data: ZoneData | None = pm.load_zones_from_parquet(video_info)

        # Should load arena but skip invalid ROIs
        self.assertIsNotNone(zone_data)
        assert zone_data is not None
        self.assertIsNotNone(zone_data.polygon)
        self.assertEqual(zone_data.roi_polygons, [])  # ROIs not loaded

    def test_backward_compatibility_has_data(self):
        """Test that has_data flag maintains backward compatibility."""
        # Create only trajectory (old behavior)
        self._create_trajectory_parquet(self.video1)

        pm = ProjectManager()
        results = pm.scan_input_paths([str(self.video1)])

        result = results[0]
        self.assertTrue(result["has_data"])  # Should be True for backward compatibility
        self.assertTrue(result["has_trajectory"])
        self.assertFalse(result["has_complete_data"])


class TestTrajectoryImportCopiesTheSidecarSet:
    """Importing a trajectory brings its 3b/3c/6/7 sidecars along (ADR-010)."""

    _SET = (
        "3b_Mascaras_{b}.parquet",
        "3c_Objetos_{b}.parquet",
        "6_FrameLedger_{b}.csv",
        "6_FrameLedger_{b}.parquet",
        "6_FrameLedger_{b}_anchor.json",
        "7_AnalysisWindow_{b}.json",
    )

    def _import(self, tmp_path: Path, source_names: list[str], dest_names: list[str]):
        from zebtrack.core.project.parquet_io_manager import ParquetIOManager

        source = tmp_path / "old_results"
        source.mkdir()
        trajectory = source / "3_CoordMovimento_old.parquet"
        trajectory.write_bytes(b"trajectory")
        for name in source_names:
            (source / name).write_text(name, encoding="utf-8")
        video = tmp_path / "CECT_4.mp4"
        video.touch()
        dest = tmp_path / "project" / "Sujeito_CECT_4"
        dest.mkdir(parents=True)
        for name in dest_names:
            (dest / name).write_text("stale", encoding="utf-8")

        counts = ParquetIOManager()._process_single_parquet_import(
            {"video": str(video), "import_trajectory": True},
            {str(video): {"trajectory": str(trajectory)}},
            "replace",
            project_path=str(tmp_path / "project"),
            get_zone_data_fn=lambda **_kwargs: ZoneData(),
            save_zone_data_fn=lambda *_args, **_kwargs: None,
            resolve_results_directory_fn=lambda *_args, **_kwargs: dest,
        )
        return counts, dest

    def test_the_whole_set_is_copied_under_the_new_base(self, tmp_path):
        names = [pattern.format(b="old") for pattern in self._SET]

        counts, dest = self._import(tmp_path, [*names, "3c_Objetos_old_2.parquet"], [])

        assert counts["trajectory"] == 1
        assert (dest / "3_CoordMovimento_CECT_4.parquet").read_bytes() == b"trajectory"
        for pattern in self._SET:
            copied = dest / pattern.format(b="CECT_4")
            assert copied.read_text(encoding="utf-8") == pattern.format(b="old")
        # Another base that merely starts the same way is not part of the set.
        assert not (dest / "3c_Objetos_CECT_4_2.parquet").exists()
        assert sorted(p.name for p in dest.iterdir()) == sorted(
            ["3_CoordMovimento_CECT_4.parquet", *(p.format(b="CECT_4") for p in self._SET)]
        )

    def test_stale_sidecars_of_the_overwritten_trajectory_are_removed(self, tmp_path):
        """Old 3c/7_ next to the replaced trajectory would describe ANOTHER run."""
        counts, dest = self._import(
            tmp_path,
            ["3b_Mascaras_old.parquet"],
            ["3c_Objetos_CECT_4.parquet", "7_AnalysisWindow_CECT_4.json", "notes.txt"],
        )

        assert counts["trajectory"] == 1
        assert (dest / "3b_Mascaras_CECT_4.parquet").exists()
        assert not (dest / "3c_Objetos_CECT_4.parquet").exists()
        assert not (dest / "7_AnalysisWindow_CECT_4.json").exists()
        assert (dest / "notes.txt").exists()

    def test_trajectory_without_sidecars_still_imports(self, tmp_path):
        counts, dest = self._import(tmp_path, [], [])

        assert counts["trajectory"] == 1
        assert [p.name for p in dest.iterdir()] == ["3_CoordMovimento_CECT_4.parquet"]


if __name__ == "__main__":
    unittest.main()

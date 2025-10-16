"""
End-to-end test for single video workflow with zone data and GUI updates.

Tests the complete flow:
1. Register single video with zone data
2. Process and generate outputs
3. Verify video appears in project overview with correct flags
4. Verify reports are accessible
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import structlog

from zebtrack.core.detector import ZoneData
from zebtrack.core.main_view_model import AppController

log = structlog.get_logger()


@patch("zebtrack.core.main_view_model.ApplicationGUI")
@patch("zebtrack.core.main_view_model.WeightManager")
def test_single_video_with_zones_shows_all_flags(mock_wm, mock_gui):
    """
    Test that a single video with zone data shows all flags correctly.
    """
    # Create mock tkinter root
    mock_root = MagicMock()
    mock_root.after = MagicMock()

    # Configure mock weight manager
    mock_wm_instance = mock_wm.return_value
    mock_wm_instance.get_default_weight.return_value = ("best_seg.pt", "/fake/path")

    controller = AppController(mock_root)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test_video.mp4")
        results_dir = os.path.join(tmpdir, "test_video_results")
        Path(results_dir).mkdir(parents=True, exist_ok=True)

        # Create a dummy video file
        with open(video_path, "w") as f:
            f.write("dummy video content")

        # Create zone data with arena and ROIs
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[
                [[10, 10], [30, 10], [30, 30], [10, 30]],
                [[70, 70], [90, 70], [90, 90], [70, 90]],
            ],
            roi_names=["ROI_1", "ROI_2"],
            roi_colors=[(255, 0, 0), (0, 255, 0)],
        )

        # Simulate the single video workflow registration
        config = {
            "group": "test_group",
            "group_display_name": "Test Group",
            "day": "1",
            "subject": "1",
        }

        # Register video with zone data (simulating start_single_video_processing)
        metadata = {
            "group": config.get("group", "single_video"),
            "group_display_name": config.get("group_display_name", "Vídeo Único"),
            "day": config.get("day", "1"),
            "subject": config.get("subject", "1"),
        }

        video_data = {
            "path": video_path,
            "status": "processing",
            "has_arena": bool(zone_data.polygon),
            "has_rois": bool(zone_data.roi_polygons),
            "metadata": metadata,
        }

        controller.project_manager.add_video_batch([video_data], save_project=False)

        # Save zone data
        controller.project_manager.save_zone_data(zone_data, video_path)

        # Create output files
        trajectory_path = os.path.join(
            results_dir,
            "3_CoordMovimento_test_video.parquet",
        )
        summary_parquet = os.path.join(
            results_dir,
            "test_video_summary.parquet",
        )
        summary_excel = os.path.join(
            results_dir,
            "test_video_summary.xlsx",
        )
        report_path = os.path.join(
            results_dir,
            "test_video_report.docx",
        )

        for path in [trajectory_path, summary_parquet, summary_excel, report_path]:
            with open(path, "w") as f:
                f.write("dummy content")

        # Register the outputs
        success = controller.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )

        assert success, "Failed to register processing outputs"

        # Verify the video entry has all flags set correctly
        all_videos = controller.project_manager.get_all_videos()
        assert len(all_videos) == 1

        video_entry = all_videos[0]

        # Check all flags
        assert video_entry["has_arena"] is True, "has_arena should be True"
        assert video_entry["has_rois"] is True, "has_rois should be True"
        assert video_entry["has_trajectory"] is True, "has_trajectory should be True"
        assert video_entry["has_summary"] is True, "has_summary should be True"
        assert video_entry["status"] == "processed", (
            f"Status should be 'processed', got {video_entry['status']}"
        )

        # Check metadata
        entry_metadata = video_entry.get("metadata", {})
        assert entry_metadata.get("group") == "test_group"
        assert entry_metadata.get("group_display_name") == "Test Group"
        assert entry_metadata.get("day") == "1"
        assert entry_metadata.get("subject") == "1"

        # Check parquet files
        parquet_files = video_entry.get("parquet_files", {})
        assert parquet_files.get("trajectory") == trajectory_path
        assert parquet_files.get("summary") == summary_parquet
        assert parquet_files.get("summary_excel") == summary_excel
        assert parquet_files.get("report_docx") == report_path

        # Verify zone data can be retrieved
        retrieved_zone_data = controller.project_manager.get_zone_data(
            video_path,
            fallback_to_global=False,
        )
        assert retrieved_zone_data is not None
        assert retrieved_zone_data.polygon == zone_data.polygon
        assert len(retrieved_zone_data.roi_polygons) == 2
        assert retrieved_zone_data.roi_names == ["ROI_1", "ROI_2"]

        log.info(
            "test.single_video_complete_workflow.success",
            has_arena=video_entry["has_arena"],
            has_rois=video_entry["has_rois"],
            has_trajectory=video_entry["has_trajectory"],
            has_summary=video_entry["has_summary"],
            status=video_entry["status"],
            metadata=entry_metadata,
        )


@patch("zebtrack.core.main_view_model.ApplicationGUI")
@patch("zebtrack.core.main_view_model.WeightManager")
def test_zone_flags_updated_during_output_registration(mock_wm, mock_gui):
    """
    Test that zone flags are updated if missing during output registration.
    """
    # Create mock tkinter root
    mock_root = MagicMock()
    mock_root.after = MagicMock()

    # Configure mock weight manager
    mock_wm_instance = mock_wm.return_value
    mock_wm_instance.get_default_weight.return_value = ("best_seg.pt", "/fake/path")

    controller = AppController(mock_root)

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test_video.mp4")
        results_dir = os.path.join(tmpdir, "test_video_results")
        Path(results_dir).mkdir(parents=True, exist_ok=True)

        # Create a dummy video file
        with open(video_path, "w") as f:
            f.write("dummy video content")

        # Add video WITHOUT zone flags
        controller.project_manager.add_video_batch(
            [{"path": video_path, "status": "processing"}], save_project=False
        )

        # Verify flags are initially False/missing
        video_entry = controller.project_manager.find_video_entry(path=video_path)
        assert not video_entry.get("has_arena")
        assert not video_entry.get("has_rois")

        # Create and save zone data
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [30, 10], [30, 30], [10, 30]]],
            roi_names=["ROI_1"],
            roi_colors=[(255, 0, 0)],
        )
        controller.project_manager.save_zone_data(zone_data, video_path)

        # Create dummy output
        trajectory_path = os.path.join(
            results_dir,
            "3_CoordMovimento_test_video.parquet",
        )
        with open(trajectory_path, "w") as f:
            f.write("dummy content")

        # Register outputs - this should update the zone flags
        success = controller.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
        )

        assert success

        # Verify flags were updated
        video_entry = controller.project_manager.find_video_entry(path=video_path)
        assert video_entry.get("has_arena") is True, "has_arena should be updated to True"
        assert video_entry.get("has_rois") is True, "has_rois should be updated to True"
        assert video_entry.get("has_trajectory") is True

        log.info("test.zone_flags_auto_update.success")

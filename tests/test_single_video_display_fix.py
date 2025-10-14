"""
Integration test to verify single video results appear in GUI tabs.

This test specifically addresses the fix for the issue where single video
analysis did not display files in the Main Control (Project Summary) tab
or reports in the Reports tab.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import structlog

from zebtrack.core.controller import AppController


log = structlog.get_logger()


@patch("zebtrack.core.controller.ApplicationGUI")
@patch("zebtrack.core.controller.WeightManager")
def test_single_video_appears_in_project_overview(mock_wm, mock_gui):
    """
    Test that a processed single video appears in the project overview
    even without a project file.
    """
    # Create mock tkinter root
    mock_root = MagicMock()
    mock_root.after = MagicMock()
    
    # Configure mock weight manager
    mock_wm_instance = mock_wm.return_value
    mock_wm_instance.get_default_weight.return_value = ("best_seg.pt", "/fake/path")
    
    controller = AppController(mock_root)
    
    # Create a temporary video file
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "test_video.mp4")
        results_dir = os.path.join(tmpdir, "test_video_results")
        Path(results_dir).mkdir(parents=True, exist_ok=True)
        
        # Create a dummy video file
        with open(video_path, "w") as f:
            f.write("dummy video content")
        
        # Simulate adding the video to project manager (what the fix does)
        controller.project_manager.add_video_batch(
            [{"path": video_path, "status": "processing"}],
            save_project=False
        )
        
        # Create output files
        trajectory_path = os.path.join(results_dir, "3_CoordMovimento_test_video.parquet")
        summary_parquet = os.path.join(results_dir, "test_video_summary.parquet")
        summary_excel = os.path.join(results_dir, "test_video_summary.xlsx")
        report_path = os.path.join(results_dir, "test_video_report.docx")
        
        # Create dummy output files
        for path in [trajectory_path, summary_parquet, summary_excel, report_path]:
            with open(path, "w") as f:
                f.write("dummy content")
        
        # Register the outputs (what the fix ensures happens)
        success = controller.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )
        
        assert success, "Failed to register processing outputs"
        
        # Verify the video appears in get_all_videos()
        all_videos = controller.project_manager.get_all_videos()
        assert len(all_videos) == 1, f"Expected 1 video, got {len(all_videos)}"
        
        video_entry = all_videos[0]
        assert video_entry["path"] == video_path
        assert video_entry["status"] in ["processing", "processed"]
        assert video_entry.get("has_trajectory") is True
        assert video_entry.get("has_summary") is True
        
        # Verify parquet_files are registered
        parquet_files = video_entry.get("parquet_files", {})
        assert parquet_files.get("trajectory") == trajectory_path
        assert parquet_files.get("summary") == summary_parquet
        assert parquet_files.get("summary_excel") == summary_excel
        assert parquet_files.get("report_docx") == report_path
        
        log.info(
            "test.single_video_display.success",
            video_entry=video_entry,
            parquet_files=parquet_files,
        )


@patch("zebtrack.core.controller.ApplicationGUI")
@patch("zebtrack.core.controller.WeightManager")
def test_single_video_does_not_create_project_file(mock_wm, mock_gui):
    """
    Test that single video workflow does not create a project file on disk.
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
        
        # Create a dummy video file
        with open(video_path, "w") as f:
            f.write("dummy video content")
        
        # Add video with save_project=False
        controller.project_manager.add_video_batch(
            [{"path": video_path, "status": "processing"}],
            save_project=False
        )
        
        # Verify no project_config.json was created
        project_file = os.path.join(tmpdir, "project_config.json")
        assert not os.path.exists(project_file), \
            "Project file should not be created for single video workflow"
        
        # Verify the video is still tracked in memory
        all_videos = controller.project_manager.get_all_videos()
        assert len(all_videos) == 1
        assert all_videos[0]["path"] == video_path
        
        log.info("test.single_video_no_project_file.success")


@patch("zebtrack.core.controller.ApplicationGUI")
@patch("zebtrack.core.controller.WeightManager")
def test_register_outputs_auto_adds_missing_video(mock_wm, mock_gui):
    """
    Test that register_processing_outputs auto-adds missing videos.
    
    This is part of the fix: if a video isn't registered yet,
    register_processing_outputs will add it automatically.
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
        
        # Create dummy output
        trajectory_path = os.path.join(results_dir, "3_CoordMovimento_test_video.parquet")
        with open(trajectory_path, "w") as f:
            f.write("dummy content")
        
        # Call register_processing_outputs WITHOUT pre-adding the video
        # The fix should auto-add it
        success = controller.project_manager.register_processing_outputs(
            video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
        )
        
        assert success, "Failed to register outputs with auto-add"
        
        # Verify the video was auto-added
        all_videos = controller.project_manager.get_all_videos()
        assert len(all_videos) == 1
        assert all_videos[0]["path"] == video_path
        assert all_videos[0].get("has_trajectory") is True
        
        log.info("test.register_outputs_auto_add.success")

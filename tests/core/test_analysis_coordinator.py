"""
Unit tests for AnalysisCoordinator.

Task 2.2: REFACTOR-VIEWMODEL-001
Tests for analysis pipeline, report generation, and parquet summaries.
"""

import os
import unittest
from unittest.mock import MagicMock, Mock, patch, call

from zebtrack.core.analysis_coordinator import AnalysisCoordinator


class TestAnalysisCoordinatorInitialization(unittest.TestCase):
    """Test suite for AnalysisCoordinator initialization."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.settings = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()
        self.video_processing_service = Mock()

    def test_init_with_all_dependencies(self):
        """Test initialization with all dependencies."""
        coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        assert coordinator.root == self.root
        assert coordinator.view == self.view
        assert coordinator.ui_event_bus == self.ui_event_bus
        assert coordinator.settings == self.settings
        assert coordinator.project_manager == self.project_manager
        assert coordinator.analysis_service == self.analysis_service
        assert coordinator.video_processing_service == self.video_processing_service

    def test_init_callbacks_are_none(self):
        """Test that callbacks are initialized to None."""
        coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=self.video_processing_service,
        )

        assert coordinator._refresh_project_views_callback is None


class TestAnalysisCoordinatorCallbacks(unittest.TestCase):
    """Test suite for AnalysisCoordinator callback setters."""

    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = AnalysisCoordinator(
            root=Mock(),
            view=Mock(),
            ui_event_bus=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            analysis_service=Mock(),
            video_processing_service=Mock(),
        )

    def test_set_refresh_callback(self):
        """Test setting refresh callback."""
        mock_callback = Mock()
        self.coordinator.set_refresh_callback(mock_callback)
        assert self.coordinator._refresh_project_views_callback == mock_callback


class TestAnalysisCoordinatorGenerateReport(unittest.TestCase):
    """Test suite for generate_report method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            settings_obj=Mock(),
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=Mock(),
        )

    def test_generate_report_no_project(self):
        """Test generate_report when no project is loaded."""
        self.project_manager.project_data = None

        self.coordinator.generate_report()

        # Should show error via event bus
        self.ui_event_bus.publish_event.assert_called_once()
        call_args = self.ui_event_bus.publish_event.call_args
        assert "Erro" in str(call_args)

    def test_generate_report_no_videos(self):
        """Test generate_report when project has no videos."""
        self.project_manager.project_data = {"videos": []}

        self.coordinator.generate_report()

        # Should show info message
        self.ui_event_bus.publish_event.assert_called_once()

    @patch("threading.Thread")
    def test_generate_report_success(self, mock_thread):
        """Test successful report generation."""
        # Setup project with videos
        self.project_manager.project_data = {
            "videos": [
                {"path": "/path/to/video1.mp4", "has_trajectory": True},
                {"path": "/path/to/video2.mp4", "has_trajectory": True},
            ]
        }

        # Mock thread
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # Execute
        self.coordinator.generate_report()

        # Verify thread was created and started
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()


class TestAnalysisCoordinatorGenerateParquetSummaries(unittest.TestCase):
    """Test suite for generate_parquet_summaries method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            settings_obj=Mock(),
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=Mock(),
        )

    def test_generate_summaries_no_project(self):
        """Test generate_parquet_summaries when no project is loaded."""
        self.project_manager.project_data = None

        self.coordinator.generate_parquet_summaries([])

        # Should show error
        self.ui_event_bus.publish_event.assert_called_once()

    def test_generate_summaries_no_eligible_videos(self):
        """Test when there are no eligible videos with trajectory data."""
        self.project_manager.project_data = {"videos": [{"path": "/path/to/video1.mp4"}]}
        self.project_manager.get_selected_videos.return_value = [
            {"path": "/path/to/video1.mp4", "has_trajectory": False}
        ]

        self.coordinator.generate_parquet_summaries(["/path/to/video1.mp4"])

        # Should show info about no eligible videos
        self.ui_event_bus.publish_event.assert_called()

    @patch("threading.Thread")
    def test_generate_summaries_success(self, mock_thread):
        """Test successful parquet summary generation."""
        # Setup
        self.project_manager.project_data = {"videos": [{"path": "/path/to/video1.mp4"}]}
        self.project_manager.get_selected_videos.return_value = [
            {"path": "/path/to/video1.mp4", "has_trajectory": True}
        ]

        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        # Execute
        self.coordinator.generate_parquet_summaries(["/path/to/video1.mp4"])

        # Verify thread was created and started
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()


class TestAnalysisCoordinatorProcessSummaryVideo(unittest.TestCase):
    """Test suite for _process_summary_video method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=Mock(),
            ui_event_bus=Mock(),
            settings_obj=Mock(),
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=Mock(),
        )

    def test_process_video_no_path(self):
        """Test processing video with no path."""
        video = {"path": None}
        settings = Mock()

        state, msg, path, changed = self.coordinator._process_summary_video(video, settings)

        assert state == "skipped"
        assert "não definido" in msg
        assert path is None
        assert changed is False

    def test_process_video_no_trajectory(self):
        """Test processing video when trajectory file is missing."""
        video = {"path": "/path/to/video.mp4", "parquet_files": {}}
        settings = Mock()

        self.project_manager.resolve_results_directory.return_value = "/path/to/results"

        with patch("os.path.exists", return_value=False):
            state, msg, path, changed = self.coordinator._process_summary_video(video, settings)

        assert state == "skipped"
        assert "ausente" in msg

    @patch("os.path.exists", return_value=True)
    @patch("pandas.read_parquet")
    @patch("cv2.VideoCapture")
    @patch("zebtrack.core.analysis_coordinator.Reporter")
    def test_process_video_success(
        self, mock_reporter_class, mock_video_capture, mock_read_parquet, mock_exists
    ):
        """Test successful video processing."""
        # Setup video data
        video = {
            "path": "/path/to/video.mp4",
            "parquet_files": {"trajectory": "/path/to/trajectory.parquet"},
            "metadata": {},
        }
        settings = Mock()
        settings.analysis.interval_frames = 10

        # Mock project manager
        self.project_manager.resolve_results_directory.return_value = "/path/to/results"
        self.project_manager.get_zone_data.return_value = {
            "arena_polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "arena_width_cm": 10.0,
            "arena_height_cm": 10.0,
            "rois": [],
        }

        # Mock pandas DataFrame
        mock_df = Mock()
        mock_df.empty = False
        mock_read_parquet.return_value = mock_df

        # Mock VideoCapture
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 1000  # fps and frame count
        mock_video_capture.return_value = mock_cap

        # Mock Reporter
        mock_reporter = Mock()
        mock_reporter.export_summary_data.return_value = None
        mock_reporter_class.return_value = mock_reporter

        # Execute
        state, msg, path, changed = self.coordinator._process_summary_video(video, settings)

        # Verify
        assert state == "completed"
        assert changed is True
        mock_reporter.export_summary_data.assert_called_once()


class TestAnalysisCoordinatorSummariesWorker(unittest.TestCase):
    """Test suite for _generate_parquet_summaries_worker method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.project_manager = Mock()
        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=Mock(),
            ui_event_bus=Mock(),
            settings_obj=Mock(),
            project_manager=self.project_manager,
            analysis_service=Mock(),
            video_processing_service=Mock(),
        )
        self.coordinator._refresh_project_views_callback = Mock()

    def test_worker_with_empty_videos(self):
        """Test worker with empty video list."""
        settings = Mock()

        # Execute
        self.coordinator._generate_parquet_summaries_worker([], settings)

        # Should still finalize
        assert self.root.after.called

    @patch.object(AnalysisCoordinator, "_process_summary_video")
    def test_worker_with_successful_videos(self, mock_process):
        """Test worker with videos that process successfully."""
        videos = [{"path": "/path/to/video1.mp4"}, {"path": "/path/to/video2.mp4"}]
        settings = Mock()

        # Mock _process_summary_video to return success
        mock_process.return_value = ("completed", "video1", "/path/to/summary.parquet", True)

        # Execute
        self.coordinator._generate_parquet_summaries_worker(videos, settings)

        # Verify both videos were processed
        assert mock_process.call_count == 2

        # Verify project was saved (data_changed=True)
        self.project_manager.save_project.assert_called_once()

        # Verify finalize was scheduled
        assert self.root.after.called

    @patch.object(AnalysisCoordinator, "_process_summary_video")
    def test_worker_with_mixed_results(self, mock_process):
        """Test worker with some successful and some skipped videos."""
        videos = [{"path": "/path/to/video1.mp4"}, {"path": "/path/to/video2.mp4"}]
        settings = Mock()

        # First succeeds, second is skipped
        mock_process.side_effect = [
            ("completed", "video1", "/path/to/summary1.parquet", True),
            ("skipped", "video2: erro", None, False),
        ]

        # Execute
        self.coordinator._generate_parquet_summaries_worker(videos, settings)

        # Verify both videos were attempted
        assert mock_process.call_count == 2

        # Verify project was saved (at least one changed)
        self.project_manager.save_project.assert_called_once()

    @patch.object(AnalysisCoordinator, "_process_summary_video")
    def test_worker_exception_handling(self, mock_process):
        """Test worker handles exceptions gracefully."""
        videos = [{"path": "/path/to/video1.mp4"}]
        settings = Mock()

        # Mock to raise exception
        mock_process.side_effect = Exception("Test error")

        # Execute - should not crash
        try:
            self.coordinator._generate_parquet_summaries_worker(videos, settings)
            # If we get here, the exception was caught internally
            # Verify finalize still runs
            assert self.root.after.called
        except Exception:
            # If exception propagates, test fails
            self.fail("Worker should handle exceptions gracefully")


class TestAnalysisCoordinatorGenerateReportWorker(unittest.TestCase):
    """Test suite for _generate_report_worker method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            settings_obj=Mock(),
            project_manager=Mock(),
            analysis_service=self.analysis_service,
            video_processing_service=Mock(),
        )

    @patch("os.path.exists", return_value=True)
    def test_report_worker_success(self, mock_exists):
        """Test successful report generation in worker."""
        videos = [{"path": "/path/to/video1.mp4", "parquet_files": {"trajectory": "/traj.parquet"}}]
        settings = Mock()
        settings.analysis.default_output_format = "docx"

        # Mock analysis service
        self.analysis_service.generate_reports.return_value = ["/path/to/report.docx"]

        # Execute
        self.coordinator._generate_report_worker(videos, settings)

        # Verify analysis service was called
        self.analysis_service.generate_reports.assert_called_once()

        # Verify UI updates were scheduled
        assert self.root.after.called

    def test_report_worker_with_empty_videos(self):
        """Test report worker with no videos."""
        settings = Mock()

        # Execute
        self.coordinator._generate_report_worker([], settings)

        # Should schedule finalize
        assert self.root.after.called


if __name__ == "__main__":
    unittest.main()

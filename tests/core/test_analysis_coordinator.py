"""
Unit tests for AnalysisCoordinator.

Task 2.2: REFACTOR-VIEWMODEL-001
Tests for analysis pipeline, report generation, and parquet summaries.
"""

import unittest
from unittest.mock import Mock, patch

from zebtrack.core.analysis_coordinator import AnalysisCoordinator


class TestAnalysisCoordinatorInitialization(unittest.TestCase):
    """Test suite for AnalysisCoordinator initialization."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.ui_coordinator = Mock()
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
            ui_coordinator=self.ui_coordinator,
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
            ui_coordinator=self.ui_coordinator,
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
            ui_coordinator=Mock(),
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
        self.ui_coordinator = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=Mock(),
            project_manager=self.project_manager,
            analysis_service=self.analysis_service,
            video_processing_service=Mock(),
        )

    def test_generate_report_no_project(self):
        """Test generate_report when no project is loaded."""
        self.project_manager.project_data = None

        self.coordinator.generate_report(videos=[])

        # Should show warning via event bus (no videos)
        self.ui_event_bus.publish_event.assert_called_once()
        call_args = self.ui_event_bus.publish_event.call_args
        assert "ui:show_warning" in str(call_args) or "Nenhum" in str(call_args)

    def test_generate_report_no_videos(self):
        """Test generate_report when project has no videos."""
        self.project_manager.project_data = {"videos": []}

        self.coordinator.generate_report(videos=[])

        # Should show warning message
        self.ui_event_bus.publish_event.assert_called_once()

    @patch("zebtrack.core.analysis_coordinator.Reporter.export_project_report")
    @patch("pandas.DataFrame.to_excel")
    @patch("pathlib.Path.exists")
    @patch("pandas.read_parquet")
    def test_generate_report_success(
        self, mock_read_parquet, mock_exists, mock_to_excel, mock_export
    ):
        """Test successful report generation."""
        from pathlib import Path

        import pandas as pd

        # Setup project with videos
        videos = [
            {"path": "/path/to/video1.mp4", "has_trajectory": True},
            {"path": "/path/to/video2.mp4", "has_trajectory": True},
        ]
        self.project_manager.project_data = {"videos": videos}
        self.project_manager.resolve_results_directory.return_value = Path("/path/to/results")

        # Mock Path.exists to return True (parquet files exist)
        mock_exists.return_value = True

        # Mock read_parquet to return DataFrame
        mock_df = pd.DataFrame({"timestamp": [1, 2], "x": [0, 1], "y": [0, 1]})
        mock_read_parquet.return_value = mock_df

        # Mock ask_save_filename
        self.view.ask_save_filename.return_value = "/path/to/output.xlsx"

        # Execute
        self.coordinator.generate_report(videos=videos)

        # Verify to_excel was called
        mock_to_excel.assert_called_once()

        # Verify docx report was also generated
        mock_export.assert_called_once()


class TestAnalysisCoordinatorGenerateParquetSummaries(unittest.TestCase):
    """Test suite for generate_parquet_summaries method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.ui_event_bus = Mock()
        self.ui_coordinator = Mock()
        self.project_manager = Mock()
        self.analysis_service = Mock()

        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=self.view,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
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
        self.project_manager.get_all_videos.return_value = [
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
        self.project_manager.get_all_videos.return_value = [
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
            ui_coordinator=Mock(),
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
            state, msg, _path, _changed = self.coordinator._process_summary_video(video, settings)

        assert state == "skipped"
        assert "ausente" in msg



class TestAnalysisCoordinatorSummariesWorker(unittest.TestCase):
    """Test suite for _generate_parquet_summaries_worker method."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.ui_coordinator = Mock()
        self.project_manager = Mock()
        self.coordinator = AnalysisCoordinator(
            root=self.root,
            view=Mock(),
            ui_event_bus=Mock(),
            ui_coordinator=self.ui_coordinator,
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
        assert self.ui_coordinator.schedule.called

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
        assert self.ui_coordinator.schedule.called

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
            assert self.ui_coordinator.schedule.called
        except Exception:
            # If exception propagates, test fails
            self.fail("Worker should handle exceptions gracefully")


class TestAnalysisCoordinatorWorkerCallbacks(unittest.TestCase):
    """Test suite for worker completion callbacks."""

    def setUp(self):
        """Set up test fixtures."""
        self.coordinator = AnalysisCoordinator(
            root=Mock(),
            view=Mock(),
            ui_event_bus=Mock(),
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            analysis_service=Mock(),
            video_processing_service=Mock(),
        )

    @patch("zebtrack.core.analysis_coordinator.log")
    def test_on_worker_complete_with_exception(self, mock_log):
        """Test callback when worker raises an exception."""
        mock_future = Mock()
        test_exception = ValueError("Test error")
        mock_future.exception.return_value = test_exception

        self.coordinator._on_worker_complete(mock_future)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args
        assert call_args[0][0] == "analysis_coordinator.worker.exception"
        assert call_args[1]["error"] == "Test error"
        assert call_args[1]["exc_info"] == test_exception

    @patch("zebtrack.core.analysis_coordinator.log")
    def test_on_worker_complete_with_no_exception(self, mock_log):
        """Test callback when worker completes successfully."""
        mock_future = Mock()
        mock_future.exception.return_value = None

        self.coordinator._on_worker_complete(mock_future)

        mock_log.error.assert_not_called()

    @patch("zebtrack.core.analysis_coordinator.log")
    def test_on_worker_complete_with_cancelled_error(self, mock_log):
        """Test callback when future is cancelled."""
        from concurrent.futures import CancelledError

        mock_future = Mock()
        mock_future.exception.side_effect = CancelledError()

        self.coordinator._on_worker_complete(mock_future)

        mock_log.warning.assert_called_once_with("analysis_coordinator.worker.cancelled")

    @patch("zebtrack.core.analysis_coordinator.log")
    def test_on_worker_complete_with_timeout_error(self, mock_log):
        """Test callback when future times out."""
        from concurrent.futures import TimeoutError as FutureTimeoutError

        mock_future = Mock()
        mock_future.exception.side_effect = FutureTimeoutError()

        self.coordinator._on_worker_complete(mock_future)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args
        assert call_args[0][0] == "analysis_coordinator.worker.timeout"

    @patch("zebtrack.core.analysis_coordinator.log")
    def test_on_worker_complete_with_unexpected_error(self, mock_log):
        """Test callback with unexpected error in callback logic."""
        mock_future = Mock()
        mock_future.exception.side_effect = RuntimeError("Unexpected error")

        self.coordinator._on_worker_complete(mock_future)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args
        assert call_args[0][0] == "analysis_coordinator.worker.callback_error"
        assert call_args[1]["exc_info"] is True

    def test_shutdown_closes_executor(self):
        """Test that shutdown properly closes the thread pool executor."""
        mock_executor = Mock()
        self.coordinator._executor = mock_executor

        self.coordinator.shutdown()

        mock_executor.shutdown.assert_called_once_with(wait=True)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for VideoOrchestrator.

Task 2.2: REFACTOR-VIEWMODEL-001
Tests for batch video processing, workflows, and project orchestration.
"""

import unittest
from typing import Any, cast
from unittest.mock import Mock, patch

from zebtrack.core.video_orchestrator import VideoOrchestrator


class TestVideoOrchestratorInitialization(unittest.TestCase):
    """Test suite for VideoOrchestrator initialization."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.state_manager = Mock()
        self.ui_event_bus = Mock()
        self.ui_coordinator = Mock()
        self.settings = Mock()
        self.project_manager = Mock()
        self.video_processing_service = Mock()
        self.analysis_service = Mock()
        self.recorder = Mock()

    def test_init_with_all_dependencies(self):
        """Test initialization with all dependencies."""
        orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        assert orchestrator.root == self.root
        assert orchestrator.view == self.view
        assert orchestrator.state_manager == self.state_manager
        assert orchestrator.ui_event_bus == self.ui_event_bus
        assert orchestrator.ui_coordinator == self.ui_coordinator
        assert orchestrator.settings == self.settings
        assert orchestrator.project_manager == self.project_manager
        assert orchestrator.video_processing_service == self.video_processing_service
        assert orchestrator.analysis_service == self.analysis_service
        assert orchestrator.recorder == self.recorder

    def test_init_callbacks_are_none(self):
        """Test that callbacks are initialized to None."""
        orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=self.ui_event_bus,
            ui_coordinator=self.ui_coordinator,
            settings_obj=self.settings,
            project_manager=self.project_manager,
            video_processing_service=self.video_processing_service,
            analysis_service=self.analysis_service,
            recorder=self.recorder,
        )

        assert orchestrator._set_main_arena_polygon_callback is None
        assert orchestrator._activate_analysis_view_mode_callback is None
        assert orchestrator._refresh_project_views_callback is None
        assert orchestrator._publish_processing_mode_callback is None


class TestVideoOrchestratorCallbacks(unittest.TestCase):
    """Test suite for VideoOrchestrator callback setters."""

    def setUp(self):
        """Set up test fixtures."""
        ui_event_bus = Mock()
        ui_event_bus.publish_event = Mock()
        self.orchestrator = VideoOrchestrator(
            root=Mock(),
            view=Mock(),
            state_manager=Mock(),
            ui_event_bus=ui_event_bus,
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            video_processing_service=Mock(),
            analysis_service=Mock(),
            recorder=Mock(),
        )
        self.publish_event_mock = ui_event_bus.publish_event

    def test_set_arena_callback(self):
        """Test setting arena polygon callback."""
        mock_callback = Mock()
        self.orchestrator.set_arena_callback(mock_callback)
        assert self.orchestrator._set_main_arena_polygon_callback == mock_callback

    def test_set_analysis_view_mode_callback(self):
        """Test setting analysis view mode callback."""
        mock_callback = Mock()
        self.orchestrator.set_analysis_view_mode_callback(mock_callback)
        assert self.orchestrator._activate_analysis_view_mode_callback == mock_callback

    def test_set_refresh_callback(self):
        """Test setting refresh callback."""
        mock_callback = Mock()
        self.orchestrator.set_refresh_callback(mock_callback)
        assert self.orchestrator._refresh_project_views_callback == mock_callback

    def test_set_publish_processing_mode_callback(self):
        """Test setting publish processing mode callback."""
        mock_callback = Mock()
        self.orchestrator.set_publish_processing_mode_callback(mock_callback)
        assert self.orchestrator._publish_processing_mode_callback == mock_callback


class TestVideoOrchestratorScanValidate(unittest.TestCase):
    """Test suite for _scan_and_validate_candidate_paths."""

    def setUp(self):
        """Set up test fixtures."""
        ui_event_bus = Mock()
        ui_event_bus.publish_event = Mock()
        self.orchestrator = VideoOrchestrator(
            root=Mock(),
            view=Mock(),
            state_manager=Mock(),
            ui_event_bus=ui_event_bus,
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            video_processing_service=Mock(),
            analysis_service=Mock(),
            recorder=Mock(),
        )
        self.publish_event_mock = ui_event_bus.publish_event

    def test_scan_with_empty_candidates(self):
        """Test scanning with empty candidate list."""
        candidate_entries: list[dict[str, Any]] = []
        result = self.orchestrator._scan_and_validate_candidate_paths(candidate_entries)

        assert result == (None, None, None)
        self.publish_event_mock.assert_called_once()

    def test_scan_with_invalid_paths(self):
        """Test scanning with candidates that have no valid paths."""
        candidate_entries: list[dict[str, Any]] = [
            {"path": None},
            {"path": ""},
            {"other_key": "value"},
        ]
        result = self.orchestrator._scan_and_validate_candidate_paths(candidate_entries)

        assert result == (None, None, None)

    @patch("zebtrack.core.video_orchestrator.ProjectManager.scan_input_paths")
    @patch("os.path.normpath")
    def test_scan_with_valid_paths(self, mock_normpath, mock_scan):
        """Test scanning with valid video paths."""
        # Setup
        candidate_entries = [
            {"path": "/path/to/video1.mp4"},
            {"path": "/path/to/video2.mp4"},
        ]

        # Mock normpath to return consistent values
        mock_normpath.side_effect = lambda x: x

        # Mock scan_input_paths to return video info
        mock_scan.return_value = [
            {"path": "/path/to/video1.mp4", "width": 1280, "height": 720},
            {"path": "/path/to/video2.mp4", "width": 1920, "height": 1080},
        ]

        # Execute
        info_by_norm, missing_files, scanned_videos = (
            self.orchestrator._scan_and_validate_candidate_paths(candidate_entries)
        )

        # Verify
        assert info_by_norm is not None
        assert len(info_by_norm) == 2
        assert missing_files == []
        assert scanned_videos is not None
        assert len(scanned_videos) == 2

    @patch("zebtrack.core.video_orchestrator.ProjectManager.scan_input_paths")
    @patch("os.path.normpath")
    def test_scan_with_missing_files(self, mock_normpath, mock_scan):
        """Test scanning when some files are missing."""
        # Setup
        candidate_entries = [
            {"path": "/path/to/video1.mp4"},
            {"path": "/path/to/missing.mp4"},
        ]

        mock_normpath.side_effect = lambda x: x

        # Only one video found
        mock_scan.return_value = [{"path": "/path/to/video1.mp4", "width": 1280, "height": 720}]

        # Execute
        info_by_norm, missing_files, scanned_videos = (
            self.orchestrator._scan_and_validate_candidate_paths(candidate_entries)
        )

        # Verify
        assert info_by_norm is not None
        assert len(info_by_norm) == 1
        assert missing_files is not None
        assert "/path/to/missing.mp4" in missing_files
        assert scanned_videos is not None
        assert len(scanned_videos) == 1
        # Should publish warning about missing files
        self.publish_event_mock.assert_called()


class TestVideoOrchestratorClassifyVideos(unittest.TestCase):
    """Test suite for _classify_candidate_videos."""

    def setUp(self):
        """Set up test fixtures."""
        self.orchestrator = VideoOrchestrator(
            root=Mock(),
            view=Mock(),
            state_manager=Mock(),
            ui_event_bus=Mock(),
            ui_coordinator=Mock(),
            settings_obj=Mock(),
            project_manager=Mock(),
            video_processing_service=Mock(),
            analysis_service=Mock(),
            recorder=Mock(),
        )

    @patch("os.path.normpath")
    def test_classify_with_trajectory(self, mock_normpath):
        """Test classification of videos with trajectory data."""
        mock_normpath.side_effect = lambda x: x

        candidate_entries = [{"path": "/path/to/video1.mp4"}]
        info_by_norm = {
            "/path/to/video1.mp4": {
                "path": "/path/to/video1.mp4",
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
                "has_complete_data": True,
            }
        }

        result = self.orchestrator._classify_candidate_videos(candidate_entries, info_by_norm)
        ready_with_trajectory, ready_with_zones, arena_only, without_arena, _data_changed = result

        assert len(ready_with_trajectory) == 1
        assert len(ready_with_zones) == 0
        assert len(arena_only) == 0
        assert len(without_arena) == 0

    @patch("os.path.normpath")
    def test_classify_with_zones_only(self, mock_normpath):
        """Test classification of videos with zones but no trajectory."""
        mock_normpath.side_effect = lambda x: x

        candidate_entries = [{"path": "/path/to/video1.mp4"}]
        info_by_norm = {
            "/path/to/video1.mp4": {
                "path": "/path/to/video1.mp4",
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False,
            }
        }

        result = self.orchestrator._classify_candidate_videos(candidate_entries, info_by_norm)
        ready_with_trajectory, ready_with_zones, arena_only, without_arena, _data_changed = result

        assert len(ready_with_trajectory) == 0
        assert len(ready_with_zones) == 1
        assert len(arena_only) == 0
        assert len(without_arena) == 0

    @patch("os.path.normpath")
    def test_classify_arena_only(self, mock_normpath):
        """Test classification of videos with arena only."""
        mock_normpath.side_effect = lambda x: x

        candidate_entries = [{"path": "/path/to/video1.mp4"}]
        info_by_norm = {
            "/path/to/video1.mp4": {
                "path": "/path/to/video1.mp4",
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
            }
        }

        result = self.orchestrator._classify_candidate_videos(candidate_entries, info_by_norm)
        ready_with_trajectory, ready_with_zones, arena_only, without_arena, _data_changed = result

        assert len(ready_with_trajectory) == 0
        assert len(ready_with_zones) == 0
        assert len(arena_only) == 1
        assert len(without_arena) == 0

    @patch("os.path.normpath")
    def test_classify_without_arena(self, mock_normpath):
        """Test classification of videos without arena."""
        mock_normpath.side_effect = lambda x: x

        candidate_entries = [{"path": "/path/to/video1.mp4"}]
        info_by_norm = {
            "/path/to/video1.mp4": {
                "path": "/path/to/video1.mp4",
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
            }
        }

        result = self.orchestrator._classify_candidate_videos(candidate_entries, info_by_norm)
        ready_with_trajectory, ready_with_zones, arena_only, without_arena, _data_changed = result

        assert len(ready_with_trajectory) == 0
        assert len(ready_with_zones) == 0
        assert len(arena_only) == 0
        assert len(without_arena) == 1

    @patch("os.path.normpath")
    def test_classify_data_changed_detection(self, mock_normpath):
        """Test that data_changed flag is set when video flags are updated."""
        mock_normpath.side_effect = lambda x: x

        # Video dict has outdated flags
        candidate_entries = [{"path": "/path/to/video1.mp4", "has_arena": False}]
        # But scanned info shows arena exists
        info_by_norm = {
            "/path/to/video1.mp4": {
                "path": "/path/to/video1.mp4",
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
            }
        }

        result = self.orchestrator._classify_candidate_videos(candidate_entries, info_by_norm)
        _, _, _, _, data_changed = result

        assert data_changed is True
        # Verify the flag was updated in the candidate dict
        assert candidate_entries[0]["has_arena"] is True


class TestVideoOrchestratorProcessingCallbacks(unittest.TestCase):
    """Test suite for _create_processing_callbacks."""

    def setUp(self):
        """Set up test fixtures."""
        self.root = Mock()
        self.view = Mock()
        self.state_manager = Mock()
        self.ui_coordinator = Mock()

        self.orchestrator = VideoOrchestrator(
            root=self.root,
            view=self.view,
            state_manager=self.state_manager,
            ui_event_bus=Mock(),
            ui_coordinator=self.ui_coordinator,
            settings_obj=Mock(),
            project_manager=Mock(),
            video_processing_service=Mock(),
            analysis_service=Mock(),
            recorder=Mock(),
        )

        self.orchestrator._refresh_project_views_callback = Mock()
        self.orchestrator._publish_processing_mode_callback = Mock()

    def test_create_callbacks_returns_all_callbacks(self):
        """Test that _create_processing_callbacks returns all required callbacks."""
        eligible_videos = [{"path": "/path/to/video1.mp4"}]
        callbacks = self.orchestrator._create_processing_callbacks(eligible_videos)

        assert callbacks.on_started is not None
        assert callbacks.on_progress is not None
        assert callbacks.on_frame_processed is not None
        assert callbacks.on_video_completed is not None
        assert callbacks.on_error is not None
        assert callbacks.on_completed is not None
        assert callbacks.on_fatal_error is not None

    def test_on_started_callback(self):
        """Test on_started callback behavior."""
        eligible_videos = [{"path": "/path/to/video1.mp4"}]
        callbacks = self.orchestrator._create_processing_callbacks(eligible_videos)

        # Execute on_started
        callbacks.on_started()

        # Verify UI coordinator calls
        self.ui_coordinator.show_progress_bar.assert_called_once_with(self.view)
        self.ui_coordinator.set_status.assert_called_once()

    def test_on_progress_callback(self):
        """Test on_progress callback behavior."""
        eligible_videos = [{"path": "/path/to/video1.mp4"}]
        callbacks = self.orchestrator._create_processing_callbacks(eligible_videos)

        # Execute on_progress
        stats = {"current_frame": 50, "total_frames": 100}
        callbacks.on_progress(0, 1, "experiment", 0.5, "Processing...", stats)

        # Verify UI updates
        self.ui_coordinator.set_status.assert_called_once()
        self.ui_coordinator.update_progress.assert_called_once_with(self.view, 0.5)
        self.state_manager.update_processing_state.assert_called_once()

    def test_on_completed_callback_not_cancelled(self):
        """Test on_completed callback when processing finishes successfully."""
        eligible_videos = [{"path": "/path/to/video1.mp4"}]
        callbacks = self.orchestrator._create_processing_callbacks(eligible_videos)

        # Execute on_completed
        callbacks.on_completed(False, "/output", {})

        # Verify cleanup calls
        self.ui_coordinator.hide_progress_bar.assert_called_once_with(self.view)
        self.state_manager.update_processing_state.assert_called()
        assert self.orchestrator._refresh_project_views_callback is not None
        refresh_callback = cast(Mock, self.orchestrator._refresh_project_views_callback)
        assert refresh_callback.called

    def test_on_error_callback(self):
        """Test on_error callback behavior."""
        eligible_videos = [{"path": "/path/to/video1.mp4"}]
        callbacks = self.orchestrator._create_processing_callbacks(eligible_videos)

        # Execute on_error
        test_error = ValueError("Test error")
        callbacks.on_error(test_error, "test context")

        # Verify error was scheduled to be shown
        # Note: actual error display happens via root.after(0, ...)
        assert self.root.after.called


if __name__ == "__main__":
    unittest.main()

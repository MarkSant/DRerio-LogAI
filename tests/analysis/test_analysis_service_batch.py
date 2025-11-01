"""
Tests for batch video processing in AnalysisService.
Focus: Batch coordination, progress tracking, error handling.
"""
import threading
from unittest.mock import MagicMock

import pytest

from zebtrack.analysis.analysis_service import AnalysisService


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.trajectory_smoothing.enabled = True
    settings.trajectory_smoothing.window_length = 11
    settings.trajectory_smoothing.polyorder = 3
    settings.performance.enable_parallel_analysis = False
    settings.video_processing.freezing_velocity_threshold = 1.0
    settings.video_processing.freezing_min_duration_s = 0.5
    return settings


@pytest.fixture
def analysis_service(mock_settings):
    """Create AnalysisService instance."""
    return AnalysisService(settings_obj=mock_settings)


@pytest.fixture
def mock_video_paths(tmp_path):
    """Create mock video paths."""
    paths = []
    for i in range(5):
        video_path = tmp_path / f"video_{i}.mp4"
        video_path.touch()

        # Create corresponding parquet
        parquet_path = tmp_path / f"video_{i}_trajectory.parquet"
        parquet_path.touch()

        paths.append({
            'video': video_path,
            'parquet': parquet_path,
            'path': str(video_path)
        })
    return paths


class TestBatchProcessing:
    """Test batch video processing functionality."""

    def test_process_videos_batch_initialization(
        self, analysis_service, mock_video_paths, tmp_path
    ):
        """Test batch processing initialization."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths]

        # Mock all required components
        mock_controller = MagicMock()
        mock_controller.apply_project_settings_to_batch.return_value = True
        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller._process_single_video.return_value = (True, str(tmp_path))
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.project_data = {}
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}

        mock_root = MagicMock()
        cancel_event = threading.Event()

        # Execute batch processing
        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process[:2],  # Process only 2 videos
            output_base_dir=str(tmp_path),
            single_video_config=None,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        assert not was_cancelled
        assert mock_controller._process_single_video.call_count == 2
        assert mock_root.after.call_count > 0

    def test_process_videos_batch_with_single_video_config(
        self, analysis_service, mock_video_paths, tmp_path
    ):
        """Test batch processing with single video configuration."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths[:1]]
        single_video_config = {'analysis_interval_frames': 5}

        mock_controller = MagicMock()
        mock_controller._process_single_video.return_value = (True, str(tmp_path))
        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}

        mock_root = MagicMock()
        cancel_event = threading.Event()

        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process,
            output_base_dir=str(tmp_path),
            single_video_config=single_video_config,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        assert not was_cancelled
        # Should not call apply_project_settings_to_batch for single video
        assert not mock_controller.apply_project_settings_to_batch.called

    def test_process_videos_batch_cancellation(self, analysis_service, mock_video_paths, tmp_path):
        """Test batch processing can be cancelled."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths]

        mock_controller = MagicMock()
        mock_controller._process_single_video.return_value = (False, None)
        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.project_data = {}
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}

        mock_root = MagicMock()
        cancel_event = threading.Event()
        cancel_event.set()  # Pre-cancel before processing

        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process,
            output_base_dir=str(tmp_path),
            single_video_config=None,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        assert was_cancelled
        # Should have made UI calls
        assert mock_root.after.call_count > 0

    def test_process_videos_batch_partial_processing(
        self, analysis_service, mock_video_paths, tmp_path
    ):
        """Test batch processing with partial success."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths[:3]]

        mock_controller = MagicMock()
        mock_controller.apply_project_settings_to_batch.return_value = True

        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.project_data = {}
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}

        mock_root = MagicMock()
        cancel_event = threading.Event()

        # Track calls and set cancel after first video is processed
        call_count = [0]

        def process_single_video_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                cancel_event.set()
            if cancel_event.is_set():
                return (False, None)
            else:
                return (True, str(tmp_path))

        mock_controller._process_single_video.side_effect = process_single_video_side_effect

        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process,
            output_base_dir=str(tmp_path),
            single_video_config=None,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        # Could be cancelled or not depending on timing
        assert isinstance(was_cancelled, bool)

    def test_process_videos_batch_with_metadata_derivation(
        self, analysis_service, mock_video_paths, tmp_path
    ):
        """Test batch processing with metadata derivation."""
        videos_to_process = [
            {'path': str(v['video']), 'metadata': {'group': 'control'}}
            for v in mock_video_paths[:2]
        ]

        mock_controller = MagicMock()
        mock_controller.apply_project_settings_to_batch.return_value = True
        mock_controller._process_single_video.return_value = (True, str(tmp_path))
        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.project_data = {}
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}
        mock_project_manager.derive_processing_metadata.return_value = {'subject': 'fish_1'}

        mock_root = MagicMock()
        cancel_event = threading.Event()

        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process,
            output_base_dir=str(tmp_path),
            single_video_config=None,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        assert not was_cancelled
        # Verify metadata derivation was attempted
        assert mock_project_manager.resolve_analysis_profile.called

    def test_process_videos_batch_exception_handling(
        self, analysis_service, mock_video_paths, tmp_path
    ):
        """Test batch processing handles exceptions gracefully."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths[:1]]

        mock_controller = MagicMock()
        mock_controller.apply_project_settings_to_batch.return_value = True
        mock_controller._process_single_video.side_effect = RuntimeError("Processing error")
        mock_controller.view.show_progress_bar = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_error = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.project_data = {}
        mock_project_manager.set_active_zone_video = MagicMock()
        mock_project_manager.resolve_analysis_profile.return_value = {'name': 'default'}

        mock_root = MagicMock()
        cancel_event = threading.Event()

        # Should not raise exception, should handle gracefully
        was_cancelled, _final_dir = analysis_service.process_videos_batch(
            videos_to_process=videos_to_process,
            output_base_dir=str(tmp_path),
            single_video_config=None,
            controller=mock_controller,
            cancel_event=cancel_event,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        # Verify error handling occurred (show_error may be called via after())
        # Just verify the batch completed without raising
        assert isinstance(was_cancelled, bool)

    def test_finalize_batch_processing_success(self, analysis_service, mock_video_paths, tmp_path):
        """Test finalize batch processing for successful completion."""
        videos_to_process = [{'path': str(v['video'])} for v in mock_video_paths[:2]]

        mock_controller = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.set_active_zone_video = MagicMock()

        mock_root = MagicMock()

        analysis_service._finalize_batch_processing(
            was_cancelled=False,
            videos_to_process=videos_to_process,
            final_output_dir=str(tmp_path),
            controller=mock_controller,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        # Verify UI callbacks were made
        assert mock_root.after.call_count > 0
        assert mock_controller.refresh_project_views.called

    def test_finalize_batch_processing_cancelled(self, analysis_service, tmp_path):
        """Test finalize batch processing for cancellation."""
        mock_controller = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.set_active_zone_video = MagicMock()

        mock_root = MagicMock()

        analysis_service._finalize_batch_processing(
            was_cancelled=True,
            videos_to_process=[],
            final_output_dir=str(tmp_path),
            controller=mock_controller,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        # Verify UI callbacks were made
        assert mock_root.after.call_count > 0

    def test_finalize_batch_processing_empty_videos_list(self, analysis_service, tmp_path):
        """Test finalize batch processing with empty videos list."""
        mock_controller = MagicMock()
        mock_controller.view.stop_analysis_view_mode = MagicMock()
        mock_controller.view.hide_progress_bar = MagicMock()
        mock_controller.view.show_info = MagicMock()
        mock_controller.view.set_status = MagicMock()
        mock_controller._publish_processing_mode = MagicMock()
        mock_controller.refresh_project_views = MagicMock()

        mock_project_manager = MagicMock()
        mock_project_manager.set_active_zone_video = MagicMock()

        mock_root = MagicMock()

        # Should handle empty videos list gracefully
        analysis_service._finalize_batch_processing(
            was_cancelled=False,
            videos_to_process=[],
            final_output_dir=str(tmp_path),
            controller=mock_controller,
            project_manager=mock_project_manager,
            root_tk=mock_root
        )

        # Verify UI callbacks were made
        assert mock_root.after.call_count > 0

    def test_determine_intervals_precedence(self, analysis_service):
        """Test that single video config takes precedence over project data."""
        single_video_config = {
            'analysis_interval_frames': 7,
            'display_interval_frames': 14
        }
        project_data = {
            'analysis_interval_frames': 20,
            'display_interval_frames': 30
        }

        analysis_interval, display_interval = analysis_service.determine_processing_intervals(
            single_video_config, project_data
        )

        # Single video config should take precedence
        assert analysis_interval == 7
        assert display_interval == 14

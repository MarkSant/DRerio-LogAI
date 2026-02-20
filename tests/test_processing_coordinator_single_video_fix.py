from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.report_generation_coordinator import ReportGenerationCoordinator
from zebtrack.coordinators.video_processing_coordinator import VideoProcessingCoordinator
from zebtrack.core.project.project_manager import ProjectManager


class TestProcessingCoordinatorSingleVideoFix:
    @pytest.fixture
    def coordinator(self):
        # Mock dependencies
        state_manager = MagicMock()
        project_manager = MagicMock(spec=ProjectManager)
        detector_service = MagicMock()
        weight_manager = MagicMock()
        settings = MagicMock()
        ui_coordinator = MagicMock()
        ui_state_controller = MagicMock()
        cancel_event = MagicMock()
        video_selection = MagicMock()
        video_validation = MagicMock()
        video_classification = MagicMock()

        coordinator = VideoProcessingCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            detector_service=detector_service,
            weight_manager=weight_manager,
            settings_obj=settings,
            ui_coordinator=ui_coordinator,
            ui_state_controller=ui_state_controller,
            cancel_event=cancel_event,
            video_selection_service=video_selection,
            video_validation_service=video_validation,
            video_classification_service=video_classification,
        )

        # Wire report coordinator for proxy methods
        report_coord = ReportGenerationCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            settings_obj=settings,
            event_bus=None,
        )
        coordinator._report_coordinator = report_coord

        return coordinator

    def test_generate_parquet_summaries_single_video_mode(self, coordinator):
        """
        Test that save_project is NOT called when project_path is None (Single Video Mode),
        even if data changed.
        """
        # Setup Single Video Mode
        coordinator.project_manager.project_path = None

        # Mock _process_summary_video on report coordinator to return changed=True
        # Returns: (status, message, path, changed)
        coordinator._report_coordinator._process_summary_video = MagicMock(
            return_value=("completed", "msg", "path.parquet", True)
        )

        target_videos = [{"path": "video.mp4"}]

        # Execute
        coordinator._report_coordinator.generate_parquet_summaries(target_videos)

        # Verify
        coordinator.project_manager.save_project.assert_not_called()

    def test_generate_parquet_summaries_project_mode(self, coordinator):
        """
        Test that save_project IS called when project_path is set (Project Mode),
        if data changed.
        """
        # Setup Project Mode
        coordinator.project_manager.project_path = "C:/fake/project"

        # Mock _process_summary_video on report coordinator to return changed=True
        coordinator._report_coordinator._process_summary_video = MagicMock(
            return_value=("completed", "msg", "path.parquet", True)
        )

        target_videos = [{"path": "video.mp4"}]

        # Execute
        coordinator._report_coordinator.generate_parquet_summaries(target_videos)

        # Verify
        coordinator.project_manager.save_project.assert_called_once()

    def test_load_zones_for_eligible_videos_single_video_mode(self, coordinator):
        """
        Test that save_project is NOT called when project_path is None
        in _load_zones_for_eligible_videos.
        """
        # Setup Single Video Mode
        coordinator.project_manager.project_path = None

        # Mock dependencies to simulate zone update
        eligible_videos = [{"path": "video.mp4", "has_arena": True}]

        # We need to mock ProjectManager static methods or instance methods used
        coordinator.project_manager.resolve_results_directory.return_value = "results_dir"
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = None

        # Mock load_zones_from_parquet on ProjectManager class or instance
        # The code uses ProjectManager.load_zones_from_parquet (static)
        # But we can patch it or rely on fallback

        with patch(
            "zebtrack.core.project.project_manager.ProjectManager.load_zones_from_parquet"
        ) as mock_load:
            mock_load.return_value = None  # Fail parquet load to trigger fallback

            # Mock get_zone_data to return a zone with polygon (simulating update)
            mock_zone = MagicMock()
            mock_zone.polygon = [[0, 0], [10, 10], [10, 0]]
            coordinator.project_manager.get_zone_data.return_value = mock_zone

            # Execute
            coordinator._load_zones_for_eligible_videos(eligible_videos)

            # Verify save_project was NOT called
            coordinator.project_manager.save_project.assert_not_called()

            # Verify save_zone_data WAS called (persist=False)
            coordinator.project_manager.save_zone_data.assert_called()
            _args, kwargs = coordinator.project_manager.save_zone_data.call_args
            assert kwargs.get("persist") is False

    def test_load_zones_for_eligible_videos_project_mode(self, coordinator):
        """
        Test that save_project IS called when project_path is set in
        _load_zones_for_eligible_videos.
        """
        # Setup Project Mode
        coordinator.project_manager.project_path = "C:/fake/project"

        eligible_videos = [{"path": "video.mp4", "has_arena": True}]
        coordinator.project_manager.resolve_results_directory.return_value = "results_dir"
        coordinator.project_manager.get_multi_aquarium_zone_data.return_value = None

        with patch(
            "zebtrack.core.project.project_manager.ProjectManager.load_zones_from_parquet"
        ) as mock_load:
            mock_load.return_value = None

            mock_zone = MagicMock()
            mock_zone.polygon = [[0, 0], [10, 10], [10, 0]]
            coordinator.project_manager.get_zone_data.return_value = mock_zone

            # Execute
            coordinator._load_zones_for_eligible_videos(eligible_videos)

            # Verify save_project WAS called
            coordinator.project_manager.save_project.assert_called_once()

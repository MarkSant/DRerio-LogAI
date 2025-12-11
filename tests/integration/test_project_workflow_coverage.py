"""Integration tests for Project Workflow Coverage.

Covers:
- Creating/Reopening projects (pre-recorded videos)
- Creating/Processing ROIs
- Main arenas
- Parquet coordinates (mocked generation/validation)
- Reports/Summaries (via ProcessingCoordinator integration)
"""

from unittest.mock import MagicMock, patch

import pytest

from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
from zebtrack.core.project_manager import ProjectManager

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create some dummy videos
    video_dir = project_dir / "videos"
    video_dir.mkdir()
    (video_dir / "video1.mp4").touch()
    (video_dir / "video2.mp4").touch()

    return project_dir


@pytest.fixture
def real_project_manager(temp_project_dir):
    """Create a real ProjectManager instance using temp dir."""
    pm = ProjectManager()
    # Mock asset manager to avoid complex dependencies
    pm.asset_manager = MagicMock()
    # Ensure default profile returns a dict, not a Mock, for JSON serialization
    pm.asset_manager._default_analysis_profile.return_value = {
        "name": "Default",
        "description": "Default profile",
        "settings": {},
    }
    return pm


@pytest.fixture
def mock_dependencies():
    """Create all mocked dependencies for ProcessingCoordinator."""
    deps = {
        "state_manager": MagicMock(),
        "detector_service": MagicMock(),
        "weight_manager": MagicMock(),
        "settings_obj": MagicMock(),
        "ui_coordinator": MagicMock(),
        "ui_state_controller": MagicMock(),
        "cancel_event": MagicMock(),
        "video_selection_service": MagicMock(),
        "video_validation_service": MagicMock(),
        "video_classification_service": MagicMock(),
        "analysis_service": MagicMock(),
        "recorder_factory": MagicMock(),
        "event_bus": MagicMock(),
        "view": MagicMock(),
        "root": None,  # Disable root so tasks run synchronously
        "detector": MagicMock(),
    }

    # Configure defaults
    deps["state_manager"].get_processing_state.return_value = MagicMock(is_processing=False)
    deps["detector_service"].detector.get_zones.return_value = []
    deps["detector_service"].detector.is_single_subject_mode.return_value = False

    # Configure settings
    deps["settings_obj"].processing.enable_parallel_analysis = False
    deps["settings_obj"].tracking.use_single_subject_tracker = False
    deps["settings_obj"].video_processing.batch_retry_strategy = "retry"

    return deps


@pytest.fixture
def integration_coordinator(real_project_manager, mock_dependencies):
    """Create ProcessingCoordinator with real ProjectManager."""
    coordinator = ProcessingCoordinator(project_manager=real_project_manager, **mock_dependencies)
    return coordinator


# =============================================================================
# TESTS
# =============================================================================


class TestProjectCreationReopening:
    """Test creating and reopening projects with videos."""

    def test_create_project_initializes_state(self, integration_coordinator, temp_project_dir):
        """Test creating a new project initializes internal state."""
        project_path = temp_project_dir / "new_project.json"

        # Simulate creating a project via ProjectManager
        integration_coordinator.project_manager.create_new_project(
            str(project_path),
            project_type="Pre-recorded",
            aquarium_width_cm=100.0,
            aquarium_height_cm=50.0,
        )
        integration_coordinator.project_manager.project_data["name"] = "Integration Test Project"

        assert str(integration_coordinator.project_manager.project_path) == str(project_path)
        assert (
            integration_coordinator.project_manager.project_data["name"]
            == "Integration Test Project"
        )

        # Verify validation passes
        result = integration_coordinator.validate_can_start_processing(check_project_loaded=True)
        assert result.is_valid is True

    def test_reopen_project_restores_state(self, integration_coordinator, temp_project_dir):
        """Test reopening an existing project restores state."""
        project_path = temp_project_dir / "existing_project"
        project_path.mkdir()

        # Create a dummy project file (project_config.json)
        import json

        config_path = project_path / "project_config.json"
        data = {
            "project_name": "Existing Project",
            "batches": [
                {
                    "videos": [
                        {
                            "path": str(temp_project_dir / "videos" / "video1.mp4"),
                            "status": "pending",
                        }
                    ]
                }
            ],
        }
        with open(config_path, "w") as f:
            json.dump(data, f)

        # Open it
        integration_coordinator.project_manager.load_project(str(project_path))

        assert (
            integration_coordinator.project_manager.project_data["project_name"]
            == "Existing Project"
        )
        assert len(integration_coordinator.project_manager.get_all_videos()) == 1


class TestZoneAndArenaWorkflow:
    """Test creating and processing ROIs and Main Arenas."""

    def test_set_main_arena_persists_to_project(self, integration_coordinator, temp_project_dir):
        """Test setting main arena saves to project file."""
        project_path = temp_project_dir / "arena_project"
        integration_coordinator.project_manager.create_new_project(
            str(project_path), project_type="Pre-recorded"
        )

        points = [[0, 0], [100, 0], [100, 50], [0, 50]]

        # Action
        success = integration_coordinator.set_main_arena_polygon(points)

        assert success is True

        # Verify persistence
        loaded_data = integration_coordinator.project_manager.project_data
        assert "detection_zones" in loaded_data
        assert loaded_data["detection_zones"]["polygon"] == points

    def test_add_roi_persists_to_project(self, integration_coordinator, temp_project_dir):
        """Test adding ROI saves to project file."""
        project_path = temp_project_dir / "roi_project"
        integration_coordinator.project_manager.create_new_project(
            str(project_path), project_type="Pre-recorded"
        )

        # Setup main arena first (required for validation)
        arena_points = [[0, 0], [100, 0], [100, 100], [0, 100]]
        integration_coordinator.set_main_arena_polygon(arena_points)

        roi_points = [[10, 10], [20, 10], [20, 20], [10, 20]]

        # Action
        success = integration_coordinator.add_roi_polygon(roi_points, "Test ROI", (255, 0, 0))

        assert success is True

        # Verify persistence
        loaded_data = integration_coordinator.project_manager.project_data
        assert len(loaded_data["detection_zones"]["roi_polygons"]) == 1
        assert loaded_data["detection_zones"]["roi_names"][0] == "Test ROI"

    def test_add_roi_overlap_logic(
        self, integration_coordinator, temp_project_dir, mock_dependencies
    ):
        """Test ROI overlap detection logic via Coordinator."""
        project_path = temp_project_dir / "overlap_project"
        integration_coordinator.project_manager.create_new_project(
            str(project_path), project_type="Pre-recorded"
        )
        integration_coordinator.set_main_arena_polygon([[0, 0], [100, 0], [100, 100], [0, 100]])

        # Add first ROI
        roi1 = [[10, 10], [30, 10], [30, 30], [10, 30]]
        integration_coordinator.add_roi_polygon(roi1, "ROI 1", (255, 0, 0))

        # Add overlapping ROI
        roi2 = [[20, 20], [40, 20], [40, 40], [20, 40]]  # Overlaps ROI 1

        # Mock view to accept overlap
        mock_dependencies["view"].ask_ok_cancel.return_value = True

        success = integration_coordinator.add_roi_polygon(roi2, "ROI 2", (0, 255, 0))

        assert success is True
        assert mock_dependencies["view"].ask_ok_cancel.called
        assert (
            "ROI 2"
            in integration_coordinator.project_manager.project_data["detection_zones"]["roi_names"]
        )


class TestParquetAndReports:
    """Test integration with Parquet generation and Reporting."""

    @patch("cv2.VideoCapture")
    @patch("zebtrack.coordinators.processing_coordinator.Reporter")
    @patch("zebtrack.coordinators.processing_coordinator.pd.read_parquet")
    @patch("os.path.exists")
    def test_generate_parquet_summaries_integration(
        self,
        mock_exists,
        mock_read_parquet,
        mock_reporter,
        mock_video_capture,
        integration_coordinator,
        temp_project_dir,
    ):
        """Test batch generation of parquet summaries."""
        # Mock VideoCapture to avoid IO on dummy file
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: 100.0  # Return 100 for width/height
        mock_video_capture.return_value = cap

        # Setup project
        project_path = temp_project_dir / "report_project"
        integration_coordinator.project_manager.create_new_project(
            str(project_path),
            project_type="Pre-recorded",
            aquarium_width_cm=100.0,
            aquarium_height_cm=50.0,
        )

        # Setup arena so video read is skipped
        integration_coordinator.set_main_arena_polygon([[0, 0], [100, 0], [100, 100], [0, 100]])

        # Add video
        video_path = str(temp_project_dir / "videos" / "video1.mp4")
        integration_coordinator.project_manager.add_video_batch(
            [
                {
                    "path": video_path,
                    "status": "complete",
                    "parquet_files": {"trajectory": "traj.parquet"},
                }
            ]
        )

        # Mock file existence and reading
        mock_exists.return_value = True
        mock_read_parquet.return_value = MagicMock(empty=False)  # Non-empty DF

        # Action
        target_videos = integration_coordinator.project_manager.get_all_videos()

        # Patch makedirs only during generation to avoid creating deep nested folders
        # and to prevent issues with os.path.exists mock if any
        with patch("os.makedirs"):
            integration_coordinator.generate_parquet_summaries(
                target_videos, integration_coordinator.settings, on_complete=MagicMock()
            )

        # Verify Reporter was called
        print(f"DEBUG: Reporter calls: {mock_reporter.mock_calls}")

        # Debug: Check if failure event was published
        args = integration_coordinator.event_bus.publish_event.call_args_list
        print(f"DEBUG: Events published: {[c[0][0] for c in args]}")

        mock_reporter.return_value.export_summary_data.assert_called()

        # Verify project updated (summary path added)
        updated_videos = integration_coordinator.project_manager.get_all_videos()
        assert "summary" in updated_videos[0]["parquet_files"]

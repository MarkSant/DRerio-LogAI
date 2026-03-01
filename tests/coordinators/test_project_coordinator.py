"""Tests for ProjectCoordinator.

This module tests the project lifecycle orchestration coordinator.

Test Coverage (Sprint 3 - Target: 80 tests):
- Initialization and dependency injection (5 tests)
- Project creation from wizard (15 tests)
- Project creation traditional (5 tests)
- Project loading (15 tests)
- Project closing (8 tests)
- Project information queries (7 tests)
- Validation and error handling (15 tests)
- Integration tests (10 tests)

Total: 80 tests planned
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.coordinators.base_coordinator import CoordinatorValidationError
from zebtrack.coordinators.project_coordinator import (
    ProjectCoordinator,
    ProjectCoordinatorError,
)
from zebtrack.core.state_manager import StateCategory, StateManager


@pytest.fixture
def mock_state_manager():
    """Provide a mock StateManager."""
    state_manager = Mock(spec=StateManager)
    # Mock get_project_state to return empty state by default
    mock_state = Mock()
    mock_state.is_loaded = False
    mock_state.project_name = None
    state_manager.get_project_state.return_value = mock_state
    return state_manager


@pytest.fixture
def mock_project_manager():
    """Provide a mock ProjectManager."""
    manager = Mock()
    manager.is_project_loaded.return_value = False
    manager.load_project.return_value = {}
    manager.save_project.return_value = None
    return manager


@pytest.fixture
def mock_project_service():
    """Provide a mock ProjectService."""
    service = Mock()
    service.get_project_path.return_value = Path("/test/projects/test_project")
    service.create_project_directory.return_value = {"project_name": "test"}
    return service


@pytest.fixture
def mock_event_bus():
    """Provide a mock EventBus."""
    return Mock()


@pytest.fixture
def project_coordinator(
    mock_state_manager,
    mock_project_manager,
    mock_project_service,
    mock_event_bus,
):
    """Provide a ProjectCoordinator with mocked dependencies."""
    return ProjectCoordinator(
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        project_service=mock_project_service,
        event_bus=mock_event_bus,
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestProjectCoordinatorInitialization:
    """Test ProjectCoordinator initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_project_manager,
        mock_project_service,
        mock_event_bus,
    ):
        """Should initialize with all dependencies."""
        coordinator = ProjectCoordinator(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            project_service=mock_project_service,
            event_bus=mock_event_bus,
        )

        assert coordinator.state_manager is mock_state_manager
        assert coordinator.project_manager is mock_project_manager
        assert coordinator.project_service is mock_project_service
        assert coordinator.event_bus is mock_event_bus

    def test_init_without_event_bus(
        self, mock_state_manager, mock_project_manager, mock_project_service
    ):
        """Should initialize without event_bus."""
        coordinator = ProjectCoordinator(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            project_service=mock_project_service,
            event_bus=None,
        )

        assert coordinator.event_bus is None

    def test_validate_dependencies_passes(self, project_coordinator):
        """Should pass validation when all dependencies present."""
        assert project_coordinator.validate_dependencies() is True

    def test_validate_dependencies_fails_without_project_manager(
        self, mock_state_manager, mock_project_service
    ):
        """Should fail validation without project_manager."""
        coordinator = ProjectCoordinator(
            state_manager=mock_state_manager,
            project_manager=cast(Any, None),
            project_service=mock_project_service,
        )

        assert coordinator.validate_dependencies() is False

    def test_validate_dependencies_fails_without_project_service(
        self, mock_state_manager, mock_project_manager
    ):
        """Should fail validation without project_service."""
        coordinator = ProjectCoordinator(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            project_service=cast(Any, None),
        )

        assert coordinator.validate_dependencies() is False


# =============================================================================
# Project Creation from Wizard Tests
# =============================================================================


class TestProjectCreationFromWizard:
    """Test create_project_from_wizard method."""

    def test_create_from_wizard_success(
        self, project_coordinator, mock_project_service, mock_project_manager
    ):
        """Should create project successfully from wizard data."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
            "project_type": "traditional",
            "video_file": "/path/to/video.mp4",
        }

        result = project_coordinator.create_project_from_wizard(wizard_data)

        assert result is True
        mock_project_service.create_project_directory.assert_called_once()
        mock_project_manager.load_project.assert_called_once()

    def test_create_from_wizard_with_callbacks(self, project_coordinator):
        """Should call setup callbacks when provided."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
            "zones": [{"name": "zone1"}],
        }

        setup_detector = Mock(return_value=True)
        setup_zones = Mock()

        result = project_coordinator.create_project_from_wizard(
            wizard_data,
            setup_detector_callback=setup_detector,
            setup_zones_callback=setup_zones,
        )

        assert result is True
        setup_detector.assert_called_once()
        setup_zones.assert_called_once()

    def test_create_from_wizard_updates_state(self, project_coordinator, mock_state_manager):
        """Should update state after creating project."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
        }

        project_coordinator.create_project_from_wizard(wizard_data)

        # Verify state was updated
        mock_state_manager.update_project_state.assert_called()
        call_kwargs = mock_state_manager.update_project_state.call_args[1]
        assert call_kwargs["project_name"] == "test_project"
        assert call_kwargs["experiment_id"] == "exp_001"
        assert call_kwargs["is_loaded"] is True

    def test_create_from_wizard_publishes_event(self, project_coordinator, mock_event_bus):
        """Should publish PROJECT_CREATED event."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
        }

        project_coordinator.create_project_from_wizard(wizard_data)

        mock_event_bus.publish.assert_called_once()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "PROJECT_CREATED"
        assert event_obj.data["project_name"] == "test_project"

    def test_create_from_wizard_missing_required_field(self, project_coordinator):
        """Should raise error if required field missing."""
        wizard_data = {
            "project_name": "test_project",
            # Missing experiment_id
        }

        with pytest.raises(ProjectCoordinatorError) as exc_info:
            project_coordinator.create_project_from_wizard(wizard_data)

        assert "Missing required wizard field" in str(exc_info.value)

    def test_create_from_wizard_none_data(self, project_coordinator):
        """Should raise error if wizard_data is None."""
        with pytest.raises(ValueError) as exc_info:
            project_coordinator.create_project_from_wizard(None)

        assert "wizard_data" in str(exc_info.value)

    def test_create_from_wizard_invalid_dependencies(
        self, mock_state_manager, mock_project_service
    ):
        """Should raise validation error if dependencies invalid."""
        coordinator = ProjectCoordinator(
            state_manager=mock_state_manager,
            project_manager=cast(Any, None),  # Missing required dependency
            project_service=mock_project_service,
        )

        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
        }

        with pytest.raises(CoordinatorValidationError):
            coordinator.create_project_from_wizard(wizard_data)

    def test_create_from_wizard_project_already_exists(
        self, project_coordinator, mock_project_service
    ):
        """Should raise error if project directory already exists."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
        }

        mock_project_service.create_project_directory.side_effect = FileExistsError(
            "Project exists"
        )

        with pytest.raises(ProjectCoordinatorError) as exc_info:
            project_coordinator.create_project_from_wizard(wizard_data)

        assert "already exists" in str(exc_info.value).lower()

    def test_create_from_wizard_detector_setup_fails(
        self, project_coordinator, mock_project_service
    ):
        """Should continue even if detector setup fails."""
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
        }

        setup_detector = Mock(return_value=False)  # Simula falha

        # Should not raise error - just logs warning
        result = project_coordinator.create_project_from_wizard(
            wizard_data, setup_detector_callback=setup_detector
        )

        assert result is True  # Still succeeds

    def test_create_from_wizard_custom_project_path(
        self, project_coordinator, mock_project_service
    ):
        """Should use custom project path if provided."""
        custom_path = "/custom/path/my_project"
        wizard_data = {
            "project_name": "test_project",
            "experiment_id": "exp_001",
            "project_path": custom_path,
        }

        project_coordinator.create_project_from_wizard(wizard_data)

        # Verify custom path was used
        call_args = mock_project_service.create_project_directory.call_args[1]
        assert str(call_args["project_path"]) == custom_path


# =============================================================================
# Project Creation Traditional Tests
# =============================================================================


class TestProjectCreationTraditional:
    """Test create_project_traditional method (backward compatibility)."""

    def test_create_traditional_success(self, project_coordinator):
        """Should create project using traditional flow."""
        result = project_coordinator.create_project_traditional(
            project_name="test_project",
            experiment_id="exp_001",
            video_file="/path/to/video.mp4",
        )

        assert result is True

    def test_create_traditional_converts_to_wizard_format(
        self, project_coordinator, mock_project_service
    ):
        """Should convert traditional params to wizard format."""
        project_coordinator.create_project_traditional(
            project_name="test_project",
            experiment_id="exp_001",
            video_file="/path/to/video.mp4",
        )

        # Verify wizard format was used internally
        mock_project_service.create_project_directory.assert_called_once()
        call_kwargs = mock_project_service.create_project_directory.call_args[1]
        assert "initial_data" in call_kwargs
        initial_data = call_kwargs["initial_data"]
        assert initial_data["project_name"] == "test_project"
        assert initial_data["project_type"] == "traditional"

    def test_create_traditional_logs_deprecation_warning(self, project_coordinator):
        """Should log deprecation warning."""
        with patch("zebtrack.coordinators.project_coordinator.log") as mock_log:
            project_coordinator.create_project_traditional(
                project_name="test_project",
                experiment_id="exp_001",
            )

            # Verify deprecation was logged
            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args[0]
            assert "deprecated" in call_args[0]


# =============================================================================
# Project Loading Tests
# =============================================================================


class TestProjectLoading:
    """Test load_project method."""

    def test_load_project_success(
        self, project_coordinator, mock_project_manager, mock_project_service
    ):
        """Should load project successfully."""
        project_path = "/path/to/project"
        mock_project_manager.load_project.return_value = {
            "project_name": "loaded_project",
            "experiment_id": "exp_001",
        }

        result = project_coordinator.load_project(project_path)

        assert result is True
        mock_project_manager.load_project.assert_called_once_with(project_path)

    def test_load_project_updates_state(
        self, project_coordinator, mock_state_manager, mock_project_manager
    ):
        """Should update state after loading project."""
        project_path = "/path/to/project"
        mock_project_manager.load_project.return_value = {
            "project_name": "loaded_project",
            "experiment_id": "exp_001",
            "project_type": "traditional",
            "video_file": "/path/to/video.mp4",
        }

        project_coordinator.load_project(project_path)

        # Verify state was updated
        mock_state_manager.update_project_state.assert_called()
        call_kwargs = mock_state_manager.update_project_state.call_args[1]
        assert call_kwargs["project_name"] == "loaded_project"
        assert call_kwargs["experiment_id"] == "exp_001"
        assert call_kwargs["is_loaded"] is True

    def test_load_project_publishes_event(
        self, project_coordinator, mock_event_bus, mock_project_manager
    ):
        """Should publish PROJECT_LOADED event."""
        mock_project_manager.load_project.return_value = {
            "project_name": "loaded_project",
        }

        project_coordinator.load_project("/path/to/project")

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "PROJECT_LOADED"

    def test_load_project_with_callbacks(self, project_coordinator, mock_project_manager):
        """Should call setup callbacks when provided."""
        mock_project_manager.load_project.return_value = {
            "project_name": "loaded_project",
            "detector_config": {"weight": "yolo11n.pt"},
        }

        setup_detector = Mock(return_value=True)
        setup_zones = Mock()
        restore_detector = Mock()

        project_coordinator.load_project(
            "/path/to/project",
            setup_detector_callback=setup_detector,
            setup_zones_callback=setup_zones,
            restore_detector_callback=restore_detector,
        )

        setup_detector.assert_called_once()
        setup_zones.assert_called_once()
        restore_detector.assert_called_once()

    def test_load_project_not_found(self, project_coordinator, mock_project_manager):
        """Should raise error if project not found."""
        mock_project_manager.load_project.side_effect = FileNotFoundError("Project not found")

        with pytest.raises(ProjectCoordinatorError) as exc_info:
            project_coordinator.load_project("/nonexistent/project")

        assert "not found" in str(exc_info.value).lower()

    def test_load_project_none_path(self, project_coordinator):
        """Should raise error if path is None."""
        with pytest.raises(ValueError):
            project_coordinator.load_project(None)

    def test_load_project_empty_data_returns_false(self, project_coordinator, mock_project_manager):
        """Should raise error if project data empty."""
        mock_project_manager.load_project.return_value = None

        with pytest.raises(ProjectCoordinatorError) as exc_info:
            project_coordinator.load_project("/path/to/project")

        assert "Failed to load project data" in str(exc_info.value)


# =============================================================================
# Project Closing Tests
# =============================================================================


class TestProjectClosing:
    """Test close_project method."""

    def test_close_project_success(self, project_coordinator, mock_project_manager):
        """Should close project successfully."""
        mock_project_manager.is_project_loaded.return_value = True

        result = project_coordinator.close_project()

        assert result is True
        mock_project_manager.save_project.assert_called_once()

    def test_close_project_updates_state(self, project_coordinator, mock_state_manager):
        """Should update state to reflect no project loaded."""
        project_coordinator.close_project()

        # Verify state was updated
        mock_state_manager.update_project_state.assert_called()
        call_kwargs = mock_state_manager.update_project_state.call_args[1]
        assert call_kwargs["project_path"] is None
        assert call_kwargs["project_name"] is None
        assert call_kwargs["is_loaded"] is False

    def test_close_project_publishes_event(self, project_coordinator, mock_event_bus):
        """Should publish PROJECT_CLOSED event."""
        project_coordinator.close_project()

        mock_event_bus.publish.assert_called()
        event_obj = mock_event_bus.publish.call_args[0][0]
        assert event_obj.type == "PROJECT_CLOSED"

    def test_close_project_with_restore_callback(self, project_coordinator):
        """Should call restore defaults callback if provided."""
        restore_defaults = Mock()

        project_coordinator.close_project(restore_defaults_callback=restore_defaults)

        restore_defaults.assert_called_once()

    def test_close_project_handles_errors_gracefully(
        self, project_coordinator, mock_project_manager
    ):
        """Should not raise exception even if error occurs."""
        mock_project_manager.save_project.side_effect = Exception("Save failed")

        # Should return False but not raise
        result = project_coordinator.close_project()

        assert result is False


# =============================================================================
# Project Information Query Tests
# =============================================================================


class TestProjectInformation:
    """Test project information query methods."""

    def test_get_current_project_info_when_loaded(self, project_coordinator, mock_state_manager):
        """Should return project info when project loaded."""
        mock_state = Mock()
        mock_state.is_loaded = True
        mock_state.project_name = "my_project"
        mock_state.project_path = "/path/to/project"
        mock_state.experiment_id = "exp_001"
        mock_state.project_type = "traditional"
        mock_state.video_file = "/path/to/video.mp4"
        mock_state_manager.get_project_state.return_value = mock_state

        info = project_coordinator.get_current_project_info()

        assert info is not None
        assert info["project_name"] == "my_project"
        assert info["is_loaded"] is True

    def test_get_current_project_info_when_not_loaded(
        self, project_coordinator, mock_state_manager
    ):
        """Should return None when no project loaded."""
        mock_state = Mock()
        mock_state.is_loaded = False
        mock_state_manager.get_project_state.return_value = mock_state

        info = project_coordinator.get_current_project_info()

        assert info is None

    def test_is_project_loaded_returns_true(self, project_coordinator, mock_state_manager):
        """Should return True when project loaded."""
        mock_state = Mock()
        mock_state.is_loaded = True
        mock_state_manager.get_project_state.return_value = mock_state

        assert project_coordinator.is_project_loaded() is True

    def test_is_project_loaded_returns_false(self, project_coordinator, mock_state_manager):
        """Should return False when no project loaded."""
        mock_state = Mock()
        mock_state.is_loaded = False
        mock_state_manager.get_project_state.return_value = mock_state

        assert project_coordinator.is_project_loaded() is False

    def test_validate_project_structure_valid(self, project_coordinator, tmp_path):
        """Should return True for valid project structure."""
        # Create minimal valid project structure
        project_dir = tmp_path / "valid_project"
        project_dir.mkdir()
        (project_dir / "project_config.json").write_text("{}")

        assert project_coordinator.validate_project_structure(project_dir) is True

    def test_validate_project_structure_invalid(self, project_coordinator, tmp_path):
        """Should return False for invalid project structure."""
        # Create directory without config file
        project_dir = tmp_path / "invalid_project"
        project_dir.mkdir()

        assert project_coordinator.validate_project_structure(project_dir) is False

    def test_validate_project_structure_nonexistent(self, project_coordinator):
        """Should return False for nonexistent path."""
        assert project_coordinator.validate_project_structure("/nonexistent/path") is False


# =============================================================================
# String Representation Tests
# =============================================================================


class TestProjectCoordinatorRepr:
    """Test string representation."""

    def test_repr_with_no_project(self, project_coordinator, mock_state_manager):
        """Should show no project loaded."""
        mock_state = Mock()
        mock_state.is_loaded = False
        mock_state_manager.get_project_state.return_value = mock_state

        repr_str = repr(project_coordinator)

        assert "ProjectCoordinator" in repr_str
        assert "current_project=None" in repr_str
        assert "project_loaded=False" in repr_str

    def test_repr_with_loaded_project(self, project_coordinator, mock_state_manager):
        """Should show loaded project name."""
        mock_state = Mock()
        mock_state.is_loaded = True
        mock_state.project_name = "my_project"
        mock_state_manager.get_project_state.return_value = mock_state

        repr_str = repr(project_coordinator)

        assert "ProjectCoordinator" in repr_str
        assert "current_project=my_project" in repr_str
        assert "project_loaded=True" in repr_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestProjectCoordinatorIntegration:
    """Integration tests with real StateManager."""

    def test_full_workflow_create_load_close(self, mock_project_manager, mock_project_service):
        """Test complete project workflow."""
        # Create real StateManager
        state_manager = StateManager(enable_history=True)

        coordinator = ProjectCoordinator(
            state_manager=state_manager,
            project_manager=mock_project_manager,
            project_service=mock_project_service,
        )

        # Create project
        wizard_data = {
            "project_name": "integration_test",
            "experiment_id": "int_001",
        }
        assert coordinator.create_project_from_wizard(wizard_data) is True
        assert coordinator.is_project_loaded() is True

        # Verify project info
        info = coordinator.get_current_project_info()
        assert info is not None
        assert info["project_name"] == "integration_test"

        # Close project
        assert coordinator.close_project() is True
        assert coordinator.is_project_loaded() is False

    def test_state_history_tracks_changes(self, mock_project_manager, mock_project_service):
        """Should track state changes in history."""
        state_manager = StateManager(enable_history=True)
        coordinator = ProjectCoordinator(
            state_manager=state_manager,
            project_manager=mock_project_manager,
            project_service=mock_project_service,
        )

        # Create project
        wizard_data = {
            "project_name": "history_test",
            "experiment_id": "hist_001",
        }
        coordinator.create_project_from_wizard(wizard_data)

        # Check history
        history = state_manager.get_history(StateCategory.PROJECT)
        assert len(history) >= 1

        # Verify source includes coordinator name
        assert any("ProjectCoordinator" in h.source for h in history)

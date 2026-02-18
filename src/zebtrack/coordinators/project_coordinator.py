"""ProjectCoordinator - Project lifecycle workflow orchestration.

This coordinator manages all project-related workflows by delegating to
services and managing state updates.

Sprint 3: Extracted from MainViewModel to improve testability and reduce complexity.

Architecture:
- Orchestrates project creation (wizard + traditional)
- Orchestrates project loading/closing
- Coordinates detector and zone setup after project load
- Manages project-specific configuration overrides

Related:
- docs/REFACTOR-MASTER-PLAN-2025.md - Sprint 3
- docs/API_REFERENCE_V3.md - API compatibility
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.state_manager import StateCategory

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_service import ProjectService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ProjectCoordinatorError(CoordinatorError):
    """Raised when project coordination fails."""

    pass


class ProjectCoordinator(BaseCoordinator):
    """
    Coordinator for project lifecycle workflows.

    This coordinator orchestrates:
    - Project creation (wizard-based and traditional)
    - Project loading and initialization
    - Project closing and cleanup
    - Zone and detector configuration
    - Project-specific settings management

    Design Principles:
    - Delegates all business logic to services
    - Updates state via StateManager
    - Publishes events via EventBus
    - Validation before operations
    - Clear error handling

    Dependencies:
        state_manager: StateManager for state tracking
        project_manager: ProjectManager for project data
        project_service: ProjectService for persistence
        event_bus: Optional EventBus for notifications

    Example:
        ```python
        coordinator = ProjectCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            project_service=project_service,
            event_bus=event_bus,
        )

        # Create project from wizard
        success = coordinator.create_project_from_wizard({
            "project_name": "my_project",
            "experiment_id": "exp_001",
            ...
        })

        # Load project
        success = coordinator.load_project("/path/to/project")

        # Close project
        coordinator.close_project()
        ```
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        project_service: ProjectService,
        event_bus: EventBus | None = None,
    ):
        """Initialize ProjectCoordinator.

        Args:
            state_manager: StateManager for state tracking
            project_manager: ProjectManager for project data management
            project_service: ProjectService for file I/O operations
            event_bus: Optional EventBus for event publishing
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        self.project_manager = project_manager
        self.project_service = project_service

        log.info(
            "project_coordinator.initialized",
            has_project_manager=project_manager is not None,
            has_project_service=project_service is not None,
        )

    def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available.

        Returns:
            True if all dependencies valid, False otherwise
        """
        if self.project_manager is None:
            log.error("dependency.missing", dep="project_manager")
            return False

        if self.project_service is None:
            log.error("dependency.missing", dep="project_service")
            return False

        if self.state_manager is None:
            log.error("dependency.missing", dep="state_manager")
            return False

        return True

    # =========================================================================
    # Project Creation
    # =========================================================================

    def create_project_from_wizard(
        self,
        wizard_data: dict[str, Any],
        setup_detector_callback: Callable[[], bool] | None = None,
        setup_zones_callback: Callable[[], None] | None = None,
    ) -> bool:
        """
        Create project from wizard data.

        This is the primary project creation method used by the wizard flow.

        Args:
            wizard_data: Data from wizard containing project configuration
            setup_detector_callback: Optional callback to initialize detector
            setup_zones_callback: Optional callback to configure zones

        Returns:
            True if project created successfully, False otherwise

        Raises:
            ProjectCoordinatorError: If creation fails

        Example wizard_data:
            {
                "project_name": "my_project",
                "experiment_id": "exp_001",
                "project_type": "traditional" | "live_arduino",
                "project_path": "/path/to/projects/my_project",
                "video_file": "/path/to/video.mp4",  # if traditional
                "arena": {...},  # arena configuration
                "rois": [...],  # ROI configurations
                "zones": [...],  # zone configurations
                "camera_index": 0,  # if live
                "arduino_port": "COM3",  # if arduino
                ...
            }
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="ProjectCoordinator",
                operation="create_project_from_wizard",
            )

        # Validate wizard data
        self._validate_not_none(wizard_data, "wizard_data")
        self._validate_type(wizard_data, dict, "wizard_data")

        # Extract required fields
        try:
            project_name = wizard_data["project_name"]
            experiment_id = wizard_data["experiment_id"]
            project_type = wizard_data.get("project_type", "traditional")
            project_path = wizard_data.get("project_path")
        except KeyError as e:
            raise ProjectCoordinatorError(
                f"Missing required wizard field: {e}",
                coordinator="ProjectCoordinator",
                operation="create_project_from_wizard",
                wizard_data_keys=list(wizard_data.keys()),
            ) from e

        log.info(
            "project_coordinator.create_from_wizard.start",
            project_name=project_name,
            project_type=project_type,
        )

        try:
            # Step 1: Create project directory and configuration
            if project_path:
                # Preserve caller-provided path string to maintain display formatting
                project_path_obj: Path | str = project_path
            else:
                # Generate project path from settings
                if self.project_manager.settings and hasattr(
                    self.project_manager.settings, "paths"
                ):
                    projects_dir = self.project_manager.settings.paths.projects_dir
                    if isinstance(projects_dir, Path):
                        project_path_obj = projects_dir / project_name
                    else:
                        project_path_obj = Path(str(projects_dir)) / project_name
                else:
                    # Fallback default if settings not available (unlikely)
                    project_path_obj = Path.home() / "ZebTrack" / "Projects" / project_name

            project_path_str = (
                project_path_obj if isinstance(project_path_obj, str) else str(project_path_obj)
            )

            # Create project via service
            self.project_service.create_project_directory(
                project_path=project_path_obj,
                project_name=project_name,
                project_type=project_type,
                initial_data={
                    "experiment_id": experiment_id,
                    **wizard_data,
                },
            )

            # Step 2: Load project into manager
            self.project_manager.load_project(project_path_str)

            # Step 3: Update state
            self._update_state(
                StateCategory.PROJECT,
                project_path=project_path_str,
                project_name=project_name,
                experiment_id=experiment_id,
                project_type=project_type,
                is_loaded=True,
            )

            # Step 4: Setup detector if callback provided
            if setup_detector_callback:
                detector_success = setup_detector_callback()
                if not detector_success:
                    log.warning(
                        "project_coordinator.create.detector_setup_failed",
                        project_name=project_name,
                    )

            # Step 5: Setup zones if callback provided
            if setup_zones_callback and wizard_data.get("zones"):
                setup_zones_callback()

            # Step 6: Publish success event
            self._publish_event(
                "PROJECT_CREATED",
                {
                    "project_name": project_name,
                    "project_path": project_path_str,
                    "project_type": project_type,
                },
            )

            log.info(
                "project_coordinator.create_from_wizard.success",
                project_name=project_name,
                project_path=project_path_str,
            )

            return True

        except FileExistsError as e:
            log.error(
                "project_coordinator.create_from_wizard.already_exists",
                project_name=project_name,
                error=str(e),
            )
            raise ProjectCoordinatorError(
                f"Project already exists: {project_name}",
                coordinator="ProjectCoordinator",
                operation="create_project_from_wizard",
                project_name=project_name,
            ) from e

        except Exception as e:  # except Exception justified: service boundary catch-all
            log.error(
                "project_coordinator.create_from_wizard.failed",
                project_name=project_name,
                error=str(e),
                exc_info=True,
            )
            raise ProjectCoordinatorError(
                f"Failed to create project: {e!s}",
                coordinator="ProjectCoordinator",
                operation="create_project_from_wizard",
                project_name=project_name,
            ) from e

    def create_project_traditional(
        self,
        project_name: str,
        experiment_id: str,
        video_file: str | None = None,
        project_path: str | None = None,
    ) -> bool:
        """
        Create project using traditional flow (deprecated in favor of wizard).

        This method maintains backward compatibility with pre-wizard code.

        Args:
            project_name: Name of the project
            experiment_id: Experiment identifier
            video_file: Optional path to video file
            project_path: Optional custom project path

        Returns:
            True if project created successfully, False otherwise

        Note:
            This method is deprecated. New code should use create_project_from_wizard().
        """
        log.warning(
            "project_coordinator.create_traditional.deprecated",
            project_name=project_name,
            recommendation="use create_project_from_wizard instead",
        )

        # Convert to wizard format and delegate
        wizard_data = {
            "project_name": project_name,
            "experiment_id": experiment_id,
            "project_type": "traditional",
        }

        if video_file:
            wizard_data["video_file"] = video_file

        if project_path:
            wizard_data["project_path"] = project_path

        return self.create_project_from_wizard(wizard_data)

    # =========================================================================
    # Project Loading
    # =========================================================================

    def load_project(
        self,
        project_path: str | Path,
        setup_detector_callback: Callable[[], bool] | None = None,
        setup_zones_callback: Callable[[], None] | None = None,
        restore_detector_callback: Callable[[dict], None] | None = None,
    ) -> bool:
        """
        Load existing project and configure everything.

        This orchestrates the complete project loading workflow:
        1. Load project data via ProjectManager
        2. Update application state
        3. Initialize detector if needed
        4. Configure zones if needed
        5. Restore detector settings if saved

        Args:
            project_path: Path to project directory
            setup_detector_callback: Optional callback to initialize detector
            setup_zones_callback: Optional callback to configure zones
            restore_detector_callback: Optional callback to restore detector settings

        Returns:
            True if project loaded successfully, False otherwise

        Raises:
            ProjectCoordinatorError: If loading fails
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="ProjectCoordinator",
                operation="load_project",
            )

        self._validate_not_none(project_path, "project_path")

        project_path_str = str(project_path)

        log.info(
            "project_coordinator.load_project.start",
            project_path=project_path_str,
        )

        try:
            # Step 1: Load project via manager
            project_data = self.project_manager.load_project(project_path_str)

            if not project_data:
                raise ProjectCoordinatorError(
                    "Failed to load project data",
                    coordinator="ProjectCoordinator",
                    operation="load_project",
                    project_path=project_path_str,
                )

            # Step 2: Extract project info
            project_name = project_data.get("project_name", "Unknown")
            experiment_id = project_data.get("experiment_id")
            project_type = project_data.get("project_type", "traditional")
            video_file = project_data.get("video_file")

            # Step 3: Update state
            self._update_state(
                StateCategory.PROJECT,
                project_path=project_path_str,
                project_name=project_name,
                experiment_id=experiment_id,
                project_type=project_type,
                video_file=video_file,
                is_loaded=True,
            )

            # Step 4: Setup detector if callback provided
            if setup_detector_callback:
                detector_success = setup_detector_callback()
                if not detector_success:
                    log.warning(
                        "project_coordinator.load.detector_setup_failed",
                        project_name=project_name,
                    )

            # Step 5: Restore detector settings if available
            if restore_detector_callback and project_data.get("detector_config"):
                restore_detector_callback(project_data["detector_config"])

            # Step 6: Setup zones if callback provided
            if setup_zones_callback:
                setup_zones_callback()

            # Step 7: Publish success event
            self._publish_event(
                "PROJECT_LOADED",
                {
                    "project_name": project_name,
                    "project_path": project_path_str,
                    "project_type": project_type,
                },
            )

            log.info(
                "project_coordinator.load_project.success",
                project_name=project_name,
                project_path=project_path_str,
            )

            return True

        except FileNotFoundError as e:
            log.error(
                "project_coordinator.load_project.not_found",
                project_path=project_path_str,
                error=str(e),
            )
            raise ProjectCoordinatorError(
                f"Project not found: {project_path_str}",
                coordinator="ProjectCoordinator",
                operation="load_project",
                project_path=project_path_str,
            ) from e

        except Exception as e:  # except Exception justified: service boundary catch-all
            log.error(
                "project_coordinator.load_project.failed",
                project_path=project_path_str,
                error=str(e),
                exc_info=True,
            )
            raise ProjectCoordinatorError(
                f"Failed to load project: {e!s}",
                coordinator="ProjectCoordinator",
                operation="load_project",
                project_path=project_path_str,
            ) from e

    # =========================================================================
    # Project Closing
    # =========================================================================

    def close_project(
        self,
        restore_defaults_callback: Callable[[], None] | None = None,
    ) -> bool:
        """
        Close the current project.

        This orchestrates project cleanup:
        1. Save any pending changes
        2. Clear project state
        3. Restore default settings if callback provided
        4. Publish close event

        Args:
            restore_defaults_callback: Optional callback to restore default settings

        Returns:
            True if project closed successfully, False otherwise
        """
        # Get current project name for logging
        project_state = self.state_manager.get_project_state()
        project_name = project_state.project_name if project_state else "Unknown"

        log.info(
            "project_coordinator.close_project.start",
            project_name=project_name,
        )

        try:
            # Step 1: Persist project state (ProjectManager handles loaded check)
            try:
                self.project_manager.save_project()
            except ProjectInvalidError:
                log.debug(
                    "project_coordinator.close_project.skip_save",
                    reason="project_not_loaded",
                )
            except Exception:  # except Exception justified: re-raise pattern
                # Re-raise to outer handler so we return False
                raise

            # Step 2: Create new empty project manager
            # Note: ProjectManager needs to be replaced with a fresh instance
            # This will be handled by the caller

            # Step 3: Update state to reflect no project loaded
            self._update_state(
                StateCategory.PROJECT,
                project_path=None,
                project_name=None,
                experiment_id=None,
                video_file=None,
                is_loaded=False,
            )

            # Step 4: Restore defaults if callback provided
            if restore_defaults_callback:
                restore_defaults_callback()

            # Step 5: Publish close event
            self._publish_event(
                "PROJECT_CLOSED",
                {"project_name": project_name},
            )

            log.info(
                "project_coordinator.close_project.success",
                project_name=project_name,
            )

            return True

        except Exception as e:  # except Exception justified: graceful stop must not crash
            log.error(
                "project_coordinator.close_project.failed",
                project_name=project_name,
                error=str(e),
                exc_info=True,
            )
            # Don't raise - closing should always succeed
            return False

    # =========================================================================
    # Project Information
    # =========================================================================

    def get_current_project_info(self) -> dict[str, Any] | None:
        """
        Get information about the currently loaded project.

        Returns:
            dict with project info, or None if no project loaded

        Example return:
            {
                "project_name": "my_project",
                "project_path": "/path/to/project",
                "experiment_id": "exp_001",
                "project_type": "traditional",
                "is_loaded": True,
            }
        """
        project_state = self.state_manager.get_project_state()

        if not project_state or not project_state.is_loaded:
            return None

        return {
            "project_name": project_state.project_name,
            "project_path": project_state.project_path,
            "experiment_id": project_state.experiment_id,
            "project_type": getattr(project_state, "project_type", "traditional"),
            "video_file": project_state.video_file,
            "is_loaded": project_state.is_loaded,
        }

    def is_project_loaded(self) -> bool:
        """
        Check if a project is currently loaded.

        Returns:
            True if project is loaded, False otherwise
        """
        project_state = self.state_manager.get_project_state()
        return project_state is not None and project_state.is_loaded

    def validate_project_structure(self, project_path: str | Path) -> bool:
        """
        Validate that a directory has valid project structure.

        Args:
            project_path: Path to validate

        Returns:
            True if valid project structure, False otherwise
        """
        try:
            project_path_obj = Path(project_path)

            # Check if directory exists
            if not project_path_obj.exists() or not project_path_obj.is_dir():
                return False

            # Check for required files (basic validation)
            config_file = project_path_obj / "project_config.json"
            if not config_file.exists():
                return False

            return True

        except OSError as e:
            log.warning(
                "project_coordinator.validate_structure.failed",
                project_path=str(project_path),
                error=str(e),
            )
            return False

    def __repr__(self) -> str:
        """String representation for debugging."""
        project_info = self.get_current_project_info()
        project_name = project_info["project_name"] if project_info else "None"

        return (
            f"<ProjectCoordinator("
            f"current_project={project_name}, "
            f"project_loaded={self.is_project_loaded()}"
            f")>"
        )

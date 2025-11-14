"""Processing Coordinator - Sprint 6 & Sprint 11.

Orchestrates video processing workflows (single video, batch, and project-level).
Delegates business logic to VideoProcessingService and VideoOrchestrator.

Sprint 6: Video processing orchestration
Sprint 11: Validation extraction and consolidation
Expands: VideoOrchestrator capabilities
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory

if TYPE_CHECKING:
    from zebtrack.analysis.analysis_service import AnalysisService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video_orchestrator import VideoOrchestrator
    from zebtrack.core.video_processing_service import VideoProcessingService
    from zebtrack.io.recorder_factory import RecorderFactory
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


@dataclass
class ValidationResult:
    """
    Result of processing validation check.

    Sprint 11: Value object for validation results to separate validation logic from UI.
    Allows coordinators to return structured validation results instead of
    showing UI dialogs directly.

    Attributes:
        is_valid: Whether validation passed
        error_code: Machine-readable error code (None if valid)
        error_message: Human-readable error message (None if valid)
        context: Additional context for the error (e.g., video count, missing data)
    """

    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None
    context: dict[str, Any] | None = None

    @classmethod
    def success(cls) -> ValidationResult:
        """Create a successful validation result."""
        return cls(is_valid=True)

    @classmethod
    def failure(
        cls,
        error_code: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            error_code=error_code,
            error_message=error_message,
            context=context or {},
        )


class ProcessingCoordinatorError(Exception):
    """Base exception for ProcessingCoordinator errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        """Initialize exception with message and optional context.

        Args:
            message: Error message
            context: Optional context dictionary
        """
        super().__init__(message)
        self.context = context or {}


class ProcessingCoordinator(BaseCoordinator):
    """
    Coordinator for video processing workflows.

    Orchestrates:
    - Single video processing workflows
    - Project-level batch processing
    - Processing validation and pre-flight checks
    - Processing state management
    - Cancel/abort operations
    - Progress tracking and event publishing

    Delegates to:
    - VideoOrchestrator: Batch processing orchestration
    - VideoProcessingService: Single video processing
    - AnalysisService: Post-processing analysis
    - ProjectManager: Video and zone management
    - StateManager: Processing state persistence
    - EventBus: UI notifications and progress updates

    Sprint 6: Video processing orchestration
    Related: REFACTOR-MASTER-PLAN-2025.md
    """

    def __init__(
        self,
        state_manager: StateManager,
        video_orchestrator: VideoOrchestrator | None = None,
        video_processing_service: VideoProcessingService | None = None,
        analysis_service: AnalysisService | None = None,
        project_manager: ProjectManager | None = None,
        recorder_factory: RecorderFactory | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize ProcessingCoordinator with dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            video_orchestrator: VideoOrchestrator for batch processing (optional)
            video_processing_service: VideoProcessingService for single video (optional)
            analysis_service: AnalysisService for post-processing (optional)
            project_manager: ProjectManager for project data (optional)
            recorder_factory: RecorderFactory for recording (optional)
            event_bus: EventBus for UI notifications (optional)
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)
        self.video_orchestrator = video_orchestrator
        self.video_processing_service = video_processing_service
        self.analysis_service = analysis_service
        self.project_manager = project_manager
        self.recorder_factory = recorder_factory

        log.info(
            "processing_coordinator.initialized",
            has_orchestrator=video_orchestrator is not None,
            has_processing_service=video_processing_service is not None,
        )

    def validate_dependencies(self) -> bool:
        """Validate that required dependencies are present.

        Returns:
            bool: True if all required dependencies are present

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        # At minimum, we need state_manager (checked by BaseCoordinator)
        # Other dependencies are optional and validated per-operation
        return True

    def validate_can_start_processing(
        self,
        *,
        check_project_loaded: bool = True,
        check_zones: bool = False,
        check_videos_exist: bool = False,
    ) -> ValidationResult:
        """
        Validate that processing can start.

        Sprint 11: Consolidated validation method that separates validation logic
        from UI concerns. Returns a structured ValidationResult instead of showing
        dialogs or publishing events directly.

        Common validations:
        - Processing not already active
        - Project is loaded (optional)
        - Zones/arena defined (optional)
        - Videos exist in project (optional)

        Args:
            check_project_loaded: Whether to validate project is loaded
            check_zones: Whether to validate zones/arena are defined
            check_videos_exist: Whether to validate videos exist in project

        Returns:
            ValidationResult: Structured validation result

        Example:
            >>> result = coordinator.validate_can_start_processing(
            ...     check_project_loaded=True,
            ...     check_zones=True
            ... )
            >>> if not result.is_valid:
            ...     # Handle error based on error_code
            ...     if result.error_code == "processing_already_active":
            ...         show_warning("Processing already active")
        """
        log.debug(
            "processing_coordinator.validate_can_start_processing",
            check_project=check_project_loaded,
            check_zones=check_zones,
            check_videos=check_videos_exist,
        )

        # Validation 1: Processing already active?
        if self.is_processing_active():
            log.warning("processing_coordinator.validation.already_active")
            return ValidationResult.failure(
                error_code="processing_already_active",
                error_message="Uma análise de vídeo já está em andamento. "
                "Por favor, aguarde ou cancele a análise atual.",
                context={"processing_info": self.get_processing_info()},
            )

        # Validation 2: Project loaded?
        if check_project_loaded:
            if not self.project_manager:
                log.error("processing_coordinator.validation.no_project_manager")
                return ValidationResult.failure(
                    error_code="no_project_manager",
                    error_message="ProjectManager não está disponível",
                    context={},
                )

            if not self.project_manager.project_path:
                log.warning("processing_coordinator.validation.no_project_loaded")
                return ValidationResult.failure(
                    error_code="no_project_loaded",
                    error_message="Nenhum projeto carregado",
                    context={},
                )

        # Validation 3: Zones/arena defined?
        if check_zones:
            if not self.project_manager:
                log.error("processing_coordinator.validation.no_project_manager_for_zones")
                return ValidationResult.failure(
                    error_code="no_project_manager",
                    error_message="ProjectManager não está disponível para validação de zonas",
                    context={},
                )

            zone_data = self.project_manager.get_zone_data()
            if not zone_data or not zone_data.polygon:
                log.warning("processing_coordinator.validation.no_main_arena")
                return ValidationResult.failure(
                    error_code="no_main_arena",
                    error_message="O polígono principal do aquário não foi definido",
                    context={
                        "has_zone_data": zone_data is not None,
                        "has_polygon": bool(zone_data and zone_data.polygon),
                        "roi_count": len(zone_data.roi_polygons) if zone_data else 0,
                    },
                )

        # Validation 4: Videos exist in project?
        if check_videos_exist:
            if not self.project_manager:
                log.error("processing_coordinator.validation.no_project_manager_for_videos")
                return ValidationResult.failure(
                    error_code="no_project_manager",
                    error_message="ProjectManager não está disponível para validação de vídeos",
                    context={},
                )

            all_videos = self.project_manager.get_all_videos() or []
            if not all_videos:
                log.warning("processing_coordinator.validation.no_videos")
                return ValidationResult.failure(
                    error_code="no_videos_in_project",
                    error_message="Nenhum vídeo cadastrado no projeto atualmente",
                    context={"video_count": 0},
                )

        # All validations passed
        log.debug("processing_coordinator.validate_can_start_processing.success")
        return ValidationResult.success()

    def start_project_processing_workflow(
        self,
        validate_zones: bool = True,
        prompt_for_arena: bool = True,
    ) -> bool:
        """
        Start project-level batch video processing workflow.

        Orchestrates project processing by:
        1. Validating dependencies (project loaded, zones defined)
        2. Checking for active processing
        3. Optionally prompting user to define arena if missing
        4. Delegating to VideoOrchestrator for batch processing
        5. Publishing events for UI updates

        Args:
            validate_zones: Whether to validate zones before processing
            prompt_for_arena: Whether to prompt user if arena is undefined

        Returns:
            bool: True if workflow started successfully, False otherwise

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            ProcessingCoordinatorError: If workflow start fails

        Example:
            >>> success = coordinator.start_project_processing_workflow()
            >>> if success:
            ...     print("Project processing started")
        """
        log.info("processing_coordinator.start_project_processing.begin")

        # Validate project manager dependency
        if self.project_manager is None:
            raise CoordinatorValidationError(
                "ProjectManager is required for project processing",
                context={"operation": "start_project_processing_workflow"},
            )

        # Validate video orchestrator dependency
        if self.video_orchestrator is None:
            raise CoordinatorValidationError(
                "VideoOrchestrator is required for project processing",
                context={"operation": "start_project_processing_workflow"},
            )

        # Check if processing is already active
        if self.is_processing_active():
            log.warning("processing_coordinator.start_project_processing.already_active")
            self._publish_event(
                "PROCESSING_ALREADY_ACTIVE",
                {
                    "message": "Processing is already active",
                    "prompt_user": True,
                },
            )
            return False

        # Validate project is loaded
        if not self.project_manager.project_path:
            log.warning("processing_coordinator.start_project_processing.no_project")
            self._publish_event(
                "NO_PROJECT_LOADED",
                {"message": "No project loaded", "prompt_user": True},
            )
            return False

        # Validate zones if requested
        if validate_zones:
            zone_validation = self._validate_zones(prompt_if_missing=prompt_for_arena)
            if not zone_validation:
                log.warning(
                    "processing_coordinator.start_project_processing.zone_validation_failed"
                )
                return False

        # Update state
        self._update_state(
            StateCategory.PROCESSING,
            is_processing=True,
            processing_type="project_batch",
        )

        # Delegate to VideoOrchestrator
        try:
            self.video_orchestrator.start_project_processing_workflow()

            # Publish success event
            self._publish_event(
                "PROJECT_PROCESSING_STARTED",
                {"processing_type": "project_batch"},
            )

            log.info("processing_coordinator.start_project_processing.success")
            return True

        except Exception as e:
            log.exception(
                "processing_coordinator.start_project_processing.failed",
                error=str(e),
            )
            # Revert state on failure
            self._update_state(
                StateCategory.PROCESSING,
                is_processing=False,
            )
            raise ProcessingCoordinatorError(
                f"Failed to start project processing: {e}",
                context={"validate_zones": validate_zones},
            ) from e

    def process_pending_project_videos(self) -> bool:
        """
        Process pending videos in the current project.

        Orchestrates by:
        1. Validating dependencies
        2. Checking for active processing
        3. Delegating to VideoOrchestrator
        4. Updating state and publishing events

        Returns:
            bool: True if processing started successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            ProcessingCoordinatorError: If processing start fails

        Example:
            >>> success = coordinator.process_pending_project_videos()
            >>> if success:
            ...     print("Processing started")
        """
        log.info("processing_coordinator.process_pending_videos.begin")

        # Validate dependencies
        if self.video_orchestrator is None:
            raise CoordinatorValidationError(
                "VideoOrchestrator is required",
                context={"operation": "process_pending_project_videos"},
            )

        if self.project_manager is None:
            raise CoordinatorValidationError(
                "ProjectManager is required",
                context={"operation": "process_pending_project_videos"},
            )

        # Check if already processing
        if self.is_processing_active():
            log.warning("processing_coordinator.process_pending_videos.already_active")
            return False

        # Update state
        self._update_state(
            StateCategory.PROCESSING,
            is_processing=True,
            processing_type="pending_videos",
        )

        # Delegate to orchestrator
        try:
            self.video_orchestrator.process_pending_project_videos()

            # Publish event
            self._publish_event(
                "PENDING_VIDEOS_PROCESSING_STARTED",
                {},
            )

            log.info("processing_coordinator.process_pending_videos.success")
            return True

        except Exception as e:
            log.exception("processing_coordinator.process_pending_videos.failed", error=str(e))
            # Revert state
            self._update_state(StateCategory.PROCESSING, is_processing=False)
            raise ProcessingCoordinatorError(
                f"Failed to process pending videos: {e}",
                context={},
            ) from e

    def start_single_video_processing(
        self,
        video_path: Path | str,
        config: dict | None = None,
    ) -> bool:
        """
        Start processing a single video.

        Orchestrates by:
        1. Validating dependencies and inputs
        2. Checking for active processing
        3. Delegating to VideoProcessingService
        4. Updating state and publishing events

        Args:
            video_path: Path to video file
            config: Optional configuration dictionary

        Returns:
            bool: True if processing started successfully

        Raises:
            CoordinatorValidationError: If dependencies are invalid
            ProcessingCoordinatorError: If processing fails
            ValueError: If video_path is invalid

        Example:
            >>> success = coordinator.start_single_video_processing(
            ...     video_path="/path/to/video.mp4",
            ...     config={"analysis_interval_frames": 10}
            ... )
        """
        log.info("processing_coordinator.start_single_video.begin", video_path=str(video_path))

        # Validate inputs
        if isinstance(video_path, str):
            video_path = Path(video_path)

        if not video_path.exists():
            raise ValueError(f"Video file does not exist: {video_path}")

        if not video_path.is_file():
            raise ValueError(f"Path is not a file: {video_path}")

        # Validate dependencies
        if self.video_processing_service is None:
            raise CoordinatorValidationError(
                "VideoProcessingService is required",
                context={"operation": "start_single_video_processing"},
            )

        # Check if already processing
        if self.is_processing_active():
            log.warning("processing_coordinator.start_single_video.already_active")
            self._publish_event(
                "PROCESSING_ALREADY_ACTIVE",
                {"message": "Cannot start: processing already active"},
            )
            return False

        # Update state
        self._update_state(
            StateCategory.PROCESSING,
            is_processing=True,
            processing_type="single_video",
            current_video=str(video_path),
        )

        # Publish event
        self._publish_event(
            "SINGLE_VIDEO_PROCESSING_STARTED",
            {
                "video_path": str(video_path),
                "config": config or {},
            },
        )

        log.info(
            "processing_coordinator.start_single_video.success",
            video_path=str(video_path),
        )
        return True

    def cancel_processing(self) -> bool:
        """
        Cancel current processing operation.

        Orchestrates by:
        1. Checking if processing is active
        2. Delegating to VideoOrchestrator for cancellation
        3. Updating state
        4. Publishing events

        Returns:
            bool: True if cancel was initiated successfully

        Raises:
            ProcessingCoordinatorError: If cancel fails

        Example:
            >>> success = coordinator.cancel_processing()
            >>> if success:
            ...     print("Processing cancelled")
        """
        log.info("processing_coordinator.cancel_processing.begin")

        if not self.is_processing_active():
            log.warning("processing_coordinator.cancel_processing.not_active")
            return False

        # Delegate to orchestrator if available
        if self.video_orchestrator is not None:
            try:
                self.video_orchestrator.cancel_current_analysis()
            except Exception as e:
                log.warning(
                    "processing_coordinator.cancel_processing.orchestrator_error",
                    error=str(e),
                )

        # Update state
        self._update_state(
            StateCategory.PROCESSING,
            is_processing=False,
            is_cancelled=True,
        )

        # Publish event
        self._publish_event("PROCESSING_CANCELLED", {})

        log.info("processing_coordinator.cancel_processing.success")
        return True

    def is_processing_active(self) -> bool:
        """
        Check if processing is currently active.

        Queries StateManager for processing state.

        Returns:
            bool: True if processing is active

        Example:
            >>> if coordinator.is_processing_active():
            ...     print("Processing in progress")
        """
        processing_state = self.state_manager.get_state(StateCategory.PROCESSING)
        return processing_state.get("is_processing", False)

    def get_processing_info(self) -> dict[str, Any]:
        """
        Get information about current processing state.

        Queries StateManager for detailed processing information.

        Returns:
            dict: Dictionary with processing information
                Keys: 'is_processing', 'processing_type', 'current_video', etc.

        Example:
            >>> info = coordinator.get_processing_info()
            >>> if info['is_processing']:
            ...     print(f"Processing type: {info['processing_type']}")
        """
        processing_state = self.state_manager.get_state(StateCategory.PROCESSING)

        start_time = processing_state.get("processing_start_time")
        if start_time is None:
            start_time = processing_state.get("start_time")

        is_cancelled = processing_state.get("cancel_requested")
        if is_cancelled is None:
            is_cancelled = processing_state.get("is_cancelled", False)

        return {
            "is_processing": processing_state.get("is_processing", False),
            "processing_type": processing_state.get("processing_type"),
            "current_video": processing_state.get("current_video"),
            "is_cancelled": is_cancelled,
            "start_time": start_time,
            "last_success": processing_state.get("last_success"),
            "last_error": processing_state.get("last_error"),
        }

    def on_processing_complete(
        self,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """
        Handle processing completion callback.

        Updates state and publishes events when processing finishes.

        Args:
            success: Whether processing completed successfully
            error_message: Optional error message if failed

        Example:
            >>> coordinator.on_processing_complete(success=True)
        """
        log.info(
            "processing_coordinator.on_processing_complete",
            success=success,
            error=error_message,
        )

        # Update state
        self._update_state(
            StateCategory.PROCESSING,
            is_processing=False,
            last_success=success,
            last_error=error_message,
        )

        # Publish event
        event_name = "PROCESSING_COMPLETED" if success else "PROCESSING_FAILED"
        self._publish_event(
            event_name,
            {
                "success": success,
                "error_message": error_message,
            },
        )

    def _validate_zones(self, prompt_if_missing: bool = True) -> bool:
        """
        Validate that zones are properly defined for processing.

        Args:
            prompt_if_missing: Whether to prompt user if zones are missing

        Returns:
            bool: True if zones are valid, False otherwise
        """
        if self.project_manager is None:
            return False

        zone_data = self.project_manager.get_zone_data()

        if not zone_data or not zone_data.polygon:
            log.warning("processing_coordinator.validate_zones.no_arena")

            if prompt_if_missing:
                # Publish event to prompt user
                self._publish_event(
                    "ZONES_MISSING",
                    {
                        "message": "Arena principal não definida",
                        "prompt_user": True,
                    },
                )

            return False

        return True

    def __repr__(self) -> str:
        """Return string representation of ProcessingCoordinator."""
        info = self.get_processing_info()
        return (
            f"<ProcessingCoordinator("
            f"active={info['is_processing']}, "
            f"type={info['processing_type']}"
            f")>"
        )

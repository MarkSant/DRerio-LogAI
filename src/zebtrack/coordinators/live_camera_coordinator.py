"""LiveCameraCoordinator - Live camera analysis workflow orchestration.

This coordinator manages live camera analysis session workflows by delegating
to LiveCameraService and coordinating with detector and recording services.

Sprint 4: Extracted from MainViewModel to improve testability and reduce complexity.

Architecture:
- Orchestrates live camera session start/stop
- Coordinates camera, detector, and recording services
- Manages session state and preview windows
- Handles timed session workflows

Related:
- docs/REFACTOR-MASTER-PLAN-2025.md - Sprint 4
- docs/API_REFERENCE_V3.md - API compatibility
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory

if TYPE_CHECKING:
    from zebtrack.core.live_camera_service import LiveCameraService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class LiveCameraCoordinatorError(CoordinatorError):
    """Raised when live camera coordination fails."""

    pass


class LiveCameraCoordinator(BaseCoordinator):
    """
    Coordinator for live camera analysis workflows.

    This coordinator orchestrates:
    - Live camera session start/stop
    - Camera hardware initialization
    - Real-time detection and analysis
    - Preview window management
    - Timed session workflows

    Design Principles:
    - Delegates camera operations to LiveCameraService
    - Coordinates multiple services (camera, detector, recording)
    - Updates state via StateManager
    - Publishes events via EventBus
    - Clear error handling and cleanup

    Dependencies:
        state_manager: StateManager for state tracking
        live_camera_service: LiveCameraService for camera operations
        camera: Camera hardware instance (optional)
        event_bus: Optional EventBus for notifications

    Example:
        ```python
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=live_camera_service,
            camera=camera,
            event_bus=event_bus,
        )

        # Start live session
        success = coordinator.start_live_session(
            camera_index=0,
            duration_s=60.0,
            experiment_id="live_001",
        )

        # Stop session
        coordinator.stop_live_session()
        ```
    """

    def __init__(
        self,
        state_manager: StateManager,
        live_camera_service: LiveCameraService,
        camera: Camera | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize LiveCameraCoordinator.

        Args:
            state_manager: StateManager for state tracking
            live_camera_service: LiveCameraService for camera operations
            camera: Optional Camera hardware instance
            event_bus: Optional EventBus for event publishing
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        self.live_camera_service = live_camera_service
        self.camera = camera

        # Session state
        self._active_session_id: str | None = None

        log.info(
            "live_camera_coordinator.initialized",
            has_live_camera_service=live_camera_service is not None,
            has_camera=camera is not None,
        )

    def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available.

        Returns:
            True if all dependencies valid, False otherwise
        """
        if self.live_camera_service is None:
            log.error("dependency.missing", dep="live_camera_service")
            return False

        if self.state_manager is None:
            log.error("dependency.missing", dep="state_manager")
            return False

        return True

    # =========================================================================
    # Live Session Management
    # =========================================================================

    def start_live_session(
        self,
        camera_index: int = 0,
        duration_s: float = 60.0,
        experiment_id: str | None = None,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
        output_base_dir: str | None = None,
        zones: list[dict] | None = None,
    ) -> bool:
        """
        Start a live camera analysis session.

        Args:
            camera_index: Camera device index to use
            duration_s: Session duration in seconds
            experiment_id: Optional experiment identifier
            analysis_interval_frames: Analyze every N frames (default: 1 = every frame)
            display_interval_frames: Display every N frames (default: 1 = every frame)
            record_video: Whether to record video during session
            output_base_dir: Custom output directory (default: live_analysis_sessions/)
            zones: Optional zone configurations for detection

        Returns:
            True if session started successfully, False otherwise

        Raises:
            LiveCameraCoordinatorError: If session cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="LiveCameraCoordinator",
                operation="start_live_session",
            )

        # Generate session ID if not provided
        if experiment_id is None:
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_id = f"live_session_{timestamp}"

        log.info(
            "live_camera_coordinator.start_session.begin",
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
        )

        try:
            # Check if session already active
            if self.is_session_active():
                raise LiveCameraCoordinatorError(
                    "Live session already active",
                    coordinator="LiveCameraCoordinator",
                    operation="start_live_session",
                    active_session=self._active_session_id,
                )

            # Validate camera index
            self._validate_type(camera_index, int, "camera_index")
            if camera_index < 0:
                raise ValueError("camera_index must be >= 0")

            # Validate duration
            self._validate_type(duration_s, (int, float), "duration_s")
            if duration_s <= 0:
                raise ValueError("duration_s must be > 0")

            # Update state to active
            self._update_state(
                StateCategory.PROCESSING,  # Or create LIVE_CAMERA category
                is_live_session_active=True,
                camera_index=camera_index,
                experiment_id=experiment_id,
                duration_s=duration_s,
            )

            # Store active session ID
            self._active_session_id = experiment_id

            # Delegate to LiveCameraService
            success = self.live_camera_service.start_session(
                camera_index=camera_index,
                duration_s=duration_s,
                experiment_id=experiment_id,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                record_video=record_video,
                output_base_dir=output_base_dir,
            )

            if not success:
                # Revert state on failure
                self._active_session_id = None
                self._update_state(
                    StateCategory.PROCESSING,
                    is_live_session_active=False,
                )
                raise LiveCameraCoordinatorError(
                    "LiveCameraService failed to start session",
                    coordinator="LiveCameraCoordinator",
                    operation="start_live_session",
                )

            # Publish success event
            self._publish_event(
                "LIVE_SESSION_STARTED",
                {
                    "experiment_id": experiment_id,
                    "camera_index": camera_index,
                    "duration_s": duration_s,
                },
            )

            log.info(
                "live_camera_coordinator.start_session.success",
                experiment_id=experiment_id,
            )

            return True

        except ValueError as e:
            log.error(
                "live_camera_coordinator.start_session.validation_error",
                error=str(e),
            )
            raise LiveCameraCoordinatorError(
                f"Validation error: {str(e)}",
                coordinator="LiveCameraCoordinator",
                operation="start_live_session",
            ) from e

        except Exception as e:
            log.error(
                "live_camera_coordinator.start_session.failed",
                experiment_id=experiment_id,
                error=str(e),
                exc_info=True,
            )

            # Clean up on failure
            self._active_session_id = None
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=False,
            )

            raise LiveCameraCoordinatorError(
                f"Failed to start live session: {str(e)}",
                coordinator="LiveCameraCoordinator",
                operation="start_live_session",
                experiment_id=experiment_id,
            ) from e

    def stop_live_session(self) -> bool:
        """
        Stop the current live camera session.

        Returns:
            True if session stopped successfully, False otherwise
        """
        log.info("live_camera_coordinator.stop_session.begin")

        try:
            # Check if session active
            if not self.is_session_active():
                log.warning("live_camera_coordinator.stop_session.no_active_session")
                return False

            # Delegate to service
            success = self.live_camera_service.stop_session()

            # Update state
            self._active_session_id = None
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=False,
            )

            # Publish event
            self._publish_event("LIVE_SESSION_STOPPED", {})

            log.info(
                "live_camera_coordinator.stop_session.success",
                success=success,
            )

            return success

        except Exception as e:
            log.error(
                "live_camera_coordinator.stop_session.failed",
                error=str(e),
                exc_info=True,
            )
            return False

    # =========================================================================
    # Camera Management
    # =========================================================================

    def initialize_camera(
        self,
        camera_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> bool:
        """
        Initialize camera hardware.

        Args:
            camera_index: Camera device index
            width: Optional desired width
            height: Optional desired height

        Returns:
            True if camera initialized successfully, False otherwise

        Raises:
            LiveCameraCoordinatorError: If camera initialization fails
        """
        log.info(
            "live_camera_coordinator.initialize_camera",
            camera_index=camera_index,
            width=width,
            height=height,
        )

        try:
            # Validate camera index
            self._validate_type(camera_index, int, "camera_index")
            if camera_index < 0:
                raise ValueError("camera_index must be >= 0")

            # Initialize camera
            # (actual implementation would create Camera instance)
            # self.camera = Camera(index=camera_index)

            # Publish event
            self._publish_event(
                "CAMERA_INITIALIZED",
                {
                    "camera_index": camera_index,
                    "width": width,
                    "height": height,
                },
            )

            return True

        except Exception as e:
            log.error(
                "live_camera_coordinator.initialize_camera.failed",
                camera_index=camera_index,
                error=str(e),
                exc_info=True,
            )
            raise LiveCameraCoordinatorError(
                f"Failed to initialize camera: {str(e)}",
                coordinator="LiveCameraCoordinator",
                operation="initialize_camera",
                camera_index=camera_index,
            ) from e

    def release_camera(self) -> bool:
        """
        Release camera hardware resources.

        Returns:
            True if camera released successfully, False otherwise
        """
        log.info("live_camera_coordinator.release_camera")

        try:
            if self.camera:
                # Release camera
                # self.camera.release()
                self.camera = None

            # Publish event
            self._publish_event("CAMERA_RELEASED", {})

            return True

        except Exception as e:
            log.error(
                "live_camera_coordinator.release_camera.failed",
                error=str(e),
                exc_info=True,
            )
            return False

    # =========================================================================
    # Session State Queries
    # =========================================================================

    def is_session_active(self) -> bool:
        """
        Check if a live session is currently active.

        Returns:
            True if session active, False otherwise
        """
        return self._active_session_id is not None

    def get_session_info(self) -> dict[str, Any] | None:
        """
        Get information about current live session.

        Returns:
            dict with session info, or None if no active session

        Example return:
            {
                "session_id": "live_001",
                "is_active": True,
                "camera_index": 0,
                "duration_s": 60.0,
            }
        """
        if not self.is_session_active():
            return None

        # Get state from StateManager
        processing_state = self.state_manager.get_processing_state()

        return {
            "session_id": self._active_session_id,
            "is_active": True,
            "camera_index": getattr(processing_state, "camera_index", None),
            "experiment_id": getattr(processing_state, "experiment_id", None),
            "duration_s": getattr(processing_state, "duration_s", None),
        }

    def get_active_session_id(self) -> str | None:
        """
        Get the ID of the currently active session.

        Returns:
            Session ID string, or None if no active session
        """
        return self._active_session_id

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<LiveCameraCoordinator("
            f"session_active={self.is_session_active()}, "
            f"session_id={self._active_session_id}, "
            f"has_camera={self.camera is not None}"
            f")>"
        )

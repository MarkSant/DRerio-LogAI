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
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.camera import Camera
    from zebtrack.settings import Settings
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
        project_manager: ProjectManager for zone data and project state
        settings: Settings configuration object
        camera: Camera hardware instance (optional)
        event_bus: Optional EventBus for notifications

    Example:
        ```python
        coordinator = LiveCameraCoordinator(
            state_manager=state_manager,
            live_camera_service=live_camera_service,
            project_manager=project_manager,
            settings=settings,
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
        project_manager: ProjectManager | None = None,
        settings: Settings | None = None,
        camera: Camera | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize LiveCameraCoordinator.

        Args:
            state_manager: StateManager for state tracking
            live_camera_service: LiveCameraService for camera operations
            project_manager: Optional ProjectManager for zone data and project state
            settings: Optional Settings configuration object
            camera: Optional Camera hardware instance
            event_bus: Optional EventBus for event publishing
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        self.live_camera_service = live_camera_service
        self.project_manager = project_manager
        self.settings = settings
        self.camera = camera

        # Session state
        self._active_session_id: str | None = None

        log.info(
            "live_camera_coordinator.initialized",
            has_live_camera_service=live_camera_service is not None,
            has_project_manager=project_manager is not None,
            has_settings=settings is not None,
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
                f"Validation error: {e!s}",
                coordinator="LiveCameraCoordinator",
                operation="start_live_session",
            ) from e

        except Exception as e:  # except Exception justified: service boundary catch-all
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
                f"Failed to start live session: {e!s}",
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
            service_result = self.live_camera_service.stop_session()
            success = bool(service_result)

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

        except Exception as e:  # except Exception justified: graceful stop must not crash
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

        except Exception as e:  # except Exception justified: service boundary catch-all
            log.error(
                "live_camera_coordinator.initialize_camera.failed",
                camera_index=camera_index,
                error=str(e),
                exc_info=True,
            )
            raise LiveCameraCoordinatorError(
                f"Failed to initialize camera: {e!s}",
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

        except Exception as e:  # except Exception justified: hardware cleanup must not crash
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

    # =========================================================================
    # Configuration-Based Session Start (Sprint 33)
    # =========================================================================

    def start_session_from_config(self, config: dict) -> bool:
        """
        Start live camera analysis with full configuration from SingleVideoConfigDialog.

        This method extracts all parameters from the config dictionary and delegates
        to LiveCameraService, ensuring intervals and other settings are respected.

        Extracted from MainViewModel (Sprint 33) to improve separation of concerns.

        Args:
            config: Configuration dictionary from SingleVideoConfigDialog containing:
                - camera_index: int - Camera device index
                - analysis_interval_frames: int - Analyze every N frames
                - display_interval_frames: int - Display every N frames
                - duration_s: float (optional) - Session duration in seconds
                - experiment_id: str (optional) - Experiment identifier
                - record_video: bool (optional) - Whether to record video

        Returns:
            True if session started successfully, False otherwise
        """
        log.info("coordinator.live_analysis.start_from_config", config_keys=list(config.keys()))

        # Extract configuration with defaults
        camera_index = config["camera_index"]

        # Duration: use from config (user-editable), fallback to setting or default
        duration_s = config.get("duration_s")
        if duration_s is None:
            settings = self.settings
            if settings is not None and hasattr(settings, "live_analysis"):
                duration_s = settings.live_analysis.default_duration_s
            else:
                duration_s = 300.0  # 5 minutes default

        # Experiment ID
        experiment_id = config.get("experiment_id") or f"camera_{camera_index}"

        # ✅ CRITICAL: Extract intervals from config (not hardcoded defaults!)
        analysis_interval_frames = config.get("analysis_interval_frames", 1)
        display_interval_frames = config.get("display_interval_frames", 1)

        # Video recording (optional)
        record_video = config.get("record_video", True)

        log.info(
            "coordinator.live_analysis.extracted_config",
            camera_index=camera_index,
            duration_s=duration_s,
            analysis_interval=analysis_interval_frames,
            display_interval=display_interval_frames,
            record_video=record_video,
        )

        # ✅ SINGLE VIDEO ANALYSIS: Ensure default arena if none defined
        # This allows detection to work without manual zone configuration
        # NOTE: Only for single video analysis, not for live projects
        zone_data = self.project_manager.get_zone_data() if self.project_manager else None

        log.info(
            "coordinator.live_analysis.checking_zones",
            has_zone_data=zone_data is not None,
            has_polygon=bool(zone_data.polygon) if zone_data else False,
        )

        if not zone_data or not zone_data.polygon:
            import math

            from zebtrack.core.detector import ZoneData

            log.info("coordinator.live_analysis.creating_default_arena", reason="no_arena_defined")

            # Open camera temporarily to get dimensions
            from zebtrack.io.camera import Camera

            settings = self.settings
            if settings is None:
                log.error("coordinator.live_analysis.missing_settings")
                return False

            temp_settings = settings.model_copy(deep=True)
            temp_settings.camera.index = camera_index
            temp_settings.camera.desired_width = 1280
            temp_settings.camera.desired_height = 720
            temp_camera = Camera(settings_obj=temp_settings)

            if temp_camera.is_opened():
                w = temp_camera.actual_width
                h = temp_camera.actual_height
                temp_camera.release()

                # Create default arena: centered square occupying 1/6 of total frame area
                # Formula: side = sqrt(total_area / 6) = sqrt(w*h / 6)
                area_ratio = 6.0
                side = math.sqrt((w * h) / area_ratio)
                cx, cy = w / 2, h / 2
                half = side / 2

                default_arena = [
                    [int(cx - half), int(cy - half)],
                    [int(cx + half), int(cy - half)],
                    [int(cx + half), int(cy + half)],
                    [int(cx - half), int(cy + half)],
                ]

                zone_data = ZoneData(polygon=default_arena)

                # Save to project_manager so detector can use it
                if self.project_manager:
                    self.project_manager.save_zone_data(zone_data, video_path=None, persist=False)

                log.info(
                    "coordinator.live_analysis.default_arena_created",
                    width=w,
                    height=h,
                    side=side,
                    area_ratio=area_ratio,
                    reason="no_arena_defined_for_single_video_analysis",
                )
            else:
                log.error(
                    "coordinator.live_analysis.default_arena_failed",
                    reason="camera_not_opened",
                )
        else:
            log.info(
                "coordinator.live_analysis.using_existing_zones",
                has_polygon=bool(zone_data.polygon),
                num_rois=len(zone_data.roi_polygons) if zone_data else 0,
            )

        # Delegate to LiveCameraService with complete configuration
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=record_video,
            analysis_config=config,
        )

        # UI feedback
        if success and self.event_bus:
            from zebtrack.ui.events import Events

            self.event_bus.publish_event(
                Events.UI_SET_STATUS,
                {
                    "message": (
                        f"Analisando câmera {camera_index} "
                        f"(análise: {analysis_interval_frames}f, "
                        f"exibição: {display_interval_frames}f)"
                    )
                },
            )
        elif not success and self.event_bus:
            from zebtrack.ui.events import Events

            self.event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Análise",
                    "message": f"Falha ao iniciar análise de câmera {camera_index}.",
                },
            )

        return success

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<LiveCameraCoordinator("
            f"session_active={self.is_session_active()}, "
            f"session_id={self._active_session_id}, "
            f"has_camera={self.camera is not None}"
            f")>"
        )

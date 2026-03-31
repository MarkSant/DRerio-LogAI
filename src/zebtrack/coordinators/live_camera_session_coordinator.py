"""Live Camera Session Coordinator - Phase 4.7 Decomposition.

Extracted from SessionCoordinator (Phase 3).

Responsibilities:
    - Live camera session lifecycle (start/stop/info)
    - Session configuration from dialogs
    - Live project recording sessions (from grid)
    - Batch session registration with LiveBatchCoordinator

Architecture:
    - Zero MainViewModel dependency
    - Pure dependency injection pattern
    - Delegates to LiveCameraService
    - Publishes events via EventBus
    - Updates StateManager for state tracking
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.coordinators.live_batch_coordinator import LiveBatchCoordinator
    from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.recording.live_camera_service import LiveCameraService
    from zebtrack.core.services.detector_service import DetectorService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class LiveCameraSessionCoordinatorError(CoordinatorError):
    """Base exception for LiveCameraSessionCoordinator errors."""

    pass


# =============================================================================
# MAIN COORDINATOR
# =============================================================================


class LiveCameraSessionCoordinator(BaseCoordinator):
    """Coordinator for live camera session lifecycle management.

    Phase 4.7 Decomposition — extracted from SessionCoordinator.

    Responsibilities:
        - Start/stop live camera analysis sessions
        - Session configuration from dialogs (start_live_camera_analysis)
        - Config-based session start (start_session_from_config)
        - Live project sessions from grid (start_live_project_session)
        - Batch session registration with LiveBatchCoordinator
    """

    def __init__(
        self,
        state_manager: StateManager,
        live_camera_service: LiveCameraService,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        settings_obj: Settings,
        live_calibration_coordinator: LiveCalibrationCoordinator,
        event_bus: EventBusV2 | None = None,
        live_batch_coordinator: LiveBatchCoordinator | None = None,
        # UI components (temporary - being phased out)
        root: Any = None,
        view: Any = None,
    ):
        """Initialize LiveCameraSessionCoordinator with pure dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            live_camera_service: LiveCameraService for live camera operations
            project_manager: ProjectManager for project data and zones
            detector_service: DetectorService for detection configuration
            settings_obj: Settings configuration object
            live_calibration_coordinator: For zone validation before recording
            event_bus: EventBus for UI notifications (optional)
            live_batch_coordinator: For batch session tracking (optional)
            root: Tkinter root window (legacy, being phased out)
            view: GUI view instance (legacy, being phased out)

        Note:
            CRITICAL: NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        # Core services
        self.live_camera_service = live_camera_service
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.settings = settings_obj
        self.live_calibration_coordinator = live_calibration_coordinator
        self.live_batch_coordinator = live_batch_coordinator

        # UI components (temporary - being phased out)
        self.root = root
        self.view = view

        # Session state
        self._active_live_session_id: str | None = None
        self._active_wizard_data: dict | None = None

        log.info(
            "live_camera_session_coordinator.initialized",
            has_live_camera_service=live_camera_service is not None,
        )

    def validate_dependencies(self) -> bool:
        """Validate that required dependencies are present.

        Returns:
            bool: True if all required dependencies are present

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        if self.live_camera_service is None:
            raise CoordinatorValidationError(
                "LiveCameraService is required but was None",
                context={
                    "coordinator": "LiveCameraSessionCoordinator",
                    "missing_dependency": "live_camera_service",
                },
            )
        if self.project_manager is None:
            raise CoordinatorValidationError(
                "ProjectManager is required but was None",
                context={
                    "coordinator": "LiveCameraSessionCoordinator",
                    "missing_dependency": "project_manager",
                },
            )
        return True

    # =============================================================================
    # LIVE SESSION LIFECYCLE
    # =============================================================================

    def start_live_session(
        self,
        camera_index: int = 0,
        duration_s: float = 60.0,
        experiment_id: str | None = None,
        analysis_interval_frames: int = 1,
        display_interval_frames: int = 1,
        record_video: bool = True,
        output_base_dir: Path | str | None = None,
        zones: list[dict] | None = None,
        wizard_data: dict | None = None,
    ) -> bool:
        """Start a live camera analysis session.

        Args:
            camera_index: Camera device index to use
            duration_s: Session duration in seconds
            experiment_id: Optional experiment identifier
            analysis_interval_frames: Analyze every N frames (default: 1 = every frame)
            display_interval_frames: Display every N frames (default: 1 = every frame)
            record_video: Whether to record video during session
            output_base_dir: Custom output directory (default: live_analysis_sessions/)
            zones: Optional zone configurations for detection
            wizard_data: Batch metadata for LiveBatchCoordinator (v2.3.0)

        Returns:
            True if session started successfully, False otherwise

        Raises:
            LiveCameraSessionCoordinatorError: If session cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="LiveCameraSessionCoordinator",
                operation="start_live_session",
            )

        # Generate session ID if not provided
        if experiment_id is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_id = f"live_session_{timestamp}"

        log.info(
            "live_camera_session_coordinator.start_live_session.begin",
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
        )

        try:
            # Check if session already active
            if self.is_live_session_active():
                raise LiveCameraSessionCoordinatorError(
                    "Live session already active",
                    coordinator="LiveCameraSessionCoordinator",
                    operation="start_live_session",
                    active_session=self._active_live_session_id,
                )

            # Validate inputs
            self._validate_type(camera_index, int, "camera_index")
            if camera_index < 0:
                raise ValueError("camera_index must be >= 0")

            self._validate_type(duration_s, (int, float), "duration_s")
            if duration_s <= 0:
                raise ValueError("duration_s must be > 0")

            # Update state to active
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=True,
                camera_index=camera_index,
                experiment_id=experiment_id,
                duration_s=duration_s,
            )

            # Store active session ID
            self._active_live_session_id = experiment_id
            self._active_wizard_data = wizard_data or {}

            # Extract animals_per_aquarium from wizard_data if available
            animals_per_aquarium = wizard_data.get("animals_per_aquarium", 1) if wizard_data else 1

            # v2.3.1: Build analysis_config with batch metadata for video registration
            analysis_config = None
            if wizard_data:
                analysis_config = {
                    "group": wizard_data.get("experimental_group"),
                    "day": wizard_data.get("experiment_day"),
                    "subject_id": wizard_data.get("subject_id"),
                    "camera_index": camera_index,
                }

            # Delegate to LiveCameraService
            success = self.live_camera_service.start_session(
                camera_index=camera_index,
                duration_s=duration_s,
                experiment_id=experiment_id,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                record_video=record_video,
                output_base_dir=output_base_dir,
                animals_per_aquarium=animals_per_aquarium,
                use_external_preview=False,  # Use integrated canvas in Analysis tab
                analysis_config=analysis_config,
            )

            if not success:
                # Revert state on failure
                self._active_live_session_id = None
                self._update_state(
                    StateCategory.PROCESSING,
                    is_live_session_active=False,
                )
                raise LiveCameraSessionCoordinatorError(
                    "LiveCameraService failed to start session",
                    coordinator="LiveCameraSessionCoordinator",
                    operation="start_live_session",
                )

            # Publish success event
            self._publish_event(
                UIEvents.LIVE_SESSION_STARTED,
                {
                    "experiment_id": experiment_id,
                    "camera_index": camera_index,
                    "duration_s": duration_s,
                },
            )

            # FIX Bug 3: Enable cancel button in integrated canvas mode
            if self.view and hasattr(self.view, "show_progress_bar"):
                if self.root:
                    self.root.after(0, self.view.show_progress_bar)
                    log.info(
                        "live_camera_session_coordinator.start_live_session.cancel_button_enabled",
                        via="show_progress_bar",
                    )
                else:
                    self.view.show_progress_bar()

            log.info(
                "live_camera_session_coordinator.start_live_session.success",
                experiment_id=experiment_id,
            )

            return True

        except ValueError as e:
            log.error(
                "live_camera_session_coordinator.start_live_session.validation_error",
                error=str(e),
            )
            raise LiveCameraSessionCoordinatorError(
                f"Validation error: {e!s}",
                coordinator="LiveCameraSessionCoordinator",
                operation="start_live_session",
            ) from e

        except Exception as e:  # except Exception justified: service boundary catch-all
            log.error(
                "live_camera_session_coordinator.start_live_session.failed",
                experiment_id=experiment_id,
                error=str(e),
                exc_info=True,
            )

            # Clean up on failure
            self._active_live_session_id = None
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=False,
            )

            raise LiveCameraSessionCoordinatorError(
                f"Failed to start live session: {e!s}",
                coordinator="LiveCameraSessionCoordinator",
                operation="start_live_session",
                experiment_id=experiment_id,
            ) from e

    def stop_live_session(self) -> bool:
        """Stop the current live camera session.

        Returns:
            True if session stopped successfully, False otherwise
        """
        log.info("live_camera_session_coordinator.stop_live_session.begin")

        try:
            # Check if session active
            if not self.is_live_session_active():
                log.warning("live_camera_session_coordinator.stop_live_session.no_active_session")
                return False

            # Delegate to service
            service_result = self.live_camera_service.stop_session()
            success = bool(service_result)

            # Update state
            self._active_live_session_id = None
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=False,
            )

            # Publish event
            self._publish_event(UIEvents.LIVE_SESSION_STOPPED, payloads.EmptyPayload())

            # v2.3.1: Re-enable start recording button after session ends
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_UPDATE_BUTTON_STATE,
                        data={"button_name": "start_rec", "state": "normal"},
                    )
                )
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_UPDATE_BUTTON_STATE,
                        data={"button_name": "stop_rec", "state": "disabled"},
                    )
                )
                log.info("live_camera_session_coordinator.stop_live_session.buttons_restored")

            # FIX Bug 3: Hide progress bar and disable cancel button
            if hasattr(self, "view") and self.view and hasattr(self.view, "hide_progress_bar"):
                if self.root:
                    self.root.after(0, self.view.hide_progress_bar)
                    log.info(
                        "live_camera_session_coordinator.stop_live_session.progress_bar_hidden"
                    )
                else:
                    self.view.hide_progress_bar()

            # FIX BUG: Unsubscribe canvas from live frame updates to stop warnings
            if hasattr(self, "view") and self.view and hasattr(self.view, "canvas_manager"):
                log.info("live_camera_session_coordinator.stop_live_session.unsubscribing_canvas")
                self.view.canvas_manager.unsubscribe_from_live_frames()
            else:
                log.warning(
                    "live_camera_session_coordinator.stop_live_session.cannot_unsubscribe",
                    has_view=hasattr(self, "view") and self.view is not None,
                    has_canvas=hasattr(self.view, "canvas_manager")
                    if hasattr(self, "view") and self.view
                    else False,
                )

            # v2.3.0: Register session for batch tracking
            if success and self.live_batch_coordinator and self._active_wizard_data:
                self._register_batch_session()

            log.info(
                "live_camera_session_coordinator.stop_live_session.success",
                success=success,
            )

            return success

        except Exception as e:  # except Exception justified: graceful stop must not crash
            log.error(
                "live_camera_session_coordinator.stop_live_session.failed",
                error=str(e),
                exc_info=True,
            )
            return False

    def is_live_session_active(self) -> bool:
        """Check if a live session is currently active.

        Returns:
            True if session active, False otherwise
        """
        return self._active_live_session_id is not None

    def get_live_session_info(self) -> dict[str, Any] | None:
        """Get information about current live session.

        Returns:
            dict with session info, or None if no active session
        """
        if not self.is_live_session_active():
            return None

        # Get state from StateManager
        processing_state = self.state_manager.get_processing_state()

        return {
            "session_id": self._active_live_session_id,
            "is_active": True,
            "camera_index": getattr(processing_state, "camera_index", None),
            "experiment_id": getattr(processing_state, "experiment_id", None),
            "duration_s": getattr(processing_state, "duration_s", None),
        }

    # =============================================================================
    # BATCH SESSION REGISTRATION
    # =============================================================================

    def _register_batch_session(self):
        """Register completed session with LiveBatchCoordinator (v2.3.0).

        Internal method called after session stops successfully.
        Extracts batch metadata from wizard_data and registers with coordinator.
        """
        if not self.live_batch_coordinator or not self._active_wizard_data:
            return

        try:
            # Extract batch metadata
            group = self._active_wizard_data.get("experimental_group")
            day = self._active_wizard_data.get("experiment_day")
            subject_id = self._active_wizard_data.get("subject_id")

            # Only register if all batch fields present
            if not all([group, day, subject_id]):
                log.debug(
                    "live_camera_session_coordinator.batch_metadata_incomplete",
                    group=group,
                    day=day,
                    subject_id=subject_id,
                )
                return

            # Find video file in live session output
            video_path = self._find_video_in_live_session()
            if not video_path:
                log.warning("live_camera_session_coordinator.batch_registration_no_video")
                return

            # Register session
            metadata = {
                "group": group,
                "day": day,
                "subject_id": subject_id,
                "timestamp": datetime.datetime.now().isoformat(),
                "duration_s": self._active_wizard_data.get("recording_duration_s"),
                "camera_index": self._active_wizard_data.get("camera_index"),
            }

            batch_id = self.live_batch_coordinator.register_session(
                experiment_id=self._active_live_session_id or "unknown",
                video_path=video_path,
                metadata=metadata,
            )

            log.info(
                "live_camera_session_coordinator.batch_session_registered",
                batch_id=batch_id,
                group=group,
                day=day,
                subject_id=subject_id,
            )

            # Check if user marked as last session
            if self._active_wizard_data.get("is_batch_last_session"):
                log.info("live_camera_session_coordinator.batch_marked_complete", batch_id=batch_id)
                self.live_batch_coordinator.mark_batch_complete(batch_id)

        except Exception as e:  # except Exception justified: non-critical fallback
            log.error(
                "live_camera_session_coordinator.batch_registration_failed",
                error=str(e),
                exc_info=True,
            )
        finally:
            # Clear wizard data after processing
            self._active_wizard_data = None

    def _find_video_in_live_session(self) -> Path | None:
        """Find video file in current live session output directory.

        Returns:
            Path to video file, or None if not found
        """
        if not hasattr(self.live_camera_service, "current_output_dir"):
            return None

        output_dir = self.live_camera_service.current_output_dir
        if not output_dir or not Path(output_dir).exists():
            return None

        # Search for video file
        video_extensions = [".mp4", ".avi", ".mkv"]
        for ext in video_extensions:
            video_files = list(Path(output_dir).glob(f"*{ext}"))
            if video_files:
                return video_files[0]

        # Fallback: return expected path
        return Path(output_dir) / "live_recording.mp4"

    # =============================================================================
    # LIVE CAMERA ANALYSIS (Single video workflow)
    # =============================================================================

    def start_live_camera_analysis(self, camera_index: int | None = None):
        """Start a live camera analysis session (single video workflow).

        Delegates to LiveCameraService for thread management and coordination.

        Args:
            camera_index: Optional camera index. If provided, uses this camera directly
                         without showing the configuration dialog. If None, shows dialog.
        """
        log.info("live_camera_session_coordinator.live_analysis.start", camera_index=camera_index)

        config = {}

        # Get configuration from dialog or use defaults
        if camera_index is not None:
            # Use camera directly with default settings
            duration_s = 300.0
            if hasattr(self.settings, "live_analysis"):
                duration_s = self.settings.live_analysis.default_duration_s

            config = {
                "camera_index": camera_index,
                "duration_s": duration_s,
                "experiment_id": f"camera_{camera_index}",
                "analysis_interval_frames": 1,
                "display_interval_frames": 1,
                "record_video": True,
            }
        else:
            # Show configuration dialog
            if not self.root:
                log.error("live_camera_session_coordinator.live_analysis.no_root")
                return

            from zebtrack.ui.dialogs import LiveAnalysisDialog

            dialog = LiveAnalysisDialog(
                self.root,
                settings_obj=self.settings,
                event_bus=self.event_bus,
            )

            if not dialog.result:
                log.info("live_camera_session_coordinator.live_analysis.cancelled")
                return

            config = dialog.result

        # Delegate to unified start method
        self.start_session_from_config(config)

    def start_session_from_config(self, config: dict) -> bool:
        """Start live camera analysis with full configuration from SingleVideoConfigDialog.

        This method extracts all parameters from the config dictionary and delegates
        to LiveCameraService, ensuring intervals and other settings are respected.

        Args:
            config: Configuration dictionary from SingleVideoConfigDialog

        Returns:
            True if session started successfully, False otherwise
        """
        log.info(
            "live_camera_session_coordinator.live_analysis.start_from_config",
            config_keys=list(config.keys()),
        )

        # Extract configuration with defaults
        camera_index = config["camera_index"]

        # Duration: use from config (user-editable), fallback to setting or default
        duration_s = config.get("duration_s")
        if duration_s is None:
            if hasattr(self.settings, "live_analysis"):
                duration_s = self.settings.live_analysis.default_duration_s
            else:
                duration_s = 300.0  # 5 minutes default

        # Experiment ID
        experiment_id = config.get("experiment_id") or f"camera_{camera_index}"

        # Extract intervals from config (not hardcoded defaults!)
        analysis_interval_frames = config.get("analysis_interval_frames", 1)
        display_interval_frames = config.get("display_interval_frames", 1)

        # Video recording (optional)
        record_video = config.get("record_video", True)

        # FIX: Update settings with dialog configuration BEFORE starting session
        animal_method = config.get("animal_method")
        aquarium_method = config.get("aquarium_method")
        use_openvino = config.get("use_openvino")
        use_single_subject_tracker = config.get("use_single_subject_tracker")

        if animal_method is not None:
            self.settings.model_selection.animal_method = animal_method
            log.info(
                "live_camera_session_coordinator.live_analysis.animal_method_updated",
                value=animal_method,
            )

        if aquarium_method is not None:
            self.settings.model_selection.aquarium_method = aquarium_method
            log.info(
                "live_camera_session_coordinator.live_analysis.aquarium_method_updated",
                value=aquarium_method,
            )

        if use_openvino is not None:
            self.settings.model_selection.use_openvino = use_openvino
            log.info(
                "live_camera_session_coordinator.live_analysis.use_openvino_updated",
                value=use_openvino,
            )

        if use_single_subject_tracker is not None:
            # Update detector service if already initialized
            if self.detector_service and self.detector_service.detector:
                self.detector_service.detector.set_single_subject_mode(use_single_subject_tracker)
                log.info(
                    "live_camera_session_coordinator.live_analysis.single_subject_updated",
                    value=use_single_subject_tracker,
                )

        log.info(
            "live_camera_session_coordinator.live_analysis.extracted_config",
            camera_index=camera_index,
            duration_s=duration_s,
            analysis_interval=analysis_interval_frames,
            display_interval=display_interval_frames,
            record_video=record_video,
            animal_method=animal_method,
            use_openvino=use_openvino,
        )

        # Check existing zones
        zone_data = self.project_manager.get_zone_data()
        log.info(
            "live_camera_session_coordinator.live_analysis.arena_check",
            has_predefined_arena=bool(zone_data and zone_data.polygon),
        )

        # Extract animals_per_aquarium for tracking configuration
        animals_per_aquarium = config.get("animals_per_aquarium", 1)
        log.info(
            "live_camera_session_coordinator.live_analysis.tracking_config",
            animals_per_aquarium=animals_per_aquarium,
        )

        # v2.2.0: Apply preferred mode if selected in wizard
        selected_mode = config.get("selected_live_mode")
        if selected_mode:
            self.live_camera_service.set_preferred_mode(selected_mode)
            log.info(
                "live_camera_session_coordinator.live_analysis.preferred_mode_applied",
                mode=selected_mode,
            )

        # v2.3.0: Build analysis_config with batch metadata for video registration
        analysis_config = {
            "group": config.get("experimental_group"),
            "day": config.get("experiment_day"),
            "subject_id": config.get("subject_id"),
            "camera_index": camera_index,
        }

        # Delegate to LiveCameraService
        # FIX: Use integrated canvas preview (no external window)
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=record_video,
            animals_per_aquarium=animals_per_aquarium,
            use_external_preview=False,  # Use canvas in Analysis tab
            analysis_config=analysis_config,
        )

        # UI feedback
        if success and self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SET_STATUS,
                    data={
                        "message": (
                            f"Analisando câmera {camera_index} "
                            f"(análise: {analysis_interval_frames}f, "
                            f"exibição: {display_interval_frames}f)"
                        )
                    },
                )
            )
        elif not success and self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SHOW_ERROR,
                    data={
                        "title": "Erro na Análise",
                        "message": f"Falha ao iniciar análise de câmera {camera_index}.",
                    },
                )
            )

        return success

    # =============================================================================
    # LIVE PROJECT SESSIONS
    # =============================================================================

    def start_live_project_session(
        self,
        day: int,
        group: str,
        subject: str,
        duration_s: float | None = None,
    ) -> bool:
        """Start a live recording session for a Live project.

        This method replaces the legacy thread-based system in gui.py,
        using LiveCameraService for unified camera management.

        Args:
            day: Day number (from project grid)
            group: Group identifier
            subject: Subject/animal identifier
            duration_s: Optional duration override (uses project default if None)

        Returns:
            True if session started successfully, False otherwise
        """
        # Validate project type
        if self.project_manager.get_project_type() != "live":
            log.error(
                "live_camera_session_coordinator.start_live_project_session.wrong_project_type"
            )
            return False

        # Extract project configuration
        project_data = self.project_manager.project_data
        camera_index = project_data.get("camera_index", 0)

        # Duration: use parameter, project default, or fallback
        if duration_s is None:
            duration_s = project_data.get("recording_duration_s", 300.0)

        # Intervals
        analysis_interval_frames = project_data.get("analysis_interval_frames", 1)
        display_interval_frames = project_data.get("display_interval_frames", 1)

        # Experiment ID for this session
        experiment_id = f"day{day}_{group}_{subject}"

        log.info(
            "live_camera_session_coordinator.live_project_session.start",
            project=self.project_manager.get_project_name(),
            experiment_id=experiment_id,
            camera_index=camera_index,
            duration_s=duration_s,
        )

        # v2.3.1: Ensure zones are defined before recording
        if not self.live_calibration_coordinator.ensure_zones_before_recording():
            log.info("live_camera_session_coordinator.live_project_session.zones_not_ready")
            return False

        # v2.3.1: Increment session count to track recordings for zone reuse dialog
        self.live_calibration_coordinator.increment_session_count()

        # v2.3.0: Store batch metadata for LiveBatchCoordinator registration
        self._active_wizard_data = {
            "experimental_group": group,
            "experiment_day": f"Dia_{day}",
            "subject_id": subject,
            "recording_duration_s": duration_s,
            "camera_index": camera_index,
            "is_batch_last_session": False,
        }

        # Extract animals_per_aquarium from project data
        animals_per_aquarium = project_data.get("animals_per_aquarium", 1)

        # v2.3.0: Build analysis_config with batch metadata for video registration
        analysis_config = {
            "group": group,
            "day": f"Dia_{day}",
            "subject_id": subject,
            "camera_index": camera_index,
        }

        # Delegate to LiveCameraService (unified system)
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=True,  # Projects always record
            animals_per_aquarium=animals_per_aquarium,
            use_external_preview=False,  # Use integrated canvas in Analysis tab
            analysis_config=analysis_config,
        )

        return success

    def __repr__(self) -> str:
        """Return string representation of LiveCameraSessionCoordinator."""
        return f"<LiveCameraSessionCoordinator(live_session={self.is_live_session_active()})>"

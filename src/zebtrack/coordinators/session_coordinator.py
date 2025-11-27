"""Session Coordinator - Phase 3 Consolidation.

Super coordinator for recording and live camera session management.

CONSOLIDATES (Phase 3 - Fase 3):
    - RecordingSessionOrchestrator (Sprint 26) - 761 lines
    - LiveCameraCoordinator (Sprint 4) - 678 lines
    - RecordingCoordinator (Sprint 4) - 466 lines

Total: ~1905 lines consolidated into this unified coordinator

This coordinator manages:
    - Recording session lifecycle (start/stop/external trigger)
    - Live camera analysis sessions
    - Arduino-triggered recording workflows
    - Live camera initialization and management
    - Timed session workflows
    - Session state tracking

Architecture:
    - Zero MainViewModel dependency
    - Pure dependency injection pattern
    - Delegates to RecordingService and LiveCameraService
    - Publishes events via EventBus
    - Updates StateManager for state tracking
"""

from __future__ import annotations

import datetime
import math
import os
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import structlog

from zebtrack.coordinators.base import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.aquarium_detector import AquariumDetector
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.core.state_manager import StateCategory
from zebtrack.io.camera import Camera
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.detector_service import DetectorService
    from zebtrack.core.live_camera_service import LiveCameraService
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.recording_service import RecordingService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.io.arduino_manager import ArduinoManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class SessionCoordinatorError(CoordinatorError):
    """Base exception for SessionCoordinator errors."""

    pass


# =============================================================================
# MAIN COORDINATOR
# =============================================================================


class SessionCoordinator(BaseCoordinator):
    """Super coordinator for recording and live camera session management.

    Phase 3 Consolidation - ALL session responsibilities:
    - Recording session workflows (manual/Arduino-triggered)
    - Live camera analysis sessions
    - Live project recording sessions
    - Session state management
    - Arduino coordination
    - Camera hardware management

    Consolidated Components:
        - RecordingSessionOrchestrator (Sprint 26)
        - LiveCameraCoordinator (Sprint 4)
        - RecordingCoordinator (Sprint 4)
    """

    def __init__(
        self,
        state_manager: StateManager,
        recording_service: RecordingService,
        live_camera_service: LiveCameraService,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        weight_manager: WeightManager,
        settings_obj: Settings,
        event_bus: EventBus | None = None,
        arduino_manager: ArduinoManager | None = None,
        # UI components (temporary - being phased out)
        root: Any = None,
        view: Any = None,
    ):
        """Initialize SessionCoordinator with pure dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            recording_service: RecordingService for recording operations
            live_camera_service: LiveCameraService for live camera operations
            project_manager: ProjectManager for project data and zones
            detector_service: DetectorService for detection configuration
            weight_manager: WeightManager for model weights
            settings_obj: Settings configuration object
            event_bus: EventBus for UI notifications (optional)
            arduino_manager: ArduinoManager for hardware control (optional)
            root: Tkinter root window (legacy, being phased out)
            view: GUI view instance (legacy, being phased out)

        Note:
            CRITICAL: NEVER pass MainViewModel. All dependencies must be explicit.
            The root and view parameters are temporary for gradual migration and will
            be removed in future sprints as UI callbacks move to pure event-based system.
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        # Core services
        self.recording_service = recording_service
        self.live_camera_service = live_camera_service
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.weight_manager = weight_manager
        self.settings = settings_obj
        self.arduino_manager = arduino_manager

        # UI components (temporary - being phased out)
        self.root = root
        self.view = view

        # Session state
        self._pending_external_trigger: dict | None = None
        self._active_live_session_id: str | None = None
        self.camera: Camera | None = None

        log.info(
            "session_coordinator.initialized",
            has_recording_service=recording_service is not None,
            has_live_camera_service=live_camera_service is not None,
            has_arduino=arduino_manager is not None,
        )

    def validate_dependencies(self) -> bool:
        """Validate that required dependencies are present.

        Returns:
            bool: True if all required dependencies are present

        Raises:
            CoordinatorValidationError: If required dependencies are missing
        """
        if self.recording_service is None:
            raise CoordinatorValidationError(
                "RecordingService is required but was None",
                context={
                    "coordinator": "SessionCoordinator",
                    "missing_dependency": "recording_service",
                },
            )
        if self.live_camera_service is None:
            raise CoordinatorValidationError(
                "LiveCameraService is required but was None",
                context={
                    "coordinator": "SessionCoordinator",
                    "missing_dependency": "live_camera_service",
                },
            )
        if self.project_manager is None:
            raise CoordinatorValidationError(
                "ProjectManager is required but was None",
                context={
                    "coordinator": "SessionCoordinator",
                    "missing_dependency": "project_manager",
                },
            )
        return True

    # =============================================================================
    # GROUP A: RECORDING SESSION MANAGEMENT (RecordingSessionOrchestrator +
    #          RecordingCoordinator)
    # =============================================================================

    def start_recording(
        self,
        day: int | None = None,
        group: str | None = None,
        cobaia: str | None = None,
        context: dict[str, Any] | None = None,
        project_data: dict[str, Any] | None = None,
        *,
        trigger_source: str = "manual",
        output_path: str | Path | None = None,
        experiment_id: str | None = None,
        duration: int | float | None = None,
    ) -> bool:
        """Start a recording session (live mode) with zone validation.

        Consolidated from RecordingSessionOrchestrator and RecordingCoordinator.

        Args:
            day: Day number (legacy parameter from RecordingSessionOrchestrator)
            group: Group identifier (legacy parameter)
            cobaia: Subject/animal identifier (legacy parameter)
            context: Recording context with session details (preferred)
            project_data: Project configuration dictionary
            trigger_source: Source of the recording trigger (manual/external)
            output_path: Recording destination when context is omitted
            experiment_id: Experiment identifier when context is omitted
            duration: Optional recording duration (seconds)

        Returns:
            True if recording started successfully, False otherwise

        Raises:
            SessionCoordinatorError: If recording cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot start recording - dependencies invalid",
                context={"trigger_source": trigger_source},
            )

        log.info("session_coordinator.recording.start", trigger_source=trigger_source)

        # Clear any pending external trigger
        self._clear_external_trigger_wait()

        # Ensure zones are defined before recording
        if not self._ensure_zones_before_recording():
            return False

        # Build context from legacy parameters if needed
        if context is None and day is not None:
            # Legacy code path from RecordingSessionOrchestrator
            if not all((day, group, cobaia)):
                if not self.view:
                    raise SessionCoordinatorError(
                        "Cannot request recording details without view",
                        coordinator="SessionCoordinator",
                    )
                details = self.view.ask_recording_details_unified()
                if not details:
                    log.warning("session_coordinator.recording.cancelled_by_user")
                    return False
                day, group, cobaia = details["day"], details["group"], details["cobaia"]

            # Save session details
            self.project_manager.save_last_session_details(day, group)

            # Create output folder
            folder_name = f"D{day}_G{group}_S{cobaia}"
            output_folder = os.path.join(self.project_manager.project_path, folder_name)
            os.makedirs(output_folder, exist_ok=True)

            # Setup Arduino if needed
            project_data = project_data or self.project_manager.project_data or {}
            arduino_enabled = bool(project_data.get("use_arduino"))

            # Build recording context
            context = {
                "day": day,
                "group": group,
                "cobaia": cobaia,
                "folder_name": folder_name,
                "output_folder": output_folder,
                "arduino_enabled": arduino_enabled,
                "arduino_port": (project_data.get("arduino_port") or "").strip(),
            }

            # Inject camera dimensions into context
            camera_width = getattr(self.view.camera, "actual_width", None) if self.view else None
            camera_height = getattr(self.view.camera, "actual_height", None) if self.view else None
            context["camera_width"] = camera_width
            context["camera_height"] = camera_height

            # Handle external trigger (may wait for signal)
            if self._handle_external_trigger(context, arduino_enabled):
                return False  # Waiting for trigger

        elif context is None:
            # New code path from RecordingCoordinator
            if output_path is None:
                raise ValueError("output_path is required when context is not provided")
            if experiment_id is None:
                raise ValueError("experiment_id is required when context is not provided")

            inferred_folder = experiment_id or Path(str(output_path)).stem
            context = {
                "output_folder": str(output_path),
                "folder_name": inferred_folder,
                "experiment_id": experiment_id,
                "duration": duration,
            }

        # Delegate to RecordingService
        project_data = project_data or self.project_manager.project_data or {}
        self._schedule_recording(context, project_data, trigger_source=trigger_source)

        return True

    def stop_recording(self) -> bool:
        """Stop the current recording session.

        Consolidated from RecordingSessionOrchestrator and RecordingCoordinator.

        Returns:
            True if recording stopped successfully, False otherwise
        """
        log.info("session_coordinator.recording.stop")

        # Clear any pending external trigger
        if self._pending_external_trigger:
            self._clear_external_trigger_wait()

        try:
            # Check if recording
            recording_state = self.state_manager.get_recording_state()
            if not recording_state or not recording_state.is_recording:
                log.warning("session_coordinator.stop_recording.not_recording")
                return False

            # Delegate to RecordingService
            self.recording_service.stop_session()

            # Update state
            self._update_state(
                StateCategory.RECORDING,
                is_recording=False,
                output_path=None,
                experiment_id=None,
                duration=None,
            )

            # Publish events
            self._publish_event("RECORDING_STOPPED", {})
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
                )
                self.event_bus.publish_event(
                    Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
                )

            log.info("session_coordinator.stop_recording.success")
            return True

        except Exception as e:
            log.error(
                "session_coordinator.stop_recording.failed",
                error=str(e),
                exc_info=True,
            )
            return False

    def is_recording(self) -> bool:
        """Check if a recording is currently in progress.

        Returns:
            True if recording, False otherwise
        """
        recording_state = self.state_manager.get_recording_state()
        return recording_state is not None and recording_state.is_recording

    def get_recording_info(self) -> dict[str, Any] | None:
        """Get information about current recording session.

        Returns:
            dict with recording info, or None if not recording
        """
        recording_state = self.state_manager.get_recording_state()

        if not recording_state or not recording_state.is_recording:
            return None

        return {
            "is_recording": recording_state.is_recording,
            "output_path": getattr(recording_state, "output_path", None),
            "experiment_id": getattr(recording_state, "experiment_id", None),
            "duration": getattr(recording_state, "duration", None),
        }

    # =============================================================================
    # GROUP B: EXTERNAL TRIGGER HANDLING (RecordingSessionOrchestrator)
    # =============================================================================

    def _handle_external_trigger(self, context: dict, arduino_enabled: bool) -> bool:
        """Handle external trigger setup for recording.

        Args:
            context: Recording context with session details
            arduino_enabled: Whether Arduino is available

        Returns:
            bool: True if waiting for trigger (stop processing), False if proceed
        """
        project_data = self.project_manager.project_data or {}
        external_trigger_requested = bool(project_data.get("external_trigger_mode"))

        if external_trigger_requested and not arduino_enabled:
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Trigger Externo Indisponível",
                        "message": "O modo de trigger externo exige um Arduino configurado.",
                    },
                )
            return True

        if external_trigger_requested and arduino_enabled:
            self._pending_external_trigger = context
            port = context.get("arduino_port", "")
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
                    {
                        "folder_name": context["folder_name"],
                        "day": context.get("day"),
                        "group": context.get("group"),
                        "cobaia": context.get("cobaia"),
                        "port": port,
                    },
                )
                self.event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": f"Aguardando sinal externo... (porta {port})"},
                )
            return True

        return False

    def trigger_recording(self, event_code: int | None = None):
        """Trigger a pending recording session from external Arduino event.

        Args:
            event_code: Optional Arduino event code that triggered recording.
        """
        if not self._pending_external_trigger:
            log.warning("session_coordinator.external_trigger.no_pending", code=event_code)
            return

        context = self._pending_external_trigger
        self._pending_external_trigger = None

        if self.event_bus:
            self.event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
        project_data = self.project_manager.project_data or {}
        self._schedule_recording(context, project_data, trigger_source="external")

    def on_arduino_event(self, event_code: int):
        """Handle Arduino event signals for external trigger control.

        Args:
            event_code: Integer code from Arduino (1 for start, 0 for stop).
        """
        log.info("session_coordinator.arduino.event_received", code=event_code)

        if event_code == 1:
            if self._pending_external_trigger:
                log.info("session_coordinator.arduino.triggering_recording")
                self.trigger_recording(event_code)
            else:
                log.warning("session_coordinator.arduino.event.unexpected_start")
        elif event_code == 0:
            if self.is_recording() or self._pending_external_trigger:
                log.info("session_coordinator.arduino.stopping_recording")
                self.stop_recording()
        else:
            log.info("session_coordinator.arduino.event.ignored", code=event_code)

    def _clear_external_trigger_wait(self):
        """Clear external trigger wait state."""
        if not self._pending_external_trigger:
            return

        self._pending_external_trigger = None
        if self.event_bus:
            self.event_bus.publish_event(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE)
            self.event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE, {"button_name": "start_rec", "state": "normal"}
            )
            self.event_bus.publish_event(
                Events.UI_UPDATE_BUTTON_STATE, {"button_name": "stop_rec", "state": "disabled"}
            )
            self.event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        """Schedule a recording session via RecordingService.

        Args:
            context: Recording context
            project_data: Project configuration
            trigger_source: Source of trigger (manual/external)
        """
        # Update state optimistically
        effective_output = context.get("output_folder")
        effective_experiment = context.get("experiment_id") or context.get("folder_name")
        effective_duration = context.get("duration")

        pre_state_update: dict[str, Any] = {
            "is_recording": True,
            "output_path": str(effective_output) if effective_output else None,
            "experiment_id": effective_experiment,
        }
        if effective_duration is not None:
            pre_state_update["duration"] = effective_duration

        self._update_state(StateCategory.RECORDING, **pre_state_update)

        # Delegate to service
        self.recording_service.schedule_recording(
            context=context,
            project_data=project_data,
            trigger_source=trigger_source,
        )

        # Publish event
        self._publish_event(
            "RECORDING_STARTED",
            {
                "folder_name": context.get("folder_name"),
                "output_folder": context.get("output_folder"),
                "trigger_source": trigger_source,
                "duration": effective_duration,
            },
        )

    # =============================================================================
    # GROUP C: LIVE CAMERA SESSION MANAGEMENT (LiveCameraCoordinator)
    # =============================================================================

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

        Returns:
            True if session started successfully, False otherwise

        Raises:
            SessionCoordinatorError: If session cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Dependencies not valid",
                coordinator="SessionCoordinator",
                operation="start_live_session",
            )

        # Generate session ID if not provided
        if experiment_id is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            experiment_id = f"live_session_{timestamp}"

        log.info(
            "session_coordinator.start_live_session.begin",
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
        )

        try:
            # Check if session already active
            if self.is_live_session_active():
                raise SessionCoordinatorError(
                    "Live session already active",
                    coordinator="SessionCoordinator",
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
                self._active_live_session_id = None
                self._update_state(
                    StateCategory.PROCESSING,
                    is_live_session_active=False,
                )
                raise SessionCoordinatorError(
                    "LiveCameraService failed to start session",
                    coordinator="SessionCoordinator",
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
                "session_coordinator.start_live_session.success",
                experiment_id=experiment_id,
            )

            return True

        except ValueError as e:
            log.error(
                "session_coordinator.start_live_session.validation_error",
                error=str(e),
            )
            raise SessionCoordinatorError(
                f"Validation error: {e!s}",
                coordinator="SessionCoordinator",
                operation="start_live_session",
            ) from e

        except Exception as e:
            log.error(
                "session_coordinator.start_live_session.failed",
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

            raise SessionCoordinatorError(
                f"Failed to start live session: {e!s}",
                coordinator="SessionCoordinator",
                operation="start_live_session",
                experiment_id=experiment_id,
            ) from e

    def stop_live_session(self) -> bool:
        """Stop the current live camera session.

        Returns:
            True if session stopped successfully, False otherwise
        """
        log.info("session_coordinator.stop_live_session.begin")

        try:
            # Check if session active
            if not self.is_live_session_active():
                log.warning("session_coordinator.stop_live_session.no_active_session")
                return False

            # Delegate to service
            success = self.live_camera_service.stop_session()

            # Update state
            self._active_live_session_id = None
            self._update_state(
                StateCategory.PROCESSING,
                is_live_session_active=False,
            )

            # Publish event
            self._publish_event("LIVE_SESSION_STOPPED", {})

            log.info(
                "session_coordinator.stop_live_session.success",
                success=success,
            )

            return success

        except Exception as e:
            log.error(
                "session_coordinator.stop_live_session.failed",
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
    # GROUP D: LIVE CAMERA ANALYSIS (RecordingSessionOrchestrator)
    # =============================================================================

    def start_live_camera_analysis(self, camera_index: int | None = None):
        """Start a live camera analysis session (single video workflow).

        Delegates to LiveCameraService for thread management and coordination.

        Args:
            camera_index: Optional camera index. If provided, uses this camera directly
                         without showing the configuration dialog. If None, shows dialog.
        """
        log.info("session_coordinator.live_analysis.start", camera_index=camera_index)

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
                "record_video": True
            }
        else:
            # Show configuration dialog
            if not self.root:
                log.error("session_coordinator.live_analysis.no_root")
                return

            from zebtrack.ui.dialogs import LiveAnalysisDialog

            dialog = LiveAnalysisDialog(self.root, settings_obj=self.settings)

            if not dialog.result:
                log.info("session_coordinator.live_analysis.cancelled")
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
        log.info("session_coordinator.live_analysis.start_from_config", config_keys=list(config.keys()))

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

        # ✅ FIX: Update settings with dialog configuration BEFORE starting session
        # This ensures LiveCameraService uses the correct model/weights
        animal_method = config.get("animal_method")
        aquarium_method = config.get("aquarium_method")
        use_openvino = config.get("use_openvino")
        use_single_subject_tracker = config.get("use_single_subject_tracker")

        if animal_method is not None:
            self.settings.model_selection.animal_method = animal_method
            log.info("session_coordinator.live_analysis.animal_method_updated", value=animal_method)

        if aquarium_method is not None:
            self.settings.model_selection.aquarium_method = aquarium_method
            log.info("session_coordinator.live_analysis.aquarium_method_updated", value=aquarium_method)

        if use_openvino is not None:
            self.settings.model_selection.use_openvino = use_openvino
            log.info("session_coordinator.live_analysis.use_openvino_updated", value=use_openvino)

        if use_single_subject_tracker is not None:
            # Update detector service if already initialized
            if self.detector_service and self.detector_service.detector:
                self.detector_service.detector.set_single_subject_mode(use_single_subject_tracker)
                log.info(
                    "session_coordinator.live_analysis.single_subject_updated",
                    value=use_single_subject_tracker,
                )

        log.info(
            "session_coordinator.live_analysis.extracted_config",
            camera_index=camera_index,
            duration_s=duration_s,
            analysis_interval=analysis_interval_frames,
            display_interval=display_interval_frames,
            record_video=record_video,
            animal_method=animal_method,
            use_openvino=use_openvino,
        )

        # ✅ CHANGED: Do NOT create default arena here anymore
        # LiveCameraService will handle aquarium detection phase:
        #   1. Try to detect aquarium (class 0) for ~30 frames
        #   2. If detected: use aquarium bbox as arena
        #   3. If not detected: create fallback arena (2x larger than old default)
        # This ensures arena is optimally sized for the actual aquarium

        zone_data = self.project_manager.get_zone_data()
        log.info(
            "session_coordinator.live_analysis.arena_check",
            has_predefined_arena=bool(zone_data and zone_data.polygon),
        )

        # Extract animals_per_aquarium for tracking configuration
        animals_per_aquarium = config.get("animals_per_aquarium", 1)
        log.info(
            "session_coordinator.live_analysis.tracking_config",
            animals_per_aquarium=animals_per_aquarium,
        )

        # Delegate to LiveCameraService
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=record_video,
            animals_per_aquarium=animals_per_aquarium,
        )

        # UI feedback
        if success and self.event_bus:
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
            self.event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro na Análise",
                    "message": f"Falha ao iniciar análise de câmera {camera_index}.",
                },
            )

        return success

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
            log.error("session_coordinator.start_live_project_session.wrong_project_type")
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
            "session_coordinator.live_project_session.start",
            project=self.project_manager.get_project_name(),
            experiment_id=experiment_id,
            camera_index=camera_index,
            duration_s=duration_s,
        )

        # Delegate to LiveCameraService (unified system)
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=True,  # Projects always record
        )

        return success

    # =============================================================================
    # GROUP E: LIVE CALIBRATION (RecordingSessionOrchestrator)
    # =============================================================================

    def run_live_calibration(self, temp_aquarium_method: str | None = None):
        """Record a short clip from the live camera and runs aquarium detection.

        Args:
            temp_aquarium_method: Temporary override for aquarium detection method
                ('det' or 'seg'). If None, uses global self.settings.
        """
        log.info("session_coordinator.live_calibration.start")

        if not self.view or not self.view.camera or not self.view.camera.is_opened():
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro", "message": "A câmera não está disponível ou aberta."},
                )
            return

        temp_video_path = None

        # Publish processing mode change (requires integration with ProcessingCoordinator)
        if self.event_bus:
            self.event_bus.publish_event(
                "PROCESSING_MODE_CHANGED",
                {"mode": ProcessingMode.SINGLE_SUBJECT, "source": "calibration.live.start"},
            )

        try:
            # 1. Create a temporary file for the calibration video
            temp_video_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_video_path = temp_video_file.name
            temp_video_file.close()

            # 2. Record a short clip
            w, h = self.view.camera.actual_width, self.view.camera.actual_height
            fps = self.settings.video_processing.fps
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))

            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Calibrando... Gravando um pequeno clipe."},
                )

            start_time = time.time()
            while time.time() - start_time < 5:  # Record for 5 seconds
                ret, frame = self.view.camera.get_frame()
                if not ret:
                    break
                writer.write(frame)
            writer.release()

            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Calibração: Analisando o clipe..."},
                )

            # 3. Run detection on the clip
            aquarium_method = temp_aquarium_method or self.settings.model_selection.aquarium_method
            model_path = self.weight_manager.get_weight_path_by_method(aquarium_method, "aquarium")

            if not model_path:
                if self.event_bus:
                    self.event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Erro",
                            "message": f"Não foi possível encontrar um modelo {aquarium_method} "
                            "para detecção do aquário.",
                        },
                    )
                return

            detector = AquariumDetector(model_path=model_path, mode=aquarium_method)
            polygons = detector.detect_aquariums(temp_video_path)

            if not polygons:
                if self.event_bus:
                    self.event_bus.publish_event(
                        Events.UI_SHOW_WARNING,
                        {
                            "title": "Detecção Falhou",
                            "message": "Nenhum aquário foi detectado. Por favor, desenhe a área manualmente.",
                        },
                    )
                return

            main_polygon = polygons[0]
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SETUP_INTERACTIVE_POLYGON, {"polygon": main_polygon}
                )

        except Exception as e:
            log.error("session_coordinator.live_calibration.error", exc_info=True)
            if self.event_bus:
                self.event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro na Calibração", "message": f"Ocorreu um erro: {e}"},
                )
        finally:
            # 4. Clean up the temporary file
            if temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)

            if self.event_bus:
                self.event_bus.publish_event(
                    "PROCESSING_MODE_RESTORE",
                    {"source": "calibration.live.complete"},
                )
                self.event_bus.publish_event(Events.UI_SET_STATUS, {"message": "Pronto."})

    # =============================================================================
    # GROUP F: HELPER METHODS (Private)
    # =============================================================================

    def _ensure_zones_before_recording(self) -> bool:
        """Ensure project zones are defined (live or non-live) before starting recording.

        Returns:
            True if recording can proceed, False if it should be cancelled.
        """
        if not self.project_manager.project_path:
            return True

        project_type = self.project_manager.get_project_type()
        zone_data = self.project_manager.get_zone_data()

        if project_type == "live" and (not zone_data or not zone_data.polygon):
            log.info("session_coordinator.recording.live_zone_validation.start")

            if not self.view:
                return False

            # For Live projects, prompt for automatic calibration
            response = self.view.ask_ok_cancel(
                "Calibração Necessária",
                "Deseja fazer calibração automática do aquário?\n"
                "(Recomendado para projetos ao vivo)",
            )

            if response:
                # Run auto-calibration
                self.run_live_calibration()

                # Check if calibration was successful
                zone_data = self.project_manager.get_zone_data()
                if not zone_data or not zone_data.polygon:
                    if self.event_bus:
                        self.event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {
                                "title": "Calibração Falhou",
                                "message": "Não foi possível detectar o aquário.\nPor favor, desenhe manualmente.",
                            },
                        )
                        self.event_bus.publish_event(
                            Events.UI_SELECT_TAB, {"tab_name": "zone_tab"}
                        )
                    return False
                else:
                    log.info("session_coordinator.recording.live_zone_validation.success")
            else:
                # User declined calibration
                if self.event_bus:
                    self.event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {
                            "title": "Zonas Obrigatórias",
                            "message": "Projetos ao vivo requerem definição de zonas.\n"
                            "Defina o polígono principal antes de gravar.",
                        },
                    )
                return False

        elif not zone_data or not zone_data.polygon:
            # Generic validation for non-Live projects
            log.warning("session_coordinator.recording.no_main_arena")

            if not self.view:
                return False

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É recomendado definir a arena antes de iniciar gravação.\n"
                "Deseja definir agora?",
            )

            if response:
                if self.event_bus:
                    self.event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                    self.event_bus.publish_event(
                        Events.UI_SHOW_INFO,
                        {
                            "title": "Defina a Arena Principal",
                            "message": "Por favor:\n"
                            "1. Use a câmera ao vivo para calibrar\n"
                            "2. Use 'Detectar Aquário (Auto)' ou\n"
                            "3. Desenhe manualmente o polígono principal\n"
                            "4. Depois volte para iniciar a gravação",
                        },
                    )
                return False
            else:
                # Continue without arena defined
                if not self.view.ask_ok_cancel(
                    "Continuar Sem Arena?",
                    "Deseja continuar a gravação sem arena definida?\n"
                    "(A arena padrão será o frame completo)",
                ):
                    log.info("session_coordinator.recording.cancelled_no_arena")
                    return False

                log.info("session_coordinator.recording.proceeding_without_arena")

        return True

    def __repr__(self) -> str:
        """Return string representation of SessionCoordinator."""
        return (
            f"<SessionCoordinator("
            f"recording={self.is_recording()}, "
            f"live_session={self.is_live_session_active()}, "
            f"has_arduino={self.arduino_manager is not None}"
            f")>"
        )

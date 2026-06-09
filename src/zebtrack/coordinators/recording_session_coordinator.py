"""Recording Session Coordinator - Phase 4.7 Decomposition.

Extracted from SessionCoordinator (Phase 3).

Responsibilities:
    - Recording session lifecycle (start/stop/info)
    - External Arduino trigger handling
    - Recording scheduling (via RecordingService or LiveCameraService)
    - Zone confirmation event handling for deferred recordings

Architecture:
    - Zero MainViewModel dependency
    - Pure dependency injection pattern
    - Delegates to RecordingService and LiveCameraService
    - Publishes events via EventBus
    - Updates StateManager for state tracking
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators import live_session_ui_prep
from zebtrack.coordinators.base_coordinator import (
    BaseCoordinator,
    CoordinatorError,
    CoordinatorValidationError,
)
from zebtrack.core.state_manager import StateCategory
from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.recording.live_camera_service import LiveCameraService
    from zebtrack.core.recording.recording_service import RecordingService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.io.arduino_manager import ArduinoManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


# =============================================================================
# EXCEPTIONS
# =============================================================================


class RecordingSessionCoordinatorError(CoordinatorError):
    """Base exception for RecordingSessionCoordinator errors."""

    pass


# =============================================================================
# MAIN COORDINATOR
# =============================================================================


class RecordingSessionCoordinator(BaseCoordinator):
    """Coordinator for recording session lifecycle management.

    Phase 4.7 Decomposition — extracted from SessionCoordinator.

    Responsibilities:
        - Start/stop recording sessions (manual and external trigger)
        - Arduino event handling (trigger_recording, on_arduino_event)
        - Recording scheduling via RecordingService or LiveCameraService
        - Zone confirmation event handling to resume deferred recordings
    """

    def __init__(
        self,
        state_manager: StateManager,
        recording_service: RecordingService,
        live_camera_service: LiveCameraService,
        project_manager: ProjectManager,
        settings_obj: Settings,
        live_calibration_coordinator: LiveCalibrationCoordinator,
        event_bus: EventBusV2 | None = None,
        arduino_manager: ArduinoManager | None = None,
        # UI components (temporary - being phased out)
        root: Any = None,
        view: Any = None,
    ):
        """Initialize RecordingSessionCoordinator with pure dependency injection.

        Args:
            state_manager: StateManager for centralized state tracking
            recording_service: RecordingService for recording operations
            live_camera_service: LiveCameraService for live analysis dispatch
            project_manager: ProjectManager for project data and zones
            settings_obj: Settings configuration object
            live_calibration_coordinator: For zone validation before recording
            event_bus: EventBus for UI notifications (optional)
            arduino_manager: ArduinoManager for hardware control (optional)
            root: Tkinter root window (legacy, being phased out)
            view: GUI view instance (legacy, being phased out)

        Note:
            CRITICAL: NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager=state_manager, event_bus=event_bus)

        # Core services
        self.recording_service = recording_service
        self.live_camera_service = live_camera_service
        self.project_manager = project_manager
        self.settings = settings_obj
        self.live_calibration_coordinator = live_calibration_coordinator
        self.arduino_manager = arduino_manager

        # UI components (temporary - being phased out)
        self.root = root
        self.view = view

        # Session state
        self._pending_external_trigger: dict | None = None
        self._pending_recording_context: dict[str, Any] | None = None
        self._pending_recording_trigger_source: str | None = None
        self._pending_recording_project_data: dict[str, Any] | None = None

        log.info(
            "recording_session_coordinator.initialized",
            has_recording_service=recording_service is not None,
            has_live_camera_service=live_camera_service is not None,
            has_arduino=arduino_manager is not None,
        )

        if self.event_bus:
            self._setup_event_listeners()

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
                    "coordinator": "RecordingSessionCoordinator",
                    "missing_dependency": "recording_service",
                },
            )
        if self.live_camera_service is None:
            raise CoordinatorValidationError(
                "LiveCameraService is required but was None",
                context={
                    "coordinator": "RecordingSessionCoordinator",
                    "missing_dependency": "live_camera_service",
                },
            )
        if self.project_manager is None:
            raise CoordinatorValidationError(
                "ProjectManager is required but was None",
                context={
                    "coordinator": "RecordingSessionCoordinator",
                    "missing_dependency": "project_manager",
                },
            )
        return True

    # =============================================================================
    # RECORDING SESSION LIFECYCLE
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
        zones_validated: bool = False,
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
            zones_validated: If True, skip zone validation

        Returns:
            True if recording started successfully, False otherwise

        Raises:
            RecordingSessionCoordinatorError: If recording cannot be started
        """
        # Validate dependencies
        if not self.validate_dependencies():
            raise CoordinatorValidationError(
                "Cannot start recording - dependencies invalid",
                context={"trigger_source": trigger_source},
            )

        log.info("recording_session_coordinator.recording.start", trigger_source=trigger_source)

        # Clear any pending external trigger
        self._clear_external_trigger_wait()

        # Build context from legacy parameters if needed (BEFORE zone validation)
        if context is None and (day is not None or output_path is None):
            # Legacy code path from RecordingSessionOrchestrator
            # OR called from UI without any parameters - need to ask user
            if not all((day, group, cobaia)):
                if not self.view:
                    raise RecordingSessionCoordinatorError(
                        "Cannot request recording details without view",
                        coordinator="RecordingSessionCoordinator",
                    )
                details = self.view.ask_recording_details_unified()
                if not details:
                    log.warning("recording_session_coordinator.recording.cancelled_by_user")
                    return False
                day, group, cobaia = details["day"], details["group"], details["cobaia"]

            # Save session details if valid
            if day is not None and group is not None:
                self.project_manager.save_last_session_details(int(day), str(group))

            # Create output folder
            folder_name = f"D{day}_G{group}_S{cobaia}"
            output_folder = os.path.join(str(self.project_manager.project_path or ""), folder_name)
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

            # Inject camera dimensions AND index into context (if camera available)
            camera_width = None
            camera_height = None
            camera_index = getattr(self.settings.camera, "index", 0)  # Default from settings

            camera = self.live_calibration_coordinator.camera
            if camera and hasattr(camera, "is_open") and camera.is_open:
                camera_width = getattr(camera, "actual_width", None)
                camera_height = getattr(camera, "actual_height", None)
                # Prefer camera's actual index if available
                if hasattr(camera, "index"):
                    camera_index = camera.index

            context["camera_width"] = camera_width
            context["camera_height"] = camera_height

            # Use project camera index if available, otherwise fallback to detected/settings
            project_camera_index = project_data.get("camera_index") if project_data else None
            if project_camera_index is not None:
                context["camera_index"] = int(project_camera_index)
            else:
                context["camera_index"] = camera_index

            # Handle external trigger (may wait for signal)
            if self._handle_external_trigger(context, arduino_enabled):
                return False  # Waiting for trigger

        elif context is None:
            # Special code path: explicit output_path provided programmatically
            # (not from UI button click)
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

        # Save context for potential zone confirmation workflow
        self._pending_recording_context = context
        self._pending_recording_project_data = (
            project_data or self.project_manager.project_data or {}
        )
        self._pending_recording_trigger_source = trigger_source

        # Ensure zones are defined before recording
        calibrator = self.live_calibration_coordinator
        if not zones_validated and not calibrator.ensure_zones_before_recording():
            # Check if we're waiting for zone confirmation
            if calibrator.pending_zone_confirmation:
                # Don't clear context - will be resumed later
                log.info("recording_session_coordinator.recording.waiting_for_zones")
                return False
            else:
                # User cancelled or error - clear context
                self._clear_pending_recording_context()
                return False

        # Increment session count after successful zone validation
        self.live_calibration_coordinator.increment_session_count()

        # Delegate to RecordingService
        self._schedule_recording(
            context, self._pending_recording_project_data, trigger_source=trigger_source
        )

        # Clear context after successful start
        self._clear_pending_recording_context()

        # FIX: Navigate to Analysis View to show recording progress
        if self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW,
                    data=payloads.EmptyPayload(),
                )
            )
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                    data=payloads.AnalysisTaskStatusPayload(step="Iniciando gravação..."),
                )
            )

        return True

    def _clear_pending_recording_context(self):
        """Clear pending recording context."""
        self._pending_recording_context = None
        self._pending_recording_project_data = None
        self._pending_recording_trigger_source = None

    def stop_recording(self) -> bool:
        """Stop the current recording session.

        Returns:
            True if recording stopped successfully, False otherwise
        """
        log.info("recording_session_coordinator.recording.stop")

        # Clear any pending external trigger
        if self._pending_external_trigger:
            self._clear_external_trigger_wait()

        try:
            # Check if recording
            recording_state = self.state_manager.get_recording_state()
            if not recording_state or not recording_state.is_recording:
                log.warning("recording_session_coordinator.stop_recording.not_recording")
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

            # Invalidate the VideoManager scan cache so the next refresh
            # picks up the newly written 1_ProcessingArea_*.parquet for the
            # just-stopped recording. Without this, has_arena stays False for
            # up to TTL (30 s) and "Controle Principal" shows trajectory ✓
            # but arena ✗ — audit Erro 3 (2026-05-25).
            try:
                from zebtrack.core.project.video_manager import VideoManager

                VideoManager.clear_scan_cache()
            except Exception:
                log.debug(
                    "recording_session_coordinator.scan_cache_invalidate.failed",
                    exc_info=True,
                )

            # Publish events
            self._publish_event(UIEvents.RECORDING_STOPPED, payloads.EmptyPayload())
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_UPDATE_BUTTON_STATE,
                        data=payloads.UpdateButtonStatePayload(
                            button_name="start_rec", state="normal"
                        ),
                    )
                )
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_UPDATE_BUTTON_STATE,
                        data=payloads.UpdateButtonStatePayload(
                            button_name="stop_rec", state="disabled"
                        ),
                    )
                )

            log.info("recording_session_coordinator.stop_recording.success")
            return True

        except Exception as e:  # except Exception justified: graceful stop must not crash
            log.error(
                "recording_session_coordinator.stop_recording.failed",
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
    # EXTERNAL TRIGGER HANDLING
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
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.ErrorOccurredPayload(
                            title="Trigger Externo Indisponível",
                            message="O modo de trigger externo exige um Arduino configurado.",
                        ),
                    )
                )
            return True

        if external_trigger_requested and arduino_enabled:
            self._pending_external_trigger = context
            port = context.get("arduino_port", "")
            if self.event_bus:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
                        data=payloads.ExternalTriggerNoticePayload(
                            folder_name=context["folder_name"],
                            day=context.get("day"),
                            group=context.get("group"),
                            cobaia=context.get("cobaia"),
                            port=port,
                        ),
                    )
                )
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SET_STATUS,
                        data=payloads.StatusPayload(
                            message=f"Aguardando sinal externo... (porta {port})"
                        ),
                    )
                )
            return True

        return False

    def trigger_recording(self, event_code: int | None = None):
        """Trigger a pending recording session from external Arduino event.

        Args:
            event_code: Optional Arduino event code that triggered recording.
        """
        if not self._pending_external_trigger:
            log.warning(
                "recording_session_coordinator.external_trigger.no_pending", code=event_code
            )
            return

        context = self._pending_external_trigger
        self._pending_external_trigger = None

        if self.event_bus:
            self.event_bus.publish(Event(type=UIEvents.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE))
        project_data = self.project_manager.project_data or {}
        self._schedule_recording(context, project_data, trigger_source="external")

    def on_arduino_event(self, event_code: int):
        """Handle Arduino event signals for external trigger control.

        Args:
            event_code: Integer code from Arduino (1 for start, 0 for stop).
        """
        log.info("recording_session_coordinator.arduino.event_received", code=event_code)

        if event_code == 1:
            if self._pending_external_trigger:
                log.info("recording_session_coordinator.arduino.triggering_recording")
                self.trigger_recording(event_code)
            else:
                log.warning("recording_session_coordinator.arduino.event.unexpected_start")
        elif event_code == 0:
            if self.is_recording() or self._pending_external_trigger:
                log.info("recording_session_coordinator.arduino.stopping_recording")
                self.stop_recording()
        else:
            log.info("recording_session_coordinator.arduino.event.ignored", code=event_code)

    def _clear_external_trigger_wait(self):
        """Clear external trigger wait state."""
        if not self._pending_external_trigger:
            return

        self._pending_external_trigger = None
        if self.event_bus:
            self.event_bus.publish(Event(type=UIEvents.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE))
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_BUTTON_STATE,
                    data=payloads.UpdateButtonStatePayload(button_name="start_rec", state="normal"),
                )
            )
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_BUTTON_STATE,
                    data=payloads.UpdateButtonStatePayload(
                        button_name="stop_rec", state="disabled"
                    ),
                )
            )
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SET_STATUS,
                    data=payloads.StatusPayload(message="Pronto."),
                )
            )

    # =============================================================================
    # RECORDING SCHEDULING
    # =============================================================================

    def _schedule_recording(
        self,
        context: dict,
        project_data: dict,
        *,
        trigger_source: str,
    ) -> None:
        """Schedule a recording session via RecordingService OR LiveCameraService.

        Args:
            context: Recording context
            project_data: Project configuration
            trigger_source: Source of trigger (manual/external)
        """
        # Check if this should be a Live Analysis session (Smart Recording)
        if context.get("is_live_analysis"):
            log.info("recording_session_coordinator.schedule.dispatching_to_live_camera")

            # Extract parameters for LiveCameraService
            camera_index = context.get("camera_index", 0)
            # Duration: use context duration (if set) or project default
            duration_s = context.get("duration")
            if duration_s is None:
                duration_s = float(project_data.get("recording_duration_s", 300))

            # Experiment ID
            experiment_id = context.get("experiment_id")
            if not experiment_id:
                # Construct from folder name components
                experiment_id = (
                    f"{context.get('day', 'D')}_"
                    f"{context.get('group', 'G')}_"
                    f"{context.get('cobaia', 'S')}"
                )

            output_folder = context.get("output_folder")

            # Other settings
            analysis_interval = int(project_data.get("analysis_interval_frames", 1))

            # v2.3.1: Build analysis_config with batch metadata for video registration
            analysis_config = {
                "group": context.get("group"),
                "day": context.get("day"),
                "subject_id": context.get("cobaia"),
                "camera_index": camera_index,
            }

            # Prepara a aba "Análise" (zera contadores, re-inscreve o canvas e
            # religa o modo de análise) ANTES de iniciar a sessão — mesmo
            # tratamento dos 3 entrypoints do LiveCameraSessionCoordinator.
            # Este despacho usa o canvas integrado (use_external_preview=False),
            # então sem a preparação a 2ª gravação recebia os frames mas o
            # preview ficava congelado (canvas desinscrito no stop anterior e
            # analysis_active desligado pela pós-análise).
            live_session_ui_prep.prepare_analysis_tab_for_live_session(self.view, self.root)

            # Delegate to LiveCameraService
            success = self.live_camera_service.start_session(
                camera_index=camera_index,
                duration_s=duration_s,
                experiment_id=experiment_id,
                analysis_interval_frames=analysis_interval,
                display_interval_frames=1,  # Default
                record_video=True,
                output_base_dir=output_folder,
                animals_per_aquarium=1,
                use_external_preview=False,  # Use integrated canvas in Analysis tab
                analysis_config=analysis_config,
            )

            if success:
                # Update state to RECORDING
                self._update_state(
                    StateCategory.RECORDING,
                    is_recording=True,
                    output_path=output_folder,
                    experiment_id=experiment_id,
                    duration=duration_s,
                )
                # Publish event
                self._publish_event(
                    UIEvents.RECORDING_STARTED,
                    {
                        "folder_name": context.get("folder_name"),
                        "output_folder": output_folder,
                        "trigger_source": trigger_source,
                        "mode": "live_analysis",
                    },
                )

                # FIX Bug 3: Enable cancel button in integrated canvas mode
                if self.view and hasattr(self.view, "show_progress_bar"):
                    if self.root:
                        self.root.after(0, self.view.show_progress_bar)
                        log.info(
                            "recording_session_coordinator.schedule.cancel_button_enabled",
                            via="show_progress_bar",
                        )
                    else:
                        self.view.show_progress_bar()

            return

        # --- FALLBACK TO DUMB RECORDING (RecordingService) ---

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
            UIEvents.RECORDING_STARTED,
            {
                "folder_name": context.get("folder_name"),
                "output_folder": context.get("output_folder"),
                "trigger_source": trigger_source,
                "duration": effective_duration,
            },
        )

    # =============================================================================
    # EVENT LISTENERS
    # =============================================================================

    def _setup_event_listeners(self):
        """Setup event listeners for coordination."""
        if not self.event_bus:
            return

        # Listen for zone saving events to resume pending recording
        self.event_bus.subscribe(UIEvents.ZONE_SAVE_MANUAL_ARENA, self._on_zone_saved)
        self.event_bus.subscribe(UIEvents.ZONE_SET_ARENA_POLYGON, self._on_zone_saved)
        self.event_bus.subscribe(UIEvents.ZONE_SAVE_ARENA, self._on_zone_saved)

    def _on_zone_saved(self, data: payloads.EventPayload | None = None) -> None:
        """Handle zone saved event to resume pending recording."""
        if not self.live_calibration_coordinator.pending_zone_confirmation:
            return

        # Só retoma (e só reseta a flag COMPARTILHADA) quando ESTE coordinator
        # realmente possui uma gravação pendente. Sem ``_pending_recording_context``,
        # a sessão pendente pertence ao ``LiveCameraSessionCoordinator`` (fluxo
        # live, retomado por ``LIVE_RECORDING_RESUME_REQUESTED`` do botão
        # "Iniciar Gravação"/"Concluir"). Nesse caso, clicar "Salvar Edição"
        # (que publica ZONE_SAVE_ARENA/ZONE_SAVE_MANUAL_ARENA) NÃO pode ser
        # tratado como confirmação de zonas: resetar a flag aqui corrompia o
        # handshake live, disparava o caminho de gravação errado e fazia a
        # auto-detecção reaparecer por cima da edição do usuário.
        if not self._pending_recording_context:
            log.debug(
                "recording_session_coordinator.zone_saved.ignored_no_local_context",
            )
            return

        log.info("recording_session_coordinator.zone_saved.resuming_recording")

        # Reset flag
        self.live_calibration_coordinator.pending_zone_confirmation = False

        # Resume recording (context is guaranteed present at this point).
        if self._pending_recording_context:
            context = self._pending_recording_context

            # CRITICAL: Detect if we are in a live project workflow to enable Live Analysis dispatch
            if self.project_manager.get_project_type() == "live":
                context["is_live_analysis"] = True
                log.info("recording_session_coordinator.zone_saved.promoted_to_live_analysis")

            output_path = context.get("output_folder")

            # CRITICAL: Mark as live analysis to use integrated canvas (not external window)
            context["use_external_preview"] = False

            # Use after() to ensure UI thread is free and avoid recursion
            if self.view and hasattr(self.view, "root"):
                self.view.root.after(
                    500,
                    lambda: self.start_recording(
                        context=context, output_path=output_path, zones_validated=True
                    ),
                )
            else:
                self.start_recording(context=context, output_path=output_path, zones_validated=True)

    def __repr__(self) -> str:
        """Return string representation of RecordingSessionCoordinator."""
        return (
            f"<RecordingSessionCoordinator("
            f"recording={self.is_recording()}, "
            f"has_arduino={self.arduino_manager is not None}"
            f")>"
        )

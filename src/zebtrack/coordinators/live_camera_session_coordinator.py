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

LIVE_PROFILE_TOOLTIP_FALLBACK = "default"


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

        # Last published UI context for live-session completion restore.
        self._last_live_analysis_metadata: dict[str, Any] = {}
        self._last_live_experiment_id: str | None = None

        # Session state
        self._active_live_session_id: str | None = None
        self._active_wizard_data: dict | None = None

        # Pending session state — populated when ensure_zones_before_recording()
        # defers (user must finish the polygon in the zone tab). The zone-tab
        # "▶️ Iniciar Gravação" button publishes LIVE_RECORDING_RESUME_REQUESTED
        # which triggers _on_resume_requested → resumes the stored call with
        # zones_validated=True.
        self._pending_live_context: dict[str, Any] | None = None
        self._pending_live_kind: str | None = None  # "project" or "config"

        # Subscribe to resume / cancel buttons published by the zone tab UI.
        if self.event_bus is not None:
            self.event_bus.subscribe(
                UIEvents.LIVE_RECORDING_RESUME_REQUESTED,
                self._on_resume_requested,  # type: ignore[arg-type]
            )
            self.event_bus.subscribe(UIEvents.LIVE_RECORDING_CANCELLED, self._on_resume_cancelled)  # type: ignore[arg-type]

        log.info(
            "live_camera_session_coordinator.initialized",
            has_live_camera_service=live_camera_service is not None,
        )

    # =============================================================================
    # PENDING-SESSION HANDSHAKE (zone-tab "Iniciar Gravação" button)
    # =============================================================================

    def _publish_pending(self, ctx: dict[str, Any]) -> None:
        """Publish LIVE_RECORDING_PENDING for the supplied context.

        Reads ``last_polygon_source`` from the calibration coordinator so the
        downstream UI / completion metadata reflects whether the polygon was
        auto-detected or drawn manually.
        """
        if self.event_bus is None:
            return
        source = "manual"
        try:
            calib_source = self.live_calibration_coordinator.last_polygon_source
            if calib_source:
                source = calib_source
        except AttributeError:
            pass

        self.event_bus.publish(
            Event(
                type=UIEvents.LIVE_RECORDING_PENDING,
                data=payloads.LiveRecordingPendingPayload(
                    experiment_id=str(ctx.get("experiment_id", "")),
                    group=ctx.get("group"),
                    day=ctx.get("day"),
                    subject_id=ctx.get("subject"),
                    polygon_source=source,
                ),
                source="LiveCameraSessionCoordinator._publish_pending",
            )
        )

    def _on_resume_requested(
        self, payload: payloads.LiveRecordingResumeRequestedPayload | None = None
    ) -> None:
        """Resume a deferred live session after the user finishes the polygon."""
        if self._pending_live_context is None or self._pending_live_kind is None:
            log.info("live_camera_session_coordinator.resume.no_pending_context")
            return

        # Clear the calibration-coordinator pending flag so future calls bypass
        # the dialog gate and proceed directly to recording.
        try:
            self.live_calibration_coordinator.pending_zone_confirmation = False
        except AttributeError:
            pass

        ctx = self._pending_live_context
        kind = self._pending_live_kind
        self._pending_live_context = None
        self._pending_live_kind = None

        log.info(
            "live_camera_session_coordinator.resume.replaying",
            kind=kind,
            experiment_id=ctx.get("experiment_id"),
        )

        # Use root.after(0, ...) so we yield the Tk thread before re-entering
        # the recording start flow (which itself may dispatch UI events).
        def _replay() -> None:
            try:
                if kind == "project":
                    self.start_live_project_session(
                        day=ctx["day_int"],
                        group=ctx["group"],
                        subject=ctx["subject"],
                        duration_s=ctx.get("duration_s"),
                        camera_index_override=ctx.get("camera_index_override"),
                        camera_friendly_name_override=ctx.get("camera_friendly_name_override"),
                        zones_validated=True,
                    )
                elif kind == "config":
                    self.start_session_from_config(
                        config=ctx["config"],
                        zones_validated=True,
                    )
            # except Exception justified: replay invokes coordinator + service
            # subsystems with heterogeneous failure modes; log and surface to UI.
            except Exception as exc:
                log.error(
                    "live_camera_session_coordinator.resume.failed",
                    error=str(exc),
                    exc_info=True,
                )
                if self.event_bus is not None:
                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SHOW_ERROR,
                            data=payloads.MessagePayload(
                                title="Erro ao retomar gravação",
                                message=f"Falha ao iniciar a gravação: {exc!s}",
                            ),
                        )
                    )

        if self.root is not None:
            self.root.after(0, _replay)
        else:
            _replay()

    def _resolve_session_paths(
        self,
        *,
        experiment_id: str | None = None,
        group: str | None = None,
        day: str | None = None,
        subject: str | None = None,
        override: Path | str | None = None,
    ) -> tuple[Path | str | None, str | None]:
        """Resolve ``(output_base_dir, session_folder_name)`` for a live session.

        Three regimes:

        1. **Explicit override**: caller pre-computed the base dir → return it
           as-is, no folder-name override (session manager applies its legacy
           ``{experiment_id}_{timestamp}`` pattern).
        2. **Project + full metadata** (group / day / subject all present):
           use ``project_manager.resolve_results_directory`` to land inside
           ``<project>/Grupo_X/Dia_Y/Sujeito_Z/`` so live results sit beside
           pre-recorded results for the same subject. Folder name becomes
           ``live_{timestamp}`` to avoid colliding with pre-recorded files.
        3. **Project only** (missing metadata): fall back to
           ``<project>/live_analysis_sessions/`` with the legacy pattern so
           the folder still sits inside the project (resolving the CWD bug)
           without inventing a hierarchy that doesn't make sense yet.
        4. **No project**: return ``(None, None)``; ``LiveSessionManager``
           uses its CWD-relative default.
        """
        if override is not None:
            return override, None

        project_path = getattr(self.project_manager, "project_path", None)
        if not project_path:
            return None, None

        # Hierarchical layout — requires all three fields so the resolver
        # doesn't fall back to "Grupo_Sem_Grupo/Dia_Indefinido/..." which
        # would be confusing.
        if group and day and subject and experiment_id:
            try:
                hierarchical = self.project_manager.resolve_results_directory(
                    experiment_id,
                    metadata={
                        "group": group,
                        "day": day,
                        "subject_id": subject,
                    },
                )
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                return Path(hierarchical), f"live_{timestamp}"
            # except Exception justified: metadata resolution touches user data
            # and may raise on malformed entries; fall back to legacy layout.
            except Exception as exc:
                log.warning(
                    "live_camera_session_coordinator.resolve_session_paths.hierarchical_failed",
                    experiment_id=experiment_id,
                    error=str(exc),
                )

        return Path(project_path) / "live_analysis_sessions", None

    def _on_resume_cancelled(
        self, payload: payloads.LiveRecordingCancelledPayload | None = None
    ) -> None:
        """Discard the pending live session (user clicked "Cancelar Sessão")."""
        if self._pending_live_context is None:
            return
        log.info(
            "live_camera_session_coordinator.resume.cancelled",
            experiment_id=self._pending_live_context.get("experiment_id"),
        )
        self._pending_live_context = None
        self._pending_live_kind = None
        try:
            self.live_calibration_coordinator.pending_zone_confirmation = False
            self.live_calibration_coordinator.clear_last_polygon_source()
        except AttributeError:
            pass

    @staticmethod
    def _format_day_label_for_metadata(day_value: Any) -> str | None:
        """Build a stable ``day_label`` string from raw day metadata."""
        if day_value in (None, "", "None"):
            return None

        text = str(day_value).strip()
        if not text:
            return None

        lower_text = text.lower()
        if lower_text.startswith("dia_"):
            text = text[4:]
        elif lower_text.startswith("dia "):
            text = text[4:]

        text = text.strip()
        if not text:
            return None

        return f"Dia {text}"

    def _resolve_live_analysis_profile_name(self, metadata: dict[str, Any]) -> str:
        """Resolve the profile label that should be shown for a live session."""
        profile_name = None

        try:
            resolved = self.project_manager.resolve_analysis_profile(metadata)
            if isinstance(resolved, dict):
                candidate = resolved.get("name")
                if candidate not in (None, ""):
                    text = str(candidate).strip()
                    if text:
                        profile_name = text
        except Exception:
            log.debug(
                "live_camera_session_coordinator.resolve_analysis_profile.failed",
                exc_info=True,
            )

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        if not isinstance(project_data, dict):
            project_data = {}

        fallback = (
            project_data.get("analysis_profile")
            or project_data.get("active_profile")
            or LIVE_PROFILE_TOOLTIP_FALLBACK
        )
        fallback_text = str(fallback).strip() or LIVE_PROFILE_TOOLTIP_FALLBACK
        return profile_name or fallback_text

    def _publish_live_task_status(
        self,
        *,
        experiment_id: str | None = None,
        step: str | None = None,
        progress_fraction: float | None = None,
    ) -> None:
        """Publish live-session task text through the shared analysis task channel."""
        if self.event_bus is None:
            return

        self.event_bus.publish(
            Event(
                type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                data=payloads.AnalysisTaskStatusPayload(
                    experiment_id=experiment_id,
                    step=step,
                    progress_fraction=progress_fraction,
                ),
                source="LiveCameraSessionCoordinator._publish_live_task_status",
            )
        )

    def _set_live_analysis_ui_state(
        self,
        *,
        status_text: str,
        experiment_id: str | None = None,
        task_step: str | None = None,
        switch_to_analysis: bool = False,
        show_progress: bool = False,
        disable_cancel: bool = False,
        restore_metadata: bool = False,
    ) -> None:
        """Apply live-session UI state on the Tk thread using legacy view refs."""
        controller = getattr(self.view, "analysis_view_controller", None) if self.view else None
        widget = getattr(self.view, "analysis_display_widget", None) if self.view else None

        if controller is None and widget is None:
            return

        def _apply() -> None:
            if controller is not None:
                if switch_to_analysis:
                    controller.switch_to_analysis_view()
                controller.set_analysis_status(status_text)
                if task_step is not None:
                    controller.update_analysis_task_status(
                        index=None,
                        total=None,
                        experiment_id=experiment_id,
                        step=task_step,
                    )
                if restore_metadata and self._last_live_analysis_metadata:
                    controller.update_analysis_metadata(metadata=self._last_live_analysis_metadata)

            if widget is not None:
                if show_progress:
                    widget.show_progress()
                if disable_cancel:
                    widget.disable_cancel_button()

        if self.root is not None:
            if restore_metadata:
                self.root.after(0, lambda: self.root.after(0, _apply))
            else:
                self.root.after(0, _apply)
        else:
            _apply()

    def _publish_live_analysis_metadata(
        self,
        *,
        experiment_id: str,
        camera_index: int,
        group: Any = None,
        day: Any = None,
        subject: Any = None,
    ) -> None:
        """Publish analysis metadata for live sessions.

        Preference order:
        1. Active video entry metadata (when available)
        2. Session metadata passed by the live start flow
        """
        if self.event_bus is None:
            return

        metadata: dict[str, Any] = {}

        active_video = self.project_manager.get_active_zone_video()
        if active_video:
            active_entry = self.project_manager.find_video_entry(path=active_video)
            if active_entry:
                metadata.update(dict(active_entry.get("metadata") or {}))
                for key in ("group", "group_display_name", "day", "subject"):
                    value = active_entry.get(key)
                    if value not in (None, "") and key not in metadata:
                        metadata[key] = value

        if metadata.get("group") in (None, "") and group not in (None, ""):
            metadata["group"] = group
            metadata.setdefault("group_display_name", str(group))

        if metadata.get("day") in (None, "") and day not in (None, ""):
            metadata["day"] = day

        if metadata.get("subject") in (None, "") and subject not in (None, ""):
            metadata["subject"] = subject
            metadata.setdefault("subject_id", subject)

        if metadata.get("day_label") in (None, ""):
            day_label = self._format_day_label_for_metadata(metadata.get("day"))
            if day_label:
                metadata["day_label"] = day_label

        profile_name = metadata.get("profile")
        if profile_name in (None, "", "None"):
            metadata["profile"] = self._resolve_live_analysis_profile_name(metadata)
        else:
            normalized_profile = str(profile_name).strip()
            metadata["profile"] = (
                normalized_profile
                if normalized_profile
                else self._resolve_live_analysis_profile_name(metadata)
            )

        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("camera_index", camera_index)
        self._last_live_analysis_metadata = dict(metadata)
        self._last_live_experiment_id = experiment_id

        log.info(
            "live_camera_session_coordinator.publish_analysis_metadata",
            experiment_id=experiment_id,
            metadata_keys=list(metadata.keys()),
            group=metadata.get("group"),
            day=metadata.get("day"),
            subject=metadata.get("subject"),
        )
        self.event_bus.publish(
            Event(
                type=UIEvents.UI_UPDATE_ANALYSIS_METADATA,
                data=payloads.AnalysisMetadataPayload(metadata=metadata),
                source="LiveCameraSessionCoordinator._publish_live_analysis_metadata",
            )
        )

        # Audit Erro 5 round 4 (2026-05-25): publish the processing mode so
        # the "Modo de rastreamento" label reflects the project config
        # (single-subject for 1 animal/aquarium vs multi-track for 2+).
        # Without this, the label defaults to MULTI_TRACK regardless of
        # what the wizard recorded under ``animals_per_aquarium``. We pick
        # the mode based on the same rules ``_resolve_single_animal_mode``
        # uses in MultiAquariumCoordinator, kept local here to avoid the
        # cross-coordinator dependency.
        try:
            from zebtrack.core.video.processing_mode import ProcessingReport

            mode = self._resolve_live_processing_mode()
            if mode is not None:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_UPDATE_PROCESSING_MODE,
                        data=payloads.UpdateProcessingModePayload(
                            report=ProcessingReport(
                                mode=mode,
                                source="LiveCameraSessionCoordinator.publish_metadata",
                            )
                        ),
                        source="LiveCameraSessionCoordinator._publish_live_analysis_metadata",
                    )
                )
                log.info(
                    "live_camera_session_coordinator.publish_processing_mode",
                    mode=mode.name,
                )
        # except Exception justified: telemetry must not block recording.
        except Exception:
            log.debug(
                "live_camera_session_coordinator.publish_processing_mode.failed",
                exc_info=True,
            )

    def _resolve_live_processing_mode(self):
        """Determine SINGLE_SUBJECT vs MULTI_TRACK from project data.

        Mirrors ``MultiAquariumCoordinator._resolve_single_animal_mode``
        but without the cross-coordinator import. Reads
        ``animals_per_aquarium`` from project_data → calibration →
        single_animal_per_aquarium flag, returning the mode.

        Audit Erro 2 round 6 (2026-05-25): logs which key resolved the
        mode (or which were checked when no value was found) so the next
        runtime can pinpoint why the label still shows "multi-animais"
        with 1 animal/aquarium. Also accepts the multi-aquarium
        ``animals_per_aquarium_list`` (used by wizard wide-multi flow).
        """
        from zebtrack.core.video.processing_mode import ProcessingMode

        project_data = getattr(self.project_manager, "project_data", {}) or {}

        def _to_mode_from_count(value: object):
            if value in (None, ""):
                return None
            try:
                return (
                    ProcessingMode.SINGLE_SUBJECT
                    if int(str(value)) <= 1
                    else ProcessingMode.MULTI_TRACK
                )
            except (TypeError, ValueError):
                return None

        # 1. Explicit flag at top level
        flag = project_data.get("single_animal_per_aquarium")
        if flag is not None:
            mode = ProcessingMode.SINGLE_SUBJECT if bool(flag) else ProcessingMode.MULTI_TRACK
            log.info(
                "live_camera.processing_mode.resolved",
                source="single_animal_per_aquarium",
                value=flag,
                mode=str(mode),
            )
            return mode

        # 2. Top-level animals_per_aquarium
        top_animals = project_data.get("animals_per_aquarium")
        mode = _to_mode_from_count(top_animals)
        if mode is not None:
            log.info(
                "live_camera.processing_mode.resolved",
                source="top.animals_per_aquarium",
                value=top_animals,
                mode=str(mode),
            )
            return mode

        # 3. tracking.use_single_subject_tracker (wizard)
        tracking = project_data.get("tracking")
        if isinstance(tracking, dict):
            tracker_pref = tracking.get("use_single_subject_tracker")
            if tracker_pref is not None:
                mode = (
                    ProcessingMode.SINGLE_SUBJECT
                    if bool(tracker_pref)
                    else ProcessingMode.MULTI_TRACK
                )
                log.info(
                    "live_camera.processing_mode.resolved",
                    source="tracking.use_single_subject_tracker",
                    value=tracker_pref,
                    mode=str(mode),
                )
                return mode

        # 4. calibration.animals_per_aquarium (wizard)
        calibration = project_data.get("calibration")
        calib_value = None
        if isinstance(calibration, dict):
            calib_value = calibration.get("animals_per_aquarium")
            mode = _to_mode_from_count(calib_value)
            if mode is not None:
                log.info(
                    "live_camera.processing_mode.resolved",
                    source="calibration.animals_per_aquarium",
                    value=calib_value,
                    mode=str(mode),
                )
                return mode

        # 5. multi-aquarium list (e.g. [1, 1, 2]) — single-subject iff all
        # entries are 1. Reading either the calibration sub-dict or the
        # _wizard_metadata depending on what survived the wizard adapter.
        list_values = None
        if isinstance(calibration, dict):
            list_values = calibration.get("animals_per_aquarium_list")
        if list_values is None:
            wizard_meta = project_data.get("_wizard_metadata")
            if isinstance(wizard_meta, dict):
                list_values = wizard_meta.get("animals_per_aquarium_list")
        if isinstance(list_values, list) and list_values:
            try:
                max_animals = max(int(v) for v in list_values)
                mode = (
                    ProcessingMode.SINGLE_SUBJECT
                    if max_animals <= 1
                    else ProcessingMode.MULTI_TRACK
                )
                log.info(
                    "live_camera.processing_mode.resolved",
                    source="animals_per_aquarium_list",
                    value=list_values,
                    max_animals=max_animals,
                    mode=str(mode),
                )
                return mode
            except (TypeError, ValueError):
                pass

        log.warning(
            "live_camera.processing_mode.keys_checked_no_match",
            keys_present={
                "single_animal_per_aquarium": flag,
                "top.animals_per_aquarium": top_animals,
                "tracking.use_single_subject_tracker": tracking.get("use_single_subject_tracker")
                if isinstance(tracking, dict)
                else None,
                "calibration.animals_per_aquarium": calib_value,
                "animals_per_aquarium_list": list_values,
            },
        )
        return None

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
            use_countdown = bool((wizard_data or {}).get("use_countdown", False))
            countdown_duration_s = int((wizard_data or {}).get("countdown_duration_s", 0) or 0)

            # v2.3.1: Build analysis_config with batch metadata for video registration
            analysis_config = None
            if wizard_data:
                analysis_config = {
                    "group": wizard_data.get("experimental_group"),
                    "day": wizard_data.get("experiment_day"),
                    "subject_id": wizard_data.get("subject_id"),
                    "camera_index": camera_index,
                }

            prestart_step = (
                "Contagem regressiva para iniciar a análise ao vivo."
                if use_countdown and countdown_duration_s > 0
                else "Iniciando análise ao vivo."
            )
            self._publish_live_analysis_metadata(
                experiment_id=experiment_id,
                camera_index=camera_index,
                group=(wizard_data or {}).get("experimental_group"),
                day=(wizard_data or {}).get("experiment_day"),
                subject=(wizard_data or {}).get("subject_id"),
            )
            self._publish_live_task_status(
                experiment_id=experiment_id,
                step=prestart_step,
            )
            self._set_live_analysis_ui_state(
                status_text=prestart_step,
                experiment_id=experiment_id,
                task_step=prestart_step,
                show_progress=True,
            )

            # Delegate to LiveCameraService
            resolved_base, session_folder = self._resolve_session_paths(
                experiment_id=experiment_id,
                group=(wizard_data or {}).get("experimental_group"),
                day=(wizard_data or {}).get("experiment_day"),
                subject=(wizard_data or {}).get("subject_id"),
                override=output_base_dir,
            )
            success = self.live_camera_service.start_session(
                camera_index=camera_index,
                duration_s=duration_s,
                experiment_id=experiment_id,
                analysis_interval_frames=analysis_interval_frames,
                display_interval_frames=display_interval_frames,
                record_video=record_video,
                output_base_dir=resolved_base,
                session_folder_name=session_folder,
                animals_per_aquarium=animals_per_aquarium,
                use_external_preview=False,  # Use integrated canvas in Analysis tab
                analysis_config=analysis_config,
                zones_validated=True,
                use_countdown=use_countdown,
                countdown_duration_s=countdown_duration_s,
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

            self._publish_live_analysis_metadata(
                experiment_id=experiment_id,
                camera_index=camera_index,
                group=(wizard_data or {}).get("experimental_group"),
                day=(wizard_data or {}).get("experiment_day"),
                subject=(wizard_data or {}).get("subject_id"),
            )
            running_step = "Análise ao vivo em andamento."
            self._publish_live_task_status(
                experiment_id=experiment_id,
                step=running_step,
            )
            self._set_live_analysis_ui_state(
                status_text=running_step,
                experiment_id=experiment_id,
                task_step=running_step,
                show_progress=True,
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

            completion_step = "Sessão ao vivo concluída."
            self._publish_live_task_status(
                experiment_id=self._last_live_experiment_id,
                step=completion_step,
                progress_fraction=1.0,
            )
            self._set_live_analysis_ui_state(
                status_text="Análise concluída.",
                experiment_id=self._last_live_experiment_id,
                task_step=completion_step,
                switch_to_analysis=True,
                show_progress=True,
                disable_cancel=True,
                restore_metadata=True,
            )

            # v2.3.1: Re-enable start recording button after session ends
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

            # v2.3.0: Register session for batch tracking.
            # Audit round 6 (2026-05-25): drop the ``live_batch_coordinator``
            # guard — ``_register_batch_session`` now handles both the
            # coordinator-wired path AND the direct-write fallback. Gating
            # the call here previously meant projects without the coordinator
            # NEVER persisted the recording to ``project_data["batches"]``,
            # leaving the listbox + Progresso stuck on "Sessão planejada".
            if success and self._active_wizard_data:
                self._register_batch_session()

            # Mirror pre-recorded completion flow: trigger project-views and
            # video-tree refresh so the "Controle Principal", "Progresso do
            # Experimento", "Configuração de Zonas" and "Processamento e
            # Relatórios" tabs reflect the newly recorded session immediately.
            # Without these, the working trees only update on manual reload.
            if success:
                # Invalidate the VideoManager scan cache so the next refresh
                # picks up the newly written 1_ProcessingArea_*.parquet for the
                # just-recorded video. Without this, has_arena stays False for
                # up to TTL (30 s) and "Controle Principal" shows trajectory ✓
                # but arena ✗ — audit Erro 3 (2026-05-25).
                try:
                    from zebtrack.core.project.video_manager import VideoManager

                    VideoManager.clear_scan_cache()
                except Exception:
                    log.debug(
                        "live_camera_session_coordinator.scan_cache_invalidate.failed",
                        exc_info=True,
                    )

            if success and self.event_bus is not None:
                self.event_bus.publish(
                    Event(
                        type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                        data=payloads.ProjectViewsRefreshRequestedPayload(
                            reason="live_session_completed",
                            immediate=True,
                        ),
                        source="LiveCameraSessionCoordinator.stop_live_session",
                    )
                )
                self.event_bus.publish(
                    Event(
                        type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                        data=payloads.VideoTreeRefreshRequestedPayload(),
                        source="LiveCameraSessionCoordinator.stop_live_session",
                    )
                )
                log.info("live_camera_session_coordinator.stop_live_session.refresh_published")

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

        Audit Erro 2/3 round 6 (2026-05-25): also persists the session into
        ``project_data["batches"]`` via a direct path when
        ``live_batch_coordinator`` is not wired — the listbox and Progresso
        grid both read from ``get_all_videos`` which only sees batches that
        live in ``project_data``. Skipping the coordinator path used to leave
        the listbox stuck on "Sessão planejada" forever even though the
        parquets were on disk.
        """
        if not self._active_wizard_data:
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

            if self.live_batch_coordinator:
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
                    log.info(
                        "live_camera_session_coordinator.batch_marked_complete",
                        batch_id=batch_id,
                    )
                    self.live_batch_coordinator.mark_batch_complete(batch_id)
            else:
                # Fallback: no batch coordinator wired — persist directly to
                # ``project_data["batches"]`` so the Progresso/listbox still
                # update. This is the same write the coordinator would do via
                # ``LiveBatchCoordinator._persist_session_to_project_data``.
                self._persist_session_to_project_data_fallback(
                    experiment_id=self._active_live_session_id or "unknown",
                    video_path=video_path,
                    metadata=metadata,
                )
                log.info(
                    "live_camera_session_coordinator.batch_session_registered_fallback",
                    group=group,
                    day=day,
                    subject_id=subject_id,
                )

        except Exception as e:  # except Exception justified: non-critical fallback
            log.error(
                "live_camera_session_coordinator.batch_registration_failed",
                error=str(e),
                exc_info=True,
            )
        finally:
            # Clear wizard data after processing
            self._active_wizard_data = None

    def _persist_session_to_project_data_fallback(
        self,
        *,
        experiment_id: str,
        video_path: Path,
        metadata: dict,
    ) -> None:
        """Fallback writer for project_data["batches"] when no batch coord is wired.

        Mirrors ``LiveBatchCoordinator._persist_session_to_project_data`` so
        the listbox/Progresso receive the same canonical entry regardless of
        wiring. Skips cancelled sessions.
        """
        pm = getattr(self, "project_manager", None) or getattr(
            getattr(self, "controller", None), "project_manager", None
        )
        if pm is None or pm.project_data is None:
            log.debug("live_camera_session_coordinator.persist_fallback.no_pm")
            return

        results_dir = video_path.parent if video_path else None
        if results_dir and (results_dir / ".cancelled").exists():
            log.info(
                "live_camera_session_coordinator.persist_fallback.skipped_cancelled",
                experiment_id=experiment_id,
            )
            return

        video_path_str = video_path.as_posix() if isinstance(video_path, Path) else str(video_path)

        normalized_metadata = {
            "group": metadata.get("group"),
            "group_display_name": metadata.get("group"),
            "day": metadata.get("day"),
            "subject": metadata.get("subject_id"),
            "subject_id": metadata.get("subject_id"),
            "experiment_id": experiment_id,
            "timestamp": metadata.get("timestamp"),
            "is_live_session": True,
        }
        normalized_metadata = {
            k: v
            for k, v in normalized_metadata.items()
            if v is not None and (v != "" or isinstance(v, bool | int | float))
        }

        has_arena = has_rois = has_trajectory = False
        if results_dir and results_dir.exists():
            has_arena = bool(list(results_dir.glob("1_ProcessingArea_*.parquet")))
            has_rois = bool(list(results_dir.glob("2_AreasOfInterest_*.parquet")))
            has_trajectory = bool(list(results_dir.glob("3_CoordMovimento_*.parquet")))

        video_entry: dict = {
            "path": video_path_str,
            "status": "processed" if has_trajectory else "recorded",
            "has_arena": has_arena,
            "has_rois": has_rois,
            "has_trajectory": has_trajectory,
            "has_complete_data": has_arena and has_rois and has_trajectory,
            "has_summary": bool(results_dir and list(results_dir.glob("*_summary.xlsx")))
            if results_dir and results_dir.exists()
            else False,
            "zones_finalized": True,
            "metadata": normalized_metadata,
            "filename": (
                video_path.name if isinstance(video_path, Path) else Path(video_path_str).name
            ),
        }

        # Idempotent insert.
        for batch in pm.project_data.get("batches", []):
            for entry in batch.get("videos", []):
                if entry.get("path") == video_path_str:
                    entry.update(
                        {
                            "status": video_entry["status"],
                            "has_arena": entry.get("has_arena") or video_entry["has_arena"],
                            "has_rois": entry.get("has_rois") or video_entry["has_rois"],
                            "has_trajectory": entry.get("has_trajectory")
                            or video_entry["has_trajectory"],
                            "has_summary": entry.get("has_summary") or video_entry["has_summary"],
                        }
                    )
                    entry["has_complete_data"] = bool(
                        entry.get("has_arena")
                        and entry.get("has_rois")
                        and entry.get("has_trajectory")
                    )
                    entry.setdefault("metadata", {}).update(normalized_metadata)
                    try:
                        pm.save_project()
                    # except Exception justified: persistence best-effort.
                    except Exception:
                        log.warning(
                            "live_camera_session_coordinator.persist_fallback.save_failed",
                            exc_info=True,
                        )
                    return

        pm.project_data.setdefault("batches", []).append(
            {
                "timestamp": datetime.datetime.now().isoformat(),
                "source": "live_camera",
                "videos": [video_entry],
            }
        )
        try:
            pm.save_project()
        # except Exception justified: persistence best-effort.
        except Exception:
            log.warning(
                "live_camera_session_coordinator.persist_fallback.save_failed",
                exc_info=True,
            )

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

    def start_session_from_config(self, config: dict, *, zones_validated: bool = False) -> bool:
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
        use_countdown = bool(config.get("use_countdown", False))
        countdown_duration_s = int(config.get("countdown_duration_s", 0) or 0)

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
            use_countdown=use_countdown,
            countdown_duration_s=countdown_duration_s,
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

        # Ad-hoc flow (LiveAnalysisDialog) — gate through the same zone-validation
        # handshake as the live project flow so the user always gets a chance to
        # review/adjust the polygon before recording begins. When deferred, the
        # zone tab's "▶️ Iniciar Gravação" button replays this call with
        # ``zones_validated=True``.
        if not zones_validated:
            zones_ready = self.live_calibration_coordinator.ensure_zones_before_recording()
            if not zones_ready:
                if self.live_calibration_coordinator.pending_zone_confirmation:
                    pending_ctx = {
                        "experiment_id": experiment_id,
                        "config": config,
                        "group": config.get("experimental_group"),
                        "day": config.get("experiment_day"),
                        "subject": config.get("subject_id"),
                    }
                    self._pending_live_context = pending_ctx
                    self._pending_live_kind = "config"
                    self._publish_pending(pending_ctx)
                    log.info(
                        "live_camera_session_coordinator.start_from_config.deferred",
                        experiment_id=experiment_id,
                    )
                else:
                    log.info("live_camera_session_coordinator.start_from_config.zones_not_ready")
                return False

        # v2.3.0: Build analysis_config with batch metadata for video registration.
        polygon_source = self.live_calibration_coordinator.last_polygon_source or "manual"
        analysis_config = {
            "group": config.get("experimental_group"),
            "day": config.get("experiment_day"),
            "subject_id": config.get("subject_id"),
            "camera_index": camera_index,
            "polygon_source": polygon_source,
        }

        prestart_step = (
            "Contagem regressiva para iniciar a análise ao vivo."
            if use_countdown and countdown_duration_s > 0
            else "Iniciando análise ao vivo."
        )
        self._publish_live_analysis_metadata(
            experiment_id=experiment_id,
            camera_index=camera_index,
            group=config.get("experimental_group"),
            day=config.get("experiment_day"),
            subject=config.get("subject_id"),
        )
        self._publish_live_task_status(
            experiment_id=experiment_id,
            step=prestart_step,
        )
        self._set_live_analysis_ui_state(
            status_text=prestart_step,
            experiment_id=experiment_id,
            task_step=prestart_step,
            show_progress=True,
        )

        # Delegate to LiveCameraService.
        # When metadata (group/day/subject) is set, results land inside the
        # project's Grupo/Dia/Sujeito hierarchy alongside pre-recorded videos.
        resolved_base, session_folder = self._resolve_session_paths(
            experiment_id=experiment_id,
            group=config.get("experimental_group"),
            day=config.get("experiment_day"),
            subject=config.get("subject_id"),
        )
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=record_video,
            output_base_dir=resolved_base,
            session_folder_name=session_folder,
            animals_per_aquarium=animals_per_aquarium,
            use_external_preview=False,  # Use canvas in Analysis tab
            analysis_config=analysis_config,
            zones_validated=True,
            use_countdown=use_countdown,
            countdown_duration_s=countdown_duration_s,
        )

        if success:
            self.live_calibration_coordinator.clear_last_polygon_source()
            self._publish_live_analysis_metadata(
                experiment_id=experiment_id,
                camera_index=camera_index,
                group=config.get("experimental_group"),
                day=config.get("experiment_day"),
                subject=config.get("subject_id"),
            )
            running_step = "Análise ao vivo em andamento."
            self._publish_live_task_status(
                experiment_id=experiment_id,
                step=running_step,
            )
            self._set_live_analysis_ui_state(
                status_text=running_step,
                experiment_id=experiment_id,
                task_step=running_step,
                show_progress=True,
            )

        # UI feedback
        if success and self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SET_STATUS,
                    data=payloads.StatusPayload(
                        message=(
                            f"Analisando câmera {camera_index} "
                            f"(análise: {analysis_interval_frames}f, "
                            f"exibição: {display_interval_frames}f)"
                        )
                    ),
                )
            )
        elif not success and self.event_bus:
            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SHOW_ERROR,
                    data=payloads.ErrorOccurredPayload(
                        title="Erro na Análise",
                        message=f"Falha ao iniciar análise de câmera {camera_index}.",
                    ),
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
        *,
        camera_index_override: int | None = None,
        camera_friendly_name_override: str | None = None,
        zones_validated: bool = False,
    ) -> bool:
        """Start a live recording session for a Live project.

        This method replaces the legacy thread-based system in gui.py,
        using LiveCameraService for unified camera management.

        Args:
            day: Day number (from project grid)
            group: Group identifier
            subject: Subject/animal identifier
            duration_s: Optional duration override (uses project default if None)
            camera_index_override: If provided, skip the friendly-name resolver
                and use this index for THIS session only (no persistence).
            camera_friendly_name_override: Friendly name paired with the override
                (only logged for traceability).

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
        saved_camera_index = project_data.get("camera_index", 0)
        saved_camera_name = project_data.get("camera_friendly_name", "") or ""

        # Resolve camera by friendly name unless the caller already overrode it
        if camera_index_override is not None:
            camera_index = int(camera_index_override)
            log.info(
                "live_camera_session_coordinator.camera.override",
                index=camera_index,
                friendly_name=camera_friendly_name_override or "",
            )
        else:
            from zebtrack.core.services.wizard_service import WizardService

            resolved_index, status = WizardService.resolve_camera_index(
                saved_camera_index, saved_camera_name
            )
            if status == "MISSING":
                log.error(
                    "live_camera_session_coordinator.camera.missing",
                    saved_index=saved_camera_index,
                    saved_name=saved_camera_name,
                )
                self.event_bus.publish(  # type: ignore[union-attr]
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data=payloads.MessagePayload(
                            title="Câmera não encontrada",
                            message=(
                                f"A câmera salva no projeto ('{saved_camera_name}') "
                                f"não foi detectada.\n\n"
                                f"Conecte o dispositivo correto ou use 'Trocar câmera' "
                                f"no diálogo de gravação para escolher outra."
                            ),
                        ),
                        source="LiveCameraSessionCoordinator.start_live_project_session",
                    )
                )
                return False

            if status == "SHIFTED":
                log.info(
                    "live_camera_session_coordinator.camera.resolved.shifted",
                    saved_index=saved_camera_index,
                    actual_index=resolved_index,
                    friendly_name=saved_camera_name,
                )
            camera_index = resolved_index

        # Duration: use parameter, project default, or fallback
        if duration_s is None:
            duration_s = project_data.get("recording_duration_s", 300.0)

        # Intervals
        analysis_interval_frames = project_data.get("analysis_interval_frames", 1)
        display_interval_frames = project_data.get("display_interval_frames", 1)
        use_countdown = bool(project_data.get("use_countdown", False))
        countdown_duration_s = int(project_data.get("countdown_duration_s", 0) or 0)

        # Experiment ID for this session
        experiment_id = f"day{day}_{group}_{subject}"

        log.info(
            "live_camera_session_coordinator.live_project_session.start",
            project=self.project_manager.get_project_name(),
            experiment_id=experiment_id,
            camera_index=camera_index,
            duration_s=duration_s,
            use_countdown=use_countdown,
            countdown_duration_s=countdown_duration_s,
        )

        # v2.3.1: Ensure zones are defined before recording.
        # When the calibration coordinator defers (auto-detect approved or user
        # chose manual mode) ``ensure_zones_before_recording`` returns False and
        # sets pending_zone_confirmation=True. In that case we stash the call
        # context and publish LIVE_RECORDING_PENDING so the zone tab can show
        # the "▶️ Iniciar Gravação" button. The button publishes
        # LIVE_RECORDING_RESUME_REQUESTED which lands in _on_resume_requested
        # and replays this method with zones_validated=True.
        if not zones_validated:
            zones_ready = self.live_calibration_coordinator.ensure_zones_before_recording()
            if not zones_ready:
                if self.live_calibration_coordinator.pending_zone_confirmation:
                    pending_ctx = {
                        "experiment_id": experiment_id,
                        "day": f"Dia_{day}",
                        "day_int": day,
                        "group": group,
                        "subject": subject,
                        "duration_s": duration_s,
                        "camera_index_override": camera_index_override,
                        "camera_friendly_name_override": camera_friendly_name_override,
                    }
                    self._pending_live_context = pending_ctx
                    self._pending_live_kind = "project"
                    self._publish_pending(pending_ctx)
                    log.info(
                        "live_camera_session_coordinator.live_project_session.deferred",
                        experiment_id=experiment_id,
                    )
                else:
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

        # v2.3.0: Build analysis_config with batch metadata for video registration.
        # ``polygon_source`` is read from the calibration coordinator (auto vs
        # manual) so register_processing_outputs can stamp the session with the
        # provenance shown later in BlockDetailDialog.
        polygon_source = self.live_calibration_coordinator.last_polygon_source or "manual"
        analysis_config = {
            "group": group,
            "day": f"Dia_{day}",
            "subject_id": subject,
            "camera_index": camera_index,
            "polygon_source": polygon_source,
        }

        prestart_step = (
            "Contagem regressiva para iniciar a análise ao vivo."
            if use_countdown and countdown_duration_s > 0
            else "Iniciando análise ao vivo."
        )
        self._publish_live_analysis_metadata(
            experiment_id=experiment_id,
            camera_index=camera_index,
            group=group,
            day=f"Dia_{day}",
            subject=subject,
        )
        self._publish_live_task_status(
            experiment_id=experiment_id,
            step=prestart_step,
        )
        self._set_live_analysis_ui_state(
            status_text=prestart_step,
            experiment_id=experiment_id,
            task_step=prestart_step,
            show_progress=True,
        )

        # Delegate to LiveCameraService (unified system).
        # Live project sessions always have full metadata, so the resolver
        # routes them into <project>/Grupo_X/Dia_Y/Sujeito_Z/live_{timestamp}/
        # alongside the pre-recorded artifacts for the same subject.
        resolved_base, session_folder = self._resolve_session_paths(
            experiment_id=experiment_id,
            group=group,
            day=f"Dia_{day}",
            subject=subject,
        )
        success = self.live_camera_service.start_session(
            camera_index=camera_index,
            duration_s=duration_s,
            experiment_id=experiment_id,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            record_video=True,  # Projects always record
            output_base_dir=resolved_base,
            session_folder_name=session_folder,
            animals_per_aquarium=animals_per_aquarium,
            use_external_preview=False,  # Use integrated canvas in Analysis tab
            analysis_config=analysis_config,
            zones_validated=True,
            use_countdown=use_countdown,
            countdown_duration_s=countdown_duration_s,
        )

        if success:
            # Polygon-source has been consumed for this session — reset so the next
            # session doesn't accidentally inherit a stale tag.
            self.live_calibration_coordinator.clear_last_polygon_source()
            self._publish_live_analysis_metadata(
                experiment_id=experiment_id,
                camera_index=camera_index,
                group=group,
                day=f"Dia_{day}",
                subject=subject,
            )
            running_step = "Análise ao vivo em andamento."
            self._publish_live_task_status(
                experiment_id=experiment_id,
                step=running_step,
            )
            self._set_live_analysis_ui_state(
                status_text=running_step,
                experiment_id=experiment_id,
                task_step=running_step,
                show_progress=True,
            )

        return success

    def __repr__(self) -> str:
        """Return string representation of LiveCameraSessionCoordinator."""
        return f"<LiveCameraSessionCoordinator(live_session={self.is_live_session_active()})>"

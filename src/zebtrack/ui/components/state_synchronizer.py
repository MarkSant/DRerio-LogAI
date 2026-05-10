"""State synchronization for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles state observation, UI updates based on state changes, and reset operations.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.video.processing_mode import ProcessingMode

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class StateSynchronizer:
    """Manages state synchronization between StateManager and UI components."""

    def __init__(
        self,
        gui,
        *,
        dialog_manager: DialogManager | None = None,
        state_manager: Any | None = None,
    ):
        """Initialize StateSynchronizer.

        Args:
            gui: Reference to ApplicationGUI instance
            dialog_manager: Optional DialogManager for dependency injection.
            state_manager: Direct StateManager reference (avoids LazyRef access).
        """
        self.gui = gui
        self._dialog_manager = dialog_manager
        self._state_manager = state_manager

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    # ========================================================================
    # State Change Subscription
    # ========================================================================

    def subscribe_to_state_changes(self) -> None:
        """Subscribe to StateManager events for reactive UI updates."""
        from zebtrack.core.state_manager import StateCategory

        # Use directly injected state_manager to avoid LazyRef access during init
        sm = self._state_manager
        if sm is None:
            # Fallback: try via controller (only safe after LazyRef is resolved)
            try:
                sm = self.gui.controller.state_manager
            except RuntimeError:
                log.warning(
                    "state_synchronizer.subscribe.skipped", reason="state_manager unavailable"
                )
                return

        # Subscribe to recording state changes
        sm.subscribe(StateCategory.RECORDING, self._on_recording_state_changed)

        # Subscribe to processing state changes
        sm.subscribe(StateCategory.PROCESSING, self._on_processing_state_changed)

        # Subscribe to detector state changes
        sm.subscribe(StateCategory.DETECTOR, self._on_detector_state_changed)

        # Subscribe to project state changes
        sm.subscribe(StateCategory.PROJECT, self._on_project_state_changed)

        log.info(
            "gui.state_observers.subscribed",
            categories=["RECORDING", "PROCESSING", "DETECTOR", "PROJECT"],
        )

    # ========================================================================
    # State Change Callbacks
    # ========================================================================

    def _on_recording_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle recording state changes."""
        if key == "is_recording":
            # Schedule UI update on main thread
            self.gui.root.after(0, self._update_recording_ui, new_value)
        elif key == "arduino_connected":
            # Schedule Arduino UI update on main thread
            self.gui.root.after(0, self._update_arduino_ui, new_value)

    def _on_processing_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle processing state changes."""
        if key == "is_processing":
            # Schedule UI update on main thread
            self.gui.root.after(0, self._update_processing_ui, new_value)

    def _on_detector_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle detector state changes."""
        if key == "detector_initialized":
            # Schedule UI update on main thread
            self.gui.root.after(0, self._update_detector_ui, new_value)

    def _on_project_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle project state changes."""
        if key == "project_path":
            # Schedule project UI update on main thread
            self.gui.root.after(0, self._update_project_ui, new_value)

    # ========================================================================
    # UI Update Methods
    # ========================================================================

    def _update_recording_ui(self, is_recording: bool) -> None:
        """Update UI elements based on recording state."""
        if is_recording:
            log.debug("gui.recording_state.started")
            # Update recording button states if they exist
            if self.gui.start_rec_btn:
                self.gui.start_rec_btn.config(state="disabled")
            if self.gui.stop_rec_btn:
                self.gui.stop_rec_btn.config(state="normal")
        else:
            log.debug("gui.recording_state.stopped")
            # Update recording button states if they exist
            if self.gui.start_rec_btn:
                self.gui.start_rec_btn.config(state="normal")
            if self.gui.stop_rec_btn:
                self.gui.stop_rec_btn.config(state="disabled")

    def _update_processing_ui(self, is_processing: bool) -> None:
        """Update UI elements based on processing state.

        NOTE: When ``is_processing=True`` we intentionally do **not** call
        ``start_analysis_view_mode()`` here.  That method resets analysis
        metadata to defaults, and because this callback is deferred via
        ``root.after(0)`` it races against the metadata publish that runs
        immediately after the *explicit* ``start_analysis_view_mode()`` call
        inside ``ProgressTrackingCoordinator._update_ui_for_processing_start``.
        The result was that correct metadata (group/day/subject) was erased.
        The coordinator already handles view-mode switching with proper
        metadata sequencing, so we only need to disable the button here.
        """
        if is_processing:
            log.debug("gui.processing_state.started")
            # Disable process button during processing
            if self.gui.process_video_btn:
                self.gui.process_video_btn.config(state="disabled")
        else:
            log.debug("gui.processing_state.stopped")
            # Re-enable process button after processing
            if self.gui.process_video_btn:
                self.gui.process_video_btn.config(state="normal")
            # Switch back from analysis view mode
            if hasattr(self.gui, "analysis_view_controller"):
                self.gui.analysis_view_controller.stop_analysis_view_mode()

    def _update_detector_ui(self, detector_initialized: bool) -> None:
        """Update UI elements based on detector state."""
        if detector_initialized:
            log.debug("gui.detector_state.initialized")
            # Detector is ready - UI elements can be enabled
        else:
            log.debug("gui.detector_state.uninitialized")
            # Detector not ready - disable dependent UI elements

    def _update_arduino_ui(self, arduino_connected: bool) -> None:
        """Update UI elements based on Arduino connection state."""
        if self.gui.arduino_dashboard_widget:
            port = None  # Port info not available in this context
            self.gui.arduino_dashboard_widget.update_status(arduino_connected, port)

            if arduino_connected:
                log.debug("gui.arduino_state.connected")
            else:
                log.debug("gui.arduino_state.disconnected")

    def _update_project_ui(self, project_path: Path | str | None) -> None:
        """Update UI elements based on project state."""
        if project_path:
            log.debug("gui.project_state.loaded", project_path=str(project_path))
            # Project loaded - update window title or status
        else:
            log.debug("gui.project_state.closed")
            if getattr(self.gui, "status_frame", None):
                try:
                    if self.gui.status_frame.winfo_exists():
                        self.gui.status_frame.destroy()
                except tk.TclError:
                    log.debug("state_sync.status_frame_destroy.suppressed", exc_info=True)
                self.gui.status_frame = None

    # ========================================================================
    # Reset Methods - Analysis Widgets
    # ========================================================================

    def reset_analysis_widgets(self) -> None:
        """Encapsula a limpeza e destruição de widgets da aba de análise."""
        # Break the cleanup into smaller helpers to reduce cognitive complexity
        self._reset_analysis_media()
        self._reset_analysis_progress_and_metadata()
        self._reset_roi_and_visual_frames()
        self._destroy_notebook_and_main_controls()
        self.gui.analysis_tab_frame = None

    def _reset_analysis_media(self) -> None:
        """Reset media-related widgets such as analysis image overlays."""
        if self.gui.analysis_display_widget:
            self.gui.analysis_display_widget.clear_video_display()
            self.gui._analysis_overlay_image = None

    def _reset_analysis_progress_and_metadata(self) -> None:
        """Reset progress indicators and analysis metadata to defaults."""
        if self.gui.analysis_display_widget:
            self.gui.analysis_display_widget.reset_to_defaults()

        # Also reset internal state vars that might be used elsewhere
        try:
            self.gui.hide_progress_bar()
        except (tk.TclError, AttributeError):
            log.debug("state_sync.hide_progress_bar.suppressed", exc_info=True)

        try:
            self.gui.analysis_status_var.set("Nenhuma análise em andamento.")
        except (tk.TclError, AttributeError):
            log.debug("state_sync.analysis_status_reset.suppressed", exc_info=True)

        try:
            self.gui.analysis_task_var.set(self._default_analysis_task_text())
        except (tk.TclError, AttributeError):
            log.debug("state_sync.analysis_task_reset.suppressed", exc_info=True)

        try:
            self._set_analysis_metadata_defaults()
        except (tk.TclError, AttributeError):
            log.debug("state_sync.metadata_defaults.suppressed", exc_info=True)

    def _reset_roi_and_visual_frames(self) -> None:
        """Handle ROI canvas and visualization frame teardown."""
        if hasattr(self.gui, "video_display") and self.gui.video_display:
            try:
                if self.gui.video_display.canvas.winfo_exists():
                    self.gui.video_display.canvas.pack_forget()
            except tk.TclError:
                log.debug("state_sync.canvas_pack_forget.suppressed", exc_info=True)

        # Destroy viz_frame (parent frame)
        if hasattr(self.gui, "viz_frame") and self.gui.viz_frame:
            try:
                if self.gui.viz_frame.winfo_exists():
                    self.gui.viz_frame.destroy()
            except tk.TclError:
                log.debug("state_sync.viz_frame_destroy.suppressed", exc_info=True)
            self.gui.viz_frame = None

        # Clean up zone tab frame components
        if hasattr(self.gui, "zone_tab_frame") and self.gui.zone_tab_frame:
            try:
                if self.gui.zone_tab_frame.winfo_exists():
                    self.gui.zone_tab_frame.destroy()
            except tk.TclError:
                log.debug("state_sync.zone_tab_frame_destroy.suppressed", exc_info=True)

    def _destroy_notebook_and_main_controls(self) -> None:
        """Destroy the main notebook and controls, clear project overview state."""
        if self.gui.notebook:
            self.gui.notebook.destroy()
            self.gui.notebook = None
        if self.gui.main_controls_frame:
            self.gui.main_controls_frame.destroy()
            self.gui.main_controls_frame = None
            self.gui.arduino_dashboard_widget = None
            self.gui.external_trigger_notice_label = None
            try:
                self.gui.external_trigger_notice_var.set("")
            except tk.TclError:
                log.debug("state_sync.trigger_notice_reset.suppressed", exc_info=True)
            if self.gui._overview_refresh_job is not None:
                try:
                    self.gui.root.after_cancel(self.gui._overview_refresh_job)
                except tk.TclError:
                    log.debug("state_sync.overview_refresh_cancel.suppressed", exc_info=True)
                self.gui._overview_refresh_job = None
            self.gui.project_overview_frame = None
        if getattr(self.gui, "status_frame", None):
            try:
                if self.gui.status_frame.winfo_exists():
                    self.gui.status_frame.destroy()
            except tk.TclError:
                log.debug("state_sync.status_frame_destroy.suppressed", exc_info=True)
            self.gui.status_frame = None

    def update_status(self, message: str) -> None:
        """Update the status bar message in the GUI.

        Args:
            message: The message to display.
        """
        if hasattr(self.gui, "set_status") and callable(self.gui.set_status):
            self.gui.set_status(message)
        elif hasattr(self.gui, "analysis_status_var"):
            try:
                self.gui.analysis_status_var.set(message)
            except (tk.TclError, AttributeError):
                log.debug("state_sync.analysis_status_set.suppressed", exc_info=True)
            # Note: project_overview_tree is a read-only property derived from
            # project_overview_widget. Clear the widget reference instead.
            if hasattr(self.gui, "project_overview_widget"):
                self.gui.project_overview_widget = None
            # Safely reset overview status caches only if they still exist
            try:
                if (
                    hasattr(self.gui, "project_status_vars")
                    and self.gui.project_status_vars is not None
                ):
                    self.gui.project_status_vars.clear()
            except (AttributeError, TypeError):
                log.debug("state_sync.project_status_vars_clear.suppressed", exc_info=True)

            try:
                if (
                    hasattr(self.gui, "_project_status_containers")
                    and self.gui._project_status_containers is not None
                ):
                    self.gui._project_status_containers.clear()
            except (AttributeError, TypeError):
                log.debug("state_sync.status_containers_clear.suppressed", exc_info=True)

            try:
                if hasattr(self.gui, "_last_overview_counts"):
                    self.gui._last_overview_counts = {}
            except AttributeError:
                log.debug("state_sync.overview_counts_reset.suppressed", exc_info=True)

    # ========================================================================
    # Reset Methods - Analysis Controls
    # ========================================================================

    def reset_analysis_controls(self) -> None:
        """Reset track selector state and cached frames."""
        self.gui._current_detections = []
        self.gui._last_analysis_frame = None
        self.gui._analysis_overlay_image = None

        if self.gui.analysis_display_widget:
            self.gui.analysis_display_widget.track_selector_var.set("Todos")
            self._update_track_options(["Todos"])

            if self.gui.analysis_display_widget.track_selector_widget:
                state = (
                    "disabled"
                    if self.gui._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
                    else "readonly"
                )
                self.gui.analysis_display_widget.track_selector_widget.configure(state=state)

    def _update_track_options(self, options: list[str]) -> None:
        """Update track selector combobox with new options."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for option in options:
            option_str = str(option).strip() or "Todos"
            if option_str not in seen:
                cleaned.append(option_str)
                seen.add(option_str)

        if not cleaned:
            cleaned = ["Todos"]

        normalized = tuple(cleaned)
        # We still update local state for consistency if GUI uses it
        self.gui._available_track_options = normalized

        if self.gui.analysis_display_widget:
            self.gui.analysis_display_widget.update_track_options(list(normalized))

    # ========================================================================
    # Reset Methods - Configuration
    # ========================================================================

    def reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self.gui._reload_config_editor_values_widget()
        self.dialog_manager.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    # ========================================================================
    # Helper Methods - Analysis Metadata
    # ========================================================================

    @staticmethod
    def _analysis_metadata_defaults() -> tuple[str, str, str]:
        """Return default values for analysis metadata."""
        return ("Sem Grupo", "Sem Dia", "Não informado")

    @classmethod
    def _default_analysis_metadata_text(cls) -> str:
        """Return default analysis metadata text."""
        group, day, subject = cls._analysis_metadata_defaults()
        return f"Grupo: {group} | Dia: {day} | Indivíduo: {subject}"

    def _set_analysis_metadata_defaults(self) -> None:
        """Set analysis metadata to default values."""
        group, day, subject = self._analysis_metadata_defaults()
        self._apply_analysis_metadata_strings(group, day, subject)

    def _apply_analysis_metadata_strings(
        self,
        group: str,
        day: str,
        subject: str,
    ) -> None:
        """Apply analysis metadata strings to UI variables."""
        combined = f"Grupo: {group} | Dia: {day} | Indivíduo: {subject}"

        if getattr(self.gui, "analysis_metadata_var", None) is not None:
            self.gui.analysis_metadata_var.set(combined)

        # Try to access variables from analysis_display_widget first
        analysis_widget = getattr(self.gui, "analysis_display_widget", None)
        if analysis_widget:
            if getattr(analysis_widget, "group_var", None) is not None:
                analysis_widget.group_var.set(f"Grupo: {group}")
            if getattr(analysis_widget, "day_var", None) is not None:
                analysis_widget.day_var.set(f"Dia: {day}")
            if getattr(analysis_widget, "subject_var", None) is not None:
                analysis_widget.subject_var.set(f"Indivíduo: {subject}")
        else:
            # Fallback to gui-level variables (legacy support)
            if getattr(self.gui, "analysis_group_var", None) is not None:
                self.gui.analysis_group_var.set(f"Grupo: {group}")
            if getattr(self.gui, "analysis_day_var", None) is not None:
                self.gui.analysis_day_var.set(f"Dia: {day}")
            if getattr(self.gui, "analysis_subject_var", None) is not None:
                self.gui.analysis_subject_var.set(f"Indivíduo: {subject}")

    @staticmethod
    def _default_analysis_task_text() -> str:
        """Return default analysis task text."""
        return "Nenhuma tarefa em andamento."

    def prepare_single_video_ui_state(self, config: dict | None) -> None:
        """Ensure zone controls reflect the incoming single-video configuration."""
        zone_controls = getattr(self.gui, "zone_controls", None)
        if not zone_controls:
            return

        try:
            zone_controls.show_single_analysis_options()
        except (tk.TclError, AttributeError):
            log.warning("state_sync.show_single_analysis_options.suppressed", exc_info=True)

        analysis_interval = None
        display_interval = None
        roi_choice = None
        stabilization_frames = None

        if config:
            analysis_interval = config.get("analysis_interval_frames")
            display_interval = config.get("display_interval_frames")
            roi_choice = config.get("roi_choice")
            stabilization_frames = config.get("stabilization_frames")

        if analysis_interval is None:
            analysis_interval = self.gui.analysis_interval_var.get()
        if display_interval is None:
            display_interval = self.gui.display_interval_var.get()
        if stabilization_frames is None:
            stabilization_frames = self.gui.stabilization_frames_var.get()

        # Share the same StringVar instances so edits from either side stay in sync
        self.gui.analysis_interval_var = zone_controls.analysis_interval_var
        self.gui.display_interval_var = zone_controls.display_interval_var
        self.gui.roi_choice_var = zone_controls.roi_choice_var
        self.gui.stabilization_frames_var = zone_controls.stabilization_frames_var

        self.gui.analysis_interval_var.set(str(analysis_interval or "10"))
        self.gui.display_interval_var.set(str(display_interval or "10"))
        self.gui.roi_choice_var.set(roi_choice or "none")
        self.gui.stabilization_frames_var.set(str(stabilization_frames or "10"))

    def update_social_summary(
        self,
        *,
        profile: str,
        stats: dict | None,
        tracks: list[str] | None,
    ) -> None:
        """Display aggregated social proximity statistics for the active video."""
        from zebtrack.core.video.processing_mode import ProcessingMode

        if stats and isinstance(stats, dict):
            percentages = stats.get("social_time_percentage") or {}
            if isinstance(percentages, dict) and percentages:
                formatted = []
                for key, value in sorted(
                    percentages.items(),
                    key=lambda item: str(item[0]),
                ):
                    if isinstance(value, int | float):
                        formatted.append(f"ID {key}: {value:.1f}%")
                if formatted:
                    if self.gui.analysis_display_widget:
                        self.gui.analysis_display_widget.set_social_summary(
                            "Interações sociais: " + ", ".join(formatted)
                        )
                else:
                    if self.gui.analysis_display_widget:
                        self.gui.analysis_display_widget.set_social_summary(
                            "Interações sociais: nenhum agrupamento registrado."
                        )
            else:
                if self.gui.analysis_display_widget:
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: nenhum agrupamento registrado."
                    )
        else:
            if self.gui.analysis_display_widget:
                normalized_tracks = [
                    str(track).strip() for track in (tracks or []) if str(track).strip()
                ]
                single_track_context = bool(normalized_tracks) and len(set(normalized_tracks)) <= 1

                if self.gui._active_processing_mode is ProcessingMode.SINGLE_SUBJECT:
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: não aplicável no modo de sujeito único."
                    )
                elif profile != "social_interaction":
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: perfil atual não gera métricas sociais."
                    )
                elif single_track_context:
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: não aplicável para um único animal monitorado."
                    )
                else:
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: aguardando dados."
                    )

        if tracks and self.gui._active_processing_mode is not ProcessingMode.SINGLE_SUBJECT:
            normalized_tracks = [str(track).strip() for track in tracks if str(track).strip()]
            if normalized_tracks:
                self._update_track_options(["Todos", *normalized_tracks])

    # ========================================================================
    # Processing Statistics Updates
    # ========================================================================

    def update_processing_stats(
        self,
        total_frames=None,
        processed_frames=None,
        detected_frames=None,
        start_time=None,
        current_frame=None,
        fps=None,  # Added: FPS from stats
        frame=None,  # Added: Frame number from stats (alias for current_frame)
        **kwargs,  # Catch any other unexpected arguments
    ) -> None:
        """Update processing statistics in real-time during video analysis.

        Args:
            total_frames: Total frames in the video
            processed_frames: Frames actually processed by detector (preferred)
            detected_frames: Frames where detections were found
            start_time: Processing start timestamp
            current_frame: Current position in video (deprecated, use frame)
            fps: Processing speed in frames per second
            frame: Current position in video
        """
        # Use processed_frames if available (new stats format)
        # Fall back to current_frame/frame for progress calculation only
        video_position = None
        if current_frame is not None:
            video_position = current_frame
        elif frame is not None:
            video_position = frame

        # If processed_frames not provided, DON'T use video position as fallback
        # since they mean different things

        # If total_frames is missing in kwargs but we have it in gui state or logic?
        # For now assume it's passed.

        if self.gui.analysis_display_widget:
            # Format values if needed before passing
            percent = None
            elapsed_str = None
            eta_str = None
            progress_value = None

            # Calculate percentage based on video position (how far through video)
            # Use video_position for progress, as that shows actual playback position
            if total_frames and video_position is not None:
                percent_val = (video_position / total_frames) * 100
                percent = f"{percent_val:.1f}%"
                progress_value = max(0.0, min(1.0, float(percent_val / 100.0)))

            # Calculate elapsed time and ETA
            # Strategy 1: Use start_time if provided (Legacy/Local)
            if start_time:
                import time

                elapsed = time.time() - start_time
                elapsed_str = self._format_time(elapsed)

                # Use video_position for ETA calculation (remaining video frames)
                if video_position and total_frames and video_position > 0:
                    rate = video_position / elapsed
                    remaining_frames = total_frames - video_position
                    if rate > 0:
                        eta = remaining_frames / rate
                        eta_str = self._format_time(eta)

            # Strategy 2: Use FPS if provided (Worker/Remote)
            elif fps and fps > 0 and video_position is not None:
                # FPS here is detection FPS, but we want video progress for ETA
                # Use video_position for more accurate time estimates
                if total_frames and video_position > 0:
                    # Estimate elapsed from processing speed and processed_frames
                    if processed_frames and processed_frames > 0:
                        elapsed = processed_frames / fps
                        elapsed_str = self._format_time(elapsed)

                        # Expected total processed = total_frames / interval
                        # But we use video position for progress
                        remaining_video_frames = total_frames - video_position
                        # Scale by interval ratio
                        expected_remaining_processed = (
                            remaining_video_frames * (processed_frames / video_position)
                            if video_position > 0
                            else 0
                        )
                        if expected_remaining_processed > 0:
                            eta = expected_remaining_processed / fps
                            eta_str = self._format_time(eta)

            self.gui.analysis_display_widget.update_progress_stats(
                total_frames=total_frames,
                processed_frames=processed_frames,
                detected_frames=detected_frames,
                percent=percent,
                elapsed=elapsed_str,
                eta=eta_str,
            )
            if progress_value is not None:
                self.gui.analysis_display_widget.update_progress(progress_value)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into human-readable time string."""
        if seconds is None or seconds < 0:
            return "-"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}h {m:02d}m {s:02d}s"
        if m:
            return f"{m:d}m {s:02d}s"
        return f"{s:d}s"

    def update_processing_mode(self, report: dict | None = None) -> None:
        """Update UI for processing mode (metadata, task status)."""
        # Logic extracted/adapted to replace legacy _publish_processing_mode

        mode = None
        if report is not None:
            if hasattr(report, "mode"):
                mode = report.mode
            elif isinstance(report, dict):
                mode = report.get("mode")

        if isinstance(mode, str):
            normalized_mode = mode.strip().upper()
            if normalized_mode == ProcessingMode.SINGLE_SUBJECT.name:
                mode = ProcessingMode.SINGLE_SUBJECT
            elif normalized_mode == ProcessingMode.MULTI_TRACK.name:
                mode = ProcessingMode.MULTI_TRACK

        if mode not in (ProcessingMode.SINGLE_SUBJECT, ProcessingMode.MULTI_TRACK):
            fallback_mode = getattr(self.gui, "_active_processing_mode", None)
            if fallback_mode in (ProcessingMode.SINGLE_SUBJECT, ProcessingMode.MULTI_TRACK):
                mode = fallback_mode

        if mode in (ProcessingMode.SINGLE_SUBJECT, ProcessingMode.MULTI_TRACK):
            self.gui._active_processing_mode = mode
            if self.gui.analysis_display_widget:
                self.gui.analysis_display_widget.set_tracking_mode(mode.display_name)
                if self.gui.analysis_display_widget.track_selector_widget:
                    state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
                    self.gui.analysis_display_widget.track_selector_widget.configure(state=state)

            if mode is ProcessingMode.SINGLE_SUBJECT:
                if self.gui.analysis_display_widget:
                    self.gui.analysis_display_widget.track_selector_var.set("Todos")
                    self.gui.analysis_display_widget.set_social_summary(
                        "Interações sociais: não aplicável no modo de sujeito único."
                    )
                self._update_track_options(["Todos"])

        # 1. Get current active video from ProjectManager via Controller
        if hasattr(self.gui, "controller") and self.gui.controller:
            pm = self.gui.controller.project_manager
            active_video = pm.get_active_zone_video()

            combined_metadata: dict = {}
            if active_video:
                entry = pm.find_video_entry(path=active_video)
                if entry:
                    combined_metadata.update(dict(entry.get("metadata") or {}))
                    for key in ("group", "group_display_name", "day", "subject"):
                        value = entry.get(key)
                        if value not in (None, "") and key not in combined_metadata:
                            combined_metadata[key] = value

            # 2. Update UI variables only when metadata exists.
            #    This avoids overwriting values that were already published by
            #    UI_UPDATE_ANALYSIS_METADATA with fallback defaults.
            if combined_metadata:
                group = combined_metadata.get("group")
                day = combined_metadata.get("day")
                subject = combined_metadata.get("subject")

                group_str = str(group) if group not in (None, "") else "Sem Grupo"
                day_str = str(day) if day not in (None, "") else "Sem Dia"
                subject_str = str(subject) if subject not in (None, "") else "Não informado"

                self._apply_analysis_metadata_strings(group_str, day_str, subject_str)

    def update_analysis_task_status(
        self,
        index: int | None = None,
        total: int | None = None,
        experiment_id: str | None = None,
        step: str | None = None,
        progress: float | None = None,
        progress_fraction: float | None = None,
        group: str | None = None,
        day: str | None = None,
        subject: str | None = None,
    ) -> None:
        """Update analysis task status in the UI."""
        # Find the task variable - either in analysis_display_widget or gui
        task_var = None
        analysis_widget = getattr(self.gui, "analysis_display_widget", None)
        if analysis_widget and getattr(analysis_widget, "task_var", None) is not None:
            task_var = analysis_widget.task_var
        elif hasattr(self.gui, "analysis_task_var") and self.gui.analysis_task_var is not None:
            task_var = self.gui.analysis_task_var

        if task_var is None:
            return

        total_videos = max(int(total) if total is not None else 0, 1)
        current_index = max(int(index) if index is not None else 0, 0) + 1

        parts: list[str] = [f"Vídeo {current_index} de {total_videos}"]

        if experiment_id:
            exp_text = str(experiment_id).strip()
            if exp_text:
                parts.append(f"— {exp_text}")

        if step:
            step_text = str(step).strip()
            if step_text:
                if step_text.lower().startswith("etapa:"):
                    step_text = step_text[6:].strip()
                if step_text:
                    parts.append(f"• {step_text}")

        task_var.set(" ".join(parts))

        effective_progress = progress_fraction
        if effective_progress is None:
            effective_progress = progress

        if (
            effective_progress is not None
            and analysis_widget
            and getattr(analysis_widget, "update_progress", None) is not None
        ):
            try:
                clamped_progress = max(0.0, min(1.0, float(effective_progress)))
                analysis_widget.update_progress(clamped_progress)
            except (TypeError, ValueError):
                log.debug("state_sync.progress_fraction_clamp.suppressed", exc_info=True)

        # Update metadata display only when at least one field is explicitly provided;
        # otherwise preserve values already set via UI_UPDATE_ANALYSIS_METADATA.
        if group is not None or day is not None or subject is not None:
            group_str = str(group) if group else "Sem Grupo"
            day_str = str(day) if day else "Sem Dia"
            subject_str = str(subject) if subject else "Não informado"
            self._apply_analysis_metadata_strings(group_str, day_str, subject_str)

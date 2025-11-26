"""State synchronization for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles state observation, UI updates based on state changes, and reset operations.
"""

import structlog

from zebtrack.core.processing_mode import ProcessingMode

log = structlog.get_logger()


class StateSynchronizer:
    """Manages state synchronization between StateManager and UI components."""

    def __init__(self, gui):
        """Initialize StateSynchronizer.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui

    # ========================================================================
    # State Change Subscription
    # ========================================================================

    def subscribe_to_state_changes(self) -> None:
        """Subscribe to StateManager events for reactive UI updates."""
        from zebtrack.core.state_manager import StateCategory

        # Subscribe to recording state changes
        self.gui.controller.state_manager.subscribe(
            StateCategory.RECORDING, self._on_recording_state_changed
        )

        # Subscribe to processing state changes
        self.gui.controller.state_manager.subscribe(
            StateCategory.PROCESSING, self._on_processing_state_changed
        )

        # Subscribe to detector state changes
        self.gui.controller.state_manager.subscribe(
            StateCategory.DETECTOR, self._on_detector_state_changed
        )

        # Subscribe to project state changes
        self.gui.controller.state_manager.subscribe(
            StateCategory.PROJECT, self._on_project_state_changed
        )

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
        """Update UI elements based on processing state."""
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

    def _update_project_ui(self, project_path) -> None:
        """Update UI elements based on project state."""
        if project_path:
            log.debug("gui.project_state.loaded", project_path=str(project_path))
            # Project loaded - update window title or status
        else:
            log.debug("gui.project_state.closed")
            # Project closed - show welcome screen

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
        except Exception:
            pass

        try:
            self.gui.analysis_status_var.set("Nenhuma análise em andamento.")
        except Exception:
            pass

        try:
            self.gui.analysis_task_var.set(self._default_analysis_task_text())
        except Exception:
            pass

        try:
            self._set_analysis_metadata_defaults()
        except Exception:
            pass

    def _reset_roi_and_visual_frames(self) -> None:
        """Handle ROI canvas and visualization frame teardown."""
        if hasattr(self.gui, "video_display") and self.gui.video_display:
            try:
                if self.gui.video_display.canvas.winfo_exists():
                    self.gui.video_display.canvas.pack_forget()
            except Exception:
                pass

        # Destroy viz_frame (parent frame)
        if hasattr(self.gui, "viz_frame") and self.gui.viz_frame:
            try:
                if self.gui.viz_frame.winfo_exists():
                    self.gui.viz_frame.destroy()
            except Exception:
                pass
            self.gui.viz_frame = None

        # Clean up zone tab frame components
        if hasattr(self.gui, "zone_tab_frame") and self.gui.zone_tab_frame:
            try:
                if self.gui.zone_tab_frame.winfo_exists():
                    self.gui.zone_tab_frame.destroy()
            except Exception:
                pass

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
            except Exception:
                pass
            if self.gui._overview_refresh_job is not None:
                try:
                    self.gui.root.after_cancel(self.gui._overview_refresh_job)
                except Exception:
                    pass
                self.gui._overview_refresh_job = None
            self.gui.project_overview_frame = None
            self.gui.project_overview_tree = None
            self.gui.project_status_vars.clear()
            self.gui._project_status_containers.clear()
            self.gui._last_overview_counts = {}

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
        self.gui.show_info(
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
        except Exception:
            pass

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
        from zebtrack.core.processing_mode import ProcessingMode

        if stats and isinstance(stats, dict):
            percentages = stats.get("social_time_percentage") or {}
            if isinstance(percentages, dict) and percentages:
                formatted = []
                for key, value in sorted(
                    percentages.items(),
                    key=lambda item: str(item[0]),
                ):
                    if isinstance(value, (int, float)):
                        formatted.append(f"ID {key}: {value:.1f}%")
                if formatted:
                    if self.gui.analysis_display_widget:
                        self.gui.analysis_display_widget.set_social_summary("Interações sociais: " + ", ".join(formatted))
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
                self.gui.analysis_display_widget.set_social_summary("Interações sociais: aguardando dados.")

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
    ) -> None:
        """Update processing statistics in real-time during video analysis."""
        if self.gui.analysis_display_widget:
            # Format values if needed before passing
            percent = None
            elapsed_str = None
            eta_str = None

            # Calculate and update percentage based on actual frame position
            if total_frames:
                frame_for_percent = current_frame if current_frame is not None else processed_frames
                if frame_for_percent is not None:
                    percent_val = (frame_for_percent / total_frames) * 100
                    percent = f"{percent_val:.1f}%"

            # Calculate elapsed time and ETA
            if start_time:
                import time

                elapsed = time.time() - start_time
                elapsed_str = self._format_time(elapsed)

                frame_for_eta = current_frame if current_frame is not None else processed_frames
                if frame_for_eta and total_frames and frame_for_eta > 0:
                    rate = frame_for_eta / elapsed
                    remaining_frames = total_frames - frame_for_eta
                    if rate > 0:
                        eta = remaining_frames / rate
                        eta_str = self._format_time(eta)
                    else:
                        eta_str = "-"

            self.gui.analysis_display_widget.update_progress_stats(
                total_frames=total_frames,
                processed_frames=processed_frames,
                detected_frames=detected_frames,
                percent=percent,
                elapsed=elapsed_str,
                eta=eta_str
            )

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

    def update_analysis_task_status(
        self,
        *,
        index: int,
        total: int,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        """Update the task summary indicating which video is being processed."""
        if not hasattr(self.gui, "analysis_task_var") or self.gui.analysis_task_var is None:
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

        self.gui.analysis_task_var.set(" ".join(parts))

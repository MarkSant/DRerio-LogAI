"""Analysis view controller — manages analysis tab state, overlays, and mode switching.

Extracted from ApplicationGUI (Phase 4.4) to isolate analysis-related
UI orchestration: view toggling, progress tracking, detection overlay,
processing mode sync, and track selector state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport

if TYPE_CHECKING:
    from tkinter import StringVar, ttk

    from zebtrack.ui.components.analysis_display import AnalysisDisplayWidget
    from zebtrack.ui.components.canvas_manager import CanvasManager
    from zebtrack.ui.components.state_synchronizer import StateSynchronizer
    from zebtrack.ui.components.validation_manager import ValidationManager
    from zebtrack.ui.components.widget_factory import WidgetFactory

log = structlog.get_logger()


class AnalysisViewController:
    """Orchestrates the analysis tab lifecycle: start/stop, overlays, mode sync.

    This class does **not** own any Tk widgets directly.  It reads and writes
    to widget references held on the host ``ApplicationGUI`` instance (via the
    ``gui`` back-reference passed at construction time).

    Attributes:
        gui: Back-reference to the parent ``ApplicationGUI``.
    """

    def __init__(self, gui: Any) -> None:
        self.gui = gui

    # ------------------------------------------------------------------
    # Convenience accessors (reduce ``self.gui.`` noise)
    # ------------------------------------------------------------------

    @property
    def _notebook(self) -> ttk.Notebook | None:
        return self.gui.notebook

    @property
    def _analysis_tab_frame(self) -> ttk.Frame | None:
        return self.gui.analysis_tab_frame

    @property
    def _zone_tab_frame(self) -> ttk.Frame | None:
        return self.gui.zone_tab_frame

    @property
    def _analysis_display(self) -> AnalysisDisplayWidget | None:
        return self.gui.analysis_display_widget

    @property
    def _canvas_manager(self) -> CanvasManager:
        return self.gui.canvas_manager

    @property
    def _state_synchronizer(self) -> StateSynchronizer:
        return self.gui.state_synchronizer

    @property
    def _validation_manager(self) -> ValidationManager:
        return self.gui.validation_manager

    @property
    def _widget_factory(self) -> WidgetFactory:
        return self.gui.widget_factory

    @property
    def _analysis_status_var(self) -> StringVar:
        return self.gui.analysis_status_var

    @property
    def _analysis_task_var(self) -> StringVar | None:
        return self.gui.analysis_task_var

    @property
    def _analysis_profile_var(self) -> StringVar:
        return self.gui.analysis_profile_var

    # ------------------------------------------------------------------
    # View toggling
    # ------------------------------------------------------------------

    def toggle_canvas_view(self) -> None:
        """Toggle between zone drawing view and analysis progress view."""
        if not self._notebook or not self._analysis_tab_frame or not self._zone_tab_frame:
            return

        current_tab = self._notebook.select()
        analysis_tab_id = str(self._analysis_tab_frame)

        if current_tab != analysis_tab_id:
            self.switch_to_analysis_view()
        else:
            self.switch_to_zones_view()

    def switch_to_analysis_view(self) -> None:
        """Switch to analysis progress view.

        If notebook doesn't exist yet (e.g., single video analysis from welcome screen),
        create the main control frame first.
        """
        log.info(
            "analysis_view_controller.switch_to_analysis.called",
            has_notebook=self._notebook is not None,
            has_analysis_tab=self._analysis_tab_frame is not None,
        )

        # Create main control frame if it doesn't exist
        if not self._notebook:
            log.info("analysis_view_controller.switch_to_analysis.creating_main_frame")
            self.gui.project_initializer.create_main_control_frame()

        if not self._notebook or not self._analysis_tab_frame:
            log.warning("analysis_view_controller.switch_to_analysis.missing_widgets_after_create")
            return

        self.gui.canvas_view_mode = "analysis"
        self._notebook.select(self._analysis_tab_frame)
        log.info("analysis_view_controller.switch_to_analysis.done")

    def switch_to_zones_view(self) -> None:
        """Switch to zone drawing view."""
        if not self._notebook or not self._zone_tab_frame:
            return

        self.gui.canvas_view_mode = "zones"
        self._notebook.select(self._zone_tab_frame)

    # ------------------------------------------------------------------
    # Analysis lifecycle
    # ------------------------------------------------------------------

    def start_analysis_view_mode(self) -> None:
        """Start analysis — immediately switch to analysis view and enable toggle."""
        log.info("analysis_view_controller.start.called")
        self.gui.analysis_active = True
        msg = "Preparando análise..."
        self._analysis_status_var.set(msg)
        if self._analysis_display:
            self._analysis_display.set_status(msg)

        if self._analysis_task_var is not None:
            self._analysis_task_var.set("Preparando fila de análise...")
        self._state_synchronizer._set_analysis_metadata_defaults()
        self.reset_analysis_controls()
        self.gui.show_progress_bar()
        if self._analysis_display:
            self._analysis_display.enable_cancel_button()
        self.switch_to_analysis_view()

        # ── Defensive mode sync (race-condition guard) ─────────────────
        mode = self.gui._active_processing_mode
        if mode is ProcessingMode.MULTI_TRACK and hasattr(self.gui, "controller"):
            coordinator = getattr(self.gui.controller, "processing_coordinator", None)
            if coordinator is not None:
                coord_mode = getattr(coordinator, "_active_processing_mode", None)
                if coord_mode is not None and coord_mode is not mode:
                    mode = coord_mode
                    self.gui._active_processing_mode = mode

        if self._analysis_display:
            self._analysis_display.set_tracking_mode(mode.display_name)
            if self._analysis_display.track_selector_widget:
                state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
                self._analysis_display.track_selector_widget.configure(state=state)

    def stop_analysis_view_mode(self) -> None:
        """Stop analysis — disable toggle and return to zones view."""
        self.gui.analysis_active = False
        if self._analysis_display:
            self._analysis_display.disable_cancel_button()
        self.gui.hide_progress_bar()
        self._analysis_status_var.set("Nenhuma análise em andamento.")
        if self._analysis_task_var is not None:
            self._analysis_task_var.set("Nenhuma tarefa em andamento.")
        self._state_synchronizer._set_analysis_metadata_defaults()
        self.reset_analysis_controls()
        self.switch_to_zones_view()

    # ------------------------------------------------------------------
    # Overlay & detection updates
    # ------------------------------------------------------------------

    def update_detection_overlay(self, detections: Any = None, report: Any = None) -> None:
        """Update the detection overlay on the canvas."""
        processing_mode = None
        if report:
            if hasattr(report, "mode"):
                processing_mode = report.mode
            elif isinstance(report, dict):
                processing_mode = report.get("mode")

        is_single_subject = processing_mode == ProcessingMode.SINGLE_SUBJECT

        if processing_mode is None and self.gui.controller:
            try:
                if hasattr(self.gui.controller, "_active_processing_mode"):
                    is_single_subject = (
                        self.gui.controller._active_processing_mode == ProcessingMode.SINGLE_SUBJECT
                    )
            except AttributeError:
                log.warning(
                    "analysis_view_controller.processing_mode_fallback.suppressed",
                    exc_info=True,
                )

        self._canvas_manager.renderer.update_overlay(detections, is_single_subject)

    def update_processing_mode(self, report: ProcessingReport | None) -> None:
        """Update the UI to reflect the active tracking pipeline."""
        if report is None:
            return

        previous_mode = self.gui._active_processing_mode
        mode = report.mode
        self.gui._active_processing_mode = mode

        if self._analysis_display:
            self._analysis_display.set_tracking_mode(mode.display_name)

        if self._analysis_display and self._analysis_display.track_selector_widget:
            state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
            self._analysis_display.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            if self._analysis_display:
                self._analysis_display.track_selector_var.set("Todos")
            self._state_synchronizer._update_track_options(["Todos"])
        elif previous_mode is ProcessingMode.SINGLE_SUBJECT:
            options = self._widget_factory.build_track_options(self.gui._current_detections)
            self._state_synchronizer._update_track_options(options)

    # ------------------------------------------------------------------
    # Progress & metadata
    # ------------------------------------------------------------------

    def update_analysis_progress(self, value: float, status_text: str | None = None) -> None:
        """Update progress bar and status in the analysis overlay."""
        if self._analysis_display:
            if self._analysis_display.progress_bar:
                self._analysis_display.progress_bar["value"] = value * 100
            if status_text:
                self._analysis_display.set_status(status_text)

        if status_text:
            if self._analysis_display:
                self._analysis_display.set_status(status_text)
            self._analysis_status_var.set(status_text)
        self.gui.update_idletasks()

    def set_analysis_status(self, status_text: str) -> None:
        """Set the main analysis status without touching progress values."""
        if self._analysis_display:
            self._analysis_display.set_status(status_text)
        self._analysis_status_var.set(status_text)

    def _set_analysis_profile_text(self, profile_name: str) -> None:
        """Apply the active analysis profile label consistently."""
        text = (profile_name or "default").strip() or "default"
        label = f"Configuração de análise: {text}"
        self._analysis_profile_var.set(label)
        if self._analysis_display:
            self._analysis_display.set_profile(text)

    def update_analysis_metadata(self, *, metadata: dict | None) -> None:
        """Update the metadata display for the currently processed video."""
        metadata = metadata or {}
        log.info(
            "analysis_view_controller.update_analysis_metadata.received",
            metadata_keys=list(metadata.keys()),
            metadata=metadata,
        )
        group_display = self._validation_manager.resolve_group_display(metadata)
        day_display = self._validation_manager.resolve_day_display(metadata)
        subject_display = self._validation_manager.resolve_subject_display(metadata)
        log.info(
            "analysis_view_controller.update_analysis_metadata.resolved",
            group=group_display,
            day=day_display,
            subject=subject_display,
        )

        self._state_synchronizer._apply_analysis_metadata_strings(
            group_display,
            day_display,
            subject_display,
        )

        profile_name = metadata.get("profile")
        if profile_name not in (None, "", "None"):
            self._set_analysis_profile_text(str(profile_name))

    def update_analysis_task_status(
        self,
        *,
        index: int | None = None,
        total: int | None = None,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        """Update the task summary indicating which video is being processed."""
        self._state_synchronizer.update_analysis_task_status(
            index=index,
            total=total,
            experiment_id=experiment_id,
            step=step,
        )

    def update_analysis_profile(self, profile_name: str) -> None:
        """Update the label describing the active analysis profile."""
        self._set_analysis_profile_text(profile_name)
        self.reset_analysis_controls()

    # ------------------------------------------------------------------
    # Controls & track selector
    # ------------------------------------------------------------------

    def reset_analysis_controls(self) -> None:
        """Reset track selector state and cached frames."""
        self.gui._current_detections = []
        self.gui._last_analysis_frame = None
        self.gui._analysis_overlay_image = None

        if self._analysis_display:
            self._analysis_display.track_selector_var.set("Todos")
            self._state_synchronizer._update_track_options(["Todos"])

            if self._analysis_display.track_selector_widget:
                state = (
                    "disabled"
                    if self.gui._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
                    else "readonly"
                )
                self._analysis_display.track_selector_widget.configure(state=state)

    def build_track_options(self, detections: list[tuple]) -> list[str]:
        """Build the list of track options from detection data."""
        observed: set[str] = set()
        for det in detections:
            if len(det) < 6:
                continue
            track_id = det[5]
            if track_id is None:
                continue
            text = str(track_id).strip()
            if text:
                observed.add(text)

        ordered = sorted(observed, key=str)
        return ["Todos", *ordered]

    def on_track_selection_changed(self, _event: Any = None) -> None:
        """Handle track selector change — re-render the last analysis frame."""
        self._canvas_manager._render_last_analysis_frame()

    # ------------------------------------------------------------------
    # Widget cleanup helpers
    # ------------------------------------------------------------------

    def cleanup_single_analysis_button(self) -> None:
        """Destroys the single analysis button if it exists."""
        from tkinter import TclError

        if (
            hasattr(self.gui, "start_single_analysis_btn")
            and self.gui.start_single_analysis_btn is not None
        ):
            if self.gui.start_single_analysis_btn.winfo_exists():
                self.gui.start_single_analysis_btn.destroy()
            self.gui.start_single_analysis_btn = None

        zone_controls = getattr(self.gui, "zone_controls", None)
        if zone_controls:
            try:
                zone_controls.hide_single_analysis_options()
            except (TclError, AttributeError):
                log.warning(
                    "analysis_view_controller.hide_single_analysis_options.suppressed",
                    exc_info=True,
                )

    def reset_analysis_widgets(self) -> None:
        """Encapsula a limpeza e destruição de widgets da aba de análise."""
        self._state_synchronizer._reset_analysis_media()
        self._state_synchronizer._reset_analysis_progress_and_metadata()
        self._state_synchronizer._reset_roi_and_visual_frames()
        self._state_synchronizer._destroy_notebook_and_main_controls()
        self.gui.analysis_tab_frame = None

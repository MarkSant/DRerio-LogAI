"""Single video workflow — manages the one-off video analysis flow.

Extracted from ApplicationGUI (Phase 4.4) to isolate the workflow that
lets a user pick a single video, define zones, and start processing
without a full project context.
"""

from __future__ import annotations

from tkinter import TclError, ttk
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui.decorators import public_api
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class SingleVideoWorkflow:
    """Handles the single-video analysis flow: file selection, zone setup, processing.

    All methods operate on the host *ApplicationGUI* via ``gui`` back-reference.
    """

    def __init__(
        self,
        gui: ApplicationGUI,
        *,
        dialog_manager: DialogManager | None = None,
    ) -> None:
        self.gui = gui
        self._dialog_manager = dialog_manager

    @property
    def dialog_manager(self) -> DialogManager:
        """DialogManager instance (injected or resolved from gui)."""
        return self._dialog_manager or self.gui.dialog_manager

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    @public_api
    def on_analyze_single_video_clicked(self) -> None:
        """Handle single video analysis. Delegates to EventDispatcher."""
        log.info("single_video_workflow.on_analyze_clicked.START")
        try:
            self.gui.event_dispatcher.handle_analyze_single_video_clicked()
            log.info("single_video_workflow.on_analyze_clicked.END")
        except Exception as e:  # except Exception justified: UI error boundary for button click
            log.error("single_video_workflow.on_analyze_clicked.ERROR", error=str(e))
            self.dialog_manager.show_error("Erro", f"Falha ao iniciar análise: {e}")

    # ------------------------------------------------------------------
    # Zone definition setup
    # ------------------------------------------------------------------

    @public_api
    def setup_zone_definition_for_single_video(self, video_path: str, config: dict) -> None:
        """Prepare and display the zone configuration tab for a single video."""
        gui = self.gui
        log.info(
            "single_video_workflow.setup_zone_definition.called",
            video_path=video_path,
            has_config=bool(config),
        )
        # Reset analysis UI elements for a clean setup
        gui.hide_progress_bar()
        gui.analysis_status_var.set("Nenhuma análise em andamento.")
        if gui.analysis_display_widget and gui.analysis_display_widget.video_label:
            try:
                gui.analysis_display_widget.video_label.configure(image="")
                gui._analysis_overlay_image = None
            except (TclError, AttributeError):
                log.debug("single_video_workflow.video_label_clear.suppressed", exc_info=True)

        gui.pending_single_video_path = video_path
        gui.pending_single_video_config = config

        # Save num_aquariums to global settings so
        # ProcessingCoordinator can see it during auto-detection
        if config and "num_aquariums" in config and gui.settings:
            try:
                gui.settings.analysis_config.num_aquariums = int(config["num_aquariums"])
            except (KeyError, ValueError, TypeError, AttributeError) as e:
                log.warning("single_video_workflow.update_settings_failed", error=str(e))

        # Ensure zone edits persist under the selected video
        gui.controller.project_manager.set_active_zone_video(video_path)

        # Open the main project view if it is not already open
        if not gui.notebook:
            gui.project_initializer.create_main_control_frame()

        gui.canvas_manager.display_roi_video_frame(video_path)
        if gui.notebook:
            gui.notebook.select(gui.zone_tab_frame)

        # Clear template selection for single video workflow
        gui.roi_template_manager.refresh_templates(clear_selection=True)

        # Add a "Start Analysis" button specific to this flow
        if not gui.start_single_analysis_btn:
            btn = ttk.Button(
                gui.fixed_button_frame,
                text="Iniciar Análise de Vídeo Único",
                command=self._on_start_single_video_processing_clicked,
            )
            btn.pack(side="bottom", fill="x", pady=5)
            gui.start_single_analysis_btn = btn

        if gui.start_single_analysis_btn:
            gui.start_single_analysis_btn.config(state="normal")

        gui.state_synchronizer.prepare_single_video_ui_state(config)

    # ------------------------------------------------------------------
    # Auto-detect
    # ------------------------------------------------------------------

    def on_auto_detect_clicked(self, stabilization_frames: int | str | None = None) -> None:
        """Handle the auto-detect button."""
        gui = self.gui

        # Prevent editing during analysis
        if gui.analysis_active:
            self.dialog_manager.show_warning(
                "Análise em Progresso",
                "Não é possível detectar zonas durante a análise de vídeo.",
            )
            return

        raw_value = (
            stabilization_frames
            if stabilization_frames is not None
            else gui.stabilization_frames_var.get()
        )

        try:
            stabilization_frames_int = int(raw_value)
            if stabilization_frames_int <= 0:
                raise ValueError
        except (ValueError, TypeError):
            self.dialog_manager.show_warning(
                "Entrada Inválida",
                "O número de frames para análise deve ser um número inteiro positivo.",
            )
            return

        # Keep UI entry in sync with validated value
        gui.stabilization_frames_var.set(str(stabilization_frames_int))

        # Clear any old interactive polygon before starting a new detection
        gui.canvas_manager.clear_interactive_polygon()

        # Get the currently active video
        video_path = None
        if hasattr(gui, "controller") and gui.controller:
            pm = gui.controller.project_manager
            video_path = pm.get_active_zone_video()

        # Fallback to pending_single_video_path for single video mode
        if not video_path:
            video_path = getattr(gui, "pending_single_video_path", None)

        log.info(
            "single_video_workflow.auto_detect.video_resolved",
            video_path=video_path,
            from_active_zone_video=bool(
                gui.controller.project_manager.get_active_zone_video()
                if hasattr(gui, "controller")
                else False
            ),
        )

        gui.event_dispatcher.publish_event(
            UIEvents.ZONE_AUTO_DETECT,
            {
                "video_path": video_path,
                "stabilization_frames": stabilization_frames_int,
            },
        )

    # ------------------------------------------------------------------
    # Start processing
    # ------------------------------------------------------------------

    def _on_start_single_video_processing_clicked(self) -> None:
        """Handle the 'Start Analysis' button in the single video flow."""
        gui = self.gui

        # If the user was editing a polygon, prompt for confirmation before saving.
        if gui.edited_polygon_points:
            response = gui.dialog_manager.confirm_save_polygon_before_analysis()
            if response is None:
                # Cancel pressed, abort analysis
                return
            elif response:
                # Yes pressed, save polygon
                gui.controller.analysis_vm.save_manual_arena(gui.edited_polygon_points)
                gui.canvas_manager.clear_interactive_polygon()
            else:
                # No pressed, discard changes
                gui.canvas_manager.clear_interactive_polygon()

        # 1. Get the zone data that the user drew
        zone_data = gui._get_zone_data_for_active_context()  # type: ignore[attr-defined]

        # Validation for Single vs Multi Aquarium
        from zebtrack.core.detection import MultiAquariumZoneData

        if isinstance(zone_data, MultiAquariumZoneData):
            if not zone_data.aquariums:
                self.dialog_manager.show_error("Erro", "Nenhum aquário foi definido.")
                return
        elif not zone_data.polygon:
            self.dialog_manager.show_error(
                "Erro",
                "A área principal do aquário (polígono) não foi definida.",
            )
            return

        updated_config = gui.validation_manager.compose_single_video_runtime_config()
        if updated_config is None:
            return
        gui.pending_single_video_config = updated_config

        # 2. Disable the button and publish the event
        if gui.start_single_analysis_btn:
            gui.start_single_analysis_btn.config(state="disabled")
        gui.event_dispatcher.publish_event(
            UIEvents.VIDEO_START_SINGLE_PROCESSING,
            {
                "video_path": gui.pending_single_video_path,
                "config": gui.pending_single_video_config,
                "zone_data": zone_data,
            },
        )

        # 3. Clear the pending state
        gui.pending_single_video_path = None
        gui.pending_single_video_config = None

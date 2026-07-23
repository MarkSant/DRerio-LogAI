"""Single video workflow — manages the one-off video analysis flow.

Extracted from ApplicationGUI (Phase 4.4) to isolate the workflow that
lets a user pick a single video, define zones, and start processing
without a full project context.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import TclError, ttk
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui import payloads
from zebtrack.ui.decorators import public_api
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from zebtrack.core.services.zone_context_service import ZoneContextService
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
        zone_context_service: ZoneContextService | None = None,
    ) -> None:
        self.gui = gui
        self._dialog_manager = dialog_manager
        self._zone_context_service = zone_context_service

    @property
    def dialog_manager(self) -> DialogManager:
        """DialogManager instance (injected or resolved from gui)."""
        return self._dialog_manager or self.gui.dialog_manager

    @property
    def zone_context_service(self) -> ZoneContextService:
        """ZoneContextService instance (injected or resolved from gui)."""
        if self._zone_context_service is not None:
            return self._zone_context_service
        zone_context_service = getattr(self.gui, "_zone_context_service", None)
        assert zone_context_service is not None, "ZoneContextService must be available"
        return zone_context_service

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
    def setup_zone_definition_for_single_video(self, video_path: Path | str, config: dict) -> None:
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

        gui.pending_single_video_path = str(video_path)
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

        # Projetos LIVE não têm arquivo de vídeo para auto-detectar — a arena
        # precisa ser detectada a partir do feed da câmera ao vivo. Roteia para
        # o fluxo de calibração pela câmera (mesmo caminho do
        # ZoneCalibrationDialog → "auto") em vez de publicar ZONE_AUTO_DETECT
        # com um path vazio, que cascateia no ``AquariumDetector`` tentando
        # abrir ``.`` como vídeo e falhando com "Cannot open video file: .".
        if not video_path and self._route_live_auto_detect(gui, stabilization_frames_int):
            return

        # Read num_aquariums para a auto-detecção multi-aquário.
        #
        # A fonte AUTORITATIVA no fluxo de vídeo único é o config submetido pelo
        # usuário (``pending_single_video_config``), e NÃO o
        # ``settings.analysis_config.num_aquariums`` global. Esse cache global é
        # ressincronizado para a contagem do projeto (default 1) sempre que a UI do
        # projeto é (re)montada — ex.: ``ProjectInitializer._sync_aquarium_count_from_project`` —
        # então logo após escolher "2 aquários" no diálogo ele já pode ter voltado a
        # 1, fazendo a auto-detecção cair em modo single (multi=False). Ler do config
        # pendente torna a detecção imune a esse reset.
        num_aquariums = 1
        pending_config = getattr(gui, "pending_single_video_config", None)
        if isinstance(pending_config, dict) and pending_config.get("num_aquariums") is not None:
            try:
                num_aquariums = int(pending_config["num_aquariums"])
            except (TypeError, ValueError):
                num_aquariums = 1
        elif gui.settings and hasattr(gui.settings, "analysis_config"):
            num_aquariums = gui.settings.analysis_config.num_aquariums

        gui.event_dispatcher.publish_event(
            UIEvents.ZONE_AUTO_DETECT,
            payloads.ZoneAutoDetectPayload(
                video_path=str(video_path) if video_path else "",
                stabilization_frames=stabilization_frames_int,
                expected_count=num_aquariums if num_aquariums >= 2 else None,
            ),
        )

    def _route_live_auto_detect(self, gui: ApplicationGUI, stabilization_frames: int) -> bool:
        """Route auto-detect to the live camera when the project is LIVE.

        Returns ``True`` when the request was handled here (the caller must then
        stop), ``False`` when this is not a live project and the caller should
        fall through to the pre-recorded video path.

        Live projects have no video file: the arena is detected from the camera
        via ``LiveCalibrationCoordinator.run_live_calibration`` — the same call
        the ``ZoneCalibrationDialog`` "auto" option makes. 30 stabilization
        frames give the camera time to adjust exposure before detection.
        """
        controller = getattr(gui, "controller", None)
        project_manager = getattr(controller, "project_manager", None) if controller else None
        if project_manager is None or project_manager.get_project_type() != "live":
            return False

        calibration_coordinator = getattr(controller, "live_calibration_coordinator", None)
        if calibration_coordinator is None:
            log.error("single_video_workflow.auto_detect.live_no_calibration_coordinator")
            self.dialog_manager.show_error(
                "Erro",
                "Não foi possível iniciar a detecção pela câmera "
                "(coordenador de calibração indisponível).",
            )
            return True

        log.info("single_video_workflow.auto_detect.live_camera_route")
        try:
            # Runs synchronously on the UI thread (opens a modal preview dialog),
            # mirroring LiveCalibrationCoordinator's own "auto" calibration path.
            calibration_coordinator.run_live_calibration(
                stabilization_frames=max(stabilization_frames, 30),
                show_preview=True,
            )
        except Exception as e:  # except Exception justified: camera + cv2 pipeline
            log.error("single_video_workflow.auto_detect.live_failed", error=str(e), exc_info=True)
            self.dialog_manager.show_error("Erro", f"Falha na detecção automática pela câmera: {e}")
        return True

    # ------------------------------------------------------------------
    # Start processing
    # ------------------------------------------------------------------

    def _on_start_single_video_processing_clicked(self) -> None:
        """Handle the 'Start Analysis' button in the single video flow.

        Envolto em error boundary: qualquer falha aqui (ou no handler síncrono de
        ``VIDEO_START_SINGLE_PROCESSING``, despachado dentro de ``publish_event``)
        precisa virar diálogo + log, e não sumir. Sem isto, exceções no caminho de
        início eram engolidas e o usuário via "nada acontece".
        """
        try:
            self._start_single_video_processing()
        except Exception as e:  # except Exception justified: UI error boundary for button click
            log.error("single_video_workflow.start.error", error=str(e), exc_info=True)
            self.dialog_manager.show_error("Erro", f"Falha ao iniciar análise: {e}")

    def _start_single_video_processing(self) -> None:
        """Validate zones/config and publish ``VIDEO_START_SINGLE_PROCESSING``."""
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
        zone_data = self.zone_context_service.get_zone_data_for_active_context(
            pending_single_video_path=getattr(gui, "pending_single_video_path", None),
        )

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
            payloads.VideoStartSingleProcessingPayload(
                video_path=gui.pending_single_video_path or "",
                config=gui.pending_single_video_config,
                zone_data=zone_data,
            ),
        )

        # 3. Clear the pending state
        gui.pending_single_video_path = None
        gui.pending_single_video_config = None

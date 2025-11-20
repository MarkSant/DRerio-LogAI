"""UI state and controller logic extracted from MainViewModel.

Sprint 28 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.weight_manager import OpenVINOExportError
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

logger = structlog.get_logger()


class UIStateController:
    """Controls UI state synchronization and updates.

    Extracted from MainViewModel in Sprint 28 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Weight management UI operations
    - UI status updates and feedback
    - Zone UI synchronization
    - Complex validation with UI dialogs
    - Processing UI state management
    - Diagnostic UI updates
    - Core UI utilities
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.view = main_view_model.view
        self.root = main_view_model.root
        self.state_manager = main_view_model.state_manager
        self.ui_coordinator = main_view_model.ui_coordinator
        self.ui_event_bus = main_view_model.ui_event_bus
        self.project_manager = main_view_model.project_manager
        self.weight_manager = main_view_model.weight_manager
        self.detector_service = main_view_model.detector_service
        self.model_service = main_view_model.model_service
        self.settings = main_view_model.settings
        self.detector_coordinator = main_view_model.hardware_coordinator  # Mapped to HardwareCoordinator
        self.project_workflow_service = main_view_model.project_workflow_service

    # ========================================================================
    # Group H: Core Utilities (extract first - most fundamental)
    # ========================================================================

    def _schedule_on_ui(self, func, *args, **kwargs):
        """
        Schedule a function to run on the UI thread.

        Phase 4: Delegates to UICoordinator for centralized UI scheduling.
        Kept for backward compatibility with existing code.
        """
        self.ui_coordinator.schedule(func, *args, **kwargs)

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Request a refresh of project-related UI components on the main thread."""
        if not getattr(self, "view", None):
            return

        refresh_fn = getattr(self.view, "refresh_project_views", None)
        if not callable(refresh_fn):
            return

        self._schedule_on_ui(
            refresh_fn,
            reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    # ========================================================================
    # Group A: Weight Management
    # ========================================================================

    def manage_weights(self):
        """Open the weight management dialog."""
        self.ui_event_bus.publish_event(Events.UI_OPEN_MANAGE_WEIGHTS_DIALOG)

    def add_new_weight(
        self, path: Path | str, set_as_default: bool, weight_type: str | None = None
    ):
        """Add a new weight with type classification."""
        path = Path(path) if isinstance(path, str) else path
        try:
            self.weight_manager.add_weight(path, set_as_default, weight_type)
            new_name = path.name
            # Refresh UI on success
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_WEIGHTS_LIST,
                {"weights": self.main_view_model.get_all_weight_names()},
            )
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": new_name})
            self.set_active_weight(new_name)  # This will also trigger conversion check
        except (ValueError, FileNotFoundError, OSError) as e:
            logger.error("controller.add_weight.failed", error=str(e), path=str(path))
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro ao Adicionar Peso", "message": str(e)},
            )

    def delete_weight(self, name: str):
        """Delete a model weight from the catalog.

        Args:
            name: Name of the weight to delete.
        """
        try:
            self.weight_manager.delete_weight(name)
            # Refresh UI on success
            self.ui_event_bus.publish_event(
                Events.UI_UPDATE_WEIGHTS_LIST,
                {"weights": self.main_view_model.get_all_weight_names()},
            )
            default_name, _ = self.main_view_model._safe_get_default_weight()
            self.ui_event_bus.publish_event(
                Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": default_name}
            )
            self.set_active_weight(default_name, None)
        except (ValueError, OSError) as e:
            logger.error("controller.delete_weight.failed", error=str(e), name=name)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro ao Excluir Peso", "message": str(e)},
            )

    def set_active_weight(self, name: str | None, dialog=None):
        """Set the active model weight and update UI accordingly.

        Args:
            name: Name of the weight to set as active.
            dialog: Optional dialog to update with OpenVINO status.
        """
        candidate = name or ""
        available = set(self.main_view_model.get_all_weight_names())

        if candidate and candidate in available:
            self.main_view_model.active_weight_name = candidate
            logger.info("controller.active_weight.set", name=candidate)
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": candidate})
            self.update_openvino_status(dialog)
            if self.main_view_model.use_openvino:
                self.convert_active_weight_to_openvino(dialog)
        else:
            if candidate:
                logger.warning("controller.active_weight.not_found", name=name)
            self.main_view_model.active_weight_name = ""
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": ""})
            self.update_openvino_status(dialog)

        if not self.main_view_model._using_project_overrides:
            self.main_view_model._global_model_defaults["active_weight"] = (
                self.main_view_model.active_weight_name or None
            )

    def load_new_weight(
        self,
        filepath: Path | str | None = None,
        weight_type: str | None = None,
        choice: str | None = None,
    ):
        """Handle the 'Load New Weight' button click."""
        if filepath is not None:
            filepath = Path(filepath) if isinstance(filepath, str) else filepath
        if filepath is None:
            self.ui_event_bus.publish_event(Events.UI_REQUEST_WEIGHT_FILE)
            return

        # Classify weight type by filename
        filename = os.path.basename(filepath)
        if weight_type is None:
            weight_type = self.main_view_model.classify_weight_type(filename)

        # If type cannot be determined, ask user
        if weight_type is None:
            self.ui_event_bus.publish_event(Events.UI_REQUEST_WEIGHT_TYPE)
            return

        # Ask user what to do with the new weight
        if choice is None:
            self.ui_event_bus.publish_event(
                Events.UI_REQUEST_WEIGHT_ACTION, {"weight_type": weight_type}
            )
            return

        if choice == "cancel":
            return
        elif choice == "yes":
            # Add as new default for this type
            self.add_new_weight(path=filepath, set_as_default=True, weight_type=weight_type)
        else:  # 'no'
            # Add as an alternative
            self.add_new_weight(path=filepath, set_as_default=False, weight_type=weight_type)

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        """Enable or disable OpenVINO inference mode.

        Args:
            use_openvino: True to enable OpenVINO, False to use PyTorch.
            dialog: Optional dialog to update with status.
        """
        self.main_view_model.use_openvino = bool(use_openvino)
        logger.info("controller.openvino_usage.set", enabled=self.main_view_model.use_openvino)
        self.ui_event_bus.publish_event(
            Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": self.main_view_model.use_openvino}
        )
        if self.main_view_model.use_openvino and self.main_view_model.active_weight_name:
            # Trigger conversion if switching to OpenVINO and model isn't converted
            self.convert_active_weight_to_openvino(dialog)
        self.update_openvino_status(dialog)

        if not self.main_view_model._using_project_overrides:
            self.main_view_model._global_model_defaults["use_openvino"] = (
                self.main_view_model.use_openvino
            )

    def convert_active_weight_to_openvino(self, dialog):
        """
        Convert the active weight to OpenVINO format.

        Delegates conversion logic to ModelService (Phase 2.1).
        MainViewModel only handles UI updates and status feedback.
        """
        if not self.main_view_model.active_weight_name:
            return

        if self.ui_event_bus:
            active_weight = self.main_view_model.active_weight_name
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS,
                {"message": f"Convertendo {active_weight} para OpenVINO..."},
            )

        try:
            # Delegate conversion to ModelService
            self.model_service.convert_to_openvino(self.main_view_model.active_weight_name)
            self.update_openvino_status(dialog)
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Verificação de conversão concluída. Pronto."},
                )
        except OpenVINOExportError as e:
            logger.error(
                "controller.convert_openvino.failed",
                error=str(e),
                weight_name=self.main_view_model.active_weight_name,
            )
            self.update_openvino_status(dialog)
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {"title": "Erro na Conversão OpenVINO", "message": str(e)},
                )
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Erro na conversão OpenVINO."},
                )

    # ========================================================================
    # Group B: UI Status Updates
    # ========================================================================

    def update_openvino_status(self, dialog=None):
        """Update the status label in the GUI based on the current state."""
        status = self.main_view_model.get_openvino_status()
        if dialog:
            dialog.update_openvino_status_label(status)
        self.ui_event_bus.publish_event(Events.UI_UPDATE_OPENVINO_STATUS, {"status": status})

    def update_detector_parameters(
        self,
        params: dict[str, float],
        *,
        reset_overrides: bool = False,
        scope: str = "global",
    ) -> bool:
        """
        Apply detector threshold updates and persist them when possible.

        Sprint 7: Delegates to DetectorCoordinator.
        """
        try:
            success = self.detector_coordinator.update_detector_parameters(
                params=params,
                reset_overrides=reset_overrides,
                scope=scope,
            )

            if success:
                self.ui_event_bus.publish_event(
                    Events.UI_SET_STATUS,
                    {"message": "Parâmetros do detector atualizados."},
                )

            return success
        except ValueError as e:
            logger.error("controller.detector.update.validation_failed", error=str(e))
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {"title": "Erro de Validação", "message": str(e)},
            )
            return False

    # ========================================================================
    # Group C: Zone UI Updates
    # ========================================================================

    def setup_detector_zones(self):
        """
        Load zone data from project and sets it on the detector instance.

        Sprint 7: Delegates to DetectorCoordinator.
        """
        # Delegate to DetectorCoordinator (all params None = load from project)
        success = self.detector_coordinator.configure_zones(
            zones_data=None,
            video_width=None,
            video_height=None,
        )

        if not success:
            logger.warning("main_view_model.setup_detector_zones.failed")
            return

        # UI logic: notify if no arena polygon defined
        zone_data = self.project_manager.get_zone_data()
        if not zone_data.polygon:
            if self.project_manager.get_project_type() == "pre-recorded":
                self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Necessária",
                        "message": "Erro: A área de processamento principal (aquário) não foi "
                        "definida. Por favor, defina-a na aba 'Configuração de Zonas' "
                        "antes de continuar.",
                    },
                )

    def apply_roi_template(self, template: dict[str, Any]) -> None:
        """Aplica um template de ROI ao vídeo ativo."""
        pm = self.project_manager
        active_video = pm.get_active_zone_video()
        if not active_video:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Vídeo não selecionado",
                    "message": "Selecione um vídeo na lista antes de aplicar o template.",
                },
            )
            return

        template_name = template.get("name") or template.get("display_name") or "Template"
        try:
            template_zone = pm.load_roi_template(
                template_name,
                location=template.get("location"),
                file_path=template.get("file"),
            )
            pm.save_zone_data(template_zone, video_path=active_video, persist=bool(pm.project_path))
            pm.set_active_zone_video(active_video)
            self.setup_detector_zones()
            self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES)
            self.ui_event_bus.publish_event(Events.UI_UPDATE_ZONE_LIST)
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Template Aplicado",
                    "message": f"As zonas foram atualizadas com o template '{template_name}'.",
                },
            )
        except FileNotFoundError as exc:
            logger.error(
                "controller.roi_templates.file_missing", template=template_name, error=str(exc)
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Arquivo não encontrado",
                    "message": "O arquivo associado ao template não foi encontrado.",
                },
            )
        except Exception as exc:
            logger.error(
                "controller.roi_templates.apply_failed", error=str(exc), template=template_name
            )
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR, {"title": "Erro ao aplicar template", "message": str(exc)}
            )

    def update_main_arena(self, polygon_points: list[list[int]]):
        """
        Update the main arena polygon in the project's zone data.

        Phase 2.1: Logic simplified but maintains compatibility with existing tests.
        ProjectService methods available for future direct usage.
        """
        logger.info("controller.zone.update_arena", points=len(polygon_points))

        # Update in-memory zone data
        zone_data = self.project_manager.get_zone_data()
        zone_data.polygon = polygon_points
        self.project_manager.save_zone_data(zone_data)

        # After updating, we need to reload the zones in the detector
        self.setup_detector_zones()
        logger.info("controller.zone.update_arena.success")

    # ========================================================================
    # Group D: User Feedback
    # ========================================================================

    def _show_post_creation_guide(self, wizard_metadata: dict):
        """
        Display a contextual onboarding message after project creation.

        Phase 5: Refactored to use ProjectWorkflowService for guide generation.
        """
        # Check view-level suppression flag
        if getattr(self.view, "suppress_post_creation_guide", False):
            logger.info("controller.post_creation_guide.skipped", reason="view_flag")
            return

        # Generate guide content via service
        guide = self.project_workflow_service.generate_post_creation_guide(
            wizard_metadata=wizard_metadata,
            check_suppression=True,
        )

        # Display guide if generated
        if guide:
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_INFO, {"title": guide["title"], "message": guide["message"]}
            )

    def _show_cancel_feedback(self) -> None:
        """Update UI immediately after a cancellation request."""
        if self.main_view_model._cancel_feedback_displayed:
            return

        self.main_view_model._cancel_feedback_displayed = True

        # Switch back to zone view and clear progress indicators right away
        self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
        self.ui_coordinator.set_status(
            self.view,
            "Cancelamento solicitado. Finalizando tarefas em segundo plano...",
        )

        # Provide immediate dialog feedback so the user knows reports won't be generated
        self.ui_coordinator.show_info(
            self.view,
            "Análise cancelada",
            "A análise de vídeo foi cancelada. Nenhum relatório será gerado.",
        )

    def _handle_validation_error(self, validation_result) -> bool:
        """
        Handle validation errors by showing appropriate UI messages.

        Sprint 13: Consolidated error handling from 3 workflow methods.
        Reduces duplication of error code -> UI event mapping.

        Args:
            validation_result: ValidationResult from ProcessingCoordinator

        Returns:
            bool: True if validation passed, False if error was shown
        """
        if validation_result.is_valid:
            return True

        # Map error codes to appropriate UI events
        error_code = validation_result.error_code
        error_message = validation_result.error_message

        if error_code == "processing_already_active":
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Análise em Andamento",
                    "message": error_message,
                },
            )
        elif error_code == "no_project_loaded":
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Nenhum Projeto Carregado",
                    "message": error_message,
                },
            )
        elif error_code == "no_videos":
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Nenhum Vídeo Encontrado",
                    "message": error_message,
                },
            )
        elif error_code == "no_weight_selected":
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Peso Não Selecionado",
                    "message": error_message,
                },
            )
        else:
            # Generic error fallback
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_ERROR,
                {
                    "title": "Erro de Validação",
                    "message": error_message,
                },
            )

        return False

    # ========================================================================
    # Group E: Complex Validation (LARGEST METHOD - HIGH RISK)
    # ========================================================================

    def _validate_zones_with_ui(self) -> bool:
        """
        Validate that zones are defined, with UI dialogs for user interaction.

        Sprint 13: Extracted from start_project_processing_workflow().
        Handles complex zone validation including:
        - Main arena validation with user dialogs
        - Default arena creation if user chooses
        - ROI warning (optional)

        Returns:
            bool: True if zones are valid/created, False if user cancelled
        """
        zone_data = self.project_manager.get_zone_data()

        # Check if main arena is defined
        if not zone_data or not zone_data.polygon:
            logger.warning("workflow.project_processing.no_main_arena")

            response = self.view.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É necessário definir a arena principal para análise precisa.\n"
                "Deseja definir agora antes de processar?",
            )

            if response:
                # Switch to zone tab and guide user
                self.ui_event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                # Load frame from first video if available
                first_video = self.project_manager.get_next_video()
                if first_video:
                    self.ui_event_bus.publish_event(
                        Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                    )

                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Defina a Arena Principal",
                        "message": "Por favor:\n"
                        "1. Use 'Detectar Aquário (Auto)' ou\n"
                        "2. Desenhe manualmente o polígono principal\n"
                        "3. Depois volte para adicionar vídeos",
                    },
                )
                return False
            else:
                # Offer default arena as fallback
                if not self.view.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    logger.info("workflow.project_processing.cancelled_no_arena")
                    return False

                # Create default arena based on first video
                first_video = self.project_manager.get_next_video()
                if first_video:
                    import cv2

                    cap = cv2.VideoCapture(first_video)
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()

                    default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                    success = self.main_view_model.set_main_arena_polygon(default_arena)
                    if success:
                        logger.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_INFO,
                            {
                                "title": "Arena Padrão Criada",
                                "message": f"Arena padrão criada ({width}x{height})\n"
                                "Recomenda-se ajustar manualmente depois.",
                            },
                        )
                    else:
                        self.ui_event_bus.publish_event(
                            Events.UI_SHOW_ERROR,
                            {"title": "Erro", "message": "Não foi possível criar arena padrão"},
                        )
                        return False
                else:
                    self.ui_event_bus.publish_event(
                        Events.UI_SHOW_ERROR,
                        {"title": "Erro", "message": "Nenhum vídeo encontrado no projeto"},
                    )
                    return False

        # Warn about missing ROIs (optional but informative)
        if not zone_data.roi_polygons:
            if not self.view.ask_ok_cancel(
                "Nenhuma ROI Definida",
                "Nenhuma Área de Interesse (ROI) foi definida.\n\n"
                "A análise usará apenas a arena principal.\n"
                "Para análises detalhadas, considere definir ROIs.\n\n"
                "Deseja continuar?",
            ):
                logger.info("workflow.project_processing.cancelled_by_user_no_roi")
                return False

        logger.info(
            "workflow.project_processing.zones_validated",
            has_main_arena=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        return True

    # ========================================================================
    # Group F: Processing UI
    # ========================================================================

    def _activate_analysis_view_mode(self) -> None:
        """Ensure the analysis tab is active so frames scale correctly."""
        if self.ui_event_bus:
            self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_ANALYSIS_VIEW)
        else:
            self.ui_coordinator.update_view(self.view, "start_analysis_view_mode")

    def _prepare_processing_ui(self, total_videos: int) -> None:
        # Phase 4: Use UICoordinator for UI updates
        self.ui_coordinator.show_progress_bar(self.view)
        self.ui_coordinator.schedule_after(
            0,
            lambda: self.view.set_status(f"Iniciando processamento para {total_videos} vídeos..."),
        )
        self.project_manager.set_active_zone_video(None)

    def _finalize_processing(
        self,
        *,
        was_cancelled: bool,
        videos_to_process: list[dict],
        final_output_dir: str,
    ) -> None:
        # Phase 4: Use UICoordinator for UI updates
        self.project_manager.set_active_zone_video(None)
        self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
        self.ui_coordinator.hide_progress_bar(self.view)

        if was_cancelled:
            self.ui_coordinator.show_info(
                self.view, "Cancelado", "A análise de vídeo foi cancelada."
            )
        else:
            self.ui_coordinator.show_info(
                self.view,
                "Processamento Concluído",
                f"Processamento de {len(videos_to_process)} vídeo(s) concluído com sucesso.\n"
                f"Resultados salvos em:\n{final_output_dir}",
            )

    # ========================================================================
    # Group G: Diagnostic UI
    # ========================================================================

    def _update_diagnostic_progress(
        self,
        progress_dialog,
        message: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """Thread-safe progress dialog update helper."""
        if not progress_dialog:
            return

        if current is None or total is None:
            self.root.after(0, progress_dialog.update_progress, message)
            return

        self.root.after(0, progress_dialog.update_progress, message, current, total)

    def _finish_progress_dialog(self, progress_dialog) -> None:
        """Safely close the diagnostic progress dialog."""
        if progress_dialog:
            self.root.after(0, progress_dialog.finish)

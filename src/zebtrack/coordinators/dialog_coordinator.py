"""Coordinator for user dialogs and confirmations.

Extracted from MainViewModel as part of Phase 1 of the refactoring
plan (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsible for coordinating all user dialogs and confirmations.
"""

from typing import TYPE_CHECKING

import structlog

from zebtrack.core.video.video_metadata_service import VideoMetadataService

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class DialogCoordinator:
    """Coordinator for user dialogs and confirmations.

    Centralizes all user interaction logic through dialogs,
    decoupling MainViewModel from direct view calls.

    Attributes:
        ui_coordinator: UI coordinator for showing dialogs.
        event_bus: Event bus for UI communication.
        state_manager: Application state manager.
        project_manager: Project manager (for zone validation).
    """

    def __init__(
        self,
        ui_coordinator: "UIScheduler",
        event_bus: "EventBusV2 | None",
        state_manager: "StateManager",
        project_manager: "ProjectManager | None" = None,
        video_metadata_service: VideoMetadataService | None = None,
    ):
        """Initialize the dialog coordinator.

        Args:
            ui_coordinator: UI coordinator.
            event_bus: Event bus (optional).
            state_manager: State manager.
            project_manager: Project manager (optional,
                but required for zone validation).
            video_metadata_service: Video metadata service (optional).
        """
        self.ui_coordinator = ui_coordinator
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.video_metadata_service = video_metadata_service or VideoMetadataService()
        self.log = structlog.get_logger()

    def confirm_exit(self) -> bool:
        """Request user confirmation to exit the application.

        Returns:
            True if user confirmed, False otherwise.
        """
        return self.ui_coordinator.ask_ok_cancel("Sair", "Deseja realmente sair?")

    def handle_mixed_data_scenario(
        self,
        scanned_videos: list[dict],
    ) -> list[dict] | None:
        """Handle scenario where some videos have data and others don't.

        Args:
            scanned_videos: List of scanned video information dicts.

        Returns:
            List of videos to process, or None if all should be
            ignored/only added.
        """
        with_data = [v for v in scanned_videos if v.get("has_data")]
        without_data = [v for v in scanned_videos if not v.get("has_data")]

        if with_data and without_data:
            # Mixed case: some have data, others don't
            return self._handle_mixed_case(scanned_videos, with_data, without_data)
        elif with_data and not without_data:
            # All selected videos have data
            return self._handle_all_have_data(scanned_videos, with_data)
        else:
            # No videos have data, process all
            return without_data

    def _handle_mixed_case(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
        without_data: list[dict],
    ) -> list[dict]:
        """Handle case where there is a mix of videos with and without data.

        Args:
            scanned_videos: All scanned videos.
            with_data: Videos that already have data.
            without_data: Videos without data.

        Returns:
            Videos to process.
        """
        msg = (
            f"{len(with_data)} vídeo(s) já possuem dados de análise.\n"
            f"{len(without_data)} vídeo(s) precisam ser processados.\n\n"
            "Deseja reprocessar os vídeos que já possuem dados?"
        )

        if self.ui_coordinator.ask_ok_cancel("Dados Mistos Encontrados", msg):
            self.log.info(
                "dialog.mixed_data.reprocess_all",
                total=len(scanned_videos),
                with_data=len(with_data),
                without_data=len(without_data),
            )
            return scanned_videos
        else:
            self.log.info(
                "dialog.mixed_data.skip_existing",
                total=len(scanned_videos),
                processing=len(without_data),
            )
            return without_data

    def _handle_all_have_data(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
    ) -> list[dict] | None:
        """Handle case where all videos already have data.

        Args:
            scanned_videos: All scanned videos.
            with_data: Videos that have data (same as scanned_videos in this case).

        Returns:
            Videos to process, or None if none should be processed.
        """
        if self.ui_coordinator.ask_ok_cancel(
            "Dados Encontrados",
            "Todos os vídeos selecionados já possuem dados de análise. "
            "Deseja reprocessá-los todos?",
        ):
            self.log.info(
                "dialog.all_have_data.reprocess",
                total=len(with_data),
            )
            return with_data
        else:
            # User doesn't want to reprocess - add to project but don't process
            self._show_processing_skipped_info()
            # Note: Responsibility for adding to the project lies with the caller
            # The dialog coordinator only decides WHAT to process
            self.log.info(
                "dialog.all_have_data.skip",
                total=len(with_data),
            )
            return None  # Signal: do not process

    def validate_zones_with_ui(self) -> bool:
        """
        Validate that zones are defined, with UI dialogs for user interaction.

        Ported from UIStateController.
        Handles complex zone validation including main arena validation.

        Returns:
            bool: True if zones are valid/created, False if user cancelled
        """
        if not self.project_manager:
            self.log.error("dialog.validate_zones.no_project_manager")
            return False

        zone_data = self.project_manager.get_zone_data()

        # Check if main arena is defined
        if not zone_data or not zone_data.polygon:
            self.log.warning("workflow.project_processing.no_main_arena")

            response = self.ui_coordinator.ask_ok_cancel(
                "Arena Principal Não Definida",
                "O polígono principal do aquário não foi definido.\n\n"
                "É necessário definir a arena principal para análise precisa.\n"
                "Deseja definir agora antes de processar?",
            )

            if response:
                # Switch to zone tab and guide user
                if self.event_bus:
                    from zebtrack.ui.event_bus_v2 import Event, UIEvents

                    self.event_bus.publish(
                        Event(
                            type=UIEvents.UI_SELECT_TAB,
                            data={"tab_name": "zone_tab"},
                        )
                    )

                    # Load frame from first video if available
                    first_video = self.project_manager.get_next_video()
                    if first_video:
                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_DISPLAY_VIDEO_FRAME,
                                data={"video_path": first_video},
                            )
                        )

                        self.event_bus.publish(
                            Event(
                                type=UIEvents.UI_SHOW_INFO,
                                data={
                                    "title": "Defina a Arena Principal",
                                    "message": "Por favor:\n"
                                    "1. Use 'Detectar Aquário (Auto)' ou\n"
                                    "2. Desenhe manualmente o polígono principal\n"
                                    "3. Depois volte para adicionar vídeos",
                                },
                            )
                        )
                return False
            else:
                # Offer default arena as fallback
                if not self.ui_coordinator.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    self.log.info("workflow.project_processing.cancelled_no_arena")
                    return False

                # Create default arena based on first video
                first_video = self.project_manager.get_next_video()
                if first_video:
                    try:
                        # Use VideoMetadataService to get dimensions
                        dimensions = self.video_metadata_service.get_video_dimensions(first_video)
                        if not dimensions:
                            self.show_error("Erro", "Não foi possível obter dimensões do vídeo")
                            return False

                        width, height = dimensions
                        default_arena = [[0, 0], [width, 0], [width, height], [0, height]]

                        # Update project manager with default arena
                        zone_data.polygon = default_arena
                        self.project_manager.save_zone_data(zone_data)

                        self.log.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )

                        if self.event_bus:
                            from zebtrack.ui.event_bus_v2 import Event, UIEvents

                            self.event_bus.publish(
                                Event(
                                    type=UIEvents.UI_SHOW_INFO,
                                    data={
                                        "title": "Arena Padrão Criada",
                                        "message": f"Arena padrão criada ({width}x{height})\n"
                                        "Recomenda-se ajustar manualmente depois.",
                                    },
                                )
                            )
                            # Trigger redraw
                            self.event_bus.publish(Event(type=UIEvents.UI_REDRAW_ZONES))
                    except Exception as e:  # except Exception justified: non-critical fallback
                        self.show_error("Erro", f"Não foi possível criar arena padrão: {e}")
                        return False
                else:
                    self.show_error("Erro", "Nenhum vídeo encontrado no projeto")
                    return False

        # Warn about missing ROIs (optional but informative)
        if not zone_data.roi_polygons:
            if not self.ui_coordinator.ask_ok_cancel(
                "Nenhuma ROI Definida",
                "Nenhuma Área de Interesse (ROI) foi definida.\n\n"
                "A análise usará apenas a arena principal.\n"
                "Para análises detalhadas, considere definir ROIs.\n\n"
                "Deseja continuar?",
            ):
                self.log.info("workflow.project_processing.cancelled_by_user_no_roi")
                return False

        self.log.info(
            "workflow.project_processing.zones_validated",
            has_main_arena=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        return True

    def _show_processing_skipped_info(self) -> None:
        """Show informational dialog about skipped processing."""
        if self.event_bus:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus.publish(
                Event(
                    type=UIEvents.UI_SHOW_INFO,
                    data={
                        "title": "Processamento Ignorado",
                        "message": "Nenhum novo vídeo foi processado.",
                    },
                )
            )
        else:
            self.ui_coordinator.show_info(
                "Processamento Ignorado",
                "Nenhum novo vídeo foi processado.",
            )

    def show_info(self, title: str, message: str) -> None:
        """Show an informational dialog."""
        self.ui_coordinator.show_info(title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Show a warning dialog."""
        self.ui_coordinator.show_warning(title, message)

    def show_error(self, title: str, message: str) -> None:
        """Show an error dialog."""
        self.ui_coordinator.show_error(title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        """Request a yes/no confirmation from the user."""
        return self.ui_coordinator.ask_ok_cancel(title, message)

    def handle_validation_error(self, validation_result) -> bool:
        """
        Handle validation errors by showing appropriate UI messages.

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

        if self.event_bus:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            if error_code == "processing_already_active":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_WARNING,
                        data={
                            "title": "Análise em Andamento",
                            "message": error_message,
                        },
                    )
                )
            elif error_code == "no_project_loaded":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Nenhum Projeto Carregado",
                            "message": error_message,
                        },
                    )
                )
            elif error_code == "no_videos":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Nenhum Vídeo Encontrado",
                            "message": error_message,
                        },
                    )
                )
            elif error_code == "no_weight_selected":
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Peso Não Selecionado",
                            "message": error_message,
                        },
                    )
                )
            else:
                # Generic error fallback
                self.event_bus.publish(
                    Event(
                        type=UIEvents.UI_SHOW_ERROR,
                        data={
                            "title": "Erro de Validação",
                            "message": error_message,
                        },
                    )
                )
        else:
            # Fallback to UI Coordinator direct calls if no event bus
            if error_code == "processing_already_active":
                self.ui_coordinator.show_warning("Análise em Andamento", error_message)
            else:
                self.ui_coordinator.show_error("Erro de Validação", error_message)

        return False

"""Coordenador de diálogos e confirmações de usuário.

Este coordenador foi extraído do MainViewModel como parte da Fase 1 do
plano de refatoração (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsável por coordenar todos os diálogos e confirmações de usuário.
"""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.components.event_bus import EventBus
    from zebtrack.ui.components.ui_coordinator import UICoordinator
    from zebtrack.core.project_manager import ProjectManager

log = structlog.get_logger()


class DialogCoordinator:
    """Coordenador para diálogos e confirmações de usuário.

    Centraliza toda a lógica de interação com usuário através de diálogos,
    desacoplando o MainViewModel de chamadas diretas à view.

    Attributes:
        ui_coordinator: Coordenador de UI para mostrar diálogos
        event_bus: Bus de eventos para comunicação com UI
        state_manager: Gerenciador de estado da aplicação
        project_manager: Gerenciador de projetos (para validação de zonas)
    """

    def __init__(
        self,
        ui_coordinator: "UICoordinator",
        event_bus: "EventBus | None",
        state_manager: "StateManager",
        project_manager: "ProjectManager | None" = None,
    ):
        """Inicializa o coordenador de diálogos.

        Args:
            ui_coordinator: Coordenador de UI
            event_bus: Bus de eventos (opcional)
            state_manager: Gerenciador de estado
            project_manager: Gerenciador de projetos (opcional, mas necessário para validação de zonas)
        """
        self.ui_coordinator = ui_coordinator
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.log = structlog.get_logger()

    def confirm_exit(self) -> bool:
        """Solicita confirmação do usuário para sair da aplicação.

        Returns:
            True se usuário confirmou, False caso contrário
        """
        return self.ui_coordinator.ask_ok_cancel(
            "Sair", "Deseja realmente sair?"
        )

    def handle_mixed_data_scenario(
        self,
        scanned_videos: list[dict],
    ) -> list[dict] | None:
        """Trata cenário onde alguns vídeos têm dados e outros não.

        Args:
            scanned_videos: Lista de informações de vídeos escaneados

        Returns:
            Lista de vídeos para processar, ou None se todos devem ser
            ignorados/apenas adicionados
        """
        with_data = [v for v in scanned_videos if v.get("has_data")]
        without_data = [v for v in scanned_videos if not v.get("has_data")]

        if with_data and without_data:
            # Caso misto: alguns têm dados, outros não
            return self._handle_mixed_case(
                scanned_videos, with_data, without_data
            )
        elif with_data and not without_data:
            # Todos os vídeos selecionados têm dados
            return self._handle_all_have_data(
                scanned_videos, with_data
            )
        else:
            # Nenhum vídeo tem dados, processar todos
            return without_data

    def _handle_mixed_case(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
        without_data: list[dict],
    ) -> list[dict]:
        """Trata caso onde há mix de vídeos com e sem dados.

        Args:
            scanned_videos: Todos os vídeos escaneados
            with_data: Vídeos que já têm dados
            without_data: Vídeos sem dados

        Returns:
            Vídeos para processar
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
        """Trata caso onde todos os vídeos já têm dados.

        Args:
            scanned_videos: Todos os vídeos escaneados
            with_data: Vídeos que têm dados (igual a scanned_videos neste caso)

        Returns:
            Vídeos para processar, ou None se nenhum deve ser processado
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
            # Usuário não quer reprocessar - adicionar ao projeto mas não processar
            self._show_processing_skipped_info()
            # Note: A responsabilidade de adicionar ao projeto é do chamador
            # O dialog coordinator apenas decide O QUE processar
            self.log.info(
                "dialog.all_have_data.skip",
                total=len(with_data),
            )
            return None  # Sinal: não processar

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
                    from zebtrack.ui.events import Events
                    self.event_bus.publish_event(Events.UI_SELECT_TAB, {"tab_name": "zone_tab"})

                    # Load frame from first video if available
                    first_video = self.project_manager.get_next_video()
                    if first_video:
                        self.event_bus.publish_event(
                            Events.UI_DISPLAY_VIDEO_FRAME, {"video_path": first_video}
                        )

                        self.event_bus.publish_event(
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
                if not self.ui_coordinator.ask_ok_cancel(
                    "Usar Arena Padrão?",
                    "Deseja usar o frame completo como arena?\n"
                    "(Não recomendado para análise precisa)",
                ):
                    self.log.info("workflow.project_processing.cancelled_no_arena")
                    return False

                # Create default arena based on first video
                # WARNING: This logic creates dependency on CV2 which might not be ideal in dialog coordinator
                # But for now we move logic as is
                first_video = self.project_manager.get_next_video()
                if first_video:
                    try:
                        import cv2
                        cap = cv2.VideoCapture(first_video)
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()

                        default_arena = [[0, 0], [width, 0], [width, height], [0, height]]
                        
                        # We need to update project manager directly since we don't have controller ref
                        zone_data.polygon = default_arena
                        self.project_manager.save_zone_data(zone_data)
                        
                        self.log.info(
                            "workflow.project_processing.default_arena_created",
                            size=f"{width}x{height}",
                        )
                        
                        if self.event_bus:
                            from zebtrack.ui.events import Events
                            self.event_bus.publish_event(
                                Events.UI_SHOW_INFO,
                                {
                                    "title": "Arena Padrão Criada",
                                    "message": f"Arena padrão criada ({width}x{height})\n"
                                    "Recomenda-se ajustar manualmente depois.",
                                },
                            )
                            # Trigger redraw
                            self.event_bus.publish_event(Events.UI_REDRAW_ZONES)
                    except Exception as e:
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
        """Mostra diálogo informativo sobre processamento ignorado."""
        if self.event_bus:
            from zebtrack.ui.events import Events

            self.event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Processamento Ignorado",
                    "message": "Nenhum novo vídeo foi processado.",
                },
            )
        else:
            self.ui_coordinator.show_info(
                "Processamento Ignorado",
                "Nenhum novo vídeo foi processado.",
            )

    def show_info(self, title: str, message: str) -> None:
        """Mostra diálogo informativo."""
        self.ui_coordinator.show_info(title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Mostra diálogo de aviso."""
        self.ui_coordinator.show_warning(title, message)

    def show_error(self, title: str, message: str) -> None:
        """Mostra diálogo de erro."""
        self.ui_coordinator.show_error(title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        """Solicita confirmação sim/não do usuário."""
        return self.ui_coordinator.ask_ok_cancel(title, message)
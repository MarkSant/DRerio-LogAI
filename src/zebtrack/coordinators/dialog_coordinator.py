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

log = structlog.get_logger()


class DialogCoordinator:
    """Coordenador para diálogos e confirmações de usuário.

    Centraliza toda a lógica de interação com usuário através de diálogos,
    desacoplando o MainViewModel de chamadas diretas à view.

    Attributes:
        ui_coordinator: Coordenador de UI para mostrar diálogos
        event_bus: Bus de eventos para comunicação com UI
        state_manager: Gerenciador de estado da aplicação
    """

    def __init__(
        self,
        ui_coordinator: "UICoordinator",
        event_bus: "EventBus | None",
        state_manager: "StateManager",
    ):
        """Inicializa o coordenador de diálogos.

        Args:
            ui_coordinator: Coordenador de UI
            event_bus: Bus de eventos (opcional)
            state_manager: Gerenciador de estado
        """
        self.ui_coordinator = ui_coordinator
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.log = structlog.get_logger()

    def confirm_exit(self, view=None) -> bool:
        """Solicita confirmação do usuário para sair da aplicação.

        Args:
            view: View instance (opcional)

        Returns:
            True se usuário confirmou, False caso contrário
        """
        return self.ui_coordinator.ask_ok_cancel(
            view, "Sair", "Deseja realmente sair?"
        )

    def handle_mixed_data_scenario(
        self, scanned_videos: list[dict], project_manager, view=None
    ) -> list[dict] | None:
        """Trata cenário onde alguns vídeos têm dados e outros não.

        Args:
            scanned_videos: Lista de informações de vídeos escaneados
            project_manager: Gerenciador de projeto para adicionar vídeos
            view: View instance (opcional)

        Returns:
            Lista de vídeos para processar, ou None se todos devem ser
            ignorados/apenas adicionados
        """
        with_data = [v for v in scanned_videos if v.get("has_data")]
        without_data = [v for v in scanned_videos if not v.get("has_data")]

        if with_data and without_data:
            # Caso misto: alguns têm dados, outros não
            return self._handle_mixed_case(
                scanned_videos, with_data, without_data, view
            )
        elif with_data and not without_data:
            # Todos os vídeos selecionados têm dados
            return self._handle_all_have_data(
                scanned_videos, with_data, project_manager, view
            )
        else:
            # Nenhum vídeo tem dados, processar todos
            return without_data

    def _handle_mixed_case(
        self,
        scanned_videos: list[dict],
        with_data: list[dict],
        without_data: list[dict],
        view=None,
    ) -> list[dict]:
        """Trata caso onde há mix de vídeos com e sem dados.

        Args:
            scanned_videos: Todos os vídeos escaneados
            with_data: Vídeos que já têm dados
            without_data: Vídeos sem dados
            view: View instance

        Returns:
            Vídeos para processar
        """
        msg = (
            f"{len(with_data)} vídeo(s) já possuem dados de análise.\n"
            f"{len(without_data)} vídeo(s) precisam ser processados.\n\n"
            "Deseja reprocessar os vídeos que já possuem dados?"
        )

        if self.ui_coordinator.ask_ok_cancel(view, "Dados Mistos Encontrados", msg):
            # Usuário quer reprocessar tudo
            self.log.info(
                "dialog.mixed_data.reprocess_all",
                total=len(scanned_videos),
                with_data=len(with_data),
                without_data=len(without_data),
            )
            return scanned_videos
        else:
            # Usuário quer pular reprocessamento
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
        project_manager,
        view=None,
    ) -> list[dict] | None:
        """Trata caso onde todos os vídeos já têm dados.

        Args:
            scanned_videos: Todos os vídeos escaneados
            with_data: Vídeos que têm dados (igual a scanned_videos neste caso)
            project_manager: Gerenciador de projeto
            view: View instance

        Returns:
            Vídeos para processar, ou None se nenhum deve ser processado
        """
        if self.ui_coordinator.ask_ok_cancel(
            view,
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
            project_manager.add_video_batch(scanned_videos)
            self.log.info(
                "dialog.all_have_data.skip",
                total=len(with_data),
            )
            return None  # Sinal: não processar, já tratado

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
        """Mostra diálogo informativo.

        Args:
            title: Título do diálogo
            message: Mensagem do diálogo
        """
        self.ui_coordinator.show_info(title, message)

    def show_error(self, title: str, message: str) -> None:
        """Mostra diálogo de erro.

        Args:
            title: Título do diálogo
            message: Mensagem de erro
        """
        self.ui_coordinator.show_error(title, message)

    def ask_yes_no(self, title: str, message: str, view=None) -> bool:
        """Solicita confirmação sim/não do usuário.

        Args:
            title: Título do diálogo
            message: Mensagem de confirmação
            view: View instance (opcional)

        Returns:
            True se usuário confirmou, False caso contrário
        """
        return self.ui_coordinator.ask_ok_cancel(view, title, message)

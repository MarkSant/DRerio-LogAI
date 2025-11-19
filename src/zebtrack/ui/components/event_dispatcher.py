"""Dispatcher de eventos para roteamento de eventos do EventBus.

Este dispatcher foi extraído do MainViewModel como parte da Fase 1 do
plano de refatoração (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsável por rotear eventos do EventBus para orchestrators/services apropriados.
"""

from typing import TYPE_CHECKING, Any, Callable, ClassVar

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.components.event_bus import EventBus

log = structlog.get_logger()


class EventDispatcher:
    """Dispatcher para rotear eventos do EventBus para handlers apropriados.

    Centraliza a lógica de registro e despacho de eventos, removendo
    essa responsabilidade do MainViewModel.

    Attributes:
        event_bus: Bus de eventos para registro
        handlers: Dict mapeando eventos para seus handlers
    """

    # Modos de passagem de parâmetros
    MODE_NO_PARAMS = "no_params"
    MODE_KWARGS_ALL = "kwargs_all"
    MODE_KWARGS_GET = "kwargs_get"
    MODE_POSITIONAL = "positional"
    MODE_POSITIONAL_OPTIONAL = "positional_optional"

    def __init__(self, event_bus: "EventBus | None"):
        """Inicializa o dispatcher de eventos.

        Args:
            event_bus: Bus de eventos (opcional)
        """
        self.event_bus = event_bus
        self.handlers: dict[str, Callable] = {}
        self.log = structlog.get_logger()

    def register_handler(
        self,
        event_name: str,
        handler: Callable,
        param_names: list[str] | None = None,
        mode: str = MODE_NO_PARAMS,
    ) -> None:
        """Registra um handler para um evento específico.

        Args:
            event_name: Nome do evento
            handler: Função handler para chamar
            param_names: Nomes dos parâmetros esperados (para modos que precisam)
            mode: Modo de passagem de parâmetros
        """
        if not self.event_bus:
            self.log.warning(
                "event_dispatcher.no_event_bus",
                event_name=event_name,
            )
            return

        # Cria dispatcher que adapta event data para handler
        dispatcher = self._create_dispatcher(handler, param_names, mode)

        # Registra no event bus
        self.event_bus.subscribe(event_name, dispatcher)
        self.handlers[event_name] = dispatcher

        self.log.debug(
            "event_dispatcher.handler_registered",
            event_name=event_name,
            mode=mode,
        )

    def _create_dispatcher(
        self,
        handler: Callable,
        param_names: list[str] | None,
        mode: str,
    ) -> Callable:
        """Cria função dispatcher que adapta event data para handler.

        Args:
            handler: Função handler original
            param_names: Nomes dos parâmetros
            mode: Modo de passagem de parâmetros

        Returns:
            Função dispatcher que recebe dict e chama handler apropriadamente
        """

        def dispatcher(data: dict) -> None:
            """Delega evento para handler."""
            try:
                if mode == self.MODE_NO_PARAMS:
                    handler()
                elif mode == self.MODE_KWARGS_ALL:
                    handler(**data)
                elif mode == self.MODE_KWARGS_GET:
                    kwargs = {param: data.get(param) for param in (param_names or [])}
                    handler(**kwargs)
                elif mode == self.MODE_POSITIONAL:
                    args = [data[param] for param in (param_names or [])]
                    handler(*args)
                elif mode == self.MODE_POSITIONAL_OPTIONAL:
                    args = [data.get(param) for param in (param_names or [])]
                    handler(*args)
                else:
                    self.log.error(
                        "event_dispatcher.unknown_mode",
                        mode=mode,
                    )
            except Exception as e:
                self.log.error(
                    "event_dispatcher.handler_error",
                    error=str(e),
                    mode=mode,
                )

        return dispatcher

    def register_direct_handler(
        self, event_name: str, handler: Callable
    ) -> None:
        """Registra handler direto (sem adaptação de parâmetros).

        Args:
            event_name: Nome do evento
            handler: Função handler que recebe dict diretamente
        """
        if not self.event_bus:
            return

        self.event_bus.subscribe(event_name, handler)
        self.handlers[event_name] = handler

        self.log.debug(
            "event_dispatcher.direct_handler_registered",
            event_name=event_name,
        )

    def unregister_handler(self, event_name: str) -> None:
        """Remove registro de um handler.

        Args:
            event_name: Nome do evento
        """
        if event_name in self.handlers:
            # EventBus não tem método unsubscribe, então apenas removemos do tracking
            del self.handlers[event_name]
            self.log.debug(
                "event_dispatcher.handler_unregistered",
                event_name=event_name,
            )

    def get_registered_count(self) -> int:
        """Retorna número de handlers registrados.

        Returns:
            Número de handlers registrados
        """
        return len(self.handlers)

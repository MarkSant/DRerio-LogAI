"""Regra única do modo de gatilho externo (Arduino dá a partida na gravação).

Existem DOIS caminhos que iniciam uma gravação ao vivo:

* o legado — botão "Iniciar Gravação" do painel de controle, via
  ``RecordingSessionCoordinator.start_recording``;
* o atual — clicar numa cobaia na grade de Progresso, via
  ``LiveCameraSessionCoordinator.start_live_project_session``.

Até este módulo, só o legado consultava ``external_trigger_mode``. Marcar o
checkbox no wizard e gravar pela grade simplesmente não fazia nada: a gravação
começava na hora, ignorando o sinal externo — falha silenciosa que só aparece
quando o dado já foi perdido. Os dois caminhos agora decidem por aqui.

A decisão é deliberadamente uma FUNÇÃO PURA sobre ``project_data``: quem chama
faz a publicação de eventos e o armazenamento do contexto pendente, porque esses
diferem entre os coordinators. O que não pode divergir é a REGRA.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()

__all__ = ["ExternalTriggerDecision", "decide_external_trigger"]


class ExternalTriggerDecision(Enum):
    """O que fazer com um pedido de gravação sob modo de gatilho externo."""

    PROCEED = "proceed"
    """Gatilho desligado — gravar imediatamente, como sempre."""

    ARM_AND_WAIT = "arm_and_wait"
    """Gatilho ligado e Arduino disponível — guardar o contexto e aguardar o
    código 1 do dispositivo. NÃO grava agora."""

    REJECT_NO_ARDUINO = "reject_no_arduino"
    """Gatilho ligado mas sem Arduino utilizável — recusar a sessão.

    Gravar às cegas aqui seria pior que recusar: o operador montou o protocolo
    esperando sincronia com um estímulo externo, e uma gravação começada na hora
    errada é dado inútil que só se descobre na análise.
    """

    REJECT_ARDUINO_OFFLINE = "reject_arduino_offline"
    """Gatilho ligado, Arduino configurado, mas a porta NÃO está aberta.

    Distinto de :attr:`REJECT_NO_ARDUINO` porque a ação do usuário é outra:
    ali falta configurar, aqui falta conectar (cabo, porta ocupada por outro
    programa, placa reiniciada). Armar nesse estado deixaria a sessão esperando
    para sempre um sinal que não tem por onde chegar — o pior desfecho possível,
    porque parece que está funcionando.
    """


def decide_external_trigger(
    project_data: dict[str, Any] | None,
    arduino_manager: Any = None,
) -> ExternalTriggerDecision:
    """Decide o tratamento de gatilho externo para esta gravação.

    Args:
        project_data: dados do projeto (``external_trigger_mode``, ``use_arduino``).
        arduino_manager: opcional. Quando fornecido e expondo ``is_connected()``,
            a decisão passa a checar CONECTIVIDADE além de intenção. Sem ele, o
            gate confia só na configuração — comportamento aceitável para quem
            não tem acesso ao manager, mas prefira passá-lo.

    ``use_arduino`` é a fonte de verdade sobre intenção — é o mesmo flag que o
    resto do pipeline usa para decidir se abre a serial. Uma porta gravada em
    ``arduino_port`` com ``use_arduino`` falso significa "o usuário desligou o
    Arduino", não "há hardware".
    """
    data = project_data or {}
    trigger_requested = bool(data.get("external_trigger_mode"))

    if not trigger_requested:
        return ExternalTriggerDecision.PROCEED

    if not bool(data.get("use_arduino")):
        log.warning("external_trigger_gate.rejected.no_arduino")
        return ExternalTriggerDecision.REJECT_NO_ARDUINO

    # ``initialize_live_components`` avisa "executando em modo offline" quando o
    # connect falha, e o projeto segue aberto com ``use_arduino=True``. Sem esta
    # checagem, a sessão armaria e esperaria um sinal que não tem por onde chegar.
    if arduino_manager is not None and hasattr(arduino_manager, "is_connected"):
        try:
            connected = bool(arduino_manager.is_connected())
        # except Exception justified: sondar o estado da serial não pode impedir
        # uma gravação; na dúvida seguimos com a decisão baseada em configuração.
        except Exception:
            log.debug("external_trigger_gate.connectivity_probe_failed", exc_info=True)
        else:
            if not connected:
                log.warning("external_trigger_gate.rejected.arduino_offline")
                return ExternalTriggerDecision.REJECT_ARDUINO_OFFLINE

    log.info(
        "external_trigger_gate.armed",
        port=(data.get("arduino_port") or "").strip(),
    )
    return ExternalTriggerDecision.ARM_AND_WAIT

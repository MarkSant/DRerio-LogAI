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

v8 (ADR-011): a janela de análise ``project_data["analysis_window"]`` também
pode esperar o Arduino (nó ``External(source="arduino")``). Nesse caso a
gravação começa JÁ e grava tudo; o código do Arduino vira evento do motor de
condições, nunca uma nova chamada de início de sessão. A tabela completa:

====================================================  ==========================
Situação                                              Decisão
====================================================  ==========================
``external_trigger_mode`` legado ligado               ``ARM_AND_WAIT`` (como antes)
janela com ``External(arduino)``, sem ``use_arduino``  ``REJECT_NO_ARDUINO``
o mesmo, com a porta offline                          ``REJECT_ARDUINO_OFFLINE``
o mesmo, com o Arduino pronto                         ``PROCEED``
as duas coisas configuradas                           ``REJECT_CONFLICTING_TRIGGERS``
====================================================  ==========================
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

import structlog

from zebtrack.i18n import _

log = structlog.get_logger()

__all__ = [
    "ExternalTriggerDecision",
    "conflicting_triggers_message",
    "decide_external_trigger",
    "normalize_arduino_port",
    "window_waits_for_arduino",
]


def normalize_arduino_port(value: object) -> str:
    """Extrai a porta como texto limpo, tolerando tipos inesperados.

    ``(data.get("arduino_port") or "").strip()`` parece seguro e não é: um JSON
    de projeto editado à mão com ``"arduino_port": 3`` faz ``3 or ""`` devolver
    o int, e ``.strip()`` levanta ``AttributeError`` — no caminho de INICIAR
    gravação. O gate existe para degradar, não para explodir.
    """
    if value is None:
        return ""
    return str(value).strip()


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

    REJECT_CONFLICTING_TRIGGERS = "reject_conflicting_triggers"
    """Modo de gatilho legado ligado E uma janela de análise que espera o Arduino.

    As duas leituras do mesmo código são incompatíveis: o legado usa o 1 para
    COMEÇAR a gravar, a janela grava tudo e usa o 1 para começar a ANÁLISE.
    Um template v3 convertido desliga o legado; religar o checkbox depois é
    exatamente esta combinação, e adivinhar qual das duas o operador quis é o
    tipo de escolha que só se descobre errada na análise (ADR-011).
    """


def conflicting_triggers_message() -> str:
    """Why a session under :attr:`ExternalTriggerDecision.REJECT_CONFLICTING_TRIGGERS` refused.

    One text for both recording paths, resolved at call time (i18n).
    """
    return _(
        "This project has External Trigger Mode on AND an analysis window that "
        "waits for the Arduino. The two read the same signal differently: the "
        "trigger waits to START RECORDING, the window records everything and "
        "waits to start the ANALYSIS.\n\n"
        "The recording was NOT started. Keep only one: turn External Trigger Mode "
        "off in the project settings (the analysis window already waits for the "
        "signal), or remove the Arduino condition from the analysis window."
    )


def window_waits_for_arduino(raw_window: Any) -> bool:
    """Whether ``project_data["analysis_window"]`` has an ``External(arduino)`` node.

    A spec that does not validate counts as "no window": the live runtime
    ignores it too (with a warning), so the gate must not wait for it either.
    """
    if not isinstance(raw_window, Mapping) or not raw_window:
        return False
    from pydantic import ValidationError

    from zebtrack.core.conditions import External, WindowSpec, iter_nodes

    try:
        spec = WindowSpec.model_validate(dict(raw_window))
    except ValidationError:
        log.warning("external_trigger_gate.window.invalid_ignored")
        return False
    for root in (spec.start, spec.stop):
        if root is None:
            continue
        if any(
            isinstance(node, External) and node.source == "arduino" for node in iter_nodes(root)
        ):
            return True
    return False


def _arduino_unavailable(
    data: Mapping[str, Any], arduino_manager: Any
) -> ExternalTriggerDecision | None:
    """``REJECT_*`` when the Arduino cannot deliver a code; ``None`` when it can.

    ``use_arduino`` é a fonte de verdade sobre intenção — é o mesmo flag que o
    resto do pipeline usa para decidir se abre a serial. Uma porta gravada em
    ``arduino_port`` com ``use_arduino`` falso significa "o usuário desligou o
    Arduino", não "há hardware".
    """
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
    return None


def decide_external_trigger(
    project_data: dict[str, Any] | None,
    arduino_manager: Any = None,
) -> ExternalTriggerDecision:
    """Decide o tratamento de gatilho externo para esta gravação.

    Args:
        project_data: dados do projeto (``external_trigger_mode``, ``use_arduino``,
            ``analysis_window``).
        arduino_manager: opcional. Quando fornecido e expondo ``is_connected()``,
            a decisão passa a checar CONECTIVIDADE além de intenção. Sem ele, o
            gate confia só na configuração — comportamento aceitável para quem
            não tem acesso ao manager, mas prefira passá-lo.
    """
    data = project_data or {}
    trigger_requested = bool(data.get("external_trigger_mode"))
    window_needs_arduino = window_waits_for_arduino(data.get("analysis_window"))

    if trigger_requested and window_needs_arduino:
        log.warning("external_trigger_gate.rejected.conflicting_triggers")
        return ExternalTriggerDecision.REJECT_CONFLICTING_TRIGGERS

    if not trigger_requested and not window_needs_arduino:
        return ExternalTriggerDecision.PROCEED

    unavailable = _arduino_unavailable(data, arduino_manager)
    if unavailable is not None:
        return unavailable

    if window_needs_arduino:
        # Grava tudo desde já; o código chega ao motor de condições como evento.
        log.info("external_trigger_gate.window_waits_for_arduino")
        return ExternalTriggerDecision.PROCEED

    log.info("external_trigger_gate.armed", port=normalize_arduino_port(data.get("arduino_port")))
    return ExternalTriggerDecision.ARM_AND_WAIT

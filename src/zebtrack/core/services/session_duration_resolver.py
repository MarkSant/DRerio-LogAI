"""Fonte canônica da duração de uma sessão de gravação ao vivo.

O wizard define UMA duração para o projeto inteiro
(``project_data["recording_duration_s"]``), o que é o caso comum. Mas um
protocolo real quase sempre precisa de exceções: um dia de habituação mais
curto, um animal que precisou de mais tempo, um bloco reprogramado. Antes deste
módulo a única saída era editar o projeto e refazer o wizard.

Precedência, da mais específica para a mais geral:

1. override da COBAIA — ``"Dia_1|Controle|3"``;
2. padrão do BLOCO dia × grupo — ``"Dia_1|Controle|*"``;
3. ``project_data["recording_duration_s"]``;
4. :data:`DEFAULT_RECORDING_DURATION_S`.

A chave é montada por :func:`duration_override_key`; **nunca** monte a string à
mão em call site. O dia é normalizado (``1``, ``"1"`` e ``"Dia_1"`` resolvem para
a mesma chave) porque o codebase carrega os três formatos — ``metadata["day"]``
guarda ``"Dia_1"``, ``BlockDetailDialog.day_num`` guarda ``1``, e o grid entrega
ora um ora outro.

Os valores são gravados em SEGUNDOS, como ``recording_duration_s``. A UI
conversa em minutos e converte na borda.

O módulo é puro: nenhuma I/O, nenhum singleton, nenhuma dependência de UI.
"""

from __future__ import annotations

from typing import Any, Final

import structlog

log = structlog.get_logger()

__all__ = [
    "DEFAULT_RECORDING_DURATION_S",
    "OVERRIDES_KEY",
    "SUBJECT_WILDCARD",
    "block_override_key",
    "collect_block_durations",
    "duration_override_key",
    "resolve_session_duration",
    "set_duration_override",
]

# Espelha o fallback histórico de ``start_live_project_session`` (5 min). Mudar
# aqui muda o comportamento de projetos que nunca definiram duração.
DEFAULT_RECORDING_DURATION_S: Final[float] = 300.0

OVERRIDES_KEY: Final[str] = "session_duration_overrides"

# Sujeito curinga = "vale para todas as cobaias deste dia+grupo". Escolhido por
# ser inválido como ID de cobaia (que é sempre numérico), então nunca colide.
SUBJECT_WILDCARD: Final[str] = "*"


def _normalize_day(day: object) -> str:
    """Normaliza ``1``, ``"1"`` e ``"Dia_1"`` para ``"Dia_1"``.

    Valor irreconhecível volta como texto limpo — a chave simplesmente não vai
    casar com nada, que é o comportamento correto (cai no default) e não uma
    exceção no meio de uma gravação.
    """
    text = str(day).strip()
    if not text:
        return ""
    if text.startswith("Dia_"):
        return text
    if text.startswith("D") and text[1:].isdigit():
        return f"Dia_{text[1:]}"
    if text.isdigit():
        return f"Dia_{text}"
    return text


def duration_override_key(day: object, group: object, subject: object) -> str:
    """Monta a chave de override de uma cobaia específica."""
    return f"{_normalize_day(day)}|{str(group).strip()}|{str(subject).strip()}"


def block_override_key(day: object, group: object) -> str:
    """Monta a chave do padrão de um bloco dia × grupo."""
    return duration_override_key(day, group, SUBJECT_WILDCARD)


def _coerce_positive_duration(value: object) -> float | None:
    """Converte para float positivo, ou ``None`` se inutilizável.

    Um override corrompido (texto, zero, negativo) NÃO pode virar exceção nem
    duração zero: os dois perderiam a gravação. Vira ``None`` e o resolver cai
    para o próximo nível de precedência, com aviso no log.
    """
    try:
        duration = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if duration <= 0 or duration != duration:  # NaN != NaN
        return None
    return duration


def resolve_session_duration(
    project_data: dict[str, Any] | None,
    day: object,
    group: object,
    subject: object,
) -> float:
    """Resolve a duração (em segundos) da sessão desta cobaia.

    Args:
        project_data: ``ProjectManager.project_data`` (aceita ``None``).
        day: Dia em qualquer formato (``1``, ``"1"``, ``"Dia_1"``).
        group: Nome do grupo experimental.
        subject: ID da cobaia.

    Returns:
        Duração em segundos, sempre > 0.
    """
    data = project_data or {}
    overrides = data.get(OVERRIDES_KEY)
    if not isinstance(overrides, dict):
        overrides = {}

    for key, level in (
        (duration_override_key(day, group, subject), "subject"),
        (block_override_key(day, group), "block"),
    ):
        if key not in overrides:
            continue
        duration = _coerce_positive_duration(overrides[key])
        if duration is not None:
            return duration
        log.warning(
            "session_duration_resolver.override.invalid",
            key=key,
            level=level,
            raw=repr(overrides[key]),
        )

    project_default = _coerce_positive_duration(data.get("recording_duration_s"))
    if project_default is not None:
        return project_default

    return DEFAULT_RECORDING_DURATION_S


def set_duration_override(
    project_data: dict[str, Any],
    day: object,
    group: object,
    subject: object,
    duration_s: float | None,
) -> None:
    """Grava (ou remove) um override em ``project_data``, in-place.

    ``duration_s=None`` REMOVE o override — é assim que o usuário volta a herdar
    o nível de cima. Passar ``0`` seria ambíguo com "gravação instantânea", então
    valores não positivos também removem.

    Não salva o projeto: quem chama decide quando persistir, porque
    ``save_project()`` pode falhar e o erro precisa chegar ao usuário.
    """
    overrides = project_data.get(OVERRIDES_KEY)
    if not isinstance(overrides, dict):
        overrides = {}
        project_data[OVERRIDES_KEY] = overrides

    key = duration_override_key(day, group, subject)
    coerced = _coerce_positive_duration(duration_s) if duration_s is not None else None

    if coerced is None:
        overrides.pop(key, None)
        log.info("session_duration_resolver.override.cleared", key=key)
    else:
        overrides[key] = coerced
        log.info("session_duration_resolver.override.set", key=key, duration_s=coerced)


def collect_block_durations(
    project_data: dict[str, Any] | None,
    day: object,
    group: object,
    subjects: list[str],
) -> dict[str, float]:
    """Duração resolvida de cada cobaia do bloco, para detectar heterogeneidade.

    Usado pelos relatórios parcial/lote: durações diferentes dentro de um mesmo
    bloco tornam métricas ABSOLUTAS (distância total, nº de entradas, tempo em
    ROI) não comparáveis entre animais, e isso precisa ser dito em voz alta.
    """
    return {
        subject: resolve_session_duration(project_data, day, group, subject) for subject in subjects
    }

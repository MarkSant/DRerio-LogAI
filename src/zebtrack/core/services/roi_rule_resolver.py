"""Fonte canônica da regra de inclusão em ROI.

Todo caminho que decide se um animal está "dentro" de uma ROI — relatório de
vídeo pré-gravado, regeração de relatório, pós-processamento ao vivo e o
gatilho Arduino ao vivo — resolve a regra por aqui. Antes deste módulo cada
caminho lia (ou ignorava) `roi_settings` do projeto por conta própria, e os
quatro divergiam: o relatório podia contar uma entrada que o Arduino não
disparou, e regenerar o relatório mudava os números.

Precedência: ``project_data["roi_settings"]`` > ``settings_obj`` > default.

O módulo é puro: nenhuma I/O, nenhum singleton, nenhuma dependência de UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import structlog

log = structlog.get_logger()

__all__ = [
    "DEFAULT_BUFFER_RADIUS_VALUE",
    "DEFAULT_MIN_BBOX_OVERLAP_RATIO",
    "DEFAULT_ROI_INCLUSION_RULE",
    "VALID_ROI_INCLUSION_RULES",
    "RoiRuleConfig",
    "apply_roi_rule_to_settings",
    "resolve_roi_rule",
]

# Espelham os defaults de ``Settings`` (settings.py).
DEFAULT_ROI_INCLUSION_RULE: Final[str] = "bbox_intersects"
DEFAULT_BUFFER_RADIUS_VALUE: Final[float] = 0.5
DEFAULT_MIN_BBOX_OVERLAP_RATIO: Final[float] = 0.10

VALID_ROI_INCLUSION_RULES: Final[frozenset[str]] = frozenset(
    {
        "centroid_in",
        "centroid_in_on_buffered_roi",
        "bbox_intersects",
        "seg_overlap",
    }
)

# Regras que exigem os parâmetros numéricos correspondentes.
_BUFFERED_RULES: Final[frozenset[str]] = frozenset({"centroid_in_on_buffered_roi"})
_OVERLAP_RULES: Final[frozenset[str]] = frozenset({"bbox_intersects", "seg_overlap"})

# Chaves reconhecidas em ``project_data["roi_settings"]`` (mesmos nomes que o
# editor de configurações já grava — não inventar chaves novas).
_KEY_RULE: Final[str] = "roi_inclusion_rule"
_KEY_BUFFER: Final[str] = "roi_buffer_radius_value"
_KEY_OVERLAP: Final[str] = "roi_min_bbox_overlap_ratio"


@dataclass(frozen=True)
class RoiRuleConfig:
    """Regra de inclusão em ROI já resolvida e coerente.

    Imutável de propósito: é passada adiante para o ``ROIAnalyzer`` e para o
    ``ArduinoRoiEvaluator``, que precisam concordar bit a bit.

    A instância é sempre autoconsistente (ver :meth:`normalized`):
    ``buffer_radius_value > 0`` e ``0 < min_bbox_overlap_ratio <= 1``, de modo
    que aplicá-la a um ``Settings`` nunca produz um estado intermediário
    inválido, independentemente da regra anterior.
    """

    rule: str = DEFAULT_ROI_INCLUSION_RULE
    buffer_radius_value: float = DEFAULT_BUFFER_RADIUS_VALUE
    min_bbox_overlap_ratio: float = DEFAULT_MIN_BBOX_OVERLAP_RATIO

    @property
    def uses_bbox(self) -> bool:
        """True quando a regra precisa da bbox da detecção, não só do centroide."""
        return self.rule in _OVERLAP_RULES

    @property
    def uses_buffer(self) -> bool:
        """True quando a regra dilata o polígono da ROI antes do teste."""
        return self.rule in _BUFFERED_RULES


def _coerce_rule(value: Any, fallback: str, *, source: str) -> str:
    """Valida o nome da regra; cai em ``fallback`` e loga quando inválido."""
    if value is None:
        return fallback
    rule = str(value).strip()
    if rule in VALID_ROI_INCLUSION_RULES:
        return rule
    log.warning(
        "roi_rule.resolve.invalid_value",
        field=_KEY_RULE,
        value=value,
        source=source,
        fallback=fallback,
    )
    return fallback


def _coerce_float(
    value: Any,
    fallback: float,
    *,
    field: str,
    source: str,
    maximum: float | None = None,
) -> float:
    """Converte e valida um parâmetro numérico; cai em ``fallback`` se inválido.

    Aceita texto (é por aqui que passam os campos da aba de Zonas, sem
    ``float()`` na UI). ``isfinite`` cobre NaN **e** ±inf: sem ele um ``inf`` no
    raio de buffer passaria pelo teste de faixa (não há ``maximum``) e viraria
    uma dilatação impossível lá na ponta.

    O mínimo é **exclusivo**: zero não é valor útil para nenhum dos dois
    parâmetros (um buffer de raio 0 não dilata; uma fração 0 aceita qualquer
    coisa) e a regra ``centroid_in_on_buffered_roi`` do ``Settings`` até o
    rejeita. Tratá-lo como inválido aqui é o que faz um ``0`` do projeto cair
    no valor global **com log**, em vez de virar default em silêncio.
    """
    if value is None:
        return fallback

    invalid = False
    try:
        number = float(value)
    except (TypeError, ValueError):
        invalid = True
        number = fallback

    if not invalid and (
        not math.isfinite(number) or number <= 0.0 or (maximum is not None and number > maximum)
    ):
        invalid = True

    if invalid:
        log.warning(
            "roi_rule.resolve.invalid_value",
            field=field,
            value=value,
            source=source,
            fallback=fallback,
        )
        return fallback
    return number


def _normalize(rule: str, buffer_radius: float, overlap_ratio: float) -> RoiRuleConfig:
    """Rede de segurança da autoconsistência da configuração.

    Com o mínimo exclusivo em :func:`_coerce_float`, todo valor que chega aqui
    já é utilizável (e os defaults também são) — este passo existe para que a
    garantia "buffer > 0 e 0 < ratio <= 1" seja do tipo, não de quem o
    construiu. É dela que depende a ordem de :func:`apply_roi_rule_to_settings`.
    """
    if buffer_radius <= 0.0:
        buffer_radius = DEFAULT_BUFFER_RADIUS_VALUE
    if not (0.0 < overlap_ratio <= 1.0):
        overlap_ratio = DEFAULT_MIN_BBOX_OVERLAP_RATIO
    return RoiRuleConfig(
        rule=rule,
        buffer_radius_value=buffer_radius,
        min_bbox_overlap_ratio=overlap_ratio,
    )


def resolve_roi_rule(project_data: Any, settings_obj: Any) -> RoiRuleConfig:
    """Resolve a regra de inclusão em ROI válida para o contexto.

    Args:
        project_data: ``ProjectManager.project_data`` (ou ``None`` quando não há
            projeto aberto). Só a sub-chave ``roi_settings`` é lida. Qualquer
            outro tipo é tratado como "sem projeto".
        settings_obj: instância de ``Settings`` injetada (ou ``None``).

    Returns:
        A configuração efetiva, já coerente. Nunca levanta: valores inválidos
        caem no nível anterior da precedência e são logados como
        ``roi_rule.resolve.invalid_value``.
    """
    rule = DEFAULT_ROI_INCLUSION_RULE
    buffer_radius = DEFAULT_BUFFER_RADIUS_VALUE
    overlap_ratio = DEFAULT_MIN_BBOX_OVERLAP_RATIO

    if settings_obj is not None:
        rule = _coerce_rule(getattr(settings_obj, _KEY_RULE, None), rule, source="settings")
        buffer_radius = _coerce_float(
            getattr(settings_obj, _KEY_BUFFER, None),
            buffer_radius,
            field=_KEY_BUFFER,
            source="settings",
        )
        overlap_ratio = _coerce_float(
            getattr(settings_obj, _KEY_OVERLAP, None),
            overlap_ratio,
            field=_KEY_OVERLAP,
            source="settings",
            maximum=1.0,
        )

    # ``.get`` num ``project_data`` de tipo inesperado levantaria AttributeError
    # — e este resolvedor roda no loop ao vivo, onde nada pode levantar.
    roi_settings: Any = project_data.get("roi_settings") if isinstance(project_data, dict) else None
    if isinstance(roi_settings, dict):
        rule = _coerce_rule(roi_settings.get(_KEY_RULE), rule, source="project")
        buffer_radius = _coerce_float(
            roi_settings.get(_KEY_BUFFER),
            buffer_radius,
            field=_KEY_BUFFER,
            source="project",
        )
        overlap_ratio = _coerce_float(
            roi_settings.get(_KEY_OVERLAP),
            overlap_ratio,
            field=_KEY_OVERLAP,
            source="project",
            maximum=1.0,
        )
    elif roi_settings is not None:
        log.warning(
            "roi_rule.resolve.invalid_value",
            field="roi_settings",
            value=type(roi_settings).__name__,
            source="project",
            fallback="settings",
        )

    return _normalize(rule, buffer_radius, overlap_ratio)


def apply_roi_rule_to_settings(settings_obj: Any, config: RoiRuleConfig) -> Any:
    """Aplica ``config`` a um objeto de settings, no lugar, e o devolve.

    ``Settings`` usa ``validate_assignment=True`` com um validador cruzado
    (regra × parâmetros), então a ordem de atribuição importa: escrever a regra
    antes do parâmetro que ela exige levantaria ``ValidationError``. A ordem
    abaixo mantém o objeto válido em todos os passos intermediários — o que só
    é possível porque :class:`RoiRuleConfig` já chega normalizada.
    """
    if settings_obj is None:
        return settings_obj

    order: tuple[tuple[str, Any], ...]
    if config.uses_buffer:
        order = (
            (_KEY_BUFFER, config.buffer_radius_value),
            (_KEY_RULE, config.rule),
            (_KEY_OVERLAP, config.min_bbox_overlap_ratio),
        )
    elif config.uses_bbox:
        order = (
            (_KEY_OVERLAP, config.min_bbox_overlap_ratio),
            (_KEY_RULE, config.rule),
            (_KEY_BUFFER, config.buffer_radius_value),
        )
    else:
        order = (
            (_KEY_RULE, config.rule),
            (_KEY_BUFFER, config.buffer_radius_value),
            (_KEY_OVERLAP, config.min_bbox_overlap_ratio),
        )

    for field, value in order:
        setattr(settings_obj, field, value)

    return settings_obj

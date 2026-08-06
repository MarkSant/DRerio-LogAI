"""Fonte canônica da regra de inclusão em ROI.

Todo caminho que decide se um animal está "dentro" de uma ROI — relatório de
vídeo pré-gravado, regeneração de relatório, pós-processamento ao vivo e o
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
    "DEFAULT_BBOX_OVERLAP_BASIS",
    "DEFAULT_BUFFER_RADIUS_VALUE",
    "DEFAULT_MIN_BBOX_OVERLAP_RATIO",
    "DEFAULT_ROI_INCLUSION_RULE",
    "VALID_BBOX_OVERLAP_BASES",
    "VALID_ROI_INCLUSION_RULES",
    "RoiRuleConfig",
    "apply_roi_rule_to_settings",
    "resolve_roi_rule",
]

# Espelham os defaults de ``Settings`` (settings.py). ``Settings`` é a fonte
# ÚNICA do valor: o ``config.yaml`` distribuído não redefine nenhum deles.
DEFAULT_ROI_INCLUSION_RULE: Final[str] = "bbox_intersects"
DEFAULT_BUFFER_RADIUS_VALUE: Final[float] = 0.5
DEFAULT_MIN_BBOX_OVERLAP_RATIO: Final[float] = 0.10
DEFAULT_BBOX_OVERLAP_BASIS: Final[str] = "bbox"

VALID_ROI_INCLUSION_RULES: Final[frozenset[str]] = frozenset(
    {
        "centroid_in",
        "centroid_in_on_buffered_roi",
        "bbox_intersects",
        "seg_overlap",
    }
)

# Denominador da fração de sobreposição (ver :attr:`RoiRuleConfig.bbox_overlap_basis`).
VALID_BBOX_OVERLAP_BASES: Final[frozenset[str]] = frozenset({"bbox", "roi", "max"})

# Regras que exigem os parâmetros numéricos correspondentes.
_BUFFERED_RULES: Final[frozenset[str]] = frozenset({"centroid_in_on_buffered_roi"})
_OVERLAP_RULES: Final[frozenset[str]] = frozenset({"bbox_intersects", "seg_overlap"})

# Regras que exigem fração de sobreposição ESTRITAMENTE positiva.
# ``bbox_intersects`` fica de fora: nela o limiar 0 tem significado próprio
# ("qualquer sobreposição de área não-nula"), que é o que o nome da regra
# sempre prometeu. ``seg_overlap`` não tem esse caminho implementado — aceitar
# 0 lá prometeria uma semântica que ninguém executa.
_STRICT_OVERLAP_RULES: Final[frozenset[str]] = frozenset({"seg_overlap"})

# Chaves reconhecidas em ``project_data["roi_settings"]`` (mesmos nomes que o
# editor de configurações já grava — não inventar chaves novas).
_KEY_RULE: Final[str] = "roi_inclusion_rule"
_KEY_BUFFER: Final[str] = "roi_buffer_radius_value"
_KEY_OVERLAP: Final[str] = "roi_min_bbox_overlap_ratio"
_KEY_BASIS: Final[str] = "roi_bbox_overlap_basis"


@dataclass(frozen=True)
class RoiRuleConfig:
    """Regra de inclusão em ROI já resolvida e coerente.

    Imutável de propósito: é passada adiante para o ``ROIAnalyzer`` e para o
    ``ArduinoRoiEvaluator``, que precisam concordar bit a bit.

    A instância é sempre autoconsistente com a própria regra, nas mesmas
    faixas do validador cruzado de ``Settings``: o parâmetro **exigido** pela
    regra é ``> 0`` (o outro pode ser ``0``, que ela ignora) — com a exceção
    documentada de ``bbox_intersects``, onde ``0`` é um valor com significado.
    É essa garantia que permite a :func:`apply_roi_rule_to_settings` escrever
    os campos sem passar por um estado intermediário inválido.
    """

    rule: str = DEFAULT_ROI_INCLUSION_RULE
    buffer_radius_value: float = DEFAULT_BUFFER_RADIUS_VALUE
    min_bbox_overlap_ratio: float = DEFAULT_MIN_BBOX_OVERLAP_RATIO
    #: Denominador da fração de sobreposição das regras de área:
    #: ``"bbox"`` = ``inter / área_bbox`` (histórico), ``"roi"`` =
    #: ``inter / área_roi``, ``"max"`` = o maior dos dois. O default ``"bbox"``
    #: distorce ROIs pequenas — uma bbox 4x maior que a ROI, cobrindo-a por
    #: inteiro, dá razão 0.25 — mas é o que reproduz os números históricos.
    bbox_overlap_basis: str = DEFAULT_BBOX_OVERLAP_BASIS

    @property
    def uses_bbox(self) -> bool:
        """True quando a regra precisa da bbox da detecção, não só do centroide."""
        return self.rule in _OVERLAP_RULES

    @property
    def uses_buffer(self) -> bool:
        """True quando a regra dilata o polígono da ROI antes do teste."""
        return self.rule in _BUFFERED_RULES

    @property
    def overlap_any(self) -> bool:
        """True quando o limiar dispensa a fração e pede só sobreposição real.

        Limiar ``0`` em ``bbox_intersects`` é o predicado que o nome da regra
        promete: **qualquer** sobreposição de área não-nula conta, sem fração
        mínima. Tangência (contato só de borda, interseção de área zero) NÃO
        conta — a checagem correspondente é topológica, não uma comparação de
        área contra zero.
        """
        return self.min_bbox_overlap_ratio <= 0.0

    # ------------------------------------------------------------------
    # Aliases com os nomes de ``Settings``
    # ------------------------------------------------------------------
    # Permitem passar uma config JÁ resolvida como camada de base de
    # :func:`resolve_roi_rule` — é assim que uma edição parcial (só a regra,
    # por exemplo) cai no valor EFETIVO atual em vez de no global.

    @property
    def roi_inclusion_rule(self) -> str:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.rule

    @property
    def roi_buffer_radius_value(self) -> float:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.buffer_radius_value

    @property
    def roi_min_bbox_overlap_ratio(self) -> float:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.min_bbox_overlap_ratio

    @property
    def roi_bbox_overlap_basis(self) -> str:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.bbox_overlap_basis

    def to_roi_settings(self) -> dict[str, Any]:
        """Serializa para ``project_data["roi_settings"]``."""
        return {
            _KEY_RULE: self.rule,
            _KEY_BUFFER: self.buffer_radius_value,
            _KEY_OVERLAP: self.min_bbox_overlap_ratio,
            _KEY_BASIS: self.bbox_overlap_basis,
        }


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


def _coerce_basis(value: Any, fallback: str, *, source: str) -> str:
    """Valida o denominador da fração; cai em ``fallback`` e loga quando inválido."""
    if value is None:
        return fallback
    basis = str(value).strip()
    if basis in VALID_BBOX_OVERLAP_BASES:
        return basis
    log.warning(
        "roi_rule.resolve.invalid_value",
        field=_KEY_BASIS,
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
    required: bool,
    maximum: float | None = None,
) -> float:
    """Converte e valida um parâmetro numérico; cai em ``fallback`` se inválido.

    Aceita texto (é por aqui que passam os campos da aba de Zonas, sem
    ``float()`` na UI). ``isfinite`` cobre NaN **e** ±inf: sem ele um ``inf`` no
    raio de buffer passaria pelo teste de faixa (não há ``maximum``) e viraria
    uma dilatação impossível lá na ponta.

    ``required`` diz se a REGRA EFETIVA usa este parâmetro, e é isso que decide
    se o mínimo é exclusivo — as mesmas faixas do validador cruzado de
    ``Settings``. Um raio 0 com ``bbox_intersects`` é irrelevante e legítimo
    (o ``config.yaml`` distribui configurações assim), então não vira ruído;
    já um raio 0 com ``centroid_in_on_buffered_roi`` não dilata nada e cai um
    nível **com log**, em vez de virar default em silêncio.
    """
    if value is None:
        return fallback

    invalid = False
    try:
        number = float(value)
    except (TypeError, ValueError):
        invalid = True
        number = fallback

    minimum_ok = number > 0.0 if required else number >= 0.0
    if not invalid and (
        not math.isfinite(number) or not minimum_ok or (maximum is not None and number > maximum)
    ):
        invalid = True

    if invalid:
        log.warning(
            "roi_rule.resolve.invalid_value",
            field=field,
            value=value,
            source=source,
            required_by_rule=required,
            fallback=fallback,
        )
        return fallback
    return number


def _normalize(rule: str, buffer_radius: float, overlap_ratio: float, basis: str) -> RoiRuleConfig:
    """Rede de segurança da autoconsistência da configuração.

    A garantia é a mesma do validador de ``Settings``: **o parâmetro exigido
    pela regra** é > 0 (o outro pode ser 0, que é irrelevante para ela), com a
    exceção de ``bbox_intersects``, cujo 0 é um limiar válido. É dela que
    depende a ordem de :func:`apply_roi_rule_to_settings` — a cada passo o
    objeto satisfaz a regra vigente, seja a antiga ou a nova.
    """
    if rule in _BUFFERED_RULES and not buffer_radius > 0.0:
        buffer_radius = DEFAULT_BUFFER_RADIUS_VALUE
    elif buffer_radius < 0.0:
        buffer_radius = DEFAULT_BUFFER_RADIUS_VALUE

    if rule in _STRICT_OVERLAP_RULES and not 0.0 < overlap_ratio <= 1.0:
        overlap_ratio = DEFAULT_MIN_BBOX_OVERLAP_RATIO
    elif not 0.0 <= overlap_ratio <= 1.0:
        overlap_ratio = DEFAULT_MIN_BBOX_OVERLAP_RATIO

    if basis not in VALID_BBOX_OVERLAP_BASES:
        basis = DEFAULT_BBOX_OVERLAP_BASIS

    return RoiRuleConfig(
        rule=rule,
        buffer_radius_value=buffer_radius,
        min_bbox_overlap_ratio=overlap_ratio,
        bbox_overlap_basis=basis,
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
    # ``.get`` num ``project_data`` de tipo inesperado levantaria AttributeError
    # — e este resolvedor roda no loop ao vivo, onde nada pode levantar.
    roi_settings: Any = project_data.get("roi_settings") if isinstance(project_data, dict) else None
    if not isinstance(roi_settings, dict):
        if roi_settings is not None:
            log.warning(
                "roi_rule.resolve.invalid_value",
                field="roi_settings",
                value=type(roi_settings).__name__,
                source="project",
                fallback="settings",
            )
        roi_settings = {}

    # A REGRA vem primeiro: é ela que define quais parâmetros são exigidos e,
    # portanto, as faixas válidas de cada um (idem validador de ``Settings``).
    rule = DEFAULT_ROI_INCLUSION_RULE
    if settings_obj is not None:
        rule = _coerce_rule(getattr(settings_obj, _KEY_RULE, None), rule, source="settings")
    rule = _coerce_rule(roi_settings.get(_KEY_RULE), rule, source="project")

    def _param(key: str, default: float, *, required: bool, maximum: float | None = None) -> float:
        value = default
        if settings_obj is not None:
            value = _coerce_float(
                getattr(settings_obj, key, None),
                value,
                field=key,
                source="settings",
                required=required,
                maximum=maximum,
            )
        return _coerce_float(
            roi_settings.get(key),
            value,
            field=key,
            source="project",
            required=required,
            maximum=maximum,
        )

    buffer_radius = _param(
        _KEY_BUFFER, DEFAULT_BUFFER_RADIUS_VALUE, required=rule in _BUFFERED_RULES
    )
    overlap_ratio = _param(
        _KEY_OVERLAP,
        DEFAULT_MIN_BBOX_OVERLAP_RATIO,
        required=rule in _STRICT_OVERLAP_RULES,
        maximum=1.0,
    )

    basis = DEFAULT_BBOX_OVERLAP_BASIS
    if settings_obj is not None:
        basis = _coerce_basis(getattr(settings_obj, _KEY_BASIS, None), basis, source="settings")
    basis = _coerce_basis(roi_settings.get(_KEY_BASIS), basis, source="project")

    return _normalize(rule, buffer_radius, overlap_ratio, basis)


def apply_roi_rule_to_settings(settings_obj: Any, config: RoiRuleConfig) -> Any:
    """Aplica ``config`` a um objeto de settings, no lugar, e o devolve.

    ``Settings`` usa ``validate_assignment=True`` com um validador cruzado
    (regra × parâmetros), então a ordem de atribuição importa: escrever a regra
    antes do parâmetro que ela exige levantaria ``ValidationError``. A ordem
    abaixo mantém o objeto válido em todos os passos intermediários — o que só
    é possível porque :class:`RoiRuleConfig` já chega normalizada.

    ``roi_bbox_overlap_basis`` fica fora dessa dança: não entra em nenhuma
    invariante cruzada, então pode ser escrito primeiro, sempre.
    """
    if settings_obj is None:
        return settings_obj

    setattr(settings_obj, _KEY_BASIS, config.bbox_overlap_basis)

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

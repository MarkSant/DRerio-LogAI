"""Fonte canônica da configuração de presença em ROI.

Todo caminho que decide se um animal está "dentro" de uma ROI — relatório de
vídeo pré-gravado, regeneração de relatório, pós-processamento ao vivo e o
gatilho Arduino ao vivo — resolve a configuração por aqui. Antes deste módulo
cada caminho lia (ou ignorava) `roi_settings` do projeto por conta própria, e os
quatro divergiam: o relatório podia contar uma entrada que o Arduino não
disparou, e regenerar o relatório mudava os números.

Precedência: ``project_data["roi_settings"]`` > ``settings_obj`` > default.

O nome ``RoiRuleConfig`` é histórico: o escopo hoje é maior que a regra
geométrica. Além de **onde** o animal está (regra + parâmetros de área), a
config carrega **quando** essa presença conta como visita — o debounce
assimétrico de entrada/saída e os limiares de duração. Os dois grupos andam
juntos de propósito: são exatamente o conjunto de parâmetros que o relatório e
o gatilho Arduino precisam compartilhar para não divergirem, e é esse
acoplamento que a classe existe para garantir. O nome ficou para não trocar
importações em ~15 arquivos sem ganho semântico.

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
    "DEFAULT_ROI_FLUTTER_ENTER_FRAMES",
    "DEFAULT_ROI_FLUTTER_EXIT_FRAMES",
    "DEFAULT_ROI_INCLUSION_RULE",
    "DEFAULT_ROI_MAX_GAP_S",
    "DEFAULT_ROI_MIN_GAP_S",
    "DEFAULT_ROI_MIN_VISIT_S",
    "MAX_GAP_AUTO_FACTOR",
    "VALID_BBOX_OVERLAP_BASES",
    "VALID_ROI_INCLUSION_RULES",
    "RoiRuleConfig",
    "apply_roi_rule_to_settings",
    "resolve_roi_rule",
]

# Espelham os defaults de ``Settings`` (settings.py). ``Settings`` é a fonte
# ÚNICA do valor: o ``config.yaml`` distribuído não redefine nenhum deles.
#
# A duplicação é deliberada e tem guarda automática. Referenciar estas
# constantes direto no ``Field(default=...)`` do Pydantic seria o ideal, mas
# criaria um ciclo de importação: qualquer import sob ``zebtrack.core.services``
# executa o ``__init__`` do pacote, que carrega ``DetectorService`` e companhia
# — e esses já importam ``zebtrack.settings`` (42 módulos entram junto).
# ``settings.py`` é um módulo-folha, sem nenhum import de ``zebtrack``, de
# propósito. A divergência silenciosa é barrada por
# ``test_resolver_defaults_match_settings_defaults``, que compara as NOVE
# chaves de ROI com os defaults declarados no modelo Pydantic.
DEFAULT_ROI_INCLUSION_RULE: Final[str] = "bbox_intersects"
DEFAULT_BUFFER_RADIUS_VALUE: Final[float] = 0.5
DEFAULT_MIN_BBOX_OVERLAP_RATIO: Final[float] = 0.10
DEFAULT_BBOX_OVERLAP_BASIS: Final[str] = "bbox"

# Debounce ASSIMÉTRICO de presença. Confirmar a entrada é barato (2 frames) e
# confirmar a saída é caro (3 frames): comportamentalmente, um animal que
# "some" por um frame no meio de uma visita continua na ROI, mas uma entrada
# precisa de menos evidência para não perder visitas curtas legítimas. É a
# mesma assimetria que o caminho Arduino já tinha em
# ``arduino.roi_exit_grace_frames``.
DEFAULT_ROI_FLUTTER_ENTER_FRAMES: Final[int] = 2
DEFAULT_ROI_FLUTTER_EXIT_FRAMES: Final[int] = 3

# Limiares de DURAÇÃO, em segundos. Contagem de frames não é invariante:
# trocar ``analysis_interval_frames`` de 10 para 5 dobra a taxa da série e muda
# silenciosamente o que um filtro de N frames faz. Duração não muda.
DEFAULT_ROI_MIN_VISIT_S: Final[float] = 0.2
# Fusão de lacunas DESLIGADA por padrão: o debounce assimétrico já exige N
# frames fora para registrar a saída, então fundir visitas por tempo em cima
# disso juntaria visitas que o pesquisador não pediu para juntar. O mecanismo
# fica disponível para quem tem rastreamento ruidoso.
DEFAULT_ROI_MIN_GAP_S: Final[float] = 0.0

# Teto do ``dt`` creditado a uma ROI. ``None`` = automático: o teto vira
# ``MAX_GAP_AUTO_FACTOR`` vezes a mediana do intervalo observado entre frames
# analisados. ``math.inf`` desliga o teto (comportamento histórico: uma lacuna
# de rastreamento de 5 s era creditada INTEIRA à ROI onde o animal reapareceu).
DEFAULT_ROI_MAX_GAP_S: Final[float | None] = None
MAX_GAP_AUTO_FACTOR: Final[float] = 3.0

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

# Regras em que o limiar 0 é o predicado de sobreposição pura. Derivado, para
# não haver duas listas contando a mesma exceção de formas diferentes.
_ANY_OVERLAP_RULES: Final[frozenset[str]] = _OVERLAP_RULES - _STRICT_OVERLAP_RULES

# Chaves reconhecidas em ``project_data["roi_settings"]`` (mesmos nomes que o
# editor de configurações já grava — não inventar chaves novas).
_KEY_RULE: Final[str] = "roi_inclusion_rule"
_KEY_BUFFER: Final[str] = "roi_buffer_radius_value"
_KEY_OVERLAP: Final[str] = "roi_min_bbox_overlap_ratio"
_KEY_BASIS: Final[str] = "roi_bbox_overlap_basis"
_KEY_ENTER: Final[str] = "roi_flutter_enter_frames"
_KEY_EXIT: Final[str] = "roi_flutter_exit_frames"
_KEY_MIN_VISIT: Final[str] = "roi_min_visit_s"
_KEY_MIN_GAP: Final[str] = "roi_min_gap_s"
_KEY_MAX_GAP: Final[str] = "roi_max_gap_s"


class _Missing:
    """Sentinela de "chave ausente", distinta de ``None``.

    Necessária só para ``roi_max_gap_s``, onde ``None`` é um valor com
    significado próprio ("teto automático") e não pode ser confundido com a
    ausência da chave. Os demais campos não têm essa ambiguidade.
    """

    def __repr__(self) -> str:  # pragma: no cover - só para depuração
        return "<MISSING>"


_MISSING: Final[_Missing] = _Missing()


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

    A garantia vale para **toda** construção, não só para o que sai do
    :func:`resolve_roi_rule`: a normalização mora no ``__post_init__``. Antes
    ela ficava só no caminho do resolvedor, então uma instância criada à mão
    podia levar um valor fora de faixa (um limiar negativo, por exemplo) direto
    para a geometria — e um limiar negativo faria ``ratio >= limiar`` valer
    para caixas que nem tocam a ROI.
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

    #: Frames consecutivos DENTRO para confirmar uma entrada, e frames
    #: consecutivos FORA para confirmar uma saída. ``1`` em ambos desliga o
    #: debounce (a presença crua vira a série estável).
    flutter_enter_frames: int = DEFAULT_ROI_FLUTTER_ENTER_FRAMES
    flutter_exit_frames: int = DEFAULT_ROI_FLUTTER_EXIT_FRAMES

    #: Visita mais curta que isto é descartada; lacuna mais curta que isto
    #: funde as duas visitas adjacentes. ``0.0`` desliga cada um.
    min_visit_s: float = DEFAULT_ROI_MIN_VISIT_S
    min_gap_s: float = DEFAULT_ROI_MIN_GAP_S

    #: Teto do ``dt`` creditado a uma ROI, em segundos. ``None`` = automático
    #: (:data:`MAX_GAP_AUTO_FACTOR` × mediana do intervalo observado);
    #: ``math.inf`` = sem teto.
    max_gap_s: float | None = DEFAULT_ROI_MAX_GAP_S

    def __post_init__(self) -> None:
        """Torna a instância autoconsistente com a própria regra.

        Rede de segurança, não validação de entrada: quem resolve a partir de
        projeto/settings já caiu de nível com log em ``_coerce_*``, então aqui
        só chega combinação genuinamente incoerente (ou construção à mão). Cada
        campo fora de faixa vira o default canônico e é logado — nunca levanta,
        porque isto roda no loop ao vivo.
        """
        object.__setattr__(self, "rule", _sanitize_rule(self.rule))
        object.__setattr__(
            self, "buffer_radius_value", _sanitize_buffer(self.rule, self.buffer_radius_value)
        )
        object.__setattr__(
            self,
            "min_bbox_overlap_ratio",
            _sanitize_overlap(self.rule, self.min_bbox_overlap_ratio),
        )
        object.__setattr__(self, "bbox_overlap_basis", _sanitize_basis(self.bbox_overlap_basis))
        object.__setattr__(
            self,
            "flutter_enter_frames",
            _sanitize_frames(
                _KEY_ENTER, self.flutter_enter_frames, DEFAULT_ROI_FLUTTER_ENTER_FRAMES
            ),
        )
        object.__setattr__(
            self,
            "flutter_exit_frames",
            _sanitize_frames(_KEY_EXIT, self.flutter_exit_frames, DEFAULT_ROI_FLUTTER_EXIT_FRAMES),
        )
        object.__setattr__(
            self,
            "min_visit_s",
            _sanitize_seconds(_KEY_MIN_VISIT, self.min_visit_s, DEFAULT_ROI_MIN_VISIT_S),
        )
        object.__setattr__(
            self,
            "min_gap_s",
            _sanitize_seconds(_KEY_MIN_GAP, self.min_gap_s, DEFAULT_ROI_MIN_GAP_S),
        )
        object.__setattr__(self, "max_gap_s", _sanitize_max_gap(self.max_gap_s))

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

        A condição é exatamente a semântica documentada — ``bbox_intersects``
        **e** limiar exatamente zero. Um ``<= 0.0`` solto trataria um limiar
        negativo como este caso especial, mascarando entrada inválida; e um
        ``== 0.0`` sem a regra responderia True para ``seg_overlap``, onde zero
        não é válido. O ``__post_init__`` já garante que negativo não chega
        aqui; a condição estrita mantém a propriedade honesta mesmo assim.
        """
        return self.rule in _ANY_OVERLAP_RULES and self.min_bbox_overlap_ratio == 0.0

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

    @property
    def roi_flutter_enter_frames(self) -> int:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.flutter_enter_frames

    @property
    def roi_flutter_exit_frames(self) -> int:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.flutter_exit_frames

    @property
    def roi_min_visit_s(self) -> float:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.min_visit_s

    @property
    def roi_min_gap_s(self) -> float:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.min_gap_s

    @property
    def roi_max_gap_s(self) -> float | None:
        """Alias com o nome usado em ``Settings``/``roi_settings``."""
        return self.max_gap_s

    def to_roi_settings(self) -> dict[str, Any]:
        """Serializa para ``project_data["roi_settings"]``."""
        return {
            _KEY_RULE: self.rule,
            _KEY_BUFFER: self.buffer_radius_value,
            _KEY_OVERLAP: self.min_bbox_overlap_ratio,
            _KEY_BASIS: self.bbox_overlap_basis,
            _KEY_ENTER: self.flutter_enter_frames,
            _KEY_EXIT: self.flutter_exit_frames,
            _KEY_MIN_VISIT: self.min_visit_s,
            _KEY_MIN_GAP: self.min_gap_s,
            _KEY_MAX_GAP: self.max_gap_s,
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


def _log_resolve_invalid(field: str, value: Any, source: str, fallback: Any) -> None:
    """Registra um valor descartado por nível de precedência."""
    log.warning(
        "roi_rule.resolve.invalid_value",
        field=field,
        value=value,
        source=source,
        fallback=fallback,
    )


def _coerce_frames(value: Any, fallback: int, *, field: str, source: str) -> int:
    """Converte e valida uma contagem de frames; cai em ``fallback`` se inválida."""
    if value is None:
        return fallback
    count = _as_frame_count(value)
    if count is None:
        _log_resolve_invalid(field, value, source, fallback)
        return fallback
    return count


def _coerce_seconds(value: Any, fallback: float, *, field: str, source: str) -> float:
    """Converte e valida uma duração em segundos; cai em ``fallback`` se inválida."""
    if value is None:
        return fallback
    number = _as_finite_float(value)
    if number is None or number < 0.0:
        _log_resolve_invalid(field, value, source, fallback)
        return fallback
    return number


def _coerce_max_gap(value: Any, fallback: float | None, *, source: str) -> float | None:
    """Converte e valida o teto de ``dt``.

    ``roi_max_gap_s`` é o único campo em que ``None`` é um VALOR ("automático"),
    não a ausência de valor. Por isso a ausência é sinalizada por
    :data:`_MISSING`, e não por ``None``: com ``.get(key)`` puro, um projeto que
    grava ``roi_max_gap_s: null`` para voltar ao automático não conseguiria
    sobrepor um teto numérico vindo do global — o ``null`` seria lido como "não
    informado" e o número do global sobreviveria.

    O caminho é real e silencioso: :meth:`RoiRuleConfig.to_roi_settings` SEMPRE
    grava a chave, então um projeto em modo automático persistido contra um
    global numérico ressuscitaria o número do global na próxima resolução.
    """
    if value is _MISSING:
        return fallback
    if value is None:
        # ``null`` explícito = automático, e é um override legítimo.
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        _log_resolve_invalid(_KEY_MAX_GAP, value, source, fallback)
        return fallback
    if number == math.inf or (math.isfinite(number) and number > 0.0):
        return number
    _log_resolve_invalid(_KEY_MAX_GAP, value, source, fallback)
    return fallback


def _log_sanitized(field: str, value: Any, fallback: Any) -> None:
    """Registra um campo incoerente trocado pelo default canônico."""
    log.warning(
        "roi_rule.config.sanitized",
        field=field,
        value=value,
        fallback=fallback,
    )


def _sanitize_rule(rule: Any) -> str:
    """Nome de regra desconhecido vira o default canônico."""
    if isinstance(rule, str) and rule in VALID_ROI_INCLUSION_RULES:
        return rule
    _log_sanitized(_KEY_RULE, rule, DEFAULT_ROI_INCLUSION_RULE)
    return DEFAULT_ROI_INCLUSION_RULE


def _as_finite_float(value: Any) -> float | None:
    """Converte para float finito; ``None`` quando não dá (texto, NaN, ±inf)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sanitize_buffer(rule: str, buffer_radius: Any) -> float:
    """Raio negativo — ou zero na regra que o EXIGE — vira o default."""
    number = _as_finite_float(buffer_radius)
    if number is not None and (number > 0.0 if rule in _BUFFERED_RULES else number >= 0.0):
        return number
    _log_sanitized(_KEY_BUFFER, buffer_radius, DEFAULT_BUFFER_RADIUS_VALUE)
    return DEFAULT_BUFFER_RADIUS_VALUE


def _sanitize_overlap(rule: str, overlap_ratio: Any) -> float:
    """Fração fora de faixa vira o default; o mínimo depende da regra.

    Zero só é aceito nas regras de :data:`_ANY_OVERLAP_RULES` (hoje,
    ``bbox_intersects``), onde é o predicado de sobreposição pura. Negativo
    nunca é aceito: ``ratio >= limiar_negativo`` valeria até para caixas que
    não tocam a ROI.
    """
    number = _as_finite_float(overlap_ratio)
    low_ok = number is not None and (
        number > 0.0 if rule in _STRICT_OVERLAP_RULES else number >= 0.0
    )
    if number is not None and low_ok and number <= 1.0:
        return number
    _log_sanitized(_KEY_OVERLAP, overlap_ratio, DEFAULT_MIN_BBOX_OVERLAP_RATIO)
    return DEFAULT_MIN_BBOX_OVERLAP_RATIO


def _sanitize_basis(basis: Any) -> str:
    """Denominador desconhecido vira o default canônico."""
    if isinstance(basis, str) and basis in VALID_BBOX_OVERLAP_BASES:
        return basis
    _log_sanitized(_KEY_BASIS, basis, DEFAULT_BBOX_OVERLAP_BASIS)
    return DEFAULT_BBOX_OVERLAP_BASIS


def _as_frame_count(value: Any) -> int | None:
    """Converte para inteiro ``>= 1``; ``None`` quando não dá.

    ``2.0`` passa (é o que sai de um YAML ou de um campo de texto), ``2.5`` não:
    meio frame não existe, e arredondar em silêncio esconderia o erro de
    digitação.
    """
    number = _as_finite_float(value)
    if number is None or not float(number).is_integer():
        return None
    count = int(number)
    return count if count >= 1 else None


def _sanitize_frames(field: str, value: Any, fallback: int) -> int:
    """Contagem de frames fora de faixa vira o default canônico."""
    count = _as_frame_count(value)
    if count is not None:
        return count
    _log_sanitized(field, value, fallback)
    return fallback


def _sanitize_seconds(field: str, value: Any, fallback: float) -> float:
    """Duração negativa ou não-finita vira o default canônico.

    ``0.0`` é válido e significa "desligado" — nunca é tratado como ausente,
    justamente a armadilha do ``x or default`` (``0.0 or 0.2`` é ``0.2``).
    """
    number = _as_finite_float(value)
    if number is not None and number >= 0.0:
        return number
    _log_sanitized(field, value, fallback)
    return fallback


def _sanitize_max_gap(value: Any) -> float | None:
    """Normaliza o teto de ``dt``: ``None`` (auto), ``inf`` (sem teto) ou ``> 0``.

    ``inf`` é aceito de propósito e não passa por :func:`_as_finite_float`: é o
    modo neutro, o único jeito de reproduzir bit a bit os números históricos.
    ``0`` e negativos não são: zerariam todo o tempo medido.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        _log_sanitized(_KEY_MAX_GAP, value, DEFAULT_ROI_MAX_GAP_S)
        return DEFAULT_ROI_MAX_GAP_S
    if number == math.inf or (math.isfinite(number) and number > 0.0):
        return number
    _log_sanitized(_KEY_MAX_GAP, value, DEFAULT_ROI_MAX_GAP_S)
    return DEFAULT_ROI_MAX_GAP_S


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

    # Debounce e limiares de duração não dependem da regra: nenhum deles muda
    # de faixa conforme a geometria escolhida, então a precedência é a simples.
    def _frames(key: str, default: int) -> int:
        value = default
        if settings_obj is not None:
            value = _coerce_frames(
                getattr(settings_obj, key, None), value, field=key, source="settings"
            )
        return _coerce_frames(roi_settings.get(key), value, field=key, source="project")

    def _seconds(key: str, default: float) -> float:
        value = default
        if settings_obj is not None:
            value = _coerce_seconds(
                getattr(settings_obj, key, None), value, field=key, source="settings"
            )
        return _coerce_seconds(roi_settings.get(key), value, field=key, source="project")

    # ``_MISSING`` (não ``None``) marca a ausência: ver :func:`_coerce_max_gap`.
    max_gap = DEFAULT_ROI_MAX_GAP_S
    if settings_obj is not None:
        max_gap = _coerce_max_gap(
            getattr(settings_obj, _KEY_MAX_GAP, _MISSING), max_gap, source="settings"
        )
    max_gap = _coerce_max_gap(roi_settings.get(_KEY_MAX_GAP, _MISSING), max_gap, source="project")

    # A autoconsistência final é do ``__post_init__`` — aqui os valores já
    # passaram pela coerção por nível de precedência.
    return RoiRuleConfig(
        rule=rule,
        buffer_radius_value=buffer_radius,
        min_bbox_overlap_ratio=overlap_ratio,
        bbox_overlap_basis=basis,
        flutter_enter_frames=_frames(_KEY_ENTER, DEFAULT_ROI_FLUTTER_ENTER_FRAMES),
        flutter_exit_frames=_frames(_KEY_EXIT, DEFAULT_ROI_FLUTTER_EXIT_FRAMES),
        min_visit_s=_seconds(_KEY_MIN_VISIT, DEFAULT_ROI_MIN_VISIT_S),
        min_gap_s=_seconds(_KEY_MIN_GAP, DEFAULT_ROI_MIN_GAP_S),
        max_gap_s=max_gap,
    )


def apply_roi_rule_to_settings(settings_obj: Any, config: RoiRuleConfig) -> Any:
    """Aplica ``config`` a um objeto de settings, no lugar, e o devolve.

    ``Settings`` usa ``validate_assignment=True`` com um validador cruzado
    (regra × parâmetros), então a ordem de atribuição importa: escrever a regra
    antes do parâmetro que ela exige levantaria ``ValidationError``. A ordem
    abaixo mantém o objeto válido em todos os passos intermediários — o que só
    é possível porque :class:`RoiRuleConfig` já chega normalizada.

    ``roi_bbox_overlap_basis``, o debounce e os limiares de duração ficam fora
    dessa dança: nenhum deles entra em invariante cruzada, então são escritos
    primeiro, sempre. Um campo NOVO que ganhe validação cruzada com a regra
    precisa entrar na ordenação abaixo, não aqui.
    """
    if settings_obj is None:
        return settings_obj

    for field, value in (
        (_KEY_BASIS, config.bbox_overlap_basis),
        (_KEY_ENTER, config.flutter_enter_frames),
        (_KEY_EXIT, config.flutter_exit_frames),
        (_KEY_MIN_VISIT, config.min_visit_s),
        (_KEY_MIN_GAP, config.min_gap_s),
        (_KEY_MAX_GAP, config.max_gap_s),
    ):
        setattr(settings_obj, field, value)

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

"""The one rule for "what experiment is this?" — animal model + protocol (ADR-014).

Until v8.1 nothing in a project said what was being studied: the app inferred
zebrafish-in-an-aquarium everywhere, and a Barnes-maze project could only be
recognised by the ROI it happened to be named ``toca``. Two independent axes now
travel in ``behavioral_config`` (the dict every analysis entry point already
receives, #695):

* ``animal_model`` — ``zebrafish`` | ``rodent`` | ``other``. Drives the interface
  vocabulary ("aquarium" vs "arena") and the per-species behavioural defaults.
* ``protocol`` — ``generic`` | ``barnes``. Drives the zone assistant, the
  analysis-window preset, the protocol metrics and the report sections.
* ``protocol_params`` — ``{<protocol>: {...}}``, each protocol's own parameters
  (``BarnesParams`` for ``barnes``). Validated by the protocol module, not here.

A project that declares nothing is ``generic`` + ``zebrafish``: every output of a
legacy project stays byte-identical. Every reader goes through
:func:`resolve_experiment_profile`; never read these keys at a call site
(guarded by ``tests/quality/test_single_source_rules.py``).

Bad values DEGRADE, never raise: an unknown animal model reads as ``other``, an
unknown protocol reads as ``generic`` with :attr:`ExperimentProfile.declared_protocol`
keeping the raw token so the report can say the protocol was not recognised
instead of silently analysing it as generic. Each degradation is logged and
returned in :attr:`ExperimentProfile.warnings`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import structlog

from zebtrack.i18n import _

__all__ = [
    "ANIMAL_MODEL_KEY",
    "PROTOCOL_KEY",
    "PROTOCOL_PARAMS_KEY",
    "AnimalModel",
    "ExperimentProfile",
    "ProtocolId",
    "forced_animal_model",
    "resolve_experiment_profile",
]

logger = structlog.get_logger()

#: ``behavioral_config`` keys. Persistence contract: never translated or renamed.
ANIMAL_MODEL_KEY = "animal_model"
PROTOCOL_KEY = "protocol"
PROTOCOL_PARAMS_KEY = "protocol_params"

#: Legacy project key that ``resolve_behavioral_config`` also reads.
_LEGACY_BLOCK_KEY = "behavioral_analysis"
_PROJECT_BLOCK_KEY = "behavioral_config"


class AnimalModel(StrEnum):
    """What is being studied. The tokens are persisted, never translated."""

    ZEBRAFISH = "zebrafish"
    RODENT = "rodent"
    OTHER = "other"


class ProtocolId(StrEnum):
    """Which behavioural protocol the project follows. Persisted tokens."""

    GENERIC = "generic"
    BARNES = "barnes"


#: Protocols that only make sense for one animal model. Choosing the protocol
#: forces the model; a project that declares another one is corrected (with a
#: warning) rather than analysed under the wrong vocabulary and defaults.
_FORCED_ANIMAL_MODEL: Mapping[ProtocolId, AnimalModel] = MappingProxyType(
    {ProtocolId.BARNES: AnimalModel.RODENT}
)

_DEFAULT_ANIMAL_MODEL = AnimalModel.ZEBRAFISH
_DEFAULT_PROTOCOL = ProtocolId.GENERIC


def forced_animal_model(protocol: ProtocolId) -> AnimalModel | None:
    """The animal model ``protocol`` imposes, or ``None`` when any model fits."""
    return _FORCED_ANIMAL_MODEL.get(protocol)


@dataclass(frozen=True, slots=True)
class ExperimentProfile:
    """The resolved answer to "what experiment is this?".

    Attributes:
        animal_model: The effective animal model (forced by the protocol when it
            imposes one).
        protocol: The effective protocol. ``GENERIC`` also for an unrecognised
            token; see ``declared_protocol``.
        protocol_params: The raw ``protocol_params[<protocol>]`` mapping of the
            effective protocol (``{}`` when absent or malformed). The protocol
            module validates it.
        declared_protocol: The normalised token found in the configuration when it
            is NOT a known protocol, else ``None``. Lets the report state that a
            protocol was declared but not recognised (a project written by a newer
            version) instead of passing it off as generic.
        warnings: Translated, user-facing degradation messages, in order.
    """

    animal_model: AnimalModel = _DEFAULT_ANIMAL_MODEL
    protocol: ProtocolId = _DEFAULT_PROTOCOL
    protocol_params: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    declared_protocol: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def is_generic(self) -> bool:
        """Generic protocol that was not an unrecognised declaration."""
        return self.protocol is ProtocolId.GENERIC and self.declared_protocol is None


def _block_of(project_data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The project's ``behavioral_config`` (or legacy ``behavioral_analysis``) block."""
    if not isinstance(project_data, Mapping):
        return {}
    if _PROJECT_BLOCK_KEY in project_data:
        block = project_data.get(_PROJECT_BLOCK_KEY)
    else:
        block = project_data.get(_LEGACY_BLOCK_KEY)
    return block if isinstance(block, Mapping) else {}


def _first_declared(sources: tuple[Mapping[str, Any], ...], key: str) -> tuple[bool, Any]:
    """``(found, value)`` of the first source that declares ``key`` (None = undeclared)."""
    for source in sources:
        if key in source and source[key] is not None:
            return True, source[key]
    return False, None


def _normalise_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    return token or None


def resolve_experiment_profile(
    project_data: Mapping[str, Any] | None = None,
    behavioral_config: Mapping[str, Any] | None = None,
) -> ExperimentProfile:
    """Resolve the experiment profile; the only reader of the profile keys.

    Precedence, per key: ``behavioral_config`` (what the analysis entry point was
    handed, already merged from settings and project by
    ``resolve_behavioral_config``) > ``project_data["behavioral_config"]`` (or the
    legacy ``behavioral_analysis`` block) > the legacy default
    (``zebrafish`` + ``generic``). A key whose value is ``None`` is undeclared.

    Never raises: malformed values degrade as the module docstring describes.

    Args:
        project_data: The project dictionary, or ``None`` (single video, ad-hoc live).
        behavioral_config: The behavioural configuration of this run, or ``None``.

    Returns:
        The resolved, immutable :class:`ExperimentProfile`.
    """
    sources: tuple[Mapping[str, Any], ...] = (
        behavioral_config if isinstance(behavioral_config, Mapping) else {},
        _block_of(project_data),
    )
    warnings: list[str] = []

    model_found, raw_model = _first_declared(sources, ANIMAL_MODEL_KEY)
    protocol_found, raw_protocol = _first_declared(sources, PROTOCOL_KEY)
    params_found, raw_params = _first_declared(sources, PROTOCOL_PARAMS_KEY)

    animal_model = _DEFAULT_ANIMAL_MODEL
    if model_found:
        token = _normalise_token(raw_model)
        try:
            animal_model = AnimalModel(token or "")
        except ValueError:
            animal_model = AnimalModel.OTHER
            logger.warning("experiment_profile.animal_model.unknown", value=repr(raw_model))
            warnings.append(
                _(
                    "Unknown animal model {value} in the project configuration; "
                    "it is treated as 'other'."
                ).format(value=repr(raw_model))
            )

    protocol = _DEFAULT_PROTOCOL
    declared_protocol: str | None = None
    if protocol_found:
        token = _normalise_token(raw_protocol)
        try:
            protocol = ProtocolId(token or "")
        except ValueError:
            declared_protocol = token or repr(raw_protocol)
            logger.warning("experiment_profile.protocol.unknown", value=repr(raw_protocol))
            warnings.append(
                _(
                    "Unknown protocol {value} in the project configuration; no "
                    "protocol-specific metric is computed for it."
                ).format(value=repr(raw_protocol))
            )

    forced = forced_animal_model(protocol)
    if forced is not None and animal_model is not forced:
        if model_found:
            logger.warning(
                "experiment_profile.animal_model.forced",
                protocol=protocol.value,
                declared=animal_model.value,
                forced=forced.value,
            )
            warnings.append(
                _(
                    "The {protocol} protocol requires the animal model '{forced}'; "
                    "the declared '{declared}' was replaced."
                ).format(protocol=protocol.value, forced=forced.value, declared=animal_model.value)
            )
        animal_model = forced

    protocol_params: Mapping[str, Any] = MappingProxyType({})
    if params_found:
        if isinstance(raw_params, Mapping):
            own = raw_params.get(protocol.value)
            if isinstance(own, Mapping):
                protocol_params = MappingProxyType(dict(own))
            elif own is not None:
                logger.warning(
                    "experiment_profile.protocol_params.malformed",
                    protocol=protocol.value,
                    value_type=type(own).__name__,
                )
                warnings.append(
                    _(
                        "The parameters of the {protocol} protocol are not a mapping; "
                        "its defaults are used."
                    ).format(protocol=protocol.value)
                )
        else:
            logger.warning(
                "experiment_profile.protocol_params.malformed",
                protocol=protocol.value,
                value_type=type(raw_params).__name__,
            )
            warnings.append(
                _("The protocol parameters are not a mapping; every protocol uses its defaults.")
            )

    return ExperimentProfile(
        animal_model=animal_model,
        protocol=protocol,
        protocol_params=protocol_params,
        declared_protocol=declared_protocol,
        warnings=tuple(warnings),
    )

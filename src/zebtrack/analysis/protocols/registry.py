"""Registry of the built-in protocols and the dispatch of their metrics (ADR-014).

The registry is built lazily, on first use, from :func:`_builtin_specs`, so
importing the analysis layer never imports a protocol's implementation (and its
heavier dependencies) for a generic project. A protocol joins the registry by
adding its spec to :func:`_builtin_specs` — the only edit a protocol module makes
outside its own package.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import structlog

from zebtrack.analysis.protocols.base import (
    ProtocolContext,
    ProtocolSpec,
    ProtocolStatus,
    UnavailableReason,
    none_metrics,
    unavailable_metrics,
)
from zebtrack.core.services.experiment_profile import ProtocolId
from zebtrack.i18n import _

__all__ = [
    "compute_protocol_metrics",
    "get_protocol",
    "registered_protocols",
]

logger = structlog.get_logger()

_REQUIRED_RESULT_KEYS = ("status", "protocol", "version")

_registry: Mapping[ProtocolId, ProtocolSpec] | None = None


def _builtin_specs() -> tuple[ProtocolSpec, ...]:
    """The protocols shipped with the app.

    ``generic`` is not a spec: it is the absence of one. Imported here, not at
    module level, so a generic analysis never imports a protocol's implementation.
    """
    from zebtrack.analysis.protocols.barnes.spec import BARNES_SPEC

    return (BARNES_SPEC,)


def _build_registry(specs: tuple[ProtocolSpec, ...]) -> Mapping[ProtocolId, ProtocolSpec]:
    registry: dict[ProtocolId, ProtocolSpec] = {}
    for spec in specs:
        if spec.protocol is ProtocolId.GENERIC:
            raise ValueError("The generic protocol has no spec; it is the absence of one.")
        if spec.protocol in registry:
            raise ValueError(f"Protocol {spec.protocol.value!r} is registered twice.")
        registry[spec.protocol] = spec
    return MappingProxyType(registry)


def _get_registry() -> Mapping[ProtocolId, ProtocolSpec]:
    global _registry
    if _registry is None:
        _registry = _build_registry(_builtin_specs())
    return _registry


def get_protocol(protocol: ProtocolId) -> ProtocolSpec | None:
    """The spec of ``protocol``, or ``None`` (always ``None`` for ``generic``)."""
    return _get_registry().get(protocol)


def registered_protocols() -> tuple[ProtocolId, ...]:
    """Protocols with a spec, in registration order (``generic`` excluded)."""
    return tuple(_get_registry())


def compute_protocol_metrics(context: ProtocolContext) -> dict[str, Any]:
    """``report["protocol_metrics"]`` for one video. Never raises.

    * generic profile → exactly ``{"status": "none"}``;
    * protocol declared but unknown → ``unavailable`` / ``unknown_protocol``;
    * known protocol without a registered spec → ``unavailable`` / ``unregistered``
      plus a validation warning;
    * the spec's ``compute_metrics`` raises, or returns something without
      ``status``/``protocol``/``version`` → ``error`` plus a validation warning.

    The profile's own degradation warnings are the caller's to report (the
    analysis hook adds them before calling this).
    """
    profile = context.profile
    if profile.is_generic:
        return none_metrics()
    if profile.declared_protocol is not None:
        return unavailable_metrics(profile.declared_protocol, UnavailableReason.UNKNOWN_PROTOCOL)

    protocol = profile.protocol
    spec = get_protocol(protocol)
    if spec is None:
        logger.warning("protocol_metrics.unregistered", protocol=protocol.value)
        context.warnings.append(
            _(
                "The {protocol} protocol is not available in this version; its "
                "metrics were not computed."
            ).format(protocol=protocol.value)
        )
        return unavailable_metrics(protocol.value, UnavailableReason.UNREGISTERED)

    try:
        result = spec.compute_metrics(context)
    # except Exception justified: a protocol's metrics must never cost the whole
    # report (trajectory, ROI and window metrics are still valid), but the report
    # has to say they are missing and why.
    except Exception as exc:
        logger.error("protocol_metrics.compute.failed", protocol=protocol.value, error=str(exc))
        context.warnings.append(
            _("The {protocol} protocol metrics could not be computed: {error}").format(
                protocol=protocol.value, error=exc
            )
        )
        return unavailable_metrics(
            protocol.value,
            UnavailableReason.EXCEPTION,
            status=ProtocolStatus.ERROR,
            error=str(exc),
        )

    if not isinstance(result, dict) or any(key not in result for key in _REQUIRED_RESULT_KEYS):
        logger.error(
            "protocol_metrics.compute.malformed",
            protocol=protocol.value,
            result_type=type(result).__name__,
        )
        context.warnings.append(
            _(
                "The {protocol} protocol returned malformed metrics; they were "
                "left out of the report."
            ).format(protocol=protocol.value)
        )
        return unavailable_metrics(
            protocol.value,
            UnavailableReason.EXCEPTION,
            status=ProtocolStatus.ERROR,
            error="malformed result",
        )
    return result

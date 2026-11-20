"""Behavioural protocols layered on the generic analysis (ADR-014).

See :mod:`zebtrack.analysis.protocols.base` for the types and
:mod:`zebtrack.analysis.protocols.registry` for the registry and dispatch. The
contract every protocol front codes against is
``docs/tasks/v8.1/barnes/CONTRACTS.md``.
"""

from zebtrack.analysis.protocols.base import (
    PROTOCOL_INPUTS_KEY,
    PROTOCOL_METRICS_KEY,
    GenericReportSection,
    ProtocolContext,
    ProtocolSpec,
    ProtocolStatus,
    UnavailableReason,
    clear_protocol_input,
    none_metrics,
    protocol_inputs_for,
    protocol_inputs_of_entry,
    set_protocol_input,
    unavailable_metrics,
)
from zebtrack.analysis.protocols.registry import (
    compute_protocol_metrics,
    get_protocol,
    registered_protocols,
)

__all__ = [
    "PROTOCOL_INPUTS_KEY",
    "PROTOCOL_METRICS_KEY",
    "GenericReportSection",
    "ProtocolContext",
    "ProtocolSpec",
    "ProtocolStatus",
    "UnavailableReason",
    "clear_protocol_input",
    "compute_protocol_metrics",
    "get_protocol",
    "none_metrics",
    "protocol_inputs_for",
    "protocol_inputs_of_entry",
    "registered_protocols",
    "set_protocol_input",
    "unavailable_metrics",
]

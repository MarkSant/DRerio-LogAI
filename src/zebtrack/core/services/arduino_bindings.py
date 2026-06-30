"""Arduino per-zone command bindings (project-scoped configuration).

A *binding* maps a ROI to the numeric tokens the application sends to the
Arduino when a tracked animal **enters** and **leaves** that ROI. DRerio LogAI
is a pure transport here: it only forwards the integer — what the firmware does
with it (light an LED, fire a relay, etc.) lives entirely in the Arduino sketch.

The model is edge-triggered: a token is emitted on the transition, and the
device is expected to hold the resulting state (e.g. an LED stays on between the
enter and exit tokens). ``session_end_tokens`` provides the "turn everything
off" sweep emitted when the live session stops.

Persisted in ``project_data["arduino_bindings"]`` as a plain list of dicts so it
round-trips through the existing project JSON without schema migrations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

log = structlog.get_logger()

# Key under which bindings are stored inside ``project_data``.
PROJECT_DATA_KEY = "arduino_bindings"


class ArduinoBinding(BaseModel):
    """A single ROI → enter/exit token mapping.

    ``on_enter``/``on_exit`` are optional: a binding may drive only one edge
    (e.g. send a token on enter but nothing on exit). Tokens are non-negative
    integers because the reference sketch reads them via ``Serial.parseInt()``.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    roi: str = Field(..., min_length=1, description="ROI name this binding targets.")
    on_enter: int | None = Field(
        default=None, ge=0, description="Token sent when an animal enters the ROI."
    )
    on_exit: int | None = Field(
        default=None, ge=0, description="Token sent when an animal leaves the ROI."
    )


class ArduinoBindingConfig(BaseModel):
    """The full set of per-zone bindings for a project."""

    model_config = ConfigDict(extra="ignore")

    bindings: list[ArduinoBinding] = Field(default_factory=list)

    @classmethod
    def from_project_data(cls, project_data: Mapping[str, Any] | None) -> ArduinoBindingConfig:
        """Build a config from ``project_data`` (tolerant of missing/legacy shapes).

        Accepts either a bare list of binding dicts (the canonical storage form)
        or a ``{"bindings": [...]}`` wrapper. Malformed entries are dropped with
        a warning rather than raising, so a corrupt project never blocks a live
        session from starting.
        """
        if not project_data:
            return cls()
        raw = project_data.get(PROJECT_DATA_KEY)
        if raw is None:
            return cls()

        entries: Any = raw.get("bindings") if isinstance(raw, Mapping) else raw
        if not isinstance(entries, list):
            log.warning("arduino_bindings.parse.unexpected_shape", type=type(raw).__name__)
            return cls()

        bindings: list[ArduinoBinding] = []
        for entry in entries:
            try:
                bindings.append(ArduinoBinding.model_validate(entry))
            # except Exception justified: skip malformed user/legacy entries.
            except Exception:
                log.warning("arduino_bindings.parse.invalid_entry", entry=entry)
        return cls(bindings=bindings)

    def to_storage(self) -> list[dict[str, Any]]:
        """Serialize to the plain list-of-dicts form stored in ``project_data``."""
        return [b.model_dump() for b in self.bindings]

    def roi_names(self) -> list[str]:
        """ROI names referenced by the bindings (order preserved, deduplicated)."""
        seen: set[str] = set()
        names: list[str] = []
        for b in self.bindings:
            if b.roi not in seen:
                seen.add(b.roi)
                names.append(b.roi)
        return names

    def session_end_tokens(self) -> list[int]:
        """Tokens to emit when the session ends — every distinct ``on_exit``.

        This drives the "turn everything off" sweep: any ROI whose exit token
        would normally clear a device state is cleared, even if an animal was
        still inside when recording stopped.
        """
        seen: set[int] = set()
        tokens: list[int] = []
        for b in self.bindings:
            if b.on_exit is not None and b.on_exit not in seen:
                seen.add(b.on_exit)
                tokens.append(b.on_exit)
        return tokens

    def is_empty(self) -> bool:
        """True when there are no bindings (the live hook can skip all work)."""
        return not self.bindings

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
from typing import Any, NamedTuple

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

log = structlog.get_logger()

# Key under which bindings are stored inside ``project_data``.
PROJECT_DATA_KEY = "arduino_bindings"


class TokenConflict(NamedTuple):
    """A token used with two contradictory meanings across the binding set.

    The application is a pure transport: it cannot know that token ``5`` means
    "green LED on" to the firmware. But it *can* tell that the same integer is
    wired as the **enter** token of one ROI and the **exit** token of another —
    a mapping that cannot be right, because a single firmware command cannot
    both set and clear a device state.

    This is the failure mode of an off-by-one while filling the bindings table
    (e.g. ``Z3 = 4/5`` when the sketch expects ``Z3 = 5/6``): the ROI's "exit"
    silently latches the *next* zone's device on, and the session-end sweep —
    built from the exit tokens — turns it on instead of off.
    """

    token: int
    enter_rois: list[str]
    exit_rois: list[str]

    def describe(self) -> str:
        """Human-readable one-liner for logs and the UI status line."""
        return (
            f"token {self.token}: entrada de {', '.join(self.enter_rois)} "
            f"e saída de {', '.join(self.exit_rois)}"
        )


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
    label: str | None = Field(
        default=None,
        description=(
            "Optional operator-facing name for whatever this token drives "
            "('Choque', 'Bomba', 'Luz azul'). Purely cosmetic — never sent to the "
            "device. The firmware's ACK text names the channel from the sketch's "
            "point of view ('Red LED 1'), which is wrong whenever the pin drives "
            "something else; this is where the operator records what is really "
            "wired. Empty/blank is normalized to None."
        ),
    )

    @field_validator("label", mode="before")
    @classmethod
    def _blank_label_is_none(cls, value: Any) -> Any:
        """Treat an empty or whitespace-only label as absent.

        The panel's entry widget yields "" when the operator clears the field.
        Keeping that would leave two different representations of "no label"
        ("" and None), so two bindings that mean the same thing would compare
        unequal and round-trip through ``to_storage`` as different JSON. One
        canonical absent value keeps equality and persistence predictable.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def display_name(self) -> str:
        """Operator-facing name for this binding's target: the label, else the ROI."""
        return self.label or self.roi


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

        The sweep only *means* "off" if each exit token clears something in the
        firmware. When :meth:`token_conflicts` is non-empty that assumption is
        broken and the sweep can latch a device **on**; callers should surface
        the conflicts rather than silently dropping tokens, since only the
        sketch knows what each integer does.
        """
        seen: set[int] = set()
        tokens: list[int] = []
        for b in self.bindings:
            if b.on_exit is not None and b.on_exit not in seen:
                seen.add(b.on_exit)
                tokens.append(b.on_exit)
        return tokens

    def token_conflicts(self) -> list[TokenConflict]:
        """Tokens wired as an ``on_enter`` here and an ``on_exit`` there.

        Returns one entry per offending token, ordered by token value. An empty
        list means every token has a single unambiguous role across the whole
        binding set. See :class:`TokenConflict` for why this matters.
        """
        enter_by_token: dict[int, list[str]] = {}
        exit_by_token: dict[int, list[str]] = {}
        for b in self.bindings:
            if b.on_enter is not None:
                enter_by_token.setdefault(b.on_enter, []).append(b.roi)
            if b.on_exit is not None:
                exit_by_token.setdefault(b.on_exit, []).append(b.roi)

        return [
            TokenConflict(
                token=token,
                enter_rois=enter_by_token[token],
                exit_rois=exit_by_token[token],
            )
            for token in sorted(set(enter_by_token) & set(exit_by_token))
        ]

    def is_empty(self) -> bool:
        """True when there are no bindings (the live hook can skip all work)."""
        return not self.bindings

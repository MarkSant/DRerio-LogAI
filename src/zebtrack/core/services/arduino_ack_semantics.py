"""Reads the firmware's own ACK text to check a per-zone binding is sane.

DRerio LogAI only transports integers: it cannot know that token ``5`` means
"green LED on" to a given sketch. But the reference firmware answers every
command with a human-readable line (``"Green LED ON"``, ``"Blue LED OFF"``),
and that line is *evidence* — it says what the device just did.

This module turns that evidence into a check. A token bound to a ROI's **enter**
edge that answers ``"... OFF"``, or an **exit** edge that answers ``"... ON"``,
is inverted: the animal arriving turns the stimulus off and leaving turns it on.
That is exactly the failure mode observed on 2026-08-04, where the bindings were
``Z1=1/5, Z2=2/6, Z3=3/7, Z4=4/8`` (a plausible "enters 1-4, exits 5-8" layout)
against a sketch that pairs ON/OFF consecutively — ``Z4 enter`` answered
``"Blue LED OFF"`` and no stimulus ever fired.

Deliberately conservative: anything it cannot classify with confidence returns
``None`` and produces no warning. A sketch that ACKs with opaque text (or none
at all) simply gets no checking, never a false alarm.
"""

from __future__ import annotations

import re
from typing import Literal

from zebtrack.i18n import _

AckState = Literal["on", "off"]

# Word-anchored so "ON" does not match inside "COMMAND" and, crucially, so
# "LIGADO" does not match inside "DESLIGADO" (no word boundary after "DES").
# "ACES" is narrowed to "ACES[AO]" (acesa/aceso/acesas/acesos) so an unrelated
# "acesso"/"acessando" in a firmware message is not read as "turned on".
_OFF_RE = re.compile(r"\b(?:OFF|DESLIG\w*|APAGA\w*)\b", re.IGNORECASE)
_ON_RE = re.compile(r"\b(?:ON|LIG\w*|ACES[AO]\w*)\b", re.IGNORECASE)  # i18n: not-ui — regex


def classify_ack(ack_text: str | None) -> AckState | None:
    """Classify a firmware ACK line as turning something on or off.

    Args:
        ack_text: The line the firmware answered with, or None.

    Returns:
        ``"on"``, ``"off"``, or None when the text is missing, opaque, or
        ambiguous (both readings present) — in which case no claim is made.
    """
    if not ack_text:
        return None
    text = str(ack_text)
    is_off = bool(_OFF_RE.search(text))
    is_on = bool(_ON_RE.search(text))
    if is_off and not is_on:
        return "off"
    if is_on and not is_off:
        return "on"
    return None


def edge_ack_is_inverted(edge: str | None, ack_text: str | None) -> bool:
    """True when the ACK contradicts the ROI edge that triggered it.

    ``enter`` is expected to turn a stimulus on and ``exit`` to turn it off.
    Returns False whenever the ACK cannot be classified, so an unclassifiable
    firmware never produces a warning.

    Args:
        edge: ``"enter"`` or ``"exit"`` (the ROI transition that sent the token).
        ack_text: The firmware's reply to that token.
    """
    state = classify_ack(ack_text)
    if state is None or edge not in ("enter", "exit"):
        return False
    return (edge == "enter" and state == "off") or (edge == "exit" and state == "on")


def describe_inversion(roi: str | None, edge: str | None, token: int | None, ack_text: str) -> str:
    """Human-readable one-liner for logs and the bindings panel."""
    # Two COMPLETE sentences chosen by `edge` instead of splicing the same
    # noun into a template twice. The Portuguese got away with it because
    # "entrada" and "saída" are both feminine; no other language owes us that.
    if edge == "enter":
        return _(
            '{roi} enter → token {token} → the firmware replied "{ack}", '
            "but an enter should switch it ON"
        ).format(roi=roi, token=token, ack=ack_text)
    return _(
        '{roi} exit → token {token} → the firmware replied "{ack}", '
        "but an exit should switch it OFF"
    ).format(roi=roi, token=token, ack=ack_text)

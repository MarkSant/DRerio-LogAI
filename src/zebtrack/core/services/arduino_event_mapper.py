"""Edge-triggered ROI-transition → Arduino-token mapper.

Pure state machine: fed the set of ROIs occupied this frame, it emits the
configured tokens only on transitions (a ROI newly entered or newly left),
never every frame. The Arduino holds the resulting device state between the
enter and exit tokens, so "permanence" needs no serial traffic.

Scope is "any-track": a ROI is considered occupied while *any* detected animal
is inside it; the enter token fires when the first animal enters and the exit
token fires when the last one leaves.

Multi-aquarium sessions (#656) feed the occupancy PER AQUARIUM
(:meth:`ArduinoEventMapper.update_scoped`): a binding scoped to an aquarium
(``ArduinoBinding.aquarium_id``) reads only that aquarium; an unscoped one is
occupied while any aquarium occupies its ROI. A single-aquarium session is
aquarium 0, so :meth:`ArduinoEventMapper.update` keeps its exact behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple

import structlog

from zebtrack.core.services.arduino_bindings import ArduinoBinding

log = structlog.get_logger()

#: ``(aquarium_id, roi)`` — ``aquarium_id`` is ``None`` for an unscoped binding.
BindingKey = tuple[int | None, str]

#: The aquarium a single-aquarium session's occupancy belongs to.
SINGLE_AQUARIUM_ID = 0


class RoiTokenEvent(NamedTuple):
    """A single edge-triggered ROI transition and the token it emits.

    ``edge`` is ``"enter"`` or ``"exit"``. Used by the closed-loop latency log
    so each serial token can be attributed to the ROI transition that caused it.
    ``aquarium_id`` is the binding's scope (``None`` for an unscoped binding).
    """

    roi: str
    edge: str
    token: int
    aquarium_id: int | None = None


def _sort_key(key: BindingKey) -> tuple[str, int]:
    aquarium_id, roi = key
    # Unscoped first, then by aquarium: with only unscoped bindings this is the
    # pre-#656 order (by ROI name).
    return (roi, -1 if aquarium_id is None else aquarium_id)


class ArduinoEventMapper:
    """Translates ROI occupancy transitions into ordered token lists.

    Args:
        bindings: The active per-zone bindings. Bindings without a usable token
            for an edge simply produce nothing on that edge.
    """

    def __init__(self, bindings: Iterable[ArduinoBinding]) -> None:
        # Last binding wins if a (aquarium, ROI) pair is listed twice — keep it
        # deterministic. Keyed by the pair, not the name: two aquariums of one
        # session usually repeat ROI names, and keying by name alone made the
        # second binding silently replace the first.
        self._by_key: dict[BindingKey, ArduinoBinding] = {
            (b.aquarium_id, b.roi): b for b in bindings
        }
        self._prev: set[BindingKey] = set()

    def update(self, occupied_rois: Iterable[str]) -> list[int]:
        """Advance one frame and return the tokens to send (possibly empty).

        Thin wrapper over :meth:`update_detailed` that discards the ROI/edge
        attribution. Kept for callers that only need the raw token stream.

        Args:
            occupied_rois: ROI names occupied this frame (extra names not in the
                bindings are ignored).
        """
        return [event.token for event in self.update_detailed(occupied_rois)]

    def update_detailed(self, occupied_rois: Iterable[str]) -> list[RoiTokenEvent]:
        """Advance one frame of a single-aquarium session.

        Args:
            occupied_rois: ROI names occupied this frame (extra names not in the
                bindings are ignored). They belong to aquarium 0.
        """
        return self.update_scoped({SINGLE_AQUARIUM_ID: occupied_rois})

    def update_scoped(
        self, occupied_by_aquarium: Mapping[int, Iterable[str]]
    ) -> list[RoiTokenEvent]:
        """Advance one frame and return the ordered ROI transition events.

        Exits are emitted before enters so that, when an animal moves directly
        from one ROI to another in a single frame, the old device state is
        cleared before the new one is set. Iteration is sorted for determinism.

        Args:
            occupied_by_aquarium: ROI names occupied this frame, per aquarium.
                An aquarium left out occupies nothing (e.g. its analysis window
                is closed).
        """
        occupied = {aq: set(rois) for aq, rois in occupied_by_aquarium.items()}
        anywhere: set[str] = set().union(*occupied.values()) if occupied else set()
        current: set[BindingKey] = set()
        for key in self._by_key:
            aquarium_id, roi = key
            rois = anywhere if aquarium_id is None else occupied.get(aquarium_id, set())
            if roi in rois:
                current.add(key)
        entered = current - self._prev
        exited = self._prev - current
        self._prev = current

        events: list[RoiTokenEvent] = []
        for key in sorted(exited, key=_sort_key):
            token = self._by_key[key].on_exit
            if token is not None:
                events.append(RoiTokenEvent(key[1], "exit", token, key[0]))
        for key in sorted(entered, key=_sort_key):
            token = self._by_key[key].on_enter
            if token is not None:
                events.append(RoiTokenEvent(key[1], "enter", token, key[0]))
        return events

    def forget_aquarium(self, aquarium_id: int) -> None:
        """Drop the state of the bindings scoped to ``aquarium_id``, emitting nothing.

        For when the caller has just swept that aquarium's exit tokens itself
        (its analysis window stopped): the next :meth:`update_scoped` must not
        send them a second time. Unscoped bindings are kept — the other aquarium
        may still be holding them.
        """
        self._prev = {key for key in self._prev if key[0] != aquarium_id}

    def reset(self) -> None:
        """Forget the previous-frame occupancy (call when a session starts)."""
        self._prev = set()

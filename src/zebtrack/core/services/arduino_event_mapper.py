"""Edge-triggered ROI-transition → Arduino-token mapper.

Pure state machine: fed the set of ROIs occupied this frame, it emits the
configured tokens only on transitions (a ROI newly entered or newly left),
never every frame. The Arduino holds the resulting device state between the
enter and exit tokens, so "permanence" needs no serial traffic.

Scope is "any-track": a ROI is considered occupied while *any* detected animal
is inside it; the enter token fires when the first animal enters and the exit
token fires when the last one leaves.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

import structlog

from zebtrack.core.services.arduino_bindings import ArduinoBinding

log = structlog.get_logger()


class RoiTokenEvent(NamedTuple):
    """A single edge-triggered ROI transition and the token it emits.

    ``edge`` is ``"enter"`` or ``"exit"``. Used by the closed-loop latency log
    so each serial token can be attributed to the ROI transition that caused it.
    """

    roi: str
    edge: str
    token: int


class ArduinoEventMapper:
    """Translates ROI occupancy transitions into ordered token lists.

    Args:
        bindings: The active per-zone bindings. Bindings without a usable token
            for an edge simply produce nothing on that edge.
    """

    def __init__(self, bindings: Iterable[ArduinoBinding]) -> None:
        # Last binding wins if a ROI is listed twice — keep it deterministic.
        self._by_roi: dict[str, ArduinoBinding] = {b.roi: b for b in bindings}
        self._prev: set[str] = set()

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
        """Advance one frame and return the ordered ROI transition events.

        Exits are emitted before enters so that, when an animal moves directly
        from one ROI to another in a single frame, the old device state is
        cleared before the new one is set. Iteration is sorted for determinism.

        Args:
            occupied_rois: ROI names occupied this frame (extra names not in the
                bindings are ignored).
        """
        current = {roi for roi in occupied_rois if roi in self._by_roi}
        entered = current - self._prev
        exited = self._prev - current
        self._prev = current

        events: list[RoiTokenEvent] = []
        for roi in sorted(exited):
            token = self._by_roi[roi].on_exit
            if token is not None:
                events.append(RoiTokenEvent(roi=roi, edge="exit", token=token))
        for roi in sorted(entered):
            token = self._by_roi[roi].on_enter
            if token is not None:
                events.append(RoiTokenEvent(roi=roi, edge="enter", token=token))
        return events

    def reset(self) -> None:
        """Forget the previous-frame occupancy (call when a session starts)."""
        self._prev = set()

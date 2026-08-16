"""Result type for an aquarium auto-detection retry pass.

Lives outside ``zebtrack.ui`` on purpose. ``LiveCalibrationCoordinator`` produces
these values and ``PreviewPolygonDialog`` renders them; the coordinator imports
the dialog only lazily (it pulls in tkinter/PIL), so the shared vocabulary cannot
live in the dialog module without dragging the UI stack into the coordinator's
import chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


# Machine tags for ``AquariumRetryOutcome.reason``.
#
# These are STABLE IDENTIFIERS, never display text. The dialog maps them to
# translated sentences at render time — branching on a rendered message would
# break silently the moment the UI language changes (CLAUDE.md).
RETRY_REASON_OK = "ok"
RETRY_REASON_NO_POLYGON = "no_polygon"
RETRY_REASON_NO_CAMERA = "no_camera"
RETRY_REASON_NO_FRAMES = "no_frames"
RETRY_REASON_CAPTURE_ERROR = "capture_error"


@dataclass(frozen=True)
class AquariumRetryOutcome:
    """Structured answer from a retry pass, so the dialog can explain a failure.

    A bare ``None`` cannot distinguish "the model found nothing at this
    threshold" from "the camera is gone". Since the preview dialog deliberately
    leaves the canvas untouched when a retry fails (the previous polygon is still
    the best candidate on screen), the status line is the *only* feedback the
    operator gets — and an undifferentiated failure there is why a failed retry
    read as "the program just re-showed the previous screen".
    """

    polygon: list[list[float]] | None = None
    frame: np.ndarray | None = None
    reason: str = RETRY_REASON_OK

    @property
    def succeeded(self) -> bool:
        """True only when an actual polygon came back."""
        return bool(self.polygon)


def normalize_retry_outcome(raw: Any) -> AquariumRetryOutcome:
    """Coerce any accepted callback return shape into an ``AquariumRetryOutcome``.

    The legacy ``(frame, polygon) | None`` contract is still honoured: it is the
    published type of ``preview_polygon_dialog`` and is what existing callers and
    tests use. An untagged ``None`` degrades to ``no_polygon``, the accurate
    reading for every legacy producer.
    """
    if isinstance(raw, AquariumRetryOutcome):
        return raw
    if raw is None:
        return AquariumRetryOutcome(reason=RETRY_REASON_NO_POLYGON)
    frame, polygon = raw
    return AquariumRetryOutcome(polygon=polygon, frame=frame, reason=RETRY_REASON_OK)

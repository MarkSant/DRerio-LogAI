"""Single decision on writing the ``3c_Objetos_<base>.parquet`` sidecar (ADR-010).

The object sidecar records, for every processed frame, one heartbeat row plus one
row per subject/context detection. Analysis windows (start/stop conditions) are
evaluated from it, so it is written by default; ``recorder.persist_object_sidecar``
is a kill switch only.

Unlike :func:`~zebtrack.core.services.mask_capture.should_capture_masks` there is
no model or ROI-rule condition: any weight produces detections, and the heartbeat
alone is what distinguishes "nothing detected" from "frame not processed".

Decision on incomplete settings: the sidecar is written only when the flag is a
real ``bool`` set to ``True``. Every real :class:`~zebtrack.settings.Settings`
has that (the Pydantic default is ``True``). ``None``, a ``MagicMock`` (whose
auto-attributes are truthy but were never configured) or a namespace without
the flag means nobody made the decision, and a sidecar nobody asked for would
scatter files through callers that never expected one. The module is pure: no
I/O, no singleton.
"""

from __future__ import annotations

from typing import Any

__all__ = ["should_capture_objects"]


def should_capture_objects(settings_obj: Any) -> bool:
    """Whether this session writes the ``3c_Objetos_`` sidecar.

    Args:
        settings_obj: The injected ``Settings`` instance (or ``None``).

    Returns:
        ``True`` only when ``settings_obj.recorder.persist_object_sidecar`` is the
        boolean ``True``.
    """
    if settings_obj is None:
        return False
    recorder_settings = getattr(settings_obj, "recorder", None)
    flag = getattr(recorder_settings, "persist_object_sidecar", None)
    return isinstance(flag, bool) and flag

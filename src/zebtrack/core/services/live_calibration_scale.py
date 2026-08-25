"""Single source for the pixel→cm scale of a LIVE session.

A live session has no calibration wizard behind it: the operator types the
aquarium's real dimensions into the dialog and the arena polygon comes from the
camera itself. The conversion is therefore always "bounding box of the arena
divided by the real size", and it was written twice — once inside the in-service
aquarium-detection phase and once (missing) in the post-analysis. The second
absence is why an ad-hoc live session reported PIXELS under a cm label.

Why not ``core.detection.calibration.Calibration``: that class computes its
ratio in the RECTIFIED image (a 600 px-wide top-down warp), which is only
comparable to the trajectory when the frames themselves were warped by its
homography. The live pipeline warps only when ``calibration.homography_matrix``
exists, so for an un-warped session the bounding-box ratio is the correct — and
the only correct — answer.

Pure module: no I/O, no Tk, no singleton.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

__all__ = ["resolve_live_pixel_per_cm"]


def resolve_live_pixel_per_cm(
    polygon: Any,
    width_cm: Any,
    height_cm: Any,
) -> tuple[float, float] | None:
    """Pixels per cm on each axis, from the arena polygon and its real size.

    Args:
        polygon: Arena vertices in pixel coordinates (``[[x, y], ...]``).
            Typed ``Any`` because the polygon legitimately arrives as a list of
            lists (persisted zones) OR as a ``numpy.ndarray`` (edit/preview
            payloads); annotating ``Sequence`` would reject the array at the
            type level while the code handles it fine. The axis-aligned
            bounding box is what is measured, so a rotated arena yields a
            slightly generous span — the same approximation the live
            auto-detection has always used.
        width_cm: Real arena width in cm, as typed by the operator.
        height_cm: Real arena height in cm.

    Returns:
        ``(px_per_cm_x, px_per_cm_y)``, or ``None`` when the scale cannot be
        established (missing/degenerate polygon, missing or non-positive
        dimensions, zero-span bounding box). ``None`` means "unknown" and MUST
        NOT be silently replaced by 1.0 by the caller without warning the user:
        1.0 turns every distance into pixels wearing a cm label.
    """
    # NOT ``if not polygon``: the arena polygon travels as a numpy array in the
    # edit/preview payloads, and truth-testing an array raises ValueError.
    if polygon is None or len(polygon) == 0:
        return None

    try:
        points = [(float(point[0]), float(point[1])) for point in polygon]
    # except (TypeError, ValueError, IndexError) justified: the polygon comes
    # from persisted project data / detector output and may be malformed.
    except (TypeError, ValueError, IndexError):
        log.warning("live_calibration_scale.polygon_malformed", exc_info=True)
        return None

    if len(points) < 3:
        log.warning("live_calibration_scale.polygon_too_small", vertices=len(points))
        return None

    try:
        real_width = float(width_cm)
        real_height = float(height_cm)
    except (TypeError, ValueError):
        return None

    if real_width <= 0 or real_height <= 0:
        return None

    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    width_px = max(xs) - min(xs)
    height_px = max(ys) - min(ys)

    if width_px <= 0 or height_px <= 0:
        log.warning(
            "live_calibration_scale.degenerate_bbox",
            width_px=width_px,
            height_px=height_px,
        )
        return None

    return (width_px / real_width, height_px / real_height)

"""ROI construction helpers.

Phase 5.6c: Encapsulates the ``Polygon`` (Shapely) import that was
previously used directly inside coordinators.  Coordinators now call
these helpers instead of importing Shapely themselves.
"""

from __future__ import annotations

from typing import Literal

from zebtrack.analysis.roi import ROI


def build_roi_from_polygon(
    name: str,
    coordinates: list[tuple[float, float]],
    coordinate_space: Literal["px", "cm"] = "px",
) -> ROI | None:
    """Build an :class:`ROI` from a list of polygon vertices.

    Returns ``None`` if the polygon has fewer than 3 vertices (invalid).

    Args:
        name: Human-readable ROI label.
        coordinates: List of ``(x, y)`` vertex tuples.
        coordinate_space: Coordinate space identifier (default ``"px"``).

    Returns:
        An ``ROI`` instance or ``None`` for degenerate polygons.
    """
    if len(coordinates) < 3:
        return None

    from shapely.geometry import Polygon

    return ROI(
        name=name,
        geometry=Polygon(coordinates),
        coordinate_space=coordinate_space,
    )


def build_rois_from_zone_polygons(
    polygons: list[list[tuple[float, float]]],
    names: list[str],
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[ROI]:
    """Build a list of ROIs from zone polygon data with optional offset.

    Each polygon's vertices are translated by ``-offset`` before
    construction.  This mirrors the local-space translation logic
    previously duplicated across multiple coordinator methods.

    Args:
        polygons: One polygon (vertex list) per ROI.
        names: Parallel list of ROI names (falls back to ``ROI_<i>``).
        offset: ``(off_x, off_y)`` to subtract from all vertices.

    Returns:
        List of successfully constructed ``ROI`` instances.
    """
    off_x, off_y = offset
    rois: list[ROI] = []
    for i, poly in enumerate(polygons):
        translated = [(float(px) - off_x, float(py) - off_y) for px, py in poly]
        name = names[i] if i < len(names) else f"ROI_{i}"
        roi = build_roi_from_polygon(name, translated)
        if roi is not None:
            rois.append(roi)
    return rois

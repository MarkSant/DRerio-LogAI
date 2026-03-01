"""Canonical perspective normalization for aquarium analysis.

This module consolidates the ``_normalize_aquarium_perspective`` logic that
was previously duplicated across ``analysis_service.py``,
``data_transformer.py``, and ``reporters/reporter_context.py``.  All three
copies now delegate to the single implementation here.

Canonical values: ``"lateral"`` (default) and ``"top_down"``.
"""

from __future__ import annotations

__all__ = ["normalize_aquarium_perspective"]


def normalize_aquarium_perspective(perspective: str | None) -> str:
    """Normalize perspective aliases to a canonical value.

    Handles hyphens, underscores, and common synonyms.

    Returns:
        ``"top_down"`` for any top/dorsal/overhead variant, ``"lateral"``
        otherwise.
    """
    raw = str(perspective or "").strip().lower().replace("-", "_")
    if raw in {
        "top_down",
        "top_down_view",
        "topdown",
        "top",
        "dorsal",
        "overhead",
    }:
        return "top_down"
    return "lateral"

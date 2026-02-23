"""Pure formatting and helper functions for project view components.

Extracted from ProjectViewManager (Phase 4.6) to isolate stateless
formatting utilities that don't depend on GUI state.

Functions that need a ProjectManager reference receive it as a parameter
instead of accessing self.gui.controller.project_manager, making them
independently testable.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


def format_status_label(count: int) -> str:
    """Format status count for display.

    Args:
        count: Number of videos.

    Returns:
        Formatted string like "5 vídeos" or "1 vídeo".
    """
    return f"{count} vídeo{'s' if count != 1 else ''}"


def format_status_summary(total: int, count: int) -> str:
    """Format status summary with count and percentage.

    Args:
        total: Total number of videos.
        count: Count for this status.

    Returns:
        Formatted string like "5 vídeos (25%)".
    """
    if total == 0:
        return "0 vídeos (0%)"
    percentage = int((count / total) * 100)
    label = format_status_label(count)
    return f"{label} ({percentage}%)"


def format_status_ratio(numerator: int, denominator: int) -> str:
    """Format ratio display.

    Args:
        numerator: Numerator value.
        denominator: Denominator value.

    Returns:
        Formatted string like "5/10".
    """
    return f"{numerator}/{denominator}"


def format_status_token(status: str) -> str:
    """Format status token for tree display.

    Args:
        status: Status string.

    Returns:
        The status string, or "—" if empty.
    """
    return status if status else "—"


def format_video_metadata(video: dict) -> str:
    """Format video metadata for display.

    Args:
        video: Video dictionary with metadata.

    Returns:
        Formatted string with metadata info.
    """
    parts = []
    metadata = video.get("metadata", {})

    if metadata.get("group"):
        parts.append(f"Grupo: {metadata['group']}")
    if metadata.get("day") is not None:
        parts.append(f"Dia: {metadata['day']}")
    if metadata.get("subject"):
        parts.append(f"Sujeito: {metadata['subject']}")

    return " | ".join(parts) if parts else "Sem metadata"


def video_sort_key(value: Any) -> tuple[int, Any]:
    """Generate sort key for video/subject identifiers.

    Numeric values sort before text values.

    Args:
        value: Identifier to sort.

    Returns:
        Tuple of (type_priority, sort_value).
    """
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        value_str = str(value) if value is not None else ""
        return (1, value_str.lower())


def summarize_batch_data(videos: list[dict], pm: Any) -> dict[str, Any]:
    """Summarize batch of videos into counts.

    Args:
        videos: List of video dictionaries.
        pm: ProjectManager instance (for has_*_data queries).

    Returns:
        Dictionary with counts by status.
    """
    counts: dict[str, int] = {
        "total": len(videos),
        "with_arena": 0,
        "with_rois": 0,
        "with_trajectory": 0,
        "with_summary": 0,
    }

    for video in videos:
        if pm.has_arena_data(video["path"]):
            counts["with_arena"] += 1
        if pm.has_roi_data(video["path"]):
            counts["with_rois"] += 1
        if pm.has_trajectory_data(video["path"]):
            counts["with_trajectory"] += 1
        if pm.has_summary_data(video["path"]):
            counts["with_summary"] += 1

    return counts


def format_data_badges(video_path: str, pm: Any) -> str:
    """Format data availability badges for a video.

    Args:
        video_path: Path to video file.
        pm: ProjectManager instance (for has_*_data queries).

    Returns:
        String with status symbols (e.g., "🏟 🎯 🧭").
    """
    from zebtrack.ui.gui import STATUS_SYMBOLS

    badges = []

    if pm.has_arena_data(video_path):
        badges.append(STATUS_SYMBOLS["arena"])
    if pm.has_roi_data(video_path):
        badges.append(STATUS_SYMBOLS["rois"])
    if pm.has_trajectory_data(video_path):
        badges.append(STATUS_SYMBOLS["trajectory"])

    return " ".join(badges) if badges else "—"

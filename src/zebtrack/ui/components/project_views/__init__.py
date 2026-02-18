"""Project Views — sub-package for decomposed ProjectViewManager.

Phase 4.6 decomposition:
    * ``ReportsTreeManager``          – Processing-reports tree & artifacts.
    * ``VideoSelectorTreeManager``    – Video selector tree, overview & batch ops.
    * ``project_view_helpers``        – Pure formatting/utility functions.
"""

from zebtrack.ui.components.project_views.project_view_helpers import (
    format_data_badges,
    format_status_label,
    format_status_ratio,
    format_status_summary,
    format_status_token,
    format_video_metadata,
    summarize_batch_data,
    video_sort_key,
)
from zebtrack.ui.components.project_views.reports_tree_manager import (
    ReportsTreeManager,
)
from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
)

__all__ = [
    "ReportsTreeManager",
    "VideoSelectorTreeManager",
    "format_data_badges",
    "format_status_label",
    "format_status_ratio",
    "format_status_summary",
    "format_status_token",
    "format_video_metadata",
    "summarize_batch_data",
    "video_sort_key",
]

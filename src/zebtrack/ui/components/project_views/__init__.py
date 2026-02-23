"""Project Views — sub-package for decomposed ProjectViewManager.

Phase 4.6 decomposition:
    * ``ReportsTreeManager``          – Processing-reports tree & artifacts.
    * ``VideoSelectorTreeManager``    – Video selector tree, overview & batch ops.
    * ``project_view_helpers``        – Pure formatting/utility functions.

Phase 5 decomposition (ReportsTreeManager → 3 focused modules):
    * ``ReportTreeBuilder``           – Tree population and status counts.
    * ``ReportGeneratorActions``      – Unified report generation & deletion.
    * ``ReportAssetActions``          – Asset deletion, file opening, artifacts.
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
from zebtrack.ui.components.project_views.report_asset_actions import (
    ReportAssetActions,
)
from zebtrack.ui.components.project_views.report_generator_actions import (
    ReportGeneratorActions,
)
from zebtrack.ui.components.project_views.report_tree_builder import (
    ReportTreeBuilder,
)
from zebtrack.ui.components.project_views.reports_tree_manager import (
    ReportsTreeManager,
)
from zebtrack.ui.components.project_views.video_selector_tree_manager import (
    VideoSelectorTreeManager,
)

__all__ = [
    "ReportAssetActions",
    "ReportGeneratorActions",
    "ReportTreeBuilder",
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

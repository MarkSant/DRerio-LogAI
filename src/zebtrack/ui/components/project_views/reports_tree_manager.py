"""Reports Tree Manager — Thin coordinator for Processing Reports tree.

Phase 5 refactoring: Logic decomposed into three focused modules:
    * ``ReportTreeBuilder`` — tree population and status counts
    * ``ReportGeneratorActions`` — unified report generation and deletion
    * ``ReportAssetActions`` — deletion, file opening, artifact helpers

This class retains the public API surface so that existing callers
(gui.py, ui_coordinator.py, widget_factory.py, project_initializer.py,
video_selector_tree_manager.py) continue to work without changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.components.project_views.report_asset_actions import ReportAssetActions
from zebtrack.ui.components.project_views.report_generator_actions import ReportGeneratorActions
from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class ReportsTreeManager:
    """Thin coordinator for Processing-Reports tree lifecycle.

    Delegates to:
        - ``ReportTreeBuilder``: tree population & status counts
        - ``ReportGeneratorActions``: report generation & deletion commands
        - ``ReportAssetActions``: asset deletion, file opening, artifacts

    Thread-safety: All UI updates must use ``gui.root.after(0, ...)`` pattern.
    """

    def __init__(
        self,
        gui: Any,
        *,
        event_bus_v2: Any | None = None,
        dialog_manager: DialogManager | None = None,
    ) -> None:
        """Initialise with parent GUI reference and optional event bus.

        Args:
            gui: Reference to ``ApplicationGUI`` instance.
            event_bus_v2: ``EventBusV2`` instance for v4.0 EDA (optional).
            dialog_manager: Optional DialogManager for dependency injection.
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
        self._dialog_manager = dialog_manager

        # Shared metadata dicts — tree node storage
        self._tree_metadata: dict = {}
        self._report_tree_metadata: dict = {}

        # Dependency getters (lazy to survive gui hot-swap)
        pm_getter = lambda: self.gui.controller.project_manager  # noqa: E731
        widget_getter = lambda: getattr(self.gui, "processing_reports_widget", None)  # noqa: E731
        reports_tree_getter = lambda: getattr(self.gui, "reports_tree", None)  # noqa: E731

        # --- Delegates ---
        self._tree_builder = ReportTreeBuilder(
            project_manager_getter=pm_getter,
            validation_manager=getattr(gui, "validation_manager", None),
            widget_factory=getattr(gui, "widget_factory", None),
            processing_reports_widget=widget_getter(),
            tree_metadata=self._tree_metadata,
        )

        self._generator = ReportGeneratorActions(
            project_manager_getter=pm_getter,
            event_dispatcher=getattr(gui, "event_dispatcher", None),
            dialog_manager=self._resolve_dialog_manager(),
            processing_reports_widget=widget_getter(),
            set_status=getattr(gui, "set_status", None),
            tree_metadata=self._tree_metadata,
            report_tree_metadata=self._report_tree_metadata,
            reports_tree_getter=reports_tree_getter,
        )

        self._assets = ReportAssetActions(
            project_manager_getter=pm_getter,
            dialog_manager=self._resolve_dialog_manager(),
            menu_manager=getattr(gui, "menu_manager", None),
            widget_factory=getattr(gui, "widget_factory", None),
            video_selector_manager=getattr(gui, "video_selector_manager", None),
            processing_reports_widget=widget_getter(),
            tree_metadata=self._tree_metadata,
            report_tree_metadata=self._report_tree_metadata,
            reports_tree_getter=reports_tree_getter,
        )

        if self.event_bus_v2:
            self._setup_event_subscriptions()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _resolve_dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or getattr(self.gui, "dialog_manager", None)

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._resolve_dialog_manager()

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _setup_event_subscriptions(self) -> None:
        """Subscribe to Event Bus V2 events relevant to reports."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        self.event_bus_v2.subscribe(
            UIEvents.PROCESSING_REPORTS_ITEM_RIGHT_CLICK,
            self._on_processing_reports_right_click,
        )

        self.event_bus_v2.subscribe(
            UIEvents.REPORTS_DELETE_UNIFIED,
            self._generator.delete_all_unified_reports,
        )

        log.debug(
            "reports_tree_manager.event_subscriptions_setup",
            events=[
                "PROCESSING_REPORTS_ITEM_RIGHT_CLICK",
                "reports.delete_unified",
            ],
        )

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def _on_processing_reports_right_click(self, data: dict) -> None:
        """Handle right-click on processing reports tree item."""
        if not isinstance(data, dict):
            return

        item_id = data.get("item_id")
        column_id = data.get("column_id")
        x = data.get("x")
        y = data.get("y")

        metadata = self._tree_metadata.get(item_id)
        if not metadata or metadata.get("type") != "video":
            return

        video_path = metadata.get("video_path")
        if not video_path:
            return

        callbacks = {
            "delete_asset": self._assets.delete_video_asset,
            "delete_all_processing": self._assets.delete_all_processing_data,
            "delete_video": self._assets.delete_video_from_project,
        }

        self.gui.menu_manager.show_processing_reports_context_menu(
            video_path, column_id, x, y, callbacks
        )

    # ------------------------------------------------------------------
    # Public API — Tree building (delegate to ReportTreeBuilder)
    # ------------------------------------------------------------------

    def refresh_processing_reports_tab(self) -> None:
        """Refresh the unified Processing and Reports tab (public entry)."""
        # Sync shared metadata to gui attribute for backward compat
        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = self._tree_metadata
        else:
            self.gui._processing_reports_tree_metadata = self._tree_metadata

        # Refresh delegate widget reference (may have been created after init)
        widget = getattr(self.gui, "processing_reports_widget", None)
        self._tree_builder._processing_reports_widget = widget

        self._tree_builder.refresh_tab()

    def update_reports_tree(self) -> None:
        """Update the reports tree view in ProcessingReportsWidget."""
        # Sync shared metadata to gui attribute for backward compat
        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = self._tree_metadata
        else:
            self.gui._processing_reports_tree_metadata = self._tree_metadata

        # Refresh delegate widget reference
        widget = getattr(self.gui, "processing_reports_widget", None)
        self._tree_builder._processing_reports_widget = widget

        self._tree_builder.update_tree()

    # ------------------------------------------------------------------
    # Public API — Artifact helpers (delegate to ReportTreeBuilder/ReportAssetActions)
    # ------------------------------------------------------------------

    def append_processing_reports_artifacts(
        self,
        tree: Any,
        parent_id: str,
        results_dir: str,
        metadata_store: dict,
    ) -> None:
        """Append report artifacts (docx, xlsx) to tree node."""
        self._tree_builder.append_artifacts(tree, parent_id, results_dir, metadata_store)

    def append_report_artifacts(
        self, tree: Any, parent_id: str, results_dir: str, metadata_store: dict
    ) -> None:
        """Legacy alias for ``append_processing_reports_artifacts``."""
        self._tree_builder.append_artifacts(tree, parent_id, results_dir, metadata_store)

    def append_report_artifacts_from_entry(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts (docx, xlsx) from video entry to reports tree."""
        self._assets.append_report_artifacts_from_entry(parent_id, entry)

    # ------------------------------------------------------------------
    # Public API — Double-click / file opening (delegate to ReportAssetActions)
    # ------------------------------------------------------------------

    def on_processing_reports_item_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on items in the Processing Reports tree."""
        # Sync metadata ref before delegating
        self._assets._tree_metadata = self._tree_metadata
        self._assets.on_processing_reports_item_double_click(event)

    def open_unified_report(self, file_type: str) -> None:
        """Open the latest unified report of the specified type."""
        self._assets.open_unified_report(file_type)

    def handle_report_video_node(self, metadata: dict) -> None:
        """Handle double-click on report video node — opens results directory."""
        self._assets.handle_report_video_node(metadata)

    # ------------------------------------------------------------------
    # Public API — Report generation (delegate to ReportGeneratorActions)
    # ------------------------------------------------------------------

    def generate_unified_report(self) -> None:
        """Generate a unified report for all project videos."""
        self._generator.generate_unified_report()

    def on_processing_reports_generate_partial(self) -> None:
        """Handle partial report generation from the unified tab."""
        self._generator.on_processing_reports_generate_partial()

    def generate_partial_report(self) -> None:
        """Gather selected videos and generate a unified partial report."""
        self._generator.generate_partial_report()

    # ------------------------------------------------------------------
    # Internal (kept for backward compat, delegates to ReportTreeBuilder)
    # ------------------------------------------------------------------

    def _refresh_processing_reports_tab(self) -> None:
        """Internal implementation — delegates to refresh_processing_reports_tab."""
        self.refresh_processing_reports_tab()

    def _get_project_status_counts(self) -> dict[str, int]:
        """Calculate status counts for the project."""
        return self._tree_builder.get_project_status_counts()

    def _populate_reports_tree_from_hierarchy(
        self, tree: Any, hierarchy: dict, parent: str, metadata_store: dict
    ) -> None:
        """Populate reports tree from hierarchy data (compat shim)."""
        self._tree_builder.populate_from_hierarchy(tree, hierarchy, parent, metadata_store)

    # ------------------------------------------------------------------
    # Deletion helpers (delegate to ReportAssetActions)
    # ------------------------------------------------------------------

    def _delete_video_asset(self, video_path: str, asset: str) -> None:
        """Delete specific asset via MenuManager reuse."""
        self._assets.delete_video_asset(video_path, asset)

    def _delete_all_processing_data(self, video_path: str) -> None:
        """Delete all processing data (arena, rois, trajectory, summary)."""
        self._assets.delete_all_processing_data(video_path)

    def _delete_video_from_project(self, video_path: str) -> None:
        """Delete video from project."""
        self._assets.delete_video_from_project(video_path)

    def _delete_all_unified_reports(self, data: dict | None = None) -> None:
        """Delete the entire unified_reports directory."""
        self._generator.delete_all_unified_reports(data)

    # ------------------------------------------------------------------
    # Private utilities (delegate to ReportAssetActions)
    # ------------------------------------------------------------------

    def _open_path_in_explorer(self, path: str) -> None:
        """Open a file or folder in the system file explorer."""
        self._assets._open_path_in_explorer(path)

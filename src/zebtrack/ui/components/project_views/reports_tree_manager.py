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

from pathlib import Path
from tkinter import Menu
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from zebtrack.ui import payloads
from zebtrack.ui.components.project_views.report_asset_actions import ReportAssetActions
from zebtrack.ui.components.project_views.report_generator_actions import ReportGeneratorActions
from zebtrack.ui.components.project_views.report_tree_builder import ReportTreeBuilder
from zebtrack.ui.dialogs.project_video_import_dialog import BatchVideoMetadataDialog
from zebtrack.ui.event_bus_v2 import Event, UIEvents

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

    _HIERARCHY_NODE_TYPES: ClassVar[frozenset[str]] = frozenset({"group", "day", "subject"})
    _AQUARIUM_NODE_TYPE: ClassVar[str] = "aquarium"
    _HIERARCHY_LABELS: ClassVar[dict[str, str]] = {
        "group": "grupo",
        "day": "dia",
        "subject": "sujeito",
    }

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
            event_dispatcher=getattr(gui, "event_dispatcher", None),
            dialog_manager=self._resolve_dialog_manager(),
            menu_manager=getattr(gui, "menu_manager", None),
            widget_factory=getattr(gui, "widget_factory", None),
            video_selector_manager=(lambda: getattr(self.gui, "video_selector_manager", None)),
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
        resolved = self._dialog_manager or getattr(self.gui, "dialog_manager", None)
        assert resolved is not None, "DialogManager must be available"
        return resolved

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

        assert self.event_bus_v2 is not None
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

    def _on_processing_reports_right_click(
        self, payload: payloads.ProjectContextMenuClickPayload
    ) -> None:
        """Handle right-click on processing reports tree item."""
        item_id = payload.item_id
        if not item_id:
            return

        column_id = payload.column_id
        x = payload.x
        y = payload.y
        if x is None or y is None:
            return

        metadata = self._tree_metadata.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")
        if node_type in self._HIERARCHY_NODE_TYPES:
            self._show_hierarchy_context_menu(item_id, metadata, x, y)
            return

        if node_type == self._AQUARIUM_NODE_TYPE:
            self._show_aquarium_context_menu(metadata, x, y)
            return

        if node_type == "file":
            self._show_report_file_context_menu(metadata, x, y)
            return

        if node_type != "video":
            return

        video_path = metadata.get("video_path")
        if not video_path:
            return

        asset_availability = self._resolve_processing_asset_availability(metadata, str(video_path))

        callbacks = {
            "delete_asset": self._assets.delete_video_asset,
            "delete_choice": self._assets.choose_video_delete_action,
        }

        self.gui.menu_manager.show_processing_reports_context_menu(
            video_path,
            column_id,
            x,
            y,
            callbacks,
            asset_availability=asset_availability,
        )

    def _show_report_file_context_menu(self, metadata: dict[str, Any], x: int, y: int) -> None:
        """Show context menu for report files instead of opening on right-click."""
        menu = Menu(self.gui.root, tearoff=0)
        menu.add_command(
            label="📂 Abrir Arquivo",
            command=lambda: self._assets.open_report_file_from_metadata(metadata),
        )
        menu.add_command(
            label="📁 Abrir Pasta do Arquivo",
            command=lambda: self._assets.open_report_parent_folder_from_metadata(metadata),
        )
        menu.post(x, y)

    def _resolve_processing_asset_availability(
        self,
        metadata: dict[str, Any],
        video_path: Path | str,
    ) -> dict[str, bool]:
        """Resolve asset availability for context menu, including aquarium-specific rows."""
        pm = self.gui.controller.project_manager
        has_arena = pm.has_arena_data(video_path)
        has_rois = pm.has_roi_data(video_path)
        has_trajectory = pm.has_trajectory_data(video_path)
        has_summary = pm.has_summary_data(video_path)

        aquarium_id = metadata.get("aquarium_id")
        if aquarium_id is None:
            return {
                "arena": bool(has_arena),
                "rois": bool(has_rois),
                "trajectory": bool(has_trajectory),
                "summary": bool(has_summary),
            }

        entry = pm.find_video_entry(path=video_path)
        if not isinstance(entry, dict):
            return {
                "arena": bool(has_arena),
                "rois": bool(has_rois),
                "trajectory": bool(has_trajectory),
                "summary": bool(has_summary),
            }

        outputs = entry.get("multi_aquarium_outputs") or {}
        aq_data = outputs.get(aquarium_id) or outputs.get(str(aquarium_id))
        parquet_files = aq_data.get("parquet_files") if isinstance(aq_data, dict) else {}
        parquet_files = parquet_files if isinstance(parquet_files, dict) else {}

        aq_has_trajectory = bool(parquet_files.get("trajectory"))
        aq_has_summary = bool(
            parquet_files.get("summary")
            or parquet_files.get("summary_excel")
            or parquet_files.get("report_docx")
        )

        return {
            "arena": bool(has_arena),
            "rois": bool(has_rois),
            "trajectory": aq_has_trajectory,
            "summary": aq_has_summary,
        }

    def _show_aquarium_context_menu(self, metadata: dict[str, Any], x: int, y: int) -> None:
        """Show explicit intent actions for aquarium nodes."""
        menu = Menu(self.gui.root, tearoff=0)

        menu.add_command(
            label="🗑️ Apagar Aquário (desenho + dados)...",
            command=lambda: self._handle_delete_aquarium_scope(metadata),
        )
        menu.add_command(
            label="🐟 Apagar Animal (manter aquário)...",
            command=lambda: self._handle_clear_aquarium_subject(metadata),
        )
        menu.add_command(
            label="🔄 Reiniciar Análises (manter desenhos)...",
            command=lambda: self._handle_reset_aquarium_analysis(metadata),
        )

        menu.post(x, y)

    def _handle_delete_aquarium_scope(self, metadata: dict[str, Any]) -> None:
        """Delete one aquarium scope including geometry and analysis outputs."""
        video_path = metadata.get("video_path")
        aquarium_id = metadata.get("aquarium_id")
        if not video_path or aquarium_id is None:
            return

        confirmed = self.dialog_manager.ask_yes_no(
            "Apagar Aquário",
            (
                f"Deseja apagar o aquário {int(aquarium_id) + 1} com seus desenhos "
                "e dados de análise?"
            ),
            icon="warning",
        )
        if not confirmed:
            return

        delete_files = self.dialog_manager.ask_yes_no(
            "Excluir Arquivos do Disco",
            (
                "Deseja também excluir os arquivos gerados desse aquário no disco?\n\n"
                "Se escolher 'Não', apenas a referência no projeto será removida."
            ),
            icon="question",
        )

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_DELETE_AQUARIUM,
            payloads.ProjectDeleteAquariumPayload(
                video_path=str(video_path),
                aquarium_id=int(aquarium_id),
                delete_files=delete_files,
                delete_zone=True,
            ),
        )

    def _handle_clear_aquarium_subject(self, metadata: dict[str, Any]) -> None:
        """Clear aquarium subject binding while preserving aquarium geometry."""
        video_path = metadata.get("video_path")
        aquarium_id = metadata.get("aquarium_id")
        if not video_path or aquarium_id is None:
            return

        confirmed = self.dialog_manager.ask_yes_no(
            "Apagar Animal",
            (
                f"Deseja apagar o animal vinculado ao aquário {int(aquarium_id) + 1} "
                "mantendo o aquário desenhado?"
            ),
            icon="warning",
        )
        if not confirmed:
            return

        delete_analysis_data = self.dialog_manager.ask_yes_no(
            "Apagar Também Dados de Análise?",
            (
                "Deseja também apagar trajetória e relatórios atuais desse aquário?\n\n"
                "Se escolher 'Não', somente o vínculo do animal será removido."
            ),
            icon="question",
        )

        delete_files = False
        if delete_analysis_data:
            delete_files = self.dialog_manager.ask_yes_no(
                "Excluir Arquivos do Disco",
                (
                    "Deseja também excluir os arquivos de análise do disco?\n\n"
                    "Se escolher 'Não', apenas a referência no projeto será removida."
                ),
                icon="question",
            )

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_CLEAR_AQUARIUM_SUBJECT,
            payloads.ProjectClearAquariumSubjectPayload(
                video_path=str(video_path),
                aquarium_id=int(aquarium_id),
                delete_analysis_data=delete_analysis_data,
                delete_files=delete_files,
            ),
        )

    def _handle_reset_aquarium_analysis(self, metadata: dict[str, Any]) -> None:
        """Reset only analysis outputs for one aquarium while preserving drawings."""
        video_path = metadata.get("video_path")
        aquarium_id = metadata.get("aquarium_id")
        if not video_path or aquarium_id is None:
            return

        confirmed = self.dialog_manager.ask_yes_no(
            "Reiniciar Análises",
            (
                f"Deseja apagar apenas trajetória e relatórios do aquário {int(aquarium_id) + 1}, "
                "mantendo arena e ROIs?"
            ),
            icon="warning",
        )
        if not confirmed:
            return

        delete_files = self.dialog_manager.ask_yes_no(
            "Excluir Arquivos do Disco",
            (
                "Deseja também excluir os arquivos de análise no disco?\n\n"
                "Se escolher 'Não', apenas a referência no projeto será removida."
            ),
            icon="question",
        )

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_RESET_ANALYSIS_DATA,
            payloads.ProjectResetAnalysisDataPayload(
                video_path=str(video_path),
                aquarium_id=int(aquarium_id),
                delete_files=delete_files,
            ),
        )

    def _show_hierarchy_context_menu(
        self,
        item_id: str,
        metadata: dict[str, Any],
        x: int,
        y: int,
    ) -> None:
        """Show context menu for group/day/subject nodes in the reports tree."""
        node_type = str(metadata.get("type", "item"))
        label = self._HIERARCHY_LABELS.get(node_type, "item")

        menu = Menu(self.gui.root, tearoff=0)
        menu.add_command(
            label=f"🔄 Editar metadata do {label}…",
            command=lambda: self._handle_hierarchy_metadata_edit_action(item_id, metadata),
        )
        menu.add_separator()
        menu.add_command(
            label=f"🗑️ Excluir {label}…",
            command=lambda: self._handle_hierarchy_delete_action(item_id, metadata),
        )
        menu.post(x, y)

    def _handle_hierarchy_metadata_edit_action(
        self,
        item_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Apply batch metadata updates to all descendant videos under a hierarchy node."""
        project_manager = self.gui.controller.project_manager
        video_paths = self._collect_descendant_video_paths(item_id)
        if not video_paths:
            return

        node_type = str(metadata.get("type", "item"))
        label = self._get_item_display_label(item_id)
        initial_values = self._build_hierarchy_metadata_defaults(metadata)
        dialog = BatchVideoMetadataDialog(
            self.gui.root,
            target_label=label,
            target_kind=self._HIERARCHY_LABELS.get(node_type, "item"),
            affected_count=len(video_paths),
            available_groups=project_manager.get_available_groups(),
            initial_values=initial_values,
            allow_subject=node_type == "subject",
        )
        if not dialog.result:
            return

        changed_count = project_manager.update_batch_video_metadata(video_paths, dialog.result)
        if not changed_count:
            return

        status_message = f"Metadados atualizados em {changed_count} vídeo(s) • {label}"
        self.gui.set_status(status_message)
        self.refresh_processing_reports_tab()

        event_bus_v2 = getattr(self.gui, "event_bus_v2", None) or self.event_bus_v2
        if event_bus_v2:
            event_bus_v2.publish(
                Event(
                    type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                    data=payloads.ProjectViewsRefreshRequestedPayload(
                        reason=status_message,
                        append_summary=True,
                        immediate=True,
                    ),
                    source="ReportsTreeManager._handle_hierarchy_metadata_edit_action",
                )
            )
            event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(),
                    source="ReportsTreeManager._handle_hierarchy_metadata_edit_action",
                )
            )

    @staticmethod
    def _build_hierarchy_metadata_defaults(metadata: dict[str, Any]) -> dict[str, Any]:
        """Build default batch-edit values from a hierarchy node."""
        defaults: dict[str, Any] = {}
        if metadata.get("group_id") is not None:
            defaults["group"] = str(metadata["group_id"])
        if metadata.get("day_id") is not None:
            defaults["day"] = metadata["day_id"]
        if metadata.get("type") == "subject" and metadata.get("subject_id") is not None:
            defaults["subject"] = str(metadata["subject_id"])
        return defaults

    def _handle_hierarchy_delete_action(self, item_id: str, metadata: dict[str, Any]) -> None:
        """Ask the user whether to delete generated data or remove the hierarchy node."""
        node_type = str(metadata.get("type", "item"))
        display_label = self._get_item_display_label(item_id)
        delete_mode = self.dialog_manager.choose_processing_reports_delete_mode(
            display_label,
            target_kind=self._HIERARCHY_LABELS.get(node_type, "item"),
        )
        if delete_mode is None:
            return

        video_paths = self._collect_descendant_video_paths(item_id)
        if not video_paths:
            return

        if delete_mode == "data":
            self._assets.reset_analysis_data_for_videos(
                video_paths,
                target_label=display_label,
            )
            return

        video_names = [path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for path in video_paths]
        confirmed, delete_files = self.dialog_manager.confirm_delete_hierarchy_node(
            node_type,
            display_label,
            len(video_names),
            video_names,
        )
        if not confirmed:
            return

        self._publish_hierarchy_delete(node_type, metadata, delete_files)

    def _publish_hierarchy_delete(
        self,
        node_type: str,
        metadata: dict[str, Any],
        delete_files: bool,
    ) -> None:
        """Publish the correct hierarchy deletion event for the selected node."""
        payload: (
            payloads.ProjectDeleteGroupPayload
            | payloads.ProjectDeleteDayPayload
            | payloads.ProjectDeleteSubjectPayload
        )
        if node_type == "group":
            payload = payloads.ProjectDeleteGroupPayload(
                group_id=str(metadata["group_id"]),
                delete_files=delete_files,
            )
            event = UIEvents.PROJECT_DELETE_GROUP
        elif node_type == "day":
            payload = payloads.ProjectDeleteDayPayload(
                group_id=str(metadata["group_id"]),
                day_id=str(metadata["day_id"]),
                delete_files=delete_files,
            )
            event = UIEvents.PROJECT_DELETE_DAY
        elif node_type == "subject":
            payload = payloads.ProjectDeleteSubjectPayload(
                group_id=str(metadata["group_id"]),
                day_id=str(metadata["day_id"]),
                subject_id=str(metadata["subject_id"]),
                delete_files=delete_files,
            )
            event = UIEvents.PROJECT_DELETE_SUBJECT
        else:
            return

        self.gui.event_dispatcher.publish_event(event, payload)

    def _get_item_display_label(self, item_id: str) -> str:
        """Return a user-facing label for a tree node without the leading emoji."""
        tree = getattr(getattr(self.gui, "processing_reports_widget", None), "tree", None)
        if not tree:
            return item_id

        raw_text = str(tree.item(item_id, "text") or "").strip()
        if " " in raw_text:
            return raw_text.split(" ", 1)[1]
        return raw_text or item_id

    def _collect_descendant_video_paths(self, item_id: str) -> list[str]:
        """Collect video paths from all descendant video nodes under a hierarchy item."""
        tree = getattr(getattr(self.gui, "processing_reports_widget", None), "tree", None)
        if not tree:
            return []

        collected: list[str] = []

        def walk(node_id: str) -> None:
            for child_id in tree.get_children(node_id):
                child_metadata = self._tree_metadata.get(child_id, {})
                if child_metadata.get("type") == "video" and child_metadata.get("video_path"):
                    collected.append(str(child_metadata["video_path"]))
                else:
                    walk(child_id)

        walk(item_id)
        return list(dict.fromkeys(collected))

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
        self._assets._processing_reports_widget = widget
        self._generator._processing_reports_widget = widget

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
        self._assets._processing_reports_widget = widget
        self._generator._processing_reports_widget = widget

        self._tree_builder.update_tree()

    # ------------------------------------------------------------------
    # Public API — Artifact helpers (delegate to ReportTreeBuilder/ReportAssetActions)
    # ------------------------------------------------------------------

    def append_processing_reports_artifacts(
        self,
        tree: Any,
        parent_id: str,
        results_dir: Path | str,
        metadata_store: dict,
    ) -> None:
        """Append report artifacts (docx, xlsx) to tree node."""
        self._tree_builder.append_artifacts(tree, parent_id, results_dir, metadata_store)

    def append_report_artifacts(
        self, tree: Any, parent_id: str, results_dir: Path | str, metadata_store: dict
    ) -> None:
        """Legacy alias for ``append_processing_reports_artifacts``."""
        self._tree_builder.append_artifacts(tree, parent_id, results_dir, metadata_store)

    def append_report_artifacts_from_entry(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts (docx, xlsx) from video entry to reports tree."""
        self._assets.append_report_artifacts_from_entry(parent_id, entry)

    # ------------------------------------------------------------------
    # Public API — Double-click / file opening (delegate to ReportAssetActions)
    # ------------------------------------------------------------------

    def on_processing_reports_item_click(self, event: Any | None = None) -> None:
        """Handle single-click on processing reports tree file nodes."""
        # Sync metadata ref before delegating
        self._assets._processing_reports_widget = getattr(
            self.gui, "processing_reports_widget", None
        )
        self._assets._tree_metadata = self._tree_metadata
        self._assets.on_processing_reports_item_click(event)

    def on_processing_reports_item_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on items in the Processing Reports tree."""
        # Sync metadata ref before delegating
        self._assets._processing_reports_widget = getattr(
            self.gui, "processing_reports_widget", None
        )
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

    def _delete_video_asset(self, video_path: Path | str, asset: str) -> None:
        """Delete specific asset via MenuManager reuse."""
        self._assets.delete_video_asset(video_path, asset)

    def _delete_all_processing_data(self, video_path: Path | str) -> None:
        """Delete all processing data (arena, rois, trajectory, summary)."""
        self._assets.delete_all_processing_data(video_path)

    def _delete_video_from_project(self, video_path: Path | str) -> None:
        """Delete video from project."""
        self._assets.delete_video_from_project(video_path)

    def _delete_all_unified_reports(self, data: dict | None = None) -> None:
        """Delete the entire unified_reports directory."""
        self._generator.delete_all_unified_reports(data)

    # ------------------------------------------------------------------
    # Private utilities (delegate to ReportAssetActions)
    # ------------------------------------------------------------------

    def _open_path_in_explorer(self, path: Path | str) -> None:
        """Open a file or folder in the system file explorer."""
        self._assets._open_path_in_explorer(path)

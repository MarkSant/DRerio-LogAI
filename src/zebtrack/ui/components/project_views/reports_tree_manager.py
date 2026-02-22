"""Reports Tree Manager — Processing Reports tree population and report artifacts.

Extracted from ProjectViewManager (Phase 4.6).  Owns every method that touches
the ProcessingReportsWidget tree, report file opening, unified-report generation,
and the right-click context-menu lifecycle for report items.

Cross-component calls:
    * self.gui.video_selector_manager.refresh_project_views(...)
      — used by _delete_all_processing_data after bulk deletion.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


class ReportsTreeManager:
    """Manage the Processing-Reports tree, report artifacts, and generation triggers.

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

        if self.event_bus_v2:
            self._setup_event_subscriptions()

    @property
    def dialog_manager(self) -> DialogManager:
        """Return injected DialogManager or fall back to gui.dialog_manager."""
        return self._dialog_manager or self.gui.dialog_manager

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def _setup_event_subscriptions(self) -> None:
        """Subscribe to Event Bus V2 events relevant to reports."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        # V2 right-click
        self.event_bus_v2.subscribe(
            UIEvents.PROCESSING_REPORTS_ITEM_RIGHT_CLICK,
            self._on_processing_reports_right_click,
        )

        # V2 unified report deletion
        self.event_bus_v2.subscribe(
            UIEvents.REPORTS_DELETE_UNIFIED,
            self._delete_all_unified_reports,
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

        metadata = getattr(self.gui, "_processing_reports_tree_metadata", {}).get(item_id)
        if not metadata or metadata.get("type") != "video":
            return

        video_path = metadata.get("video_path")
        if not video_path:
            return

        callbacks = {
            "delete_asset": self._delete_video_asset,
            "delete_all_processing": self._delete_all_processing_data,
            "delete_video": self._delete_video_from_project,
        }

        self.gui.menu_manager.show_processing_reports_context_menu(
            video_path, column_id, x, y, callbacks
        )

    def _delete_video_asset(self, video_path: str, asset: str) -> None:
        """Delete specific asset via MenuManager reuse."""
        self.gui.menu_manager.handle_overview_asset_removal(video_path, asset)

    def _delete_all_processing_data(self, video_path: str) -> None:
        """Delete all processing data (arena, rois, trajectory, summary)."""
        pm = self.gui.controller.project_manager

        confirm = self.gui.dialog_manager.ask_ok_cancel(
            "Apagar Dados de Processamento",
            f"Tem certeza que deseja apagar TODOS os dados de processamento "
            f"(Arena, ROIs, Trajetória, Relatórios) para:\n\n{os.path.basename(video_path)}?\n\n"
            f"O vídeo será mantido no projeto.",
        )
        if not confirm:
            return

        assets = ["summary", "trajectory", "rois", "arena"]
        changed = False

        for asset in assets:
            if pm.remove_asset(video_path, asset, delete_files=True):
                changed = True

        if changed:
            self.gui.video_selector_manager.refresh_project_views(
                reason="Dados de processamento apagados", append_summary=True
            )

    def _delete_video_from_project(self, video_path: str) -> None:
        """Delete video from project."""
        self.gui.menu_manager.handle_overview_asset_removal(video_path, "video")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_processing_reports_tab(self) -> None:
        """Refresh the unified Processing and Reports tab (public entry)."""
        self._refresh_processing_reports_tab()

    def update_reports_tree(self) -> None:
        """Update the reports tree view in ProcessingReportsWidget.

        Refreshes tree content based on current project state.
        """
        widget = getattr(self.gui, "processing_reports_widget", None)
        if not widget or not widget.tree:
            return

        widget.clear_tree()

        project_manager = self.gui.controller.project_manager
        all_videos = project_manager.get_all_videos()

        hierarchy = self.gui.validation_manager._build_video_hierarchy_data(all_videos, "")

        status_counts = self._get_project_status_counts()

        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = {}

        self.gui._processing_reports_tree_metadata.clear()
        metadata_store = self.gui._processing_reports_tree_metadata

        self._populate_reports_tree_from_hierarchy(widget.tree, hierarchy, "", metadata_store)

        widget.update_status_counts(status_counts)

        log.debug("reports_tree_manager.reports_tree_updated")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_processing_reports_tab(self) -> None:
        """Refresh processing reports tab (internal implementation).

        Updates the tree with current project data and report artifacts.
        """
        if not hasattr(self.gui, "processing_reports_widget"):
            return
        if not self.gui.processing_reports_widget:
            return

        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()

        for v in all_videos:
            if v.get("path") and "CECT_8" in v.get("path", ""):
                log.info(
                    "debug.refresh_tab.video_state",
                    path=os.path.basename(v.get("path")),
                    has_traj=v.get("has_trajectory"),
                    has_arena=v.get("has_arena"),
                )

        hierarchy = self.gui.validation_manager._build_video_hierarchy_data(all_videos, "")

        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = {}
        self.gui._processing_reports_tree_metadata.clear()

        tree = self.gui.processing_reports_widget.tree
        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        self._populate_reports_tree_from_hierarchy(
            tree, hierarchy, "", self.gui._processing_reports_tree_metadata
        )

        status_counts = self._get_project_status_counts()
        if hasattr(self.gui.processing_reports_widget, "update_status_counts"):
            self.gui.processing_reports_widget.update_status_counts(status_counts)

        if hasattr(self.gui.processing_reports_widget, "_update_button_states"):
            project_path = str(pm.project_path) if pm and pm.project_path else None
            self.gui.processing_reports_widget._update_button_states(project_path=project_path)

    # ------------------------------------------------------------------
    # Tree population helpers
    # ------------------------------------------------------------------

    def _populate_reports_tree_from_hierarchy(
        self,
        tree: Any,
        hierarchy: dict,
        parent: str,
        metadata_store: dict,
    ) -> None:
        """Populate reports tree from hierarchy data."""
        for group_id, group_data in sorted(hierarchy.items()):
            self._insert_group_node(tree, parent, group_id, group_data, metadata_store)

    def _insert_group_node(
        self,
        tree: Any,
        parent: str,
        group_id: str | int,
        group_data: dict,
        metadata_store: dict,
    ) -> None:
        """Insert a group node and its children into the tree."""
        group_name = group_data.get("display", group_id)
        group_node_id = f"group_{group_id}"

        tree.insert(
            parent,
            "end",
            iid=group_node_id,
            text=f"🏷️ {group_name}",
            values=("", "", "", "", "", ""),
            open=True,
        )

        metadata_store[group_node_id] = {
            "type": "group",
            "group_id": group_id,
        }

        days = group_data.get("days", {})
        for day_id, videos in sorted(days.items(), key=lambda x: str(x[0])):
            self._insert_day_node(tree, group_node_id, day_id, videos, group_id, metadata_store)

    def _insert_day_node(
        self,
        tree: Any,
        parent: str,
        day_id: str | int,
        videos: list,
        group_id: str | int,
        metadata_store: dict,
    ) -> None:
        """Insert a day node and its videos into the tree."""
        day_label = f"Dia {day_id}"
        if videos and isinstance(videos, list) and len(videos) > 0:
            first_video = videos[0]
            if isinstance(first_video, dict):
                meta = first_video.get("metadata", {})
                if meta and meta.get("day") is not None:
                    day_val = meta.get("day")
                    day_label = f"{day_val:02d}" if isinstance(day_val, int) else str(day_val)
                elif "day_label" in first_video:
                    day_label = first_video["day_label"]

        day_node_id = f"{parent}_day_{day_id}"

        tree.insert(
            parent,
            "end",
            iid=day_node_id,
            text=f"📅 {day_label}",
            values=("", "", "", "", "", ""),
            open=True,
        )

        metadata_store[day_node_id] = {
            "type": "day",
            "group_id": group_id,
            "day_id": day_id,
        }

        for video in videos:
            self._insert_video_node(tree, day_node_id, video, metadata_store)

    def _insert_video_node(self, tree: Any, parent: str, video: dict, metadata_store: dict) -> None:
        """Insert a video node into the tree."""
        from zebtrack.ui.gui import STATUS_SYMBOLS

        video_path = video.get("path")
        if not video_path:
            return

        video_name = os.path.basename(video_path)
        subject = video.get("subject", "")
        subject_label = f"Sujeito {subject}" if subject else video_name

        col_arena = STATUS_SYMBOLS["arena"] if video.get("has_arena") else ""
        col_rois = STATUS_SYMBOLS["rois"] if video.get("has_rois") else ""
        col_traj = STATUS_SYMBOLS["trajectory"] if video.get("has_trajectory") else ""
        col_summary = STATUS_SYMBOLS["summary"] if video.get("has_summary") else ""

        status_label = "Processado" if video.get("has_trajectory") else "Pendente"
        if not video.get("has_arena"):
            status_label = "Sem Arena"

        multi_subject_index = video.get("multi_subject_index", 0)
        is_multi_subject_entry = video.get("is_multi_subject_entry", False)
        if is_multi_subject_entry:
            video_node_id = f"{parent}_video_{video_path}_sub_{multi_subject_index}"
        else:
            video_node_id = f"{parent}_video_{video_path}"

        tree.insert(
            parent,
            "end",
            iid=video_node_id,
            text=f"🐟 {subject_label}",
            values=(
                col_arena,
                col_rois,
                col_traj,
                col_summary,
                status_label,
                video_path,
            ),
        )

        metadata_store[video_node_id] = {
            "type": "video",
            "video_path": video_path,
            "results_dir": video.get("results_dir"),
        }

        multi_outputs = video.get("multi_aquarium_outputs")
        if not multi_outputs:
            try:
                pm = self.gui.controller.project_manager
                canonical_entry = pm.find_video_entry(path=video_path) if pm else None
                if canonical_entry and isinstance(canonical_entry, dict):
                    multi_outputs = canonical_entry.get("multi_aquarium_outputs")
            except (AttributeError, KeyError, TypeError):
                log.debug("reports_tree_manager.multi_outputs_fallback.suppressed", exc_info=True)

        if multi_outputs and isinstance(multi_outputs, dict) and len(multi_outputs) > 0:
            self._insert_multi_aquarium_nodes(
                tree,
                video_node_id,
                video,
                multi_outputs,
                metadata_store,
                is_multi_subject_entry,
                multi_subject_index,
            )
        else:
            self._insert_single_aquarium_node(
                tree, video_node_id, video, video_path, metadata_store
            )

    def _insert_multi_aquarium_nodes(
        self,
        tree: Any,
        parent: str,
        video: dict,
        multi_outputs: dict,
        metadata_store: dict,
        is_multi_subject_entry: bool,
        multi_subject_index: int,
    ) -> None:
        """Insert nodes for multi-aquarium outputs."""
        from zebtrack.ui.gui import STATUS_SYMBOLS

        normalized_outputs: dict[int, dict] = {}
        for raw_key, raw_output in multi_outputs.items():
            aq_digits = "".join(ch for ch in str(raw_key) if ch.isdigit())
            if not aq_digits:
                continue
            try:
                aq_id_int = int(aq_digits)
                normalized_outputs[aq_id_int] = dict(raw_output)
            except (ValueError, TypeError):
                continue

        video_path = video.get("path")

        for aq_id, aq_output in sorted(normalized_outputs.items()):
            if is_multi_subject_entry:
                subject_entries = video.get("metadata", {}).get("subject_entries", [])
                if multi_subject_index < len(subject_entries):
                    entry = subject_entries[multi_subject_index]
                    row_aq_id = entry.get("aquarium_id")
                    if row_aq_id is None:
                        row_aq_id = multi_subject_index

                    aq_subject = aq_output.get("subject_id")
                    row_subject = entry.get("subject")

                    if row_aq_id is not None and aq_id != row_aq_id:
                        if not (aq_subject and row_subject and str(aq_subject) == str(row_subject)):
                            continue

            aq_results_dir = aq_output.get("results_dir")
            aq_group = aq_output.get("group", "")
            aq_subject = aq_output.get("subject_id", "")
            aq_parquet_files = aq_output.get("parquet_files", {})

            aq_has_traj = bool(aq_parquet_files.get("trajectory"))
            aq_has_summary = bool(
                aq_parquet_files.get("summary") or aq_parquet_files.get("summary_excel")
            )
            aq_col_traj = STATUS_SYMBOLS["trajectory"] if aq_has_traj else ""
            aq_col_summary = STATUS_SYMBOLS["summary"] if aq_has_summary else ""

            aq_label = f"Aquário {aq_id}"
            if aq_group:
                aq_label += f" - {aq_group}"
            if aq_subject:
                aq_label += f" ({aq_subject})"

            aq_node_id = f"{parent}_aquarium_{aq_id}"

            tree.insert(
                parent,
                "end",
                iid=aq_node_id,
                text=f"🐠 {aq_label}",
                values=(
                    "",
                    "",
                    aq_col_traj,
                    aq_col_summary,
                    "",
                    aq_results_dir or "",
                ),
            )

            metadata_store[aq_node_id] = {
                "type": "aquarium",
                "video_path": video_path,
                "aquarium_id": aq_id,
                "results_dir": aq_results_dir,
                "group": aq_group,
                "subject_id": aq_subject,
            }

            if aq_results_dir and os.path.exists(aq_results_dir):
                self.append_processing_reports_artifacts(
                    tree, aq_node_id, aq_results_dir, metadata_store
                )

    def _insert_single_aquarium_node(
        self,
        tree: Any,
        parent: str,
        video: dict,
        video_path: str,
        metadata_store: dict,
    ) -> None:
        """Insert nodes for single-aquarium outputs."""
        results_dir = video.get("results_dir")
        if not results_dir:
            pm = self.gui.controller.project_manager
            results_dir = pm.resolve_results_directory(
                experiment_id=video.get("experiment_id")
                or video.get("metadata", {}).get("experiment_id"),
                video_path=video_path,
                metadata=video.get("metadata"),
            )
            if isinstance(results_dir, Path):
                results_dir = str(results_dir)

        if results_dir and os.path.exists(results_dir):
            self.append_processing_reports_artifacts(tree, parent, results_dir, metadata_store)

    # ------------------------------------------------------------------
    # Artifact helpers
    # ------------------------------------------------------------------

    def append_processing_reports_artifacts(
        self,
        tree: Any,
        parent_id: str,
        results_dir: str,
        metadata_store: dict,
    ) -> None:
        """Append report artifacts (docx, xlsx) to tree node."""
        if not os.path.exists(results_dir):
            return

        for file in os.listdir(results_dir):
            if file.endswith((".docx", ".xlsx")):
                file_path = os.path.join(results_dir, file)
                item_id = self.gui.widget_factory.build_processing_report_artifact_id(
                    parent_id, file_path
                )

                icon = "📄" if file.endswith(".docx") else "📊"

                tree.insert(
                    parent_id,
                    "end",
                    iid=item_id,
                    text=f"{icon} {file}",
                    values=("", "", "", "", "", ""),
                )

                metadata_store[item_id] = {
                    "type": "file",
                    "file_path": file_path,
                }

    def append_report_artifacts(
        self, tree: Any, parent_id: str, results_dir: str, metadata_store: dict
    ) -> None:
        """Legacy alias for ``append_processing_reports_artifacts``."""
        self.append_processing_reports_artifacts(tree, parent_id, results_dir, metadata_store)

    def append_report_artifacts_from_entry(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts (docx, xlsx) from video entry to reports tree."""
        tree = getattr(self.gui, "reports_tree", None)
        if not tree:
            return

        video_path = entry.get("path")
        if not video_path:
            return

        results_dir = entry.get("results_dir") or ""
        parquet_files = entry.get("parquet_files") or {}
        experiment_id = Path(video_path).stem if video_path else None

        def _resolve_artifact(candidate: str | None, suffix: str) -> str | None:
            if candidate and os.path.exists(candidate):
                return candidate
            if results_dir and experiment_id:
                guess_path = Path(results_dir) / f"{experiment_id}_{suffix}"
                if guess_path.exists():
                    return str(guess_path)
            return None

        docx_path = _resolve_artifact(parquet_files.get("report_docx"), "report.docx")
        excel_path = _resolve_artifact(parquet_files.get("summary_excel"), "summary.xlsx")

        artifacts: list[tuple[str, str, str]] = []
        if docx_path:
            artifacts.append(("file", docx_path, "📝 Word: " + Path(docx_path).name))
        if excel_path:
            artifacts.append(("file", excel_path, "📊 Excel: " + Path(excel_path).name))

        if not artifacts:
            return

        for _kind, artifact_path, label in artifacts:
            child_id = tree.insert(
                parent_id,
                "end",
                text=label,
                values=("", "", "", "", "Abrir"),
                tags=("report-file",),
            )
            self.gui._report_tree_metadata[child_id] = {
                "type": "file",
                "path": artifact_path,
                "parent_video": video_path,
            }

        tree.item(parent_id, open=True)

    # ------------------------------------------------------------------
    # Double-click / file opening
    # ------------------------------------------------------------------

    def on_processing_reports_item_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on items in the Processing Reports tree."""
        if not self.gui.processing_reports_widget or not self.gui.processing_reports_widget.tree:
            return

        tree = self.gui.processing_reports_widget.tree

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata = self.gui._processing_reports_tree_metadata.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")

        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        if node_type == "video":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info("gui.open_results_folder", path=results_dir)
                self._open_path_in_explorer(results_dir)
            return

        if node_type == "aquarium":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info(
                    "gui.open_aquarium_results_folder",
                    path=results_dir,
                    aquarium_id=metadata.get("aquarium_id"),
                )
                self._open_path_in_explorer(results_dir)
            return

    def _handle_report_file_node(self, metadata: dict) -> None:
        """Handle opening of report file node."""
        file_path = metadata.get("file_path") or metadata.get("path")
        if not file_path or not os.path.exists(file_path):
            return

        log.info("gui.open_report_file", path=file_path)
        self._open_path_in_explorer(file_path)

    def open_unified_report(self, file_type: str) -> None:
        """Open the latest unified report of the specified type."""
        pm = self.gui.controller.project_manager
        if not pm.project_path:
            return

        unified_dir = Path(pm.project_path) / "unified_reports"
        if not unified_dir.exists():
            self.dialog_manager.show_warning(
                "Indisponível", "Nenhum relatório unificado encontrado."
            )
            return

        pattern = ""
        if file_type == "word":
            pattern = "*.docx"
        elif file_type == "excel":
            pattern = "*.xlsx"
        elif file_type == "parquet":
            pattern = "*.parquet"

        if not pattern:
            return

        files = list(unified_dir.glob(pattern))
        if not files:
            self.dialog_manager.show_warning(
                "Indisponível", f"Nenhum relatório {file_type} encontrado."
            )
            return

        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        self._handle_report_file_node({"file_path": str(latest_file)})

    def handle_report_video_node(self, metadata: dict) -> None:
        """Handle double-click on report video node — opens results directory."""
        video_path = metadata.get("video_path")
        if not video_path:
            return

        controller = getattr(self.gui, "controller", None)
        pm = getattr(controller, "project_manager", None)
        if not pm:
            return

        entry = pm.find_video_entry(path=video_path)
        results_dir = metadata.get("results_dir") or ""
        metadata_hint: dict = {}
        has_results = False

        if entry:
            metadata_hint = dict(entry.get("metadata") or {})
            if not results_dir:
                results_dir = entry.get("results_dir") or ""
            for key in ("group", "group_display_name", "day", "subject"):
                if entry.get(key) is not None and key not in metadata_hint:
                    metadata_hint[key] = entry[key]
            parquet_files = entry.get("parquet_files") or {}
            for key in ("summary", "summary_excel", "report_docx"):
                candidate_path = parquet_files.get(key)
                if candidate_path and os.path.exists(candidate_path):
                    has_results = True
                    break

        experiment_id = Path(video_path).stem
        if not results_dir:
            results_path = pm.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_hint,
            )
            results_dir = str(results_path)

        if not has_results and results_dir:
            summary_candidate = Path(results_dir) / f"{experiment_id}_summary.parquet"
            report_candidate = Path(results_dir) / f"{experiment_id}_report.docx"
            excel_candidate = Path(results_dir) / f"{experiment_id}_summary.xlsx"
            if summary_candidate.exists() or report_candidate.exists() or excel_candidate.exists():
                has_results = True

        if not results_dir or not os.path.isdir(results_dir) or not has_results:
            self.dialog_manager.show_warning(
                "Relatórios indisponíveis",
                "Gere o relatório para este vídeo antes de abrir a pasta de resultados.",
            )
            return

        self._open_path_in_explorer(results_dir)

    # ------------------------------------------------------------------
    # Unified-report generation
    # ------------------------------------------------------------------

    def generate_unified_report(self) -> None:
        """Generate a unified report for all project videos."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        all_videos = self.gui.controller.project_manager.get_all_videos()
        if not all_videos:
            self.dialog_manager.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return

        replace_existing = self._resolve_unified_generation_strategy()
        if replace_existing is None:
            return

        self.gui.event_dispatcher.publish_event(
            UIEvents.REPORT_GENERATE,
            {
                "videos": all_videos,
                "report_type": "unified",
                "report_scope": "all",
                "replace_existing": replace_existing,
            },
        )

    def on_processing_reports_generate_partial(self) -> None:
        """Handle partial report generation from the unified tab."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        if not self.gui.processing_reports_widget:
            return

        selection = self.gui.processing_reports_widget.get_selection()
        if not selection:
            return

        selected_videos: list[dict] = []
        all_videos = self.gui.controller.project_manager.get_all_videos()
        metadata_store = getattr(self.gui, "_processing_reports_tree_metadata", {})

        for item_id in selection:
            metadata = metadata_store.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            replace_existing = self._resolve_unified_generation_strategy()
            if replace_existing is None:
                return

            self.gui.event_dispatcher.publish_event(
                UIEvents.REPORT_GENERATE,
                {
                    "videos": selected_videos,
                    "report_type": "unified",
                    "report_scope": "selected",
                    "replace_existing": replace_existing,
                },
            )

    def generate_partial_report(self) -> None:
        """Gather selected videos and generate a unified partial report from reports tree."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        if not hasattr(self.gui, "reports_tree") or not self.gui.reports_tree:
            return

        selected_items = self.gui.reports_tree.selection()
        if not selected_items:
            return

        selected_videos: list[dict] = []
        all_videos = self.gui.controller.project_manager.get_all_videos()
        metadata_store = getattr(self.gui, "_report_tree_metadata", {})

        for item_id in selected_items:
            if not self.gui.reports_tree.exists(item_id):
                continue
            metadata = metadata_store.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            replace_existing = self._resolve_unified_generation_strategy()
            if replace_existing is None:
                return

            self.gui.event_dispatcher.publish_event(
                UIEvents.REPORT_GENERATE,
                {
                    "videos": selected_videos,
                    "report_type": "unified",
                    "report_scope": "selected",
                    "replace_existing": replace_existing,
                },
            )

    def _resolve_unified_generation_strategy(self) -> bool | None:
        """Resolve conflict strategy when unified reports already exist.

        Returns:
            True to overwrite, False to keep and append, None if user cancels.
        """
        pm = self.gui.controller.project_manager
        if not pm.project_path:
            return False

        unified_dir = Path(pm.project_path) / "unified_reports"
        if not unified_dir.exists():
            return False

        has_existing = (
            any(unified_dir.glob("*.parquet"))
            or any(unified_dir.glob("*.xlsx"))
            or any(unified_dir.glob("*.docx"))
        )
        if not has_existing:
            return False

        response = self.gui.dialog_manager.ask_yes_no_cancel(
            "Relatórios Unificados Existentes",
            (
                "Já existem relatórios unificados neste projeto.\n\n"
                "Sim: apagar os anteriores e gerar novo\n"
                "Não: manter anteriores e gerar outro com novo nome\n"
                "Cancelar: abortar geração"
            ),
            icon="warning",
        )

        if response is None:
            self.gui.set_status("Geração de relatório unificado cancelada pelo usuário.")
            return None

        return bool(response)

    def _delete_all_unified_reports(self, data: dict | None = None) -> None:
        """Delete the entire unified_reports directory.

        Subscribed to event ``reports.delete_unified``.
        """
        pm = self.gui.controller.project_manager
        if not pm.project_path:
            return

        import shutil
        import stat
        import time

        unified_dir = os.path.join(pm.project_path, "unified_reports")

        def on_rm_error(func, path, exc_info):
            """Handler to clear read-only/locked files."""
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except OSError:
                log.debug(
                    "reports_tree_manager.rmtree_retry.suppressed",
                    path=path,
                    exc_info=True,
                )

        if os.path.exists(unified_dir):
            success = False
            last_error = None

            for _ in range(3):
                try:
                    shutil.rmtree(unified_dir, onerror=on_rm_error)
                    success = True
                    break
                except OSError as e:
                    last_error = e
                    time.sleep(0.5)

            if success:
                log.info("project.delete_unified.success", path=unified_dir)
                self.dialog_manager.show_info(
                    "Sucesso", "Todos os relatórios unificados foram apagados."
                )

                if hasattr(self.gui, "processing_reports_widget"):
                    self.gui.processing_reports_widget._update_button_states(pm.project_path)
            else:
                log.warning("project.delete_unified.failed", error=str(last_error))

                msg = "Não foi possível apagar a pasta.\nVerifique se algum arquivo está aberto."
                if last_error and "OneDrive" in str(unified_dir):
                    msg += (
                        "\n\nO OneDrive pode estar bloqueando arquivos. "
                        "Tente novamente em instantes."
                    )

                self.dialog_manager.show_error("Erro ao Apagar", f"{msg}\n\nErro: {last_error}")
        else:
            self.dialog_manager.show_info("Aviso", "Não havia relatórios unificados para apagar.")

    # ------------------------------------------------------------------
    # Status counts
    # ------------------------------------------------------------------

    def _get_project_status_counts(self) -> dict[str, int]:
        """Calculate status counts for the project."""
        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()

        counts: dict[str, int] = {
            "total": len(all_videos),
            "pending": 0,
            "processing": 0,
            "processed": 0,
            "complete": 0,
            "failed": 0,
            "arena": 0,
            "rois": 0,
            "trajectory": 0,
            "summary": 0,
        }

        for video in all_videos:
            status = video.get("status", "pending")
            if status in counts:
                counts[status] += 1

            path = video.get("path")
            if path:
                if pm.has_arena_data(path):
                    counts["arena"] += 1
                if pm.has_roi_data(path):
                    counts["rois"] += 1
                if pm.has_trajectory_data(path):
                    counts["trajectory"] += 1
                if pm.has_summary_data(path):
                    counts["summary"] += 1

        return counts

    # ------------------------------------------------------------------
    # Legacy stubs
    # ------------------------------------------------------------------

    def on_report_item_select(self, event: Any | None = None) -> None:
        """Handle selection of report item (LEGACY stub)."""
        log.warning(
            "reports_tree_manager.on_report_item_select_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )

    def on_report_item_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on report item (LEGACY stub)."""
        log.warning(
            "reports_tree_manager.on_report_item_double_click_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    def _open_path_in_explorer(self, path: str) -> None:
        """Open a file or folder in the system file explorer."""
        try:
            if sys.platform == "win32":
                startfile = getattr(os, "startfile", None)
                if callable(startfile):
                    startfile(path)
                else:
                    raise OSError("startfile not available")
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as e:
            log.error("gui.open_path.failed", path=path, error=str(e))
            self.dialog_manager.show_error("Erro", f"Não foi possível abrir: {e}")

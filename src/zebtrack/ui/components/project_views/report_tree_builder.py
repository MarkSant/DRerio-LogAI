"""Report Tree Builder — Tree population and status counting for reports tree.

Extracted from ReportsTreeManager (Phase 5 decomposition).
Owns all methods that build/populate the Treeview nodes for groups, days,
videos, aquariums, and status counts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.ui.components.validation_manager import ValidationManager
    from zebtrack.ui.components.widget_factory import WidgetFactory

log = structlog.get_logger()


class ReportTreeBuilder:
    """Build and populate the Processing-Reports Treeview nodes.

    Extracted from ReportsTreeManager to isolate tree-building logic from
    event handling and report generation concerns.

    Attributes:
        project_manager: ProjectManager for video queries.
        validation_manager: ValidationManager for hierarchy data.
        widget_factory: WidgetFactory for tree item ID generation.
        processing_reports_widget: The ProcessingReportsWidget for the tree.
    """

    def __init__(
        self,
        *,
        project_manager_getter: Any,
        validation_manager: ValidationManager | None = None,
        widget_factory: WidgetFactory | None = None,
        processing_reports_widget: Any | None = None,
        tree_metadata: dict | None = None,
    ) -> None:
        """Initialise with required dependencies.

        Args:
            project_manager_getter: Callable or attribute that returns
                the current ProjectManager (supports hot-swapping).
            validation_manager: ValidationManager for hierarchy building.
            widget_factory: WidgetFactory for artifact ID generation.
            processing_reports_widget: The ProcessingReportsWidget reference.
            tree_metadata: Shared metadata dict for tree node storage.
        """
        self._project_manager_getter = project_manager_getter
        self._validation_manager = validation_manager
        self._widget_factory = widget_factory
        self._processing_reports_widget = processing_reports_widget
        self._tree_metadata: dict = tree_metadata if tree_metadata is not None else {}

    @property
    def project_manager(self) -> ProjectManager:
        """Return the current ProjectManager (supports hot-swap)."""
        if callable(self._project_manager_getter):
            return self._project_manager_getter()
        return self._project_manager_getter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_tab(self) -> None:
        """Refresh processing reports tab with current project data.

        Updates the tree with current project data and report artifacts.
        """
        widget = self._processing_reports_widget
        if not widget:
            return

        pm = self.project_manager
        all_videos = pm.get_all_videos()

        for v in all_videos:
            vpath = v.get("path")
            if vpath and "CECT_8" in vpath:
                log.info(
                    "debug.refresh_tab.video_state",
                    path=os.path.basename(vpath),
                    has_traj=v.get("has_trajectory"),
                    has_arena=v.get("has_arena"),
                )

        assert self._validation_manager is not None
        hierarchy = self._validation_manager._build_video_hierarchy_data(all_videos, "")

        self._tree_metadata.clear()

        tree = widget.tree
        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        self.populate_from_hierarchy(tree, hierarchy, "", self._tree_metadata)

        status_counts = self.get_project_status_counts()
        if hasattr(widget, "update_status_counts"):
            widget.update_status_counts(status_counts)

        if hasattr(widget, "_update_button_states"):
            project_path = str(pm.project_path) if pm and pm.project_path else None
            widget._update_button_states(project_path=project_path)

    def update_tree(self) -> None:
        """Update the reports tree view in ProcessingReportsWidget.

        Refreshes tree content based on current project state.
        """
        widget = self._processing_reports_widget
        if not widget or not widget.tree:
            return

        widget.clear_tree()

        pm = self.project_manager
        all_videos = pm.get_all_videos()

        assert self._validation_manager is not None
        hierarchy = self._validation_manager._build_video_hierarchy_data(all_videos, "")

        status_counts = self.get_project_status_counts()

        self._tree_metadata.clear()

        self.populate_from_hierarchy(widget.tree, hierarchy, "", self._tree_metadata)

        widget.update_status_counts(status_counts)

        log.debug("report_tree_builder.reports_tree_updated")

    # ------------------------------------------------------------------
    # Tree population helpers
    # ------------------------------------------------------------------

    def populate_from_hierarchy(
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
                pm = self.project_manager
                canonical_entry = pm.find_video_entry(path=video_path) if pm else None
                if canonical_entry and isinstance(canonical_entry, dict):
                    multi_outputs = canonical_entry.get("multi_aquarium_outputs")
            except (AttributeError, KeyError, TypeError):
                log.debug("report_tree_builder.multi_outputs_fallback.suppressed", exc_info=True)

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
                self.append_artifacts(tree, aq_node_id, aq_results_dir, metadata_store)

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
            pm = self.project_manager
            results_dir = pm.resolve_results_directory(
                experiment_id=video.get("experiment_id")
                or video.get("metadata", {}).get("experiment_id"),
                video_path=video_path,
                metadata=video.get("metadata"),
            )
            if isinstance(results_dir, Path):
                results_dir = str(results_dir)

        if results_dir and os.path.exists(results_dir):
            self.append_artifacts(tree, parent, results_dir, metadata_store)

    # ------------------------------------------------------------------
    # Artifact helpers (used by tree building)
    # ------------------------------------------------------------------

    def append_artifacts(
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
                assert self._widget_factory is not None
                item_id = self._widget_factory.build_processing_report_artifact_id(
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

    # ------------------------------------------------------------------
    # Status counts
    # ------------------------------------------------------------------

    def get_project_status_counts(self) -> dict[str, int]:
        """Calculate status counts for the project."""
        pm = self.project_manager
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

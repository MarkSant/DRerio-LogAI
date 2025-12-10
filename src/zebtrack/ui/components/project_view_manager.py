"""
Project View Manager Component for ApplicationGUI.

Responsável por gerenciar visualizações de projeto, navegação entre views,
atualização de árvores e refresh de dados.

Categories:
1. Navegação e Window Management
2. Project Overview Management
3. Formatadores e Helpers
4. Pipeline e Video Selector Management
5. Processing Reports Management
6. Reports Tree Management
7. Event Handlers
"""

import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


class ProjectViewManager:
    """
    Manager for project views, navigation, and data refresh.

    Encapsulates all view management logic extracted from ApplicationGUI.
    Uses self.gui to access parent GUI state and methods.

    Thread-safety: All UI updates must use gui.root.after(0, ...) pattern.
    """

    def __init__(self, gui, event_bus_v2=None):
        """
        Initialize ProjectViewManager with reference to parent GUI.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2

        # Subscribe to events if event bus is available
        if self.event_bus_v2:
            self._setup_event_subscriptions()
        self._overview_refresh_pending = False
        self._overview_refresh_after_id = None

    def _setup_event_subscriptions(self):
        """Subscribe to Event Bus V2 events for v4.0 Event-Driven Architecture."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        # Subscribe to VIDEO_TREE_REFRESH_REQUESTED event
        # (replaces direct gui._populate_video_selector_tree calls)
        self.event_bus_v2.subscribe(
            UIEvents.VIDEO_TREE_REFRESH_REQUESTED, self._on_video_tree_refresh_requested
        )

        # Subscribe to READINESS_SNAPSHOT_UPDATED event
        # (replaces direct gui.apply_pending_readiness_snapshot calls)
        self.event_bus_v2.subscribe(
            UIEvents.READINESS_SNAPSHOT_UPDATED, self._on_readiness_snapshot_updated
        )

        # Subscribe to VIDEO_HIERARCHY_SNAPSHOT_UPDATED event
        self.event_bus_v2.subscribe(
            UIEvents.VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: self.on_video_hierarchy_snapshot_updated(d.get("snapshot", [])),
        )

        log.debug(
            "project_view_manager.event_subscriptions_setup",
            events=[
                "VIDEO_TREE_REFRESH_REQUESTED",
                "READINESS_SNAPSHOT_UPDATED",
                "VIDEO_HIERARCHY_SNAPSHOT_UPDATED",
            ],
        )

    def _on_video_tree_refresh_requested(self, data: dict):
        """Handle VIDEO_TREE_REFRESH_REQUESTED event.

        Args:
            data: Event payload containing filter_text
        """
        if not isinstance(data, dict):
            log.warning("project_view_manager._on_video_tree_refresh_requested.invalid_data_type",
                       data_type=type(data).__name__)
            return
        filter_text = data.get("filter_text")
        log.debug("project_view_manager.video_tree_refresh_event_received", filter_text=filter_text)
        self._populate_video_selector_tree(filter_text)

    def _on_readiness_snapshot_updated(self, data: dict):
        """Handle READINESS_SNAPSHOT_UPDATED event.

        Args:
            data: Event payload containing readiness snapshot data
        """
        if not isinstance(data, dict):
            log.warning("project_view_manager._on_readiness_snapshot_updated.invalid_data_type",
                       data_type=type(data).__name__)
            return
        ready_with_trajectory = data.get("ready_with_trajectory", [])
        ready_with_zones = data.get("ready_with_zones", [])
        arena_only = data.get("arena_only", [])
        without_arena = data.get("without_arena", [])

        log.debug(
            "project_view_manager.readiness_snapshot_event_received",
            ready_with_trajectory_count=len(ready_with_trajectory),
            ready_with_zones_count=len(ready_with_zones),
            arena_only_count=len(arena_only),
            without_arena_count=len(without_arena),
        )

        self.apply_pending_readiness_snapshot(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

    # ===========================================================================
    # CATEGORIA 1: NAVEGAÇÃO E WINDOW MANAGEMENT
    # ===========================================================================

    def update_window_title(self, project_name: str | None = None):
        """
        Update the window title with optional project name.

        Args:
            project_name: Name of the current project, or None for default title
        """
        if project_name:
            self.gui.root.title(f"DRerio LogAI - {project_name}")
        else:
            self.gui.root.title("DRerio LogAI")

    def navigate_to_processing_reports_tab(self) -> None:
        """Navigate to the Processing and Reports tab."""
        if not self.gui.notebook:
            return

        # Find the index of the Processing and Reports tab
        tab_count = self.gui.notebook.index("end")
        for i in range(tab_count):
            tab_text = self.gui.notebook.tab(i, "text")
            if "Processamento e Relatórios" in tab_text:
                self.gui.notebook.select(i)
                return

        log.warning("gui.navigate.processing_reports_tab_not_found")

    # ===========================================================================
    # CATEGORIA 2: PROJECT OVERVIEW MANAGEMENT
    # ===========================================================================

    def request_overview_refresh(
        self,
        reason: str | None = None,
        *,
        force: bool = False,
        debounce_ms: int = 300,
    ) -> None:
        if force:
            if self._overview_refresh_after_id:
                self.gui.root.after_cancel(self._overview_refresh_after_id)
                self._overview_refresh_after_id = None
            self._overview_refresh_pending = False
            self.refresh_project_views(
                reason=reason,
                append_summary=False,
                immediate=True,
            )
            return

        if self._overview_refresh_pending:
            return

        self._overview_refresh_pending = True
        if reason:
            log.debug("gui.overview.refresh_requested", reason=reason)

        def _execute():
            self._overview_refresh_pending = False
            self._overview_refresh_after_id = None
            self.refresh_project_views(reason=reason)

        self._overview_refresh_after_id = self.gui.root.after(debounce_ms, _execute)

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Refresh project overview, pipeline table, and reports tab."""
        if reason:
            log.debug(
                "project_view_manager.refresh_project_views",
                reason=reason,
                append_summary=append_summary,
                immediate=immediate,
            )
            if append_summary and hasattr(self.gui, "set_status"):
                try:
                    self.gui.set_status(reason)
                except Exception:
                    log.warning("project_view_manager.refresh_project_views.status_failed")

        # Refresh project overview
        self._refresh_project_overview()

        # Refresh pipeline table if in pre-recorded mode
        project_type = self.gui.controller.project_manager.get_project_type()
        if project_type == "pre-recorded":
            self._refresh_pipeline_video_table()

        # Refresh processing reports tab
        self._refresh_processing_reports_tab()

    def _refresh_project_overview(self) -> None:
        """Update the project overview panel with current project data."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        self._update_project_overview_summary()
        self._update_project_overview_tree()

        # Schedule legend update via root.after for thread-safety
        def _update_legend():
            if hasattr(self.gui, "project_overview_widget"):
                if self.gui.project_overview_widget:
                    self.gui.project_overview_widget.update_legend()

        self.gui.root.after(0, _update_legend)

    def _update_project_overview_summary(self) -> None:
        """Update the summary section of the project overview."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()

        # Count videos by status
        status_counts = Counter()
        for video in all_videos:
            has_trajectory = pm.has_trajectory_data(video["path"])
            has_summary = pm.has_summary_data(video["path"])

            if has_summary:
                status_counts["complete"] += 1
            elif has_trajectory:
                status_counts["processed"] += 1
            else:
                status_counts["pending"] += 1

        status_counts["total"] = len(all_videos)

        # Update widget
        self.gui.project_overview_widget.update_summary(status_counts)

    def _update_project_overview_tree(self) -> None:
        """Update the tree view in the project overview."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        # Request update via event
        if self.event_bus_v2:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED,
                    data={},
                    source="ProjectViewManager._update_project_overview_tree",
                )
            )
        else:
            # Fallback if no event bus
            self._build_video_hierarchy_snapshot()

    def _build_video_hierarchy_snapshot(self) -> list[dict]:
        """Build video hierarchy snapshot. Delegates to ValidationManager."""
        controller = getattr(self.gui, "controller", None)
        if not controller or not controller.project_manager:
            return []

        pm = controller.project_manager
        all_videos = pm.get_all_videos() or []

        if hasattr(self.gui, "validation_manager"):
            # Use prepare_overview_hierarchy_for_widget to get the correct structure
            # (groups, summaries) instead of build_video_hierarchy_snapshot
            # which returns a simpler list
            hierarchy_data = (
                self.gui.validation_manager.prepare_overview_hierarchy_for_widget(all_videos)
            )

            # Extract the 'groups' list which contains the snapshot data
            snapshot = hierarchy_data.get("groups", [])

            # Publish the update
            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
                        data={"snapshot": snapshot},
                        source="ProjectViewManager._build_video_hierarchy_snapshot",
                    )
                )
            return snapshot
        return []

    def on_video_hierarchy_snapshot_updated(self, snapshot: list[dict]) -> None:
        """Handle video hierarchy snapshot update event."""
        if not hasattr(self.gui, "project_overview_widget") or not self.gui.project_overview_widget:
            return
        self.gui.project_overview_widget.update_tree(snapshot)

    # ===========================================================================
    # CATEGORIA 3: FORMATADORES E HELPERS
    # ===========================================================================

    def format_status_label(self, count: int) -> str:
        """Format status count for display."""
        return f"{count} vídeo{'s' if count != 1 else ''}"

    def format_status_summary(self, total: int, count: int) -> str:
        """
        Format status summary with count and percentage.

        Args:
            total: Total number of videos
            count: Count for this status

        Returns:
            Formatted string like "5 vídeos (25%)"
        """
        if total == 0:
            return "0 vídeos (0%)"
        percentage = int((count / total) * 100)
        label = self.format_status_label(count)
        return f"{label} ({percentage}%)"

    def format_status_ratio(self, numerator: int, denominator: int) -> str:
        """
        Format ratio display.

        Args:
            numerator: Numerator value
            denominator: Denominator value

        Returns:
            Formatted string like "5/10"
        """
        return f"{numerator}/{denominator}"

    def summarize_batch_data(self, videos: list[dict]) -> dict[str, Any]:
        """
        Summarize batch of videos into counts.

        Args:
            videos: List of video dictionaries

        Returns:
            Dictionary with counts by status
        """
        pm = self.gui.controller.project_manager
        counts = {
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

    def format_data_badges(self, video_path: str) -> str:
        """
        Format data availability badges for a video.

        Args:
            video_path: Path to video file

        Returns:
            String with status symbols (e.g., "🏟 🎯 🧭")
        """
        from zebtrack.ui.gui import STATUS_SYMBOLS

        pm = self.gui.controller.project_manager
        badges = []

        if pm.has_arena_data(video_path):
            badges.append(STATUS_SYMBOLS["arena"])
        if pm.has_roi_data(video_path):
            badges.append(STATUS_SYMBOLS["rois"])
        if pm.has_trajectory_data(video_path):
            badges.append(STATUS_SYMBOLS["trajectory"])

        return " ".join(badges) if badges else "—"

    def format_video_metadata(self, video: dict) -> str:
        """
        Format video metadata for display.

        Args:
            video: Video dictionary with metadata

        Returns:
            Formatted string with metadata info
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

    @staticmethod
    def format_status_token(status: str) -> str:
        """Format status token for tree display."""
        return status if status else "—"

    @staticmethod
    def _video_sort_key(value):
        """Generate sort key for video/subject identifiers.

        Numeric values sort before text values.
        Args:
            value: Identifier to sort

        Returns:
            Tuple of (type_priority, sort_value)
        """
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            value_str = str(value) if value is not None else ""
            return (1, value_str.lower())

    # ===========================================================================
    # CATEGORIA 4: PIPELINE E VIDEO SELECTOR MANAGEMENT
    # ===========================================================================

    def update_zone_summary_cards(self) -> None:
        """Update zone summary cards with current project status."""
        if not hasattr(self.gui, "zone_summary_cards") or not self.gui.zone_summary_cards:
            return

        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()
        counts = self.summarize_batch_data(all_videos)

        # Counts are: total, with_arena, with_rois, with_trajectory, with_summary

        arena_pending = counts["total"] - counts["with_arena"]

        # Videos that have arena but need ROIs
        rois_needed = counts["with_arena"] - counts["with_rois"]
        rois_needed = max(0, rois_needed)

        if "arena_pending" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["arena_pending"].set(str(arena_pending))

        if "rois_pending" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["rois_pending"].set(str(rois_needed))

        if "ready_processing" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["ready_processing"].set(str(counts["with_rois"]))

    def apply_pending_readiness_snapshot(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> None:
        """Apply pending readiness snapshot based on video readiness states."""
        mapping: dict[str, tuple[str, ...]] = {}

        def _assign(entries: list[dict], *tags: str) -> None:
            for info in entries or []:
                path = info.get("path")
                if path:
                    mapping[path] = tuple(tags)

        _assign(ready_with_trajectory, "ready_full")
        _assign(ready_with_zones, "ready_partial")
        _assign(arena_only, "ready_optional", "ready_partial")
        _assign(without_arena, "ready_missing")

        self.gui._pending_readiness_snapshot = mapping

        if hasattr(self.gui, "video_selector_tree") and self.gui.video_selector_tree:
            filter_text = self.gui._video_selector_filter

            # NEW PATH - Event-Driven Architecture v4.0
            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                        data={"filter_text": filter_text},
                        source="ProjectViewManager._build_readiness_snapshot",
                    )
                )
            else:
                # Fallback for tests or if event bus missing (call internal impl)
                self._populate_video_selector_tree(filter_text)

    def refresh_pipeline_video_table(self) -> None:
        """Refresh the pipeline video table in pre-recorded projects."""
        # Note: This method is called _refresh_pipeline_video_table in gui.py
        # but exposed as public method here
        self._refresh_pipeline_video_table()

    def _populate_video_selector_tree(self, filter_text: str | None = None) -> None:
        """Populate video selector tree with filtered videos.

        Args:
            filter_text: Optional filter string
        """
        # Access tree via ZoneControls
        zone_controls = getattr(self.gui, "zone_controls", None)
        if not zone_controls or not zone_controls.video_selector_tree:
            return
        tree = zone_controls.video_selector_tree

        # Capture current selection to restore later
        selected_tag = None
        selection = tree.selection()
        if selection:
            try:
                tags = tree.item(selection[0], "tags")
                if tags:
                    selected_tag = tags[0]
            except Exception:
                selected_tag = None

        # Clear tree
        for item in tree.get_children():
            tree.delete(item)

        # Get data
        pm = getattr(self.gui.controller, "project_manager", None)
        if not pm:
            return

        try:
            all_videos = pm.get_all_videos()
        except Exception:
            all_videos = []

        # Build hierarchy using ValidationManager helper (delegation)
        if hasattr(self.gui, "validation_manager"):
            hierarchy = self.gui.validation_manager._build_video_hierarchy_data(
                all_videos, filter_text or ""
            )
        else:
            log.warning("project_view_manager.populate_tree.missing_validation_manager")
            return

        # Populate tree
        from zebtrack.ui.gui import STATUS_SYMBOLS

        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            group_display = f"🏷️ {group_data['display']}"
            group_node = tree.insert("", "end", text=group_display, open=True)

            for day_id, videos in sorted(
                group_data["days"].items(),
                key=lambda item: self._video_sort_key(item[0]),
            ):
                # Resolve day title
                sample_meta = videos[0].get("metadata") if videos else None
                day_title = self.gui.validation_manager._build_day_title(day_id, sample_meta)
                day_node = tree.insert(group_node, "end", text=f"📅 {day_title}", open=True)

                for video_entry in sorted(
                    videos,
                    key=lambda entry: self._video_sort_key(entry.get("subject")),
                ):
                    # Format subject label
                    subject_val = video_entry.get("subject")
                    subject_label = self.gui.validation_manager.format_subject_label(subject_val)

                    filename = video_entry.get("filename", "")
                    path = video_entry.get("path", "")

                    # Build status string
                    badges = []
                    if video_entry.get("has_arena"):
                        badges.append(STATUS_SYMBOLS["arena"])
                    if video_entry.get("has_rois"):
                        badges.append(STATUS_SYMBOLS["rois"])
                    if video_entry.get("has_trajectory"):
                        badges.append(STATUS_SYMBOLS["trajectory"])

                    status_display = " ".join(badges) if badges else "—"

                    display_text = f"🐟 Sujeito {subject_label}"

                    tree.insert(
                        day_node,
                        "end",
                        text=display_text,
                        values=(status_display, filename),
                        tags=(path,),
                    )

        # Apply expansion state if available
        if hasattr(zone_controls, "apply_video_tree_expand_state"):
            zone_controls.apply_video_tree_expand_state()

        # Restore selection
        if selected_tag:
            self._reselect_video_tree_item(tree, selected_tag)

    def _reselect_video_tree_item(self, tree, target_tag: str) -> None:
        """Reselect an item in the tree by tag."""
        if not target_tag or not tree:
            return

        def _walk(node: str) -> bool:
            for child in tree.get_children(node):
                tags = tree.item(child, "tags")
                if tags and tags[0] == target_tag:
                    # Ensure branch is visible before selecting
                    parent = tree.parent(child)
                    while parent:
                        tree.item(parent, open=True)
                        parent = tree.parent(parent)

                    tree.selection_set(child)
                    tree.see(child)
                    return True

                if _walk(child):
                    return True
            return False

        _walk("")

    def _refresh_pipeline_video_table(self) -> None:
        """Refresh pipeline video table (internal implementation)."""
        log.warning(
            "project_view_manager.refresh_pipeline_video_table_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ProcessingReportsWidget
        # Kept here for backward compatibility

    def trigger_batch_trajectory_processing(self, selection=None) -> None:
        """Trigger batch trajectory processing for selected or all videos."""
        from zebtrack.ui.events import Events

        selections = []
        if selection is not None:
            # Selection passed directly (e.g. from callback args)
            selections = self.gui._resolve_processing_reports_video_paths(selection)
        else:
            # Try to resolve from active widget
            selections = self.resolve_processing_reports_video_paths()

            # Fallback to legacy pipeline selection
            if not selections:
                selections = self._get_selected_pipeline_video_paths()

            # Fallback to all eligible videos in legacy pipeline if explicit selection empty?
            # (Legacy behavior was: if no selection, process all listed in table)
            if not selections and hasattr(self.gui, "pipeline_video_vars"):
                pipeline_vars = getattr(self.gui, "pipeline_video_vars", {}) or {}
                selections = list(pipeline_vars.keys())

        if not selections:
            self.gui.show_info(
                "Processamento",
                "Nenhum vídeo elegível foi encontrado ou selecionado.",
            )
            return

        unique_paths = list(dict.fromkeys(selections))

        self.gui.event_dispatcher.publish_event(
            Events.PROJECT_PROCESS_VIDEOS, {"video_paths": unique_paths}
        )
        self.request_overview_refresh()
        # Switch to analysis tab to show progress
        self.gui._switch_to_analysis_view()

    def trigger_parquet_summaries(self) -> None:
        """Trigger export of parquet summaries for selected videos."""
        from zebtrack.ui.events import Events

        # Try to resolve from active widget (new tab)
        selections = self.resolve_processing_reports_video_paths()

        # Fallback to legacy pipeline selection
        if not selections:
            selections = self._get_selected_pipeline_video_paths()

        if not selections:
            self.gui.show_info(
                "Sumários",
                "Selecione ao menos um vídeo com trajetória para exportar o sumário.",
            )
            return

        unique_paths = list(dict.fromkeys(selections))

        self.gui.event_dispatcher.publish_event(
            Events.PROJECT_GENERATE_SUMMARIES, {"video_paths": unique_paths}
        )
        self.refresh_project_views()

    def generate_unified_report(self) -> None:
        """Generate a unified report for all project videos."""
        from zebtrack.ui.events import Events

        all_videos = self.gui.controller.project_manager.get_all_videos()
        if not all_videos:
            self.gui.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return
        self.gui.event_dispatcher.publish_event(
            Events.REPORT_GENERATE,
            {"videos": all_videos, "report_type": "unified"},
        )

    def _get_selected_pipeline_video_paths(self) -> list[str]:
        """Get selected video paths from legacy pipeline tree."""
        tree = getattr(self.gui, "pipeline_video_tree", None)
        if not tree:
            return []

        selected_items = list(tree.selection() or [])
        if not selected_items:
            return []

        final_selection: list[str] = []
        seen_subjects: set[str] = set()
        pipeline_vars = getattr(self.gui, "pipeline_video_vars", {})
        had_hierarchy_nodes = False

        def add_subject(item_id: str) -> None:
            if item_id in pipeline_vars and item_id not in seen_subjects:
                seen_subjects.add(item_id)
                final_selection.append(item_id)

        def collect_descendants(item_id: str) -> None:
            # Ensure parent nodes are expanded so children become visible.
            try:
                tree.item(item_id, open=True)
            except Exception:
                pass

            for child in tree.get_children(item_id):
                if child in pipeline_vars:
                    add_subject(child)
                else:
                    collect_descendants(child)

        for item in selected_items:
            if item in pipeline_vars:
                add_subject(item)
            else:
                had_hierarchy_nodes = True
                collect_descendants(item)

        if had_hierarchy_nodes or len(final_selection) != len(selected_items):
            # Replace Treeview selection with the resolved subject entries only.
            try:
                tree.selection_set(tuple(final_selection))
            except Exception:
                pass

        return final_selection

    def resolve_processing_reports_video_paths(self, selection=None) -> list[str]:
        """
        Resolve selected video paths from processing reports tree.

        Args:
            selection: Optional list of item IDs. If None, uses current tree selection.

        Returns:
            List of selected video paths
        """
        if not hasattr(self.gui, "processing_reports_widget"):
            return []
        if not self.gui.processing_reports_widget:
            return []

        tree = self.gui.processing_reports_widget.tree
        if not tree:
            return []

        selected = selection if selection is not None else tree.selection()
        video_paths = []

        for item_id in selected:
            video_path = tree.set(item_id, "video_path")
            if video_path and os.path.isfile(video_path):
                video_paths.append(video_path)

        return video_paths

    def update_pipeline_buttons_state(self) -> None:
        """Update state of pipeline action buttons."""
        log.warning(
            "project_view_manager.update_pipeline_buttons_state_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ProcessingReportsWidget
        # Kept here for backward compatibility

    def populate_video_selector_tree(self, search_text: str = "") -> None:
        """
        Populate video selector tree with filtered videos.

        Args:
            search_text: Search filter text
        """
        log.warning(
            "project_view_manager.populate_video_selector_tree_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ZoneControlsWidget
        # Kept here for backward compatibility

    def refresh_video_selector_tree(self) -> None:
        """Refresh the video selector tree."""
        log.warning(
            "project_view_manager.refresh_video_selector_tree_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ZoneControlsWidget
        # Kept here for backward compatibility

    # ===========================================================================
    # CATEGORIA 5: PROCESSING REPORTS MANAGEMENT
    # ===========================================================================

    def refresh_processing_reports_tab(self) -> None:
        """Refresh the unified Processing and Reports tab."""
        self._refresh_processing_reports_tab()

    def _refresh_processing_reports_tab(self) -> None:
        """
        Refresh processing reports tab (internal implementation).

        Updates the tree with current project data and report artifacts.
        """
        if not hasattr(self.gui, "processing_reports_widget"):
            return
        if not self.gui.processing_reports_widget:
            return

        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()

        # Build hierarchy
        # hierarchy = self.gui._build_report_hierarchy(all_videos, pm) # Legacy call
        hierarchy = self.gui.validation_manager._build_video_hierarchy_data(all_videos, "")

        # Clear existing metadata
        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = {}
        self.gui._processing_reports_tree_metadata.clear()

        # Update widget tree
        tree = self.gui.processing_reports_widget.tree
        if not tree:
            return

        # Clear tree
        for item in tree.get_children():
            tree.delete(item)

        # Populate tree
        self._populate_reports_tree_from_hierarchy(
            tree, hierarchy, "", self.gui._processing_reports_tree_metadata
        )

    def append_processing_reports_artifacts(
        self,
        tree,
        parent_id: str,
        results_dir: str,
        metadata_store: dict,
    ) -> None:
        """
        Append report artifacts to tree node.

        Args:
            tree: ttk.Treeview widget
            parent_id: Parent node ID
            results_dir: Results directory path
            metadata_store: Metadata storage dictionary
        """
        if not os.path.exists(results_dir):
            return

        # Look for report files
        for file in os.listdir(results_dir):
            if file.endswith((".docx", ".xlsx")):
                file_path = os.path.join(results_dir, file)
                item_id = self.gui.widget_factory.build_processing_report_artifact_id(
                    parent_id, file_path
                )

                # Determine icon based on file type
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

    def on_processing_reports_item_double_click(self, event=None) -> None:
        """
        Handle double-click on items in the Processing Reports tree.

        Args:
            event: Tkinter event object
        """
        if not self.gui.processing_reports_widget or not self.gui.processing_reports_widget.tree:
            return

        tree = self.gui.processing_reports_widget.tree

        # Get item at click position
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

        # Handle file nodes (docx/xlsx) - open them
        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        # Handle video nodes - open results folder
        if node_type == "video":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info("gui.open_results_folder", path=results_dir)
                try:
                    if os.name == "nt":  # Windows
                        os.startfile(results_dir)
                    elif os.name == "posix":  # macOS, Linux
                        subprocess.Popen(["xdg-open", results_dir])
                except Exception as e:
                    log.error("gui.open_results_folder.failed", error=str(e))
                    self.gui.show_error("Erro", f"Não foi possível abrir a pasta: {e}")

    def _handle_report_file_node(self, metadata: dict) -> None:
        """
        Handle opening of report file node.

        Args:
            metadata: Node metadata dictionary
        """
        file_path = metadata.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return

        log.info("gui.open_report_file", path=file_path)
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":  # macOS
                subprocess.Popen(["open", file_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", file_path])
        except Exception as e:
            log.error("gui.open_report_file.failed", error=str(e))
            self.gui.show_error("Erro", f"Não foi possível abrir o arquivo: {e}")

    def on_processing_reports_generate_partial(self) -> None:
        """Handle partial report generation from the unified tab."""
        from zebtrack.ui.events import Events

        if not self.gui.processing_reports_widget:
            return

        selection = self.gui.processing_reports_widget.get_selection()
        if not selection:
            return

        selected_videos = []
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
            self.gui.event_dispatcher.publish_event(
                Events.REPORT_GENERATE,
                {"videos": selected_videos, "report_type": "partial"},
            )

    def generate_partial_report(self) -> None:
        """Gather selected videos and generate a partial report from reports tree."""
        from zebtrack.ui.events import Events

        if not hasattr(self.gui, "reports_tree") or not self.gui.reports_tree:
            return

        selected_items = self.gui.reports_tree.selection()
        if not selected_items:
            return

        selected_videos = []
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
            self.gui.event_dispatcher.publish_event(
                Events.REPORT_GENERATE,
                {"videos": selected_videos, "report_type": "partial"},
            )

    # ===========================================================================
    # CATEGORIA 6: REPORTS TREE MANAGEMENT
    # ===========================================================================

    def update_reports_tree(self) -> None:
        """
        Update the reports tree view in ProcessingReportsWidget.

        This method refreshes the tree content based on current project state.
        """
        widget = getattr(self.gui, "processing_reports_widget", None)
        if not widget or not widget.tree:
            return

        # Clear existing items
        widget.clear_tree()

        # Get data
        project_manager = self.gui.controller.project_manager
        hierarchy = project_manager.get_video_hierarchy()
        status_counts = project_manager.get_status_counts()

        # Get or Initialize metadata store for this tree
        # We store it on the GUI instance to persist across refreshes,
        # matching pattern used in other trees
        if not hasattr(self.gui, "_processing_reports_tree_metadata"):
            self.gui._processing_reports_tree_metadata = {}

        # Clear metadata for fresh population
        self.gui._processing_reports_tree_metadata.clear()
        metadata_store = self.gui._processing_reports_tree_metadata

        # Populate tree
        self._populate_reports_tree_from_hierarchy(
            widget.tree,
            hierarchy,
            "",  # specific root if needed, else empty for actual root
            metadata_store
        )

        # Update status cards
        widget.update_status_counts(status_counts)

        log.debug("project_view_manager.reports_tree_updated")

    def _populate_reports_tree_from_hierarchy(
        self,
        tree,
        hierarchy: dict,
        parent: str,
        metadata_store: dict,
    ) -> None:
        """
        Populate reports tree from hierarchy data.

        Args:
            tree: ttk.Treeview widget
            hierarchy: Hierarchy data dictionary
            parent: Parent node ID
            metadata_store: Metadata storage dictionary
        """
        from zebtrack.ui.gui import STATUS_SYMBOLS

        # Iterate over groups
        for group_id, group_data in sorted(hierarchy.items()):
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

            # Iterate over days
            days = group_data.get("days", {})
            for day_id, videos in sorted(days.items()):
                # Fix: day_data (now videos) is a list of video entries, not a dict with 'display'
                # Derive day title from first video metadata if possible
                day_label = f"Dia {day_id}"
                if videos and isinstance(videos, list) and len(videos) > 0:
                     first_video = videos[0]
                     if isinstance(first_video, dict):
                         meta = first_video.get("metadata", {})
                         if meta and meta.get("day") is not None:
                             # Use ValidationManager logic or similar consistent formatting if available
                             # For now, simplistic fallback to match previous potential intent
                             day_val = meta.get("day")
                             day_label = f"{day_val:02d}" if isinstance(day_val, int) else str(day_val)
                         elif "day_label" in first_video:
                             day_label = first_video["day_label"]

                day_node_id = f"{group_node_id}_day_{day_id}"

                tree.insert(
                    group_node_id,
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

                # Iterate over videos
                # 'videos' is already the list of video dictionaries for this day
                for video in videos:
                    video_path = video.get("path") # Fixed: "path" not "video_path" usually
                    if not video_path:
                         video_path = video.get("video_path") # Try fallback
                    if not video_path:
                        continue

                    video_name = os.path.basename(video_path)
                    subject = video.get("metadata", {}).get("subject", "")
                    subject_label = f"Sujeito {subject}" if subject else video_name

                    # Build individual column values
                    col_arena = STATUS_SYMBOLS["arena"] if video.get("has_arena") else ""
                    col_rois = STATUS_SYMBOLS["rois"] if video.get("has_rois") else ""
                    col_traj = STATUS_SYMBOLS["trajectory"] if video.get("has_trajectory") else ""
                    col_summary = STATUS_SYMBOLS["summary"] if video.get("has_summary") else ""

                    # Determine status label
                    status_label = "Processado" if video.get("has_trajectory") else "Pendente"
                    if not video.get("has_arena"):
                         status_label = "Sem Arena"

                    video_node_id = f"{day_node_id}_video_{video_path}"

                    tree.insert(
                        day_node_id,
                        "end",
                        iid=video_node_id,
                        text=f"🐟 {subject_label}",
                        values=(col_arena, col_rois, col_traj, col_summary, status_label, video_path),
                    )

                    metadata_store[video_node_id] = {
                        "type": "video",
                        "video_path": video_path,
                        "results_dir": video.get("results_dir"),
                    }

                    # Append artifacts (docx, xlsx files)
                    # Use ProjectManager lookup for robustness if not in entry
                    results_dir = video.get("results_dir")
                    if not results_dir:
                         pm = self.gui.controller.project_manager
                         results_dir = pm.resolve_results_directory(
                            experiment_id=video.get("experiment_id") or video.get("metadata", {}).get("experiment_id"),
                            video_path=video_path,
                            metadata=video.get("metadata")
                         )
                         if isinstance(results_dir, Path):
                             results_dir = str(results_dir)

                    if results_dir and os.path.exists(results_dir):
                        self.append_processing_reports_artifacts(
                            tree, video_node_id, results_dir, metadata_store
                        )

    def append_report_artifacts(
        self, tree, parent_id: str, results_dir: str, metadata_store: dict
    ) -> None:
        """
        Append report artifacts (LEGACY name for backward compatibility).

        Args:
            tree: ttk.Treeview widget
            parent_id: Parent node ID
            results_dir: Results directory path
            metadata_store: Metadata storage dictionary
        """
        self.append_processing_reports_artifacts(tree, parent_id, results_dir, metadata_store)

    # ===========================================================================
    # CATEGORIA 7: EVENT HANDLERS
    # ===========================================================================

    def on_report_item_select(self, event=None) -> None:
        """Handle selection of report item."""
        log.warning(
            "project_view_manager.on_report_item_select_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ProcessingReportsWidget
        # Kept here for backward compatibility

    def on_report_item_double_click(self, event=None) -> None:
        """Handle double-click on report item."""
        log.warning(
            "project_view_manager.on_report_item_double_click_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )
        # This functionality has been moved to ProcessingReportsWidget
        # Kept here for backward compatibility

    def on_project_overview_tree_double_click(self, event=None) -> None:
        """
        Handle double-click on project overview tree.

        Args:
            event: Tkinter event object
        """
        self._on_project_overview_tree_double_click_impl(event)

    def _on_project_overview_tree_double_click_impl(self, event=None) -> None:
        """
        Implement double-click handler for project overview tree.

        Args:
            event: Tkinter event object
        """
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        tree = self.gui.project_overview_widget.tree
        if not tree:
            return

        # Get selected item
        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        # Get video path from tree metadata
        video_path = tree.set(item_id, "video_path")
        if not video_path:
            return

        # Open results folder if it exists
        pm = self.gui.controller.project_manager
        results_dir = pm.get_video_results_dir(video_path)

        if results_dir and os.path.exists(results_dir):
            log.info("gui.open_results_folder", path=results_dir)
            try:
                if os.name == "nt":  # Windows
                    os.startfile(results_dir)
                elif os.name == "posix":  # macOS, Linux
                    subprocess.Popen(["xdg-open", results_dir])
            except Exception as e:
                log.error("gui.open_results_folder.failed", error=str(e))
                self.gui.show_error("Erro", f"Não foi possível abrir a pasta: {e}")

    def on_project_overview_right_click(self, event=None) -> None:
        """
        Handle right-click on project overview tree.

        Args:
            event: Tkinter event object
        """
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        tree = self.gui.project_overview_widget.tree
        if not tree:
            return

        # Select item at cursor
        item_id = tree.identify_row(event.y)
        if item_id:
            tree.selection_set(item_id)
            self.gui.menu_manager.show_project_overview_context_menu(event)

    def update_delete_template_button_state(self) -> None:
        """Update state of delete template button."""
        # This method operates on zone controls, kept here for backward compatibility
        if not hasattr(self.gui, "delete_template_btn"):
            return

        has_selection = False
        if hasattr(self.gui, "roi_template_var"):
            current = self.gui.roi_template_var.get()
            has_selection = bool(current and current != "Nenhum")

        if hasattr(self.gui, "delete_template_btn"):
            state = "normal" if has_selection else "disabled"
            self.gui.delete_template_btn.config(state=state)

    def refresh_openvino_summary(self) -> None:
        """Refresh OpenVINO model summary display."""
        if not hasattr(self.gui, "_openvino_display_var"):
            return

        openvino_status = self.gui.controller.get_openvino_cache_status()
        self.gui._openvino_display_var.set(openvino_status)

    def append_report_artifacts_from_entry(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts (docx, xlsx) from video entry to reports tree."""
        from pathlib import Path

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

        docx_path = _resolve_artifact(
            parquet_files.get("report_docx"),
            "report.docx",
        )
        excel_path = _resolve_artifact(
            parquet_files.get("summary_excel"),
            "summary.xlsx",
        )

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

    def handle_report_video_node(self, metadata: dict) -> None:
        """Handle double-click on report video node - opens results directory."""
        import sys
        from pathlib import Path

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
            self.gui.show_warning(
                "Relatórios indisponíveis",
                ("Gere o relatório para este vídeo antes de abrir a pasta de resultados."),
            )
            return

        # Open directory in file explorer
        try:
            if sys.platform.startswith("win"):
                os.startfile(results_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{results_dir}"')
            else:  # Linux and other Unix-like systems
                os.system(f'xdg-open "{results_dir}"')
        except Exception as exc:
            log.error("project_view.open_explorer_failed", path=results_dir, error=str(exc))
            self.gui.show_error("Erro", f"Não foi possível abrir a pasta:\n{exc}")

    def handle_project_overview_double_click(self, item_id: str) -> None:
        """Implement double-click logic on project overview tree."""
        import os

        if not self.gui.project_overview_tree:
            return

        tags = self.gui.project_overview_tree.item(item_id, "tags") or ()
        if not tags:
            return

        video_path = tags[0]
        if not video_path or video_path.startswith("status_"):
            return

        if not os.path.exists(video_path):
            self.gui.show_warning(
                "Arquivo não encontrado",
                f"O vídeo selecionado não foi localizado:\n{video_path}",
            )
            return

        success = self.gui.canvas_manager.load_video_frame_to_canvas(video_path, frame_number=0)
        if success:
            self.gui._maybe_offer_zone_reuse(video_path)
            self.gui.canvas_manager.redraw_zones_from_project_data()
            message = f"Frame carregado: {os.path.basename(video_path)}"
            self.gui.set_status(message)
            self.gui._request_overview_refresh(reason=message, append_summary=True)
        else:
            self.gui.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

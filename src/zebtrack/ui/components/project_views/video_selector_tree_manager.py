"""Video Selector Tree Manager — Project overview, video selector, and batch operations.

Extracted from ProjectViewManager (Phase 4.6).  Owns every method that
populates the video-selector tree (Zone tab), the project-overview panel,
batch-processing triggers, and navigation helpers.

Cross-component calls:
    * self.gui.reports_tree_manager._refresh_processing_reports_tab()
      — called inside ``refresh_project_views`` to keep the reports tab in sync.
"""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
from collections import Counter
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui import payloads as payloads
from zebtrack.ui.components.project_views.project_view_helpers import (
    summarize_batch_data,
    video_sort_key,
)

if TYPE_CHECKING:
    from zebtrack.ui.components.dialog_manager import DialogManager

log = structlog.get_logger()


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class VideoSelectorTreeManager:
    """Manage the video-selector tree, project overview, and batch operations.

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
        self._overview_refresh_pending = False
        self._overview_refresh_after_id: str | None = None

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
        """Subscribe to Event Bus V2 events relevant to video selector / overview."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        assert self.event_bus_v2 is not None
        self.event_bus_v2.subscribe(
            UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
            self._on_video_tree_refresh_requested,
        )

        self.event_bus_v2.subscribe(
            UIEvents.UI_REQUEST_PROCESS_VIDEOS,
            self._on_request_process_videos,
        )

        self.event_bus_v2.subscribe(
            UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
            lambda d: self.refresh_project_views(
                reason=d.get("reason"),
                append_summary=d.get("append_summary", False),
                immediate=d.get("immediate", False),
            ),
        )

        self.event_bus_v2.subscribe(
            UIEvents.READINESS_SNAPSHOT_UPDATED,
            self._on_readiness_snapshot_updated,
        )

        self.event_bus_v2.subscribe(
            UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: self.on_video_hierarchy_snapshot_updated(d.get("snapshot", [])),
        )

        log.debug(
            "video_selector_tree_manager.event_subscriptions_setup",
            events=[
                "VIDEO_TREE_REFRESH_REQUESTED",
                "UI_REQUEST_PROCESS_VIDEOS",
                "PROJECT_VIEWS_REFRESH_REQUESTED",
                "READINESS_SNAPSHOT_UPDATED",
                "VIDEO_HIERARCHY_SNAPSHOT_UPDATED",
            ],
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_video_tree_refresh_requested(self, data: payloads.EventPayload) -> None:
        """Handle VIDEO_TREE_REFRESH_REQUESTED event."""
        filter_text = _payload_get(data, "filter_text")
        log.debug(
            "video_selector_tree_manager.video_tree_refresh_event_received",
            filter_text=filter_text,
        )
        self._populate_video_selector_tree(filter_text)

    def _on_request_process_videos(self, data: dict) -> None:
        """Handle UI request to process videos (Selection with Fallback).

        Called when users click "Process Video" in Analysis view.
        Attempts to process current selection; if none, processes all pending videos.
        """
        log.info("video_selector_tree_manager.request_process_videos")
        self.trigger_batch_trajectory_processing(fallback_to_pending=True)

    def _on_readiness_snapshot_updated(self, data: payloads.EventPayload) -> None:
        """Handle READINESS_SNAPSHOT_UPDATED event."""
        ready_with_trajectory = _payload_get(data, "ready_with_trajectory", [])
        ready_with_zones = _payload_get(data, "ready_with_zones", [])
        arena_only = _payload_get(data, "arena_only", [])
        without_arena = _payload_get(data, "without_arena", [])

        log.debug(
            "video_selector_tree_manager.readiness_snapshot_event_received",
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

    # ==================================================================
    # Navigation & Window Management
    # ==================================================================

    def update_window_title(self, project_name: str | None = None) -> None:
        """Update the window title with optional project name."""
        if project_name:
            self.gui.root.title(f"DRerio LogAI - {project_name}")
        else:
            self.gui.root.title("DRerio LogAI")

    def navigate_to_processing_reports_tab(self) -> None:
        """Navigate to the Processing and Reports tab."""
        if not self.gui.notebook:
            return

        tab_count = self.gui.notebook.index("end")
        for i in range(tab_count):
            tab_text = self.gui.notebook.tab(i, "text")
            if "Processamento e Relatórios" in tab_text:
                self.gui.notebook.select(i)
                return

        log.warning("gui.navigate.processing_reports_tab_not_found")

    # ==================================================================
    # Project Overview Management
    # ==================================================================

    def request_overview_refresh(
        self,
        reason: str | None = None,
        *,
        force: bool = False,
        debounce_ms: int = 300,
    ) -> None:
        """Request a debounced or forced overview refresh."""
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

        def _execute() -> None:
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
                "video_selector_tree_manager.refresh_project_views",
                reason=reason,
                append_summary=append_summary,
                immediate=immediate,
            )
            if append_summary and hasattr(self.gui, "set_status"):
                try:
                    self.gui.set_status(reason)
                except (tk.TclError, AttributeError):
                    log.warning("video_selector_tree_manager.refresh_project_views.status_failed")

        # Refresh project overview
        self._refresh_project_overview()

        # Refresh processing reports tab (cross-component call — public API)
        self.gui.reports_tree_manager.refresh_processing_reports_tab()

    def _refresh_project_overview(self) -> None:
        """Update the project overview panel with current project data."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        self._update_project_overview_summary()
        self._update_project_overview_tree()

        def _update_legend() -> None:
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

        status_counts: Counter[str] = Counter()
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

        self.gui.project_overview_widget.update_summary(status_counts)

    def _update_project_overview_tree(self) -> None:
        """Update the tree view in the project overview."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        if self.event_bus_v2:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED,
                    data={},
                    source="VideoSelectorTreeManager._update_project_overview_tree",
                )
            )
        else:
            self._build_video_hierarchy_snapshot()

    def _build_video_hierarchy_snapshot(self) -> list[dict]:
        """Build video hierarchy snapshot. Delegates to ValidationManager."""
        controller = getattr(self.gui, "controller", None)
        if not controller or not controller.project_manager:
            return []

        pm = controller.project_manager
        all_videos = pm.get_all_videos() or []

        if hasattr(self.gui, "validation_manager"):
            hierarchy_data = self.gui.validation_manager.prepare_overview_hierarchy_for_widget(
                all_videos
            )

            snapshot = hierarchy_data.get("groups", [])

            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
                        data={"snapshot": snapshot},
                        source="VideoSelectorTreeManager._build_video_hierarchy_snapshot",
                    )
                )
            return snapshot
        return []

    def on_video_hierarchy_snapshot_updated(self, snapshot: list[dict]) -> None:
        """Handle video hierarchy snapshot update event."""
        if not hasattr(self.gui, "project_overview_widget") or not self.gui.project_overview_widget:
            return
        self.gui.project_overview_widget.update_tree(snapshot)

    # ==================================================================
    # Zone Summary Cards
    # ==================================================================

    def update_zone_summary_cards(self) -> None:
        """Update zone summary cards with current project status."""
        if not hasattr(self.gui, "zone_summary_cards") or not self.gui.zone_summary_cards:
            return

        pm = self.gui.controller.project_manager
        all_videos = pm.get_all_videos()
        counts = summarize_batch_data(all_videos, pm)

        arena_pending = counts["total"] - counts["with_arena"]

        rois_needed = counts["with_arena"] - counts["with_rois"]
        rois_needed = max(0, rois_needed)

        if "arena_pending" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["arena_pending"].set(str(arena_pending))

        if "rois_pending" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["rois_pending"].set(str(rois_needed))

        if "ready_processing" in self.gui.zone_summary_cards:
            self.gui.zone_summary_cards["ready_processing"].set(str(counts["with_rois"]))

    # ==================================================================
    # Readiness Snapshot
    # ==================================================================

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

            if self.event_bus_v2:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.event_bus_v2.publish(
                    Event(
                        type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                        data={"filter_text": filter_text},
                        source="VideoSelectorTreeManager._build_readiness_snapshot",
                    )
                )
            else:
                self._populate_video_selector_tree(filter_text)

    # ==================================================================
    # Video Selector Tree Population
    # ==================================================================

    def _populate_video_selector_tree(self, filter_text: str | None = None) -> None:
        """Populate video selector tree with filtered videos."""
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
            except tk.TclError:
                selected_tag = None

        # Clear tree
        for item in tree.get_children():
            tree.delete(item)

        pm = getattr(self.gui.controller, "project_manager", None)
        if not pm:
            return

        try:
            all_videos = pm.get_all_videos()
        except (OSError, ValueError, KeyError) as e:
            log.warning("video_selector_tree_manager.get_all_videos.failed", error=str(e))
            all_videos = []

        if hasattr(self.gui, "validation_manager"):
            hierarchy = self.gui.validation_manager._build_video_hierarchy_data(
                all_videos, filter_text or ""
            )
        else:
            log.warning("video_selector_tree_manager.populate_tree.missing_validation_manager")
            return

        from zebtrack.ui.gui import STATUS_SYMBOLS

        for _group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            group_display = f"🏷️ {group_data['display']}"
            group_node = tree.insert("", "end", text=group_display, open=True)

            for day_id, videos in sorted(
                group_data["days"].items(),
                key=lambda item: video_sort_key(item[0]),
            ):
                sample_meta = videos[0].get("metadata") if videos else None
                day_title = self._build_day_title(day_id, sample_meta)
                day_node = tree.insert(group_node, "end", text=f"📅 {day_title}", open=True)

                for video_entry in sorted(
                    videos,
                    key=lambda entry: video_sort_key(entry.get("subject")),
                ):
                    subject_val = video_entry.get("subject")
                    subject_label = self.gui.validation_manager.format_subject_label(subject_val)

                    filename = video_entry.get("filename", "")
                    path = video_entry.get("path", "")

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

        if hasattr(zone_controls, "apply_video_tree_expand_state"):
            zone_controls.apply_video_tree_expand_state()

        if selected_tag:
            self._reselect_video_tree_item(tree, selected_tag)

    def _reselect_video_tree_item(self, tree: Any, target_tag: str) -> None:
        """Reselect an item in the tree by tag."""
        if not target_tag or not tree:
            return

        def _walk(node: str) -> bool:
            for child in tree.get_children(node):
                tags = tree.item(child, "tags")
                if tags and tags[0] == target_tag:
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

    # ==================================================================
    # Batch Processing Triggers
    # ==================================================================

    def trigger_batch_trajectory_processing(
        self, selection: Any | None = None, fallback_to_pending: bool = False
    ) -> None:
        """Trigger batch trajectory processing for selected or all videos."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        selections: list[str] = []
        if selection is not None:
            selections = self._resolve_processing_reports_video_paths(selection)
        else:
            selections = self.resolve_processing_reports_video_paths()

        if not selections:
            if fallback_to_pending:
                self.gui.event_dispatcher.publish_event(
                    UIEvents.PROJECT_PROCESS_VIDEOS, {"video_paths": None}
                )
                self.request_overview_refresh()
                self.gui.analysis_view_controller.switch_to_analysis_view()
                return

            self.dialog_manager.show_info(
                "Processamento",
                "Nenhum vídeo elegível foi encontrado ou selecionado.",
            )
            return

        unique_paths = list(dict.fromkeys(selections))
        log.info(
            "debug.batch_processing.deduplicated_paths",
            original_count=len(selections),
            unique_count=len(unique_paths),
            unique_paths=unique_paths,
        )

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_PROCESS_VIDEOS, {"video_paths": unique_paths}
        )
        self.request_overview_refresh()
        self.gui.analysis_view_controller.switch_to_analysis_view()

    def trigger_parquet_summaries(self) -> None:
        """Trigger export of parquet summaries for selected videos."""
        from zebtrack.ui.event_bus_v2 import UIEvents

        selections = self.resolve_processing_reports_video_paths()

        if not selections:
            self.dialog_manager.show_info(
                "Sumários",
                "Selecione ao menos um vídeo com trajetória para exportar o sumário.",
            )
            return

        unique_paths = list(dict.fromkeys(selections))

        self.gui.event_dispatcher.publish_event(
            UIEvents.PROJECT_GENERATE_SUMMARIES, {"video_paths": unique_paths}
        )
        self.refresh_project_views()

    # ==================================================================
    # Selection Resolution
    # ==================================================================

    def resolve_processing_reports_video_paths(self, selection: Any | None = None) -> list[str]:
        """Resolve selected video paths from ANY active tree (Reports or Overview)."""
        reports_paths: list[str] = []
        if hasattr(self.gui, "processing_reports_widget") and self.gui.processing_reports_widget:
            tree = self.gui.processing_reports_widget.tree
            if tree:
                selected = selection if selection is not None else tree.selection()
                log.warning("debug.reports_tree.selection", count=len(selected))
                for item_id in selected:
                    video_path = tree.set(item_id, "video_path")
                    if video_path and os.path.isfile(video_path):
                        reports_paths.append(video_path)

        if reports_paths:
            log.warning("debug.reports_tree.found", paths=reports_paths)
            return reports_paths

        log.warning("debug.fallback.project_overview")
        return self._resolve_selection_from_project_overview()

    def _resolve_processing_reports_video_paths(self, selection: tuple[str, ...]) -> list[str]:
        """Resolve selection item IDs to video paths, handling groups recursively."""
        if (
            not hasattr(self.gui, "processing_reports_widget")
            or not self.gui.processing_reports_widget
        ):
            return []

        tree = self.gui.processing_reports_widget.tree
        if not tree:
            return []

        paths: set[str] = set()

        def _collect(item_id: str) -> None:
            try:
                p = tree.set(item_id, "video_path")
                if p:
                    paths.add(p)
                else:
                    for child in tree.get_children(item_id):
                        _collect(child)
            except tk.TclError:
                log.debug(
                    "video_selector_tree_manager.collect_video_paths.suppressed",
                    exc_info=True,
                )

        for item in selection:
            _collect(item)

        return list(paths)

    def _resolve_selection_from_project_overview(self) -> list[str]:
        """Resolve selected video paths from Project Overview tree."""
        if not hasattr(self.gui, "project_overview_widget"):
            return []
        if not self.gui.project_overview_widget:
            return []

        tree = self.gui.project_overview_widget.tree
        if not tree:
            return []

        selection = tree.selection()
        video_paths: list[str] = []

        for item_id in selection:
            values = tree.item(item_id, "values")
            log.warning("debug.selection_resolution", item_id=item_id, values=values)

            if values and len(values) >= 6:
                path_candidate = values[5]
                if path_candidate and os.path.exists(path_candidate):
                    video_paths.append(path_candidate)
                    continue
                else:
                    log.warning("debug.selection.invalid_path", path=path_candidate)

            tags = tree.item(item_id, "tags")
            if tags:
                path_candidate = tags[0]
                if path_candidate and os.path.exists(path_candidate):
                    video_paths.append(path_candidate)
                    continue

        log.warning("debug.resolved_paths", count=len(video_paths), paths=video_paths)
        return video_paths

    # ==================================================================
    # Double-click & Context-menu Handlers
    # ==================================================================

    def on_project_overview_tree_double_click(self, event: Any | None = None) -> None:
        """Handle double-click on project overview tree."""
        self._on_project_overview_tree_double_click_impl(event)

    def _on_project_overview_tree_double_click_impl(self, event: Any | None = None) -> None:
        """Implement double-click handler for project overview tree."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        tree = self.gui.project_overview_widget.tree
        if not tree:
            return

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        video_path = tree.set(item_id, "video_path")
        if not video_path:
            return

        pm = self.gui.controller.project_manager
        results_dir = pm.get_video_results_dir(video_path)

        if results_dir and os.path.exists(results_dir):
            log.info("gui.open_results_folder", path=results_dir)
            try:
                if os.name == "nt":
                    startfile = getattr(os, "startfile", None)
                    if callable(startfile):
                        startfile(results_dir)
                    else:
                        raise OSError("startfile not available")
                elif os.name == "posix":
                    subprocess.Popen(["xdg-open", results_dir])
            except OSError as e:
                log.error("gui.open_results_folder.failed", error=str(e))
                self.dialog_manager.show_error("Erro", f"Não foi possível abrir a pasta: {e}")

    def on_project_overview_right_click(self, event: Any | None = None) -> None:
        """Handle right-click on project overview tree."""
        if not hasattr(self.gui, "project_overview_widget"):
            return
        if not self.gui.project_overview_widget:
            return

        tree = self.gui.project_overview_widget.tree
        if not tree:
            return
        if event is None:
            return

        item_id = tree.identify_row(event.y)
        if item_id:
            tree.selection_set(item_id)
            self.gui.menu_manager.show_project_overview_context_menu(event)

    def handle_project_overview_double_click(self, item_id: str) -> None:
        """Implement double-click logic on project overview tree."""
        if not self.gui.project_overview_tree:
            return

        tags = self.gui.project_overview_tree.item(item_id, "tags") or ()
        if not tags:
            return

        video_path = tags[0]
        if not video_path or video_path.startswith("status_"):
            return

        if not os.path.exists(video_path):
            self.dialog_manager.show_warning(
                "Arquivo não encontrado",
                f"O vídeo selecionado não foi localizado:\n{video_path}",
            )
            return

        success = self.gui.canvas_manager.load_video_frame_to_canvas(video_path, frame_number=0)
        if success:
            self.dialog_manager.offer_zone_reuse(video_path)
            self.gui.canvas_manager.redraw_zones_from_project_data()
            message = f"Frame carregado: {os.path.basename(video_path)}"
            self.gui.set_status(message)
            self.gui.video_selector_manager.request_overview_refresh(reason=message)
        else:
            self.dialog_manager.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

    # ==================================================================
    # Misc
    # ==================================================================

    def update_delete_template_button_state(self) -> None:
        """Update state of delete template button."""
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

    # ==================================================================
    # Legacy stubs
    # ==================================================================

    def populate_video_selector_tree(self, search_text: str = "") -> None:
        """Populate video selector tree (LEGACY stub)."""
        log.warning(
            "video_selector_tree_manager.populate_video_selector_tree_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )

    def refresh_video_selector_tree(self) -> None:
        """Refresh the video selector tree (LEGACY stub)."""
        log.warning(
            "video_selector_tree_manager.refresh_video_selector_tree_deprecated",
            message="This method is LEGACY and may be removed in future versions",
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _build_day_title(self, day_value: Any, metadata: dict | None = None) -> str:
        """Proxy to validation_manager._build_day_title."""
        return self.gui.validation_manager._build_day_title(day_value, metadata)

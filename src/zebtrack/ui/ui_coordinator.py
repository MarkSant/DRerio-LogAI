"""UICoordinator - Mediator pattern implementation for Event-Driven Architecture.

This module implements the UICoordinator class, which coordinates communication
and state synchronization between UI components via the Event Bus V2.

This is part of the v4.0 Event-Driven Architecture refactoring (PLANO_ACAO_V4.md - Track 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.components.canvas_manager import CanvasManager
    from zebtrack.ui.components.dialog_manager import DialogManager
    from zebtrack.ui.components.project_view_manager import ProjectViewManager
    from zebtrack.ui.components.state_synchronizer import StateSynchronizer
    from zebtrack.ui.components.validation_manager import ValidationManager

log = structlog.get_logger().bind(component="ui.ui_coordinator")


class UICoordinator:
    """Coordinates communication and state synchronization between UI components.

    **Pattern**: Mediator Pattern

    **Responsibilities**:
    - Subscribe to UI events from EventBusV2
    - Coordinate multi-component updates in response to events
    - Manage inter-component dependencies
    - Encapsulate complex UI workflows
    - Eliminate direct Component → GUI calls (replace with event-driven coordination)

    **Architecture Transformation**:

    Before (v3.0 - Facade with bidirectional dependencies):
    ```
    DialogManager ──> GUI.update_zone_listbox() ──> CanvasManager
         └──> GUI.refresh_project_views() ──> ProjectViewManager
         └──> GUI._validate_zones() ──> ValidationManager
    ```

    After (v4.0 - Event-Driven with Mediator):
    ```
    DialogManager ──> Event Bus ──> UICoordinator ──> CanvasManager
                                         └──> ProjectViewManager
                                         └──> ValidationManager
    ```

    **Benefits**:
    - Components are decoupled (no direct GUI dependencies)
    - Communication is centralized and auditable
    - Easier to test components in isolation
    - Easier to add new subscribers to events
    - Clear separation of concerns

    **Thread Safety**:
    - The UICoordinator runs on the main (UI) thread
    - All event handlers assume they are called on the main thread
    - If events are published from background threads, the EventBusV2
      executes handlers synchronously on that thread, so handlers must
      use `root.after(0, ...)` to dispatch UI updates to the main thread.
    """

    def __init__(
        self,
        event_bus: EventBusV2,
        *,
        canvas_manager: CanvasManager | None = None,
        validation_manager: ValidationManager | None = None,
        project_view_manager: ProjectViewManager | None = None,
        dialog_manager: DialogManager | None = None,
        state_synchronizer: StateSynchronizer | None = None,
        root=None,
    ) -> None:
        """Initialize the UICoordinator.

        Args:
            event_bus: The EventBusV2 instance for pub/sub communication.
            canvas_manager: Optional CanvasManager for canvas updates.
            validation_manager: Optional ValidationManager for validation.
            project_view_manager: Optional ProjectViewManager for project views.
            dialog_manager: Optional DialogManager for dialogs.
            state_synchronizer: Optional StateSynchronizer for status updates.
            root: Optional Tkinter root for thread-safe UI updates.
        """
        self.event_bus = event_bus
        self.canvas_manager = canvas_manager
        self.validation_manager = validation_manager
        self.project_view_manager = project_view_manager
        self.dialog_manager = dialog_manager
        self.state_synchronizer = state_synchronizer
        self.root = root

        # Statistics for monitoring
        self._events_handled = 0
        self._errors_count = 0

        # Setup subscriptions to all relevant events
        self._setup_subscriptions()

        log.info("ui_coordinator.initialized", subscriptions=self._count_subscriptions())

    def _count_subscriptions(self) -> int:
        """Count number of subscriptions setup."""
        # This is a rough count based on _setup_subscriptions method
        return 10  # Updated when adding more subscriptions

    def _setup_subscriptions(self) -> None:
        """Subscribe to all relevant UI events.

        This method sets up the event listeners for the UICoordinator.
        Each handler coordinates updates across multiple components.
        """
        # Zone & ROI Management Events
        self.event_bus.subscribe(UIEvents.ZONES_UPDATED, self._on_zones_updated)
        self.event_bus.subscribe(UIEvents.POLYGON_EDIT_REQUESTED, self._on_polygon_edit_requested)

        # Project & Video Management Events
        self.event_bus.subscribe(UIEvents.VIDEO_LOADED, self._on_video_loaded)
        self.event_bus.subscribe(
            UIEvents.VIDEO_TREE_REFRESH_REQUESTED, self._on_video_tree_refresh_requested
        )
        self.event_bus.subscribe(
            UIEvents.VIDEO_HIERARCHY_SNAPSHOT_REQUESTED,
            self._on_video_hierarchy_snapshot_requested,
        )
        self.event_bus.subscribe(
            UIEvents.READINESS_SNAPSHOT_UPDATED, self._on_readiness_snapshot_updated
        )
        self.event_bus.subscribe(
            UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED, self._on_project_views_refresh_requested
        )

        # Analysis & Processing Events
        self.event_bus.subscribe(
            UIEvents.PROCESSING_STATS_UPDATED, self._on_processing_stats_updated
        )
        self.event_bus.subscribe(UIEvents.SOCIAL_SUMMARY_UPDATED, self._on_social_summary_updated)
        self.event_bus.subscribe(
            UIEvents.ANALYSIS_TASK_STATUS_UPDATED, self._on_analysis_task_status_updated
        )

        # External Trigger Events
        self.event_bus.subscribe(UIEvents.EXTERNAL_TRIGGER_NOTICE, self._on_external_trigger_notice)
        self.event_bus.subscribe(
            UIEvents.EXTERNAL_TRIGGER_NOTICE_CLEARED, self._on_external_trigger_notice_cleared
        )

        log.debug("ui_coordinator.subscriptions_setup", count=self._count_subscriptions())

    # ===========================
    # Event Handlers (Workflows)
    # ===========================

    def _on_zones_updated(self, data: dict[str, Any]) -> None:
        """Handle ZONES_UPDATED event - coordinate UI updates.

        **Workflow 1: Zone Update Coordination**

        Publishers: DialogManager, PolygonDrawingService, ROITemplateManager,
                    ZoneControlBuilder, Renderer (5 publishers)

        Coordinates:
        1. Update canvas zone listbox
        2. Validate zones
        3. Refresh project views if needed
        4. Enable/disable ROI drawing button based on arena existence

        Args:
            data: Event payload containing:
                - zone_data: ZoneData | None - The updated zone data
        """
        self._events_handled += 1
        zone_data = data.get("zone_data")

        try:
            # 1. Update canvas zone listbox
            if self.canvas_manager:
                self._safe_ui_call(lambda: self.canvas_manager.update_zone_listbox(zone_data))
                self._safe_ui_call(lambda: self.canvas_manager.update_roi_button_state())
                log.debug(
                    "ui_coordinator.zones_updated.canvas_updated", has_zones=zone_data is not None
                )

            # 2. Validate zones (if validation manager is available)
            # Validation is handled during creation/editing or processing start.
            # No separate validate_zones method exists or is needed here.
            # if self.validation_manager and zone_data:
            #     self._safe_ui_call(lambda: self.validation_manager.validate_zones())
            #     log.debug("ui_coordinator.zones_updated.zones_validated")

            # 3. Refresh project views if needed
            if self.project_view_manager:
                self._safe_ui_call(
                    lambda: self.project_view_manager.request_overview_refresh(
                        reason="zones_updated"
                    )
                )
                log.debug("ui_coordinator.zones_updated.views_refreshed")

            log.info(
                "ui_coordinator.zones_updated.completed",
                has_zones=zone_data is not None,
                total_handled=self._events_handled,
            )

        except Exception as e:
            self._errors_count += 1
            log.exception(
                "ui_coordinator.zones_updated.error",
                error=str(e),
                errors_count=self._errors_count,
            )

    def _on_video_tree_refresh_requested(self, data: dict[str, Any]) -> None:
        """Handle VIDEO_TREE_REFRESH_REQUESTED event.

        **Workflow 2: Video Tree Refresh Coordination**

        Publishers: ZoneControlBuilder (2x), ProjectViewManager (3 publishers)

        Coordinates:
        1. Refresh video selector tree with filter
        2. Maintain selection if possible

        Args:
            data: Event payload containing:
                - filter_text: str | None - Filter string for the video tree
        """
        self._events_handled += 1
        filter_text = data.get("filter_text")

        try:
            if self.project_view_manager:
                self._safe_ui_call(
                    lambda: self.project_view_manager._populate_video_selector_tree(filter_text)
                )
                log.debug(
                    "ui_coordinator.video_tree_refresh.completed",
                    has_filter=filter_text is not None,
                )

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.video_tree_refresh.error", error=str(e))

    def _on_readiness_snapshot_updated(self, data: dict[str, Any]) -> None:
        """Handle READINESS_SNAPSHOT_UPDATED event.

        **Workflow 3: Readiness Snapshot Update Coordination**

        Publishers: DialogManager (after zone reuse operations)

        Coordinates:
        1. Apply video readiness snapshot to ProjectViewManager
        2. Update validation state if needed

        Args:
            data: Event payload containing:
                - ready_with_trajectory: list[dict]
                - ready_with_zones: list[dict]
                - arena_only: list[dict]
                - without_arena: list[dict]
        """
        self._events_handled += 1

        try:
            if self.project_view_manager:
                self._safe_ui_call(
                    lambda: self.project_view_manager.apply_pending_readiness_snapshot(
                        ready_with_trajectory=data.get("ready_with_trajectory", []),
                        ready_with_zones=data.get("ready_with_zones", []),
                        arena_only=data.get("arena_only", []),
                        without_arena=data.get("without_arena", []),
                    )
                )
                log.debug("ui_coordinator.readiness_snapshot.updated")

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.readiness_snapshot.error", error=str(e))

    def _on_polygon_edit_requested(self, data: dict[str, Any]) -> None:
        """Handle POLYGON_EDIT_REQUESTED event.

        **Workflow 4: Polygon Edit Setup Coordination**

        Publishers: CanvasManager (initiates editing)

        Coordinates:
        1. Setup interactive polygon editing in CanvasManager
        2. Update drawing state

        Args:
            data: Event payload containing:
                - polygon: np.ndarray - The polygon points to edit
        """
        self._events_handled += 1
        polygon = data.get("polygon")

        try:
            if self.canvas_manager and polygon is not None:
                self._safe_ui_call(lambda: self.canvas_manager.setup_interactive_polygon(polygon))
                log.debug("ui_coordinator.polygon_edit.setup_completed")

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.polygon_edit.error", error=str(e))

    def _on_video_hierarchy_snapshot_requested(self, data: dict[str, Any]) -> None:
        """Handle VIDEO_HIERARCHY_SNAPSHOT_REQUESTED event.

        **Workflow 5: Video Hierarchy Snapshot Build Coordination**

        Publishers: ProjectViewManager (self-contained update)

        Coordinates:
        1. Build video hierarchy snapshot
        2. Update internal state

        Args:
            data: Event payload (usually empty or with optional context)
        """
        self._events_handled += 1

        try:
            if self.project_view_manager:
                self._safe_ui_call(
                    lambda: self.project_view_manager._build_video_hierarchy_snapshot()
                )
                log.debug("ui_coordinator.video_hierarchy_snapshot.built")

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.video_hierarchy_snapshot.error", error=str(e))

    def _on_video_loaded(self, data: dict[str, Any]) -> None:
        """Handle VIDEO_LOADED event.

        **Workflow 6: Video Load Coordination**

        Publishers: CanvasManager, VideoDisplayWidget

        Coordinates:
        1. Load video frame to canvas
        2. Check for existing zones
        3. Offer zone reuse if no zones exist

        Args:
            data: Event payload containing:
                - video_path: str - Path to the loaded video
        """
        self._events_handled += 1
        video_path = data.get("video_path")

        try:
            # 1. Load frame to canvas
            if self.canvas_manager and video_path:
                self._safe_ui_call(lambda: self.canvas_manager.load_video_frame(video_path))
                log.debug("ui_coordinator.video_loaded.frame_loaded", video_path=video_path)

            # 2. Check for existing zones and offer reuse
            if (
                self.validation_manager
                and self.dialog_manager
                and video_path
                and not self.validation_manager.has_zones(video_path)
            ):
                self._safe_ui_call(lambda: self.dialog_manager.offer_zone_reuse(video_path))
                log.debug("ui_coordinator.video_loaded.zone_reuse_offered")

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.video_loaded.error", error=str(e))

    def _on_project_views_refresh_requested(self, data: dict[str, Any]) -> None:
        """Handle PROJECT_VIEWS_REFRESH_REQUESTED event.

        **Workflow 7: Project Views Refresh Coordination**

        Publishers: Various components that trigger project view updates

        Coordinates:
        1. Refresh project overview
        2. Refresh processing reports
        3. Update statistics

        Args:
            data: Event payload containing:
                - reason: str | None - Reason for refresh
                - append_summary: bool - Whether to append summary
                - immediate: bool - Whether to refresh immediately
        """
        self._events_handled += 1

        try:
            if self.project_view_manager:
                reason = data.get("reason")
                append_summary = data.get("append_summary", False)
                immediate = data.get("immediate", False)

                self._safe_ui_call(
                    lambda: self.project_view_manager.refresh_project_views(
                        reason=reason, append_summary=append_summary, immediate=immediate
                    )
                )
                log.debug("ui_coordinator.project_views_refresh.completed", reason=reason)

        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.project_views_refresh.error", error=str(e))

    def _on_processing_stats_updated(self, data: dict[str, Any]) -> None:
        """Handle PROCESSING_STATS_UPDATED event."""
        self._events_handled += 1
        try:
            if self.state_synchronizer:
                self._safe_ui_call(lambda: self.state_synchronizer.update_processing_stats(**data))
        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.processing_stats_updated.error", error=str(e))

    def _on_social_summary_updated(self, data: dict[str, Any]) -> None:
        """Handle SOCIAL_SUMMARY_UPDATED event."""
        self._events_handled += 1
        try:
            if self.state_synchronizer:
                self._safe_ui_call(lambda: self.state_synchronizer.update_social_summary(**data))
        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.social_summary_updated.error", error=str(e))

    def _on_analysis_task_status_updated(self, data: dict[str, Any]) -> None:
        """Handle ANALYSIS_TASK_STATUS_UPDATED event."""
        self._events_handled += 1
        try:
            if self.state_synchronizer:
                self._safe_ui_call(
                    lambda: self.state_synchronizer.update_analysis_task_status(**data)
                )
        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.analysis_task_status_updated.error", error=str(e))

    def _on_external_trigger_notice(self, data: dict[str, Any]) -> None:
        """Handle EXTERNAL_TRIGGER_NOTICE event."""
        self._events_handled += 1
        try:
            if self.dialog_manager:
                self._safe_ui_call(
                    lambda: self.dialog_manager.show_external_trigger_notice(
                        data.get("session_label", ""), **data
                    )
                )
        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.external_trigger_notice.error", error=str(e))

    def _on_external_trigger_notice_cleared(self, data: dict[str, Any]) -> None:
        """Handle EXTERNAL_TRIGGER_NOTICE_CLEARED event."""
        self._events_handled += 1
        try:
            if self.dialog_manager:
                self._safe_ui_call(lambda: self.dialog_manager.clear_external_trigger_notice())
        except Exception as e:
            self._errors_count += 1
            log.exception("ui_coordinator.external_trigger_notice_cleared.error", error=str(e))

    # ===========================
    # Helper Methods
    # ===========================

    def _safe_ui_call(self, func: callable) -> None:
        """Execute a UI update safely on the main thread.

        If self.root is available and we're not on the main thread,
        schedule the call with root.after(0, ...). Otherwise, call directly.

        Args:
            func: The callable to execute (should be a lambda or method reference)
        """
        if self.root:
            # Always use root.after for thread safety, even if on main thread
            # This ensures consistency and avoids race conditions
            self.root.after(0, func)
        else:
            # No root available, call directly (e.g., in tests)
            func()

    def get_statistics(self) -> dict[str, int]:
        """Get coordinator statistics for monitoring and debugging.

        Returns:
            dict with keys:
                - events_handled: Total number of events processed
                - errors_count: Number of errors encountered
        """
        return {
            "events_handled": self._events_handled,
            "errors_count": self._errors_count,
        }

    def reset_statistics(self) -> None:
        """Reset coordinator statistics (useful for testing)."""
        self._events_handled = 0
        self._errors_count = 0

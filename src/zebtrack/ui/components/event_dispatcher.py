"""Event dispatching for ApplicationGUI.

Extracted from gui.py to reduce God Object complexity.
Handles event bus integration, event handlers, and event routing.
"""

from tkinter import filedialog, messagebox
from typing import Any

import numpy as np
import structlog

from zebtrack.ui.dialogs import ManageWeightsDialog
from zebtrack.ui.event_bus import CallableEvent, EventType, NamedEvent
from zebtrack.ui.events import Events

log = structlog.get_logger()


class EventDispatcher:
    """Manages event handling and dispatching for ApplicationGUI.

    This class extracts event bus integration logic from ApplicationGUI,
    including subscription management, event handlers, and event polling.
    """

    def __init__(self, gui):
        """Initialize EventDispatcher.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui
        self._event_bus_handlers = {}

    # =========================================================================
    # Event Bus Subscription
    # =========================================================================

    def subscribe_to_ui_events(self) -> None:
        """Subscribe to events published by the MainViewModel for UI updates."""
        if not self.gui.event_bus:
            return

        # A mapping from event names to their handler methods in the GUI
        ui_event_handlers = {
            # Basic UI feedback
            Events.UI_SET_STATUS: self._handle_set_status,
            Events.UI_SHOW_ERROR: self._handle_show_error,
            Events.UI_SHOW_WARNING: self._handle_show_warning,
            Events.UI_SHOW_INFO: self._handle_show_info,
            Events.UI_UPDATE_BUTTON_STATE: self._handle_update_button_state,
            # Navigation and view updates
            Events.UI_NAVIGATE_TO_WELCOME: self._handle_navigate_to_welcome,
            Events.UI_NAVIGATE_TO_PROJECT_VIEW: self._handle_navigate_to_project_view,
            Events.UI_NAVIGATE_TO_ANALYSIS_VIEW: self._handle_navigate_to_analysis_view,
            Events.UI_REFRESH_PROJECT_VIEWS: self._handle_refresh_project_views,
            Events.UI_SELECT_TAB: self._handle_select_tab,
            # Model and weight management
            Events.UI_UPDATE_WEIGHTS_LIST: self._handle_update_weights_list,
            Events.UI_SET_ACTIVE_WEIGHT: self._handle_set_active_weight,
            Events.UI_UPDATE_OPENVINO_CHECKBOX: self._handle_update_openvino_checkbox,
            Events.UI_UPDATE_OPENVINO_STATUS: self._handle_update_openvino_status,
            # Zone and drawing management
            Events.UI_REDRAW_ZONES: self._handle_redraw_zones,
            Events.UI_UPDATE_ZONE_LIST: self._handle_update_zone_list,
            Events.UI_SETUP_INTERACTIVE_POLYGON: self._handle_setup_interactive_polygon,
            # Frame and overlay display
            Events.UI_DISPLAY_VIDEO_FRAME: self._handle_display_video_frame,
            Events.UI_DISPLAY_FRAME: self._handle_display_frame,
            Events.UI_UPDATE_DETECTION_OVERLAY: self._handle_update_detection_overlay,
            # Live recording and Arduino
            Events.UI_UPDATE_ARDUINO_STATUS: self._handle_update_arduino_status,
            Events.UI_APPEND_ARDUINO_LOG: self._handle_append_arduino_log,
            Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE: self._handle_show_external_trigger_notice,
            Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE: self._handle_clear_external_trigger_notice,
            # Analysis and processing
            Events.UI_UPDATE_PROCESSING_MODE: self._handle_update_processing_mode,
            Events.UI_UPDATE_PROCESSING_STATS: self._handle_update_processing_stats,
            Events.UI_UPDATE_ANALYSIS_METADATA: self._handle_update_analysis_metadata,
            Events.UI_UPDATE_ANALYSIS_TASK_STATUS: self._handle_update_analysis_task_status,
            Events.UI_UPDATE_SOCIAL_SUMMARY: self._handle_update_social_summary,
            Events.UI_REQUEST_WEIGHT_FILE: self._handle_request_weight_file,
            Events.UI_REQUEST_WEIGHT_TYPE: self._handle_request_weight_type,
            Events.UI_REQUEST_WEIGHT_ACTION: self._handle_request_weight_action,
            Events.UI_OPEN_MANAGE_WEIGHTS_DIALOG: self._handle_open_manage_weights_dialog,
        }

        for event_name, handler in ui_event_handlers.items():
            self.gui.event_bus.subscribe(event_name, handler)

    def subscribe_zone_component_events(self):
        """Subscribe to events emitted by ZoneControlsWidget.

        This method connects component events to existing ApplicationGUI handlers,
        maintaining backward compatibility while using the new component architecture.
        """
        if not self.gui.event_bus:
            return

        # Drawing action events
        self.gui.event_bus.subscribe(
            "zone.toggle_view", lambda data: self.gui._toggle_canvas_view()
        )
        self.gui.event_bus.subscribe(
            "zone.draw_arena", lambda data: self.gui._start_main_arena_drawing()
        )
        self.gui.event_bus.subscribe("zone.draw_roi", lambda data: self.gui._start_roi_drawing())
        self.gui.event_bus.subscribe("zone.save_arena", lambda data: self.gui._on_save_arena())
        self.gui.event_bus.subscribe(
            "zone.discard_arena", lambda data: self.gui._on_discard_arena()
        )

        # ROI template events
        self.gui.event_bus.subscribe(
            "zone.template_apply", lambda data: self.gui._on_apply_roi_template()
        )
        self.gui.event_bus.subscribe(
            "zone.template_save", lambda data: self.gui._on_save_roi_template()
        )
        self.gui.event_bus.subscribe(
            "zone.template_import", lambda data: self.gui._on_import_roi_template()
        )

        # Zone list interaction events
        self.gui.event_bus.subscribe(
            "zone.list_item_double_click", lambda data: self.gui._edit_selected_zone_vertices()
        )
        self.gui.event_bus.subscribe(
            "zone.list_item_right_click",
            lambda data: self.gui._on_zone_right_click(self._create_mock_event(data)),
        )

        # Video selector events
        self.gui.event_bus.subscribe(
            "zone.video_double_click", lambda data: self.gui._load_selected_video_frame()
        )
        self.gui.event_bus.subscribe(
            "zone.video_frame_load", lambda data: self.gui._load_selected_video_frame()
        )
        self.gui.event_bus.subscribe(
            "zone.video_refresh", lambda data: self.gui._refresh_video_selector_tree()
        )
        # Note: zone.video_search_changed is handled differently (continuous filtering),
        # so it's not subscribed here - the component handles it internally

        self.gui.event_bus.subscribe(
            "zone.auto_detect_clicked", self._handle_zone_auto_detect_event
        )

    # =========================================================================
    # UI Event Handlers
    # =========================================================================

    def _handle_request_weight_file(self, data: dict) -> None:
        """Handle the request to open a file dialog for selecting a weight file."""
        filepath = filedialog.askopenfilename(
            title="Selecione o arquivo de peso do modelo (.pt)",
            filetypes=[("PyTorch Model", "*.pt"), ("All files", "*.*")],
        )
        if filepath:
            # Publish event back to view model with the selected file path
            self.publish_event(Events.MODEL_LOAD_NEW_WEIGHT, {"filepath": filepath})

    def _handle_request_weight_type(self, data: dict) -> None:
        """Handle the request to ask the user for the weight type."""
        weight_type = self.gui._prompt_for_weight_type()
        if weight_type:
            self.publish_event(Events.MODEL_LOAD_NEW_WEIGHT, {"weight_type": weight_type})

    def _handle_request_weight_action(self, data: dict) -> None:
        """Handle the request to ask the user what to do with the new weight."""
        weight_type = data.get("weight_type", "desconhecido")
        response = messagebox.askyesnocancel(
            "Adicionar Novo Peso",
            f"O modelo foi identificado como do tipo '{weight_type}'.\n\n"
            "Deseja definir este como o novo padrão para este tipo?\n\n"
            "• Sim: Define como novo padrão.\n"
            "• Não: Adiciona como uma opção alternativa.\n"
            "• Cancelar: Não adiciona o peso.",
        )
        choice = "cancel"
        if response is True:
            choice = "yes"
        elif response is False:
            choice = "no"

        self.publish_event(Events.MODEL_LOAD_NEW_WEIGHT, {"choice": choice})

    def _handle_open_manage_weights_dialog(self, data: dict) -> None:
        """Open the weight management dialog."""
        ManageWeightsDialog(self.gui.root, self.gui.controller)

    def _handle_set_status(self, data: dict) -> None:
        """Update status bar message."""
        self.gui.set_status(data.get("message", ""))
        self.gui.update_idletasks()

    def _handle_navigate_to_welcome(self, data: dict) -> None:
        """Navigate to welcome screen."""
        self.gui._create_welcome_frame()

    def _handle_navigate_to_project_view(self, data: dict) -> None:
        """Navigate to project view."""
        self.gui._load_project_view()

    def _handle_navigate_to_analysis_view(self, data: dict) -> None:
        """Navigate to analysis view."""
        activate_mode = data.get("activate_mode", True)
        if activate_mode:
            self.gui.start_analysis_view_mode()
        else:
            self.gui._switch_to_analysis_view()

    def _handle_select_tab(self, data: dict) -> None:
        """Select a specific tab in the notebook."""
        tab_name = data.get("tab_name")
        if tab_name == "zone_tab" and self.gui.zone_tab_frame:
            self.gui.notebook.select(self.gui.zone_tab_frame)

    def _handle_update_weights_list(self, data: dict) -> None:
        """Update the weights dropdown list."""
        self.gui.update_weights_dropdown(data.get("weights", []))

    def _handle_set_active_weight(self, data: dict) -> None:
        """Set the active weight in the dropdown."""
        self.gui.set_active_weight_in_dropdown(data.get("weight_name"))

    def _handle_update_openvino_checkbox(self, data: dict) -> None:
        """Update OpenVINO checkbox state."""
        self.gui.update_openvino_checkbox(data.get("is_checked", False))

    def _handle_redraw_zones(self, data: dict) -> None:
        """Redraw zones on canvas.

        Phase 4: Pass zone_data from event instead of pulling from controller.
        """
        self.gui.redraw_zones_from_project_data(data.get("zone_data"))

    def _handle_update_zone_list(self, data: dict) -> None:
        """Update zone list widget.

        Phase 4: Pass zone_data from event instead of pulling from controller.
        """
        self.gui.update_zone_listbox(data.get("zone_data"))

    def _handle_display_frame(self, data: dict) -> None:
        """Display a frame on the canvas."""
        frame = data.get("frame")
        self.gui.display_frame(frame)

    def _handle_update_detection_overlay(self, data: dict) -> None:
        """Update detection overlay on canvas."""
        detections = data.get("detections")
        report = data.get("report")
        self.gui.update_detection_overlay(detections, report)

    def _handle_show_external_trigger_notice(self, data: dict) -> None:
        """Show external trigger notice."""
        self.gui.show_external_trigger_notice(**data)

    def _handle_clear_external_trigger_notice(self, data: dict) -> None:
        """Clear external trigger notice."""
        self.gui.clear_external_trigger_notice()

    def _handle_update_processing_stats(self, data: dict) -> None:
        """Update processing statistics display."""
        stats = data.get("stats", {})
        # Map stats to the parameters expected by update_progress_stats
        self.gui.update_progress_stats(
            total=stats.get("total_frames"),
            processed=stats.get("processed_frames"),
            detected=stats.get("detected_frames"),
            percent=stats.get("percent"),
            elapsed=stats.get("elapsed"),
            eta=stats.get("eta"),
        )

    def _handle_update_analysis_metadata(self, data: dict) -> None:
        """Update analysis metadata display."""
        self.gui.update_analysis_metadata(**data)

    def _handle_update_analysis_task_status(self, data: dict) -> None:
        """Update analysis task status."""
        self.gui.update_analysis_task_status(**data.get("payload", {}))

    def _handle_update_social_summary(self, data: dict) -> None:
        """Update social summary display."""
        self.gui.update_social_summary(**data)

    def _handle_show_error(self, data: dict) -> None:
        """Show error message dialog."""
        self.gui.show_error(data.get("title", "Erro"), data.get("message", ""))

    def _handle_show_warning(self, data: dict) -> None:
        """Show warning message dialog."""
        self.gui.show_warning(data.get("title", "Aviso"), data.get("message", ""))

    def _handle_show_info(self, data: dict) -> None:
        """Show info message dialog."""
        self.gui.show_info(data.get("title", "Informação"), data.get("message", ""))

    def _handle_update_button_state(self, data: dict) -> None:
        """Update button state (enabled/disabled)."""
        self.gui.update_button_state(data.get("button_name"), data.get("state"))

    def _handle_refresh_project_views(self, data: dict) -> None:
        """Refresh project views."""
        self.gui.refresh_project_views(
            reason=data.get("reason"),
            append_summary=data.get("append_summary", False),
            immediate=data.get("immediate", False),
        )

    def _handle_update_arduino_status(self, data: dict) -> None:
        """Update Arduino connection status."""
        if self.gui.arduino_dashboard_widget:
            self.gui.arduino_dashboard_widget.update_status(data.get("connected"), data.get("port"))

    def _handle_append_arduino_log(self, data: dict) -> None:
        """Append message to Arduino log."""
        if self.gui.arduino_dashboard_widget:
            self.gui.arduino_dashboard_widget.append_log(data.get("message", ""))

    def _handle_update_openvino_status(self, data: dict) -> None:
        """Update OpenVINO status display."""
        self.gui.update_openvino_status_display(data.get("status", ""))

    def _handle_setup_interactive_polygon(self, data: dict) -> None:
        """Set up interactive polygon editing."""
        polygon = data.get("polygon")
        if polygon is not None:
            self.gui.setup_interactive_polygon(np.array(polygon))

    def _handle_display_video_frame(self, data: dict) -> None:
        """Display video frame from path."""
        self.gui.display_roi_video_frame(data.get("video_path"))

    def _handle_update_processing_mode(self, data: dict) -> None:
        """Update processing mode display."""
        self.gui.update_processing_mode(data.get("report"))

    def _handle_project_refresh_requested(self, data: dict) -> None:
        """Handle refresh request from ProjectOverviewWidget."""
        self.gui._request_overview_refresh(immediate=True)

    def _handle_project_video_double_click(self, data: dict) -> None:
        """Handle video double-click from ProjectOverviewWidget."""
        item_id = data.get("item_id")
        if item_id:
            self.gui._on_project_overview_tree_double_click_impl(item_id)

    def _handle_project_video_right_click(self, data: dict) -> None:
        """Handle video right-click from ProjectOverviewWidget."""
        item_id = data.get("item_id")
        x = data.get("x")
        y = data.get("y")
        if item_id and x is not None and y is not None:
            self.gui._show_project_overview_context_menu(item_id, x, y)

    def _handle_zone_auto_detect_event(self, data: dict | None) -> None:
        """Proxy auto-detect requests coming from the ZoneControlsWidget."""
        frames_value = None
        if data:
            frames_value = data.get("stabilization_frames")
        self.gui._on_auto_detect_clicked(stabilization_frames=frames_value)

    # =========================================================================
    # Event Bus Coordination
    # =========================================================================

    def register_event_bus_handlers(self) -> None:
        """Register handlers for different event types."""
        self._event_bus_handlers = {
            EventType.CALLABLE: self._handle_callable_event,
            EventType.NAMED: self._handle_named_event,
        }

    def _handle_callable_event(self, payload: CallableEvent) -> None:
        """Execute a callable event.

        Args:
            payload: CallableEvent containing the function to execute
        """
        try:
            payload.execute()
        except Exception:
            log.warning("gui.event_bus.callable_failed", exc_info=True)

    def _handle_named_event(self, payload: NamedEvent) -> None:
        """Dispatch named events to controller subscribers.

        Args:
            payload: NamedEvent containing event name and data
        """
        log.info("gui.handle_named_event.called", event_name=payload.event_name)
        try:
            if self.gui.event_bus:
                self.gui.event_bus.dispatch_named_event(payload)
        except Exception:
            log.warning(
                "gui.event_bus.named_event_failed",
                event_name=payload.event_name,
                exc_info=True,
            )

    def publish_event(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        """Publish a named event to the controller via the event bus.

        Falls back to direct controller method call if event bus is not available.

        Args:
            event_name: Name of the event (from Events class)
            data: Optional event data dictionary
        """
        if self.gui.event_bus:
            self.gui.event_bus.publish_event(event_name, data or {})
        else:
            # Fallback to direct controller call (backward compatibility)
            # This path is only used when event bus is disabled
            log.debug("gui.publish_event.no_bus", event_name=event_name)

    def schedule_event_bus_poll(self) -> None:
        """Schedule the next event bus poll cycle."""
        log.debug(
            "gui.event_bus.schedule_poll.called",
            has_bus=self.gui.event_bus is not None,
            has_after_id=self.gui._event_bus_after_id is not None,
        )
        if self.gui.event_bus is None:
            log.warning("gui.event_bus.schedule_poll.no_bus")
            return
        if self.gui._event_bus_after_id is None:
            self.gui._event_bus_after_id = self.gui.root.after(
                self.gui._event_bus_poll_interval_ms,
                self.poll_event_bus,
            )
            log.debug(
                "gui.event_bus.schedule_poll.scheduled", after_id=self.gui._event_bus_after_id
            )
        else:
            log.debug(
                "gui.event_bus.schedule_poll.already_scheduled",
                after_id=self.gui._event_bus_after_id,
            )

    def poll_event_bus(self) -> None:
        """Poll the event bus for pending events and dispatch them.

        This method runs periodically on the Tkinter main thread,
        processing events from the event bus queue.
        """
        self.gui._event_bus_after_id = None
        if self.gui.event_bus is None:
            log.warning("gui.event_bus.poll_no_bus")
            return

        queue_size = self.gui.event_bus.size()
        if queue_size > 0:
            log.debug("gui.event_bus.poll_queue_size", size=queue_size)

        events = self.gui.event_bus.drain(max_items=50)
        if events:
            log.debug("gui.event_bus.polling", event_count=len(events))

        processed = 0
        for event in events:
            # Use the EventType handlers to dispatch CALLABLE and NAMED events
            handler = self._event_bus_handlers.get(event.type)
            if handler is None:
                log.warning(
                    "gui.event_bus.unhandled_event_type",
                    event_type=event.type.name,
                )
                continue
            try:
                handler(event.payload)
                processed += 1
            except Exception:
                log.warning(
                    "gui.event_bus.handler_error",
                    event_type=event.type.name,
                    exc_info=True,
                )

        if processed:
            log.debug("gui.event_bus.processed", count=processed)

        log.info("gui.event_bus.poll_complete", will_reschedule=True)
        self.schedule_event_bus_poll()

    def stop_event_bus_polling(self) -> None:
        """Stop the event bus polling cycle.

        Cancels any scheduled poll operations.
        """
        if self.gui._event_bus_after_id is not None:
            try:
                self.gui.root.after_cancel(self.gui._event_bus_after_id)
            except Exception:
                log.warning("gui.event_bus.stop_failed", exc_info=True)
            finally:
                self.gui._event_bus_after_id = None

    # =========================================================================
    # Video Analysis Workflows
    # =========================================================================

    def handle_analyze_single_video_clicked(self) -> None:
        """Handle the UI part of the single video workflow."""
        from zebtrack.ui.dialogs import SingleVideoConfigDialog
        from zebtrack.ui.events import Events

        dialog = SingleVideoConfigDialog(self.gui.root, settings_obj=self.gui.controller.settings)
        if not dialog.result:
            return  # User cancelled

        source_type = dialog.result.get("source_type", "video")

        if source_type == "camera":
            # Camera analysis: Pass complete configuration to respect all settings
            # (camera_index, analysis_interval_frames, display_interval_frames, etc.)
            config = dialog.result
            self.gui.controller.live_camera_coordinator.start_session_from_config(config)
            return

        # Video file analysis: require video_path
        video_path = dialog.result.get("video_path")
        if not video_path:
            return

        # Pass both config and video path to the controller via event
        self.publish_event(
            Events.VIDEO_ANALYZE_SINGLE,
            {
                "video_path": video_path,
                "config": dialog.result,
            },
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _create_mock_event(self, data: dict):
        """Create a mock event object for backward compatibility with old event handlers.

        Args:
            data: Dictionary containing event data with 'x' and 'y' coordinates

        Returns:
            MockEvent object with coordinate attributes
        """

        class MockEvent:
            def __init__(self, data, zone_listbox):
                self.x_root = data.get("x", 0)
                self.y_root = data.get("y", 0)
                # Convert root coordinates to widget-relative coordinates
                if zone_listbox and "x" in data and "y" in data:
                    self.x = data["x"] - zone_listbox.winfo_rootx()
                    self.y = data["y"] - zone_listbox.winfo_rooty()
                else:
                    self.x = 0
                    self.y = 0

        return MockEvent(data, self.gui.zone_listbox)

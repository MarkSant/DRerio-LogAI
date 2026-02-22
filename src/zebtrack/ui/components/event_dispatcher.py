"""Dispatcher de eventos para roteamento de eventos do EventBusV2.

Handles both Core-side dispatching (routing commands to orchestrators)
and UI-side dispatching (routing UI updates to widgets).
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI
else:
    ApplicationGUI = Any

log = structlog.get_logger()


class EventDispatcher:
    """Dispatcher for routing EventBusV2 events to appropriate handlers.

    Adapts to both MainViewModel (Core) and ApplicationGUI (UI) usage.
    """

    # Parameter passing modes
    MODE_NO_PARAMS = "no_params"
    MODE_KWARGS_ALL = "kwargs_all"
    MODE_KWARGS_GET = "kwargs_get"
    MODE_POSITIONAL = "positional"
    MODE_POSITIONAL_OPTIONAL = "positional_optional"

    def __init__(self, context: "EventBusV2 | ApplicationGUI | None"):
        """Initialize the event dispatcher.

        Args:
            context: Can be an EventBusV2 instance (Core usage)
                     or ApplicationGUI (UI usage).
        """
        self.log = structlog.get_logger()
        self.handlers: dict[UIEvents | str, Callable] = {}

        # Detect context type
        self.gui: ApplicationGUI | None = None
        self.event_bus: EventBusV2 | None = None

        if context is None:
            self.event_bus = None
        elif hasattr(context, "subscribe") and callable(getattr(context, "subscribe", None)):
            # Context behaves like EventBusV2 (preferred branch to keep mocks working)
            self.event_bus = cast(EventBusV2, context)
        elif hasattr(context, "event_bus"):
            # Context is likely ApplicationGUI
            self.gui = cast(ApplicationGUI, context)
            self.event_bus = cast(EventBusV2 | None, getattr(context, "event_bus", None))
        else:
            # Fallback/Unknown - treat as raw event bus reference
            self.event_bus = cast(EventBusV2, context)

    def _require_gui(self) -> "ApplicationGUI":
        if self.gui is None:
            raise RuntimeError("EventDispatcher requires ApplicationGUI context for UI events.")
        return self.gui

    # --- Core Dispatching Methods (Used by MainViewModel) ---

    def register_handler(
        self,
        event_name: UIEvents,
        handler: Callable,
        param_names: list[str] | None = None,
        mode: str = MODE_NO_PARAMS,
    ) -> None:
        """Register a handler for a specific event."""
        if not self.event_bus:
            self.log.warning("event_dispatcher.no_event_bus", event_name=event_name)
            return

        dispatcher = self._create_dispatcher(handler, param_names, mode)
        self.event_bus.subscribe(event_name, dispatcher)
        self.handlers[event_name] = dispatcher

    def _create_dispatcher(
        self,
        handler: Callable,
        param_names: list[str] | None,
        mode: str,
    ) -> Callable:
        """Create dispatcher function that adapts event data for the handler."""

        def dispatcher(data: dict) -> None:
            try:
                if mode == self.MODE_NO_PARAMS:
                    handler()
                elif mode == self.MODE_KWARGS_ALL:
                    handler(**data)
                elif mode == self.MODE_KWARGS_GET:
                    kwargs = {param: data.get(param) for param in (param_names or [])}
                    handler(**kwargs)
                elif mode == self.MODE_POSITIONAL:
                    args = [data[param] for param in (param_names or [])]
                    handler(*args)
                elif mode == self.MODE_POSITIONAL_OPTIONAL:
                    args = [data.get(param) for param in (param_names or [])]
                    handler(*args)
            except Exception as e:
                self.log.error("event_dispatcher.handler_error", error=str(e), mode=mode)

        return dispatcher

    def register_direct_handler(self, event_name: UIEvents, handler: Callable) -> None:
        """Register a direct handler (no parameter adaptation)."""
        if not self.event_bus:
            return
        self.event_bus.subscribe(event_name, handler)
        self.handlers[event_name] = handler

    def unregister_handler(self, event_name: UIEvents) -> None:
        """Remove a previously registered handler, if it exists."""
        dispatcher = self.handlers.pop(event_name, None)
        if not dispatcher or not self.event_bus:
            return

        unsubscribe = getattr(self.event_bus, "unsubscribe", None)
        if callable(unsubscribe):
            try:
                unsubscribe(event_name, dispatcher)
            except Exception as exc:  # pragma: no cover - defensive
                self.log.warning(
                    "event_dispatcher.unsubscribe_failed",
                    event_name=event_name,
                    error=str(exc),
                )

    def get_registered_count(self) -> int:
        """Return the total number of handlers currently registered."""
        return len(self.handlers)

    # --- UI Dispatching Methods (Used by ApplicationGUI) ---

    def register_event_bus_handlers(self) -> None:
        """Register handlers specific to the GUI instance."""
        if not self.gui or not self.event_bus:
            return

        event_bus = self.event_bus

        # Handlers that need access to GUI instance
        # Example: self.gui.update_status(...)
        event_bus.subscribe(
            UIEvents.UI_SETUP_INTERACTIVE_POLYGON,
            lambda data: self._handle_setup_interactive_polygon(
                data.get("polygon") if isinstance(data, dict) else None
            ),
        )

    def subscribe_to_ui_events(self) -> None:
        """Subscribe to UI-related events."""
        if not self.gui or not self.event_bus:
            return

        gui = self._require_gui()
        event_bus = self.event_bus

        # Import UIEvents to use constants

        # Navigation & Lifecycle
        event_bus.subscribe(
            UIEvents.UI_NAVIGATE_TO_WELCOME, lambda d: gui.widget_factory.create_welcome_frame()
        )

        event_bus.subscribe(
            UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW,
            lambda d: gui.project_initializer.create_main_control_frame(),
        )

        event_bus.subscribe(
            UIEvents.PROJECT_CLOSED,
            lambda d: gui.state_synchronizer._destroy_notebook_and_main_controls(),
        )

        # Generic UI updates
        event_bus.subscribe(
            UIEvents.UI_SHOW_INFO,
            lambda d: gui.dialog_manager.show_info(
                d.get("title", "Info") if isinstance(d, dict) else "Info",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_SHOW_WARNING,
            lambda d: gui.dialog_manager.show_warning(
                d.get("title", "Aviso") if isinstance(d, dict) else "Aviso",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_SHOW_ERROR,
            lambda d: gui.dialog_manager.show_error(
                d.get("title", "Erro") if isinstance(d, dict) else "Erro",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )

        # External Triggers
        event_bus.subscribe(
            UIEvents.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
            lambda d: gui.dialog_manager.show_external_trigger_notice(
                d.get("session_label", "") if isinstance(d, dict) else "",
                **(
                    {k: v for k, v in d.items() if k != "session_label"}
                    if isinstance(d, dict)
                    else {}
                ),
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE,
            lambda d: gui.dialog_manager.clear_external_trigger_notice(),
        )

        # Status updates
        event_bus.subscribe(
            UIEvents.UI_SET_STATUS,
            lambda d: gui.status_var.set(d.get("message", "") if isinstance(d, dict) else ""),
        )

        # View navigation
        event_bus.subscribe(
            UIEvents.UI_SELECT_TAB,
            lambda d: gui.notebook.select(
                getattr(gui, f"{d.get('tab_name') if isinstance(d, dict) else ''}_frame", 0)
            )
            if gui.notebook
            else None,
        )

        # Single video zone setup (Decoupling from MainViewModel)
        event_bus.subscribe(
            UIEvents.SETUP_ZONE_DEFINITION_FOR_SINGLE_VIDEO,
            self._handle_setup_zone_definition_for_single_video,
        )

        # Analysis Updates
        event_bus.subscribe(
            UIEvents.UI_UPDATE_PROCESSING_STATS,
            lambda d: gui.state_synchronizer.update_processing_stats(
                **d.get("stats", {}) if isinstance(d, dict) else {}
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ANALYSIS_METADATA,
            lambda d: gui.analysis_view_controller.update_analysis_metadata(
                metadata=d.get("metadata") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_SOCIAL_SUMMARY,
            lambda d: gui.state_synchronizer.update_social_summary(
                **d if isinstance(d, dict) else {}
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            lambda d: gui.state_synchronizer.update_analysis_task_status(
                **d.get("payload", {}) if isinstance(d, dict) else {}
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_DETECTION_OVERLAY,
            lambda d: gui.analysis_view_controller.update_detection_overlay(
                detections=d.get("detections") if isinstance(d, dict) else None,
                report=d.get("report") if isinstance(d, dict) else None,
            ),
        )

        # Project View Updates
        event_bus.subscribe(
            UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: gui.video_selector_manager.on_video_hierarchy_snapshot_updated(
                d.get("snapshot", []) if isinstance(d, dict) else []
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_REFRESH_PROJECT_VIEWS,
            lambda d: gui.video_selector_manager.refresh_project_views(
                reason=d.get("reason") if isinstance(d, dict) else None,
                append_summary=d.get("append_summary", False) if isinstance(d, dict) else False,
                immediate=d.get("immediate", False) if isinstance(d, dict) else False,
            ),
        )

        # Weight Management
        event_bus.subscribe(
            UIEvents.UI_SET_ACTIVE_WEIGHT,
            lambda d: gui.weight_hardware_manager.set_active_weight_in_dropdown(
                d.get("weight_name") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_OPENVINO_STATUS,
            lambda d: gui.weight_hardware_manager.update_openvino_status_display(
                str(d.get("status")) if isinstance(d, dict) and d.get("status") else "Unknown"
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
            lambda d: gui.weight_hardware_manager.update_openvino_checkbox(
                bool(d.get("is_checked")) if isinstance(d, dict) else False
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_WEIGHTS_LIST,
            lambda d: gui.weight_hardware_manager.update_weights_dropdown(
                list(d.get("weights", [])) if isinstance(d, dict) else []
            ),
        )

        # Arduino / Hardware
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ARDUINO_STATUS,
            lambda d: gui.arduino_dashboard_widget.update_status(
                bool(d.get("connected")) if isinstance(d, dict) else False,
                str(d.get("port")) if isinstance(d, dict) and d.get("port") else None,
            )
            if gui.arduino_dashboard_widget
            else None,
        )
        event_bus.subscribe(
            UIEvents.UI_APPEND_ARDUINO_LOG,
            lambda d: gui.arduino_dashboard_widget.append_log(
                str(d.get("message") or "") if isinstance(d, dict) else ""
            )
            if gui.arduino_dashboard_widget
            else None,
        )

        # View Navigation & Modes
        def _handle_navigate_to_analysis(d):
            log.info("event_dispatcher.navigate_to_analysis_view.received")
            gui.analysis_view_controller.start_analysis_view_mode()

        log.info(
            "event_dispatcher.subscribing_navigation",
            event_name=UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW,
            event_bus_id=id(event_bus),
        )
        event_bus.subscribe(UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW, _handle_navigate_to_analysis)
        event_bus.subscribe(
            UIEvents.UI_NAVIGATE_FROM_ANALYSIS_VIEW,
            lambda d: gui.analysis_view_controller.stop_analysis_view_mode(),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_PROCESSING_MODE,
            self._handle_update_processing_mode,
        )

        # General UI
        event_bus.subscribe(
            UIEvents.UI_UPDATE_BUTTON_STATE,
            lambda d: gui.update_button_state(
                d.get("button_name") if isinstance(d, dict) else None,
                d.get("state") if isinstance(d, dict) else None,
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_DISPLAY_FRAME,
            lambda d: gui.canvas_manager.update_video_frame(
                d.get("frame") if isinstance(d, dict) else None,  # type: ignore[arg-type]  # frame is Any from dict
                d.get("detections") if isinstance(d, dict) else None,
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_DISPLAY_VIDEO_FRAME,
            lambda d: gui.canvas_manager.display_roi_video_frame(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )

        # Zone Updates
        event_bus.subscribe(
            UIEvents.UI_REDRAW_ZONES,
            lambda d: gui.canvas_manager.redraw_zones_from_project_data(
                d.get("zone_data") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ZONE_LIST, lambda d: gui.canvas_manager.update_zone_listbox()
        )

        # Weight Management Interactive Requests
        event_bus.subscribe(
            UIEvents.UI_REQUEST_WEIGHT_TYPE,
            lambda d: gui.weight_hardware_manager.handle_request_weight_type(
                str(d.get("filepath")) if isinstance(d, dict) and d.get("filepath") else ""
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_REQUEST_WEIGHT_ACTION,
            lambda d: gui.weight_hardware_manager.handle_request_weight_action(
                str(d.get("filepath")) if isinstance(d, dict) and d.get("filepath") else "",
                str(d.get("weight_type")) if isinstance(d, dict) and d.get("weight_type") else "",
            ),
        )

    def _handle_update_processing_mode(self, data: dict) -> None:
        """Handle UI_UPDATE_PROCESSING_MODE event.

        Expected payload: {"report": ProcessingReport}
        """
        if not self.gui or not isinstance(data, dict):
            return

        gui = self._require_gui()
        report = data.get("report")
        gui.state_synchronizer.update_processing_mode(report)

    def _handle_setup_interactive_polygon(self, polygon_data) -> None:
        """Handle legacy interactive polygon requests from the event bus."""
        if not self.gui:
            return

        gui = self._require_gui()
        polygon = polygon_data if polygon_data is not None else []

        import numpy as np

        polygon_array = np.array(polygon, dtype=float)
        gui.canvas_manager.setup_interactive_polygon(polygon_array)

    def _handle_setup_zone_definition_for_single_video(self, data: dict) -> None:
        """Handler for single video zone setup event."""
        if not isinstance(data, dict):
            self.log.warning(
                "event_dispatcher._handle_setup_zone_definition_for_single_video.invalid_data_type",
                data_type=type(data).__name__,
            )
            return
        self.log.info(
            "event_dispatcher._handle_setup_zone_definition_for_single_video.called",
            has_gui=bool(self.gui),
            video_path=data.get("video_path"),
        )
        if not self.gui:
            self.log.error("event_dispatcher._handle_setup_zone_definition_for_single_video.no_gui")
            return
        gui = self._require_gui()
        video_path = data.get("video_path")
        config = data.get("config")
        if video_path and config:
            if hasattr(gui, "single_video_workflow"):
                self.log.info(
                    "event_dispatcher._handle_setup_zone_definition_for_single_video.calling_gui_method"
                )
                gui.single_video_workflow.setup_zone_definition_for_single_video(video_path, config)
            else:
                self.log.error(
                    "gui.missing_method", method="setup_zone_definition_for_single_video"
                )
        else:
            self.log.error(
                "event_dispatcher._handle_setup_zone_definition_for_single_video.missing_data",
                has_video_path=bool(video_path),
                has_config=bool(config),
            )

    def subscribe_zone_component_events(self) -> None:
        """Subscribe to events emitted by ZoneControlsWidget."""
        if not self.gui or not self.event_bus:
            return

        gui = self._require_gui()
        event_bus = self.event_bus

        # Drawing Actions
        event_bus.subscribe(
            UIEvents.ZONE_AUTO_DETECT_CLICKED,
            lambda d: gui.single_video_workflow.on_auto_detect_clicked(
                stabilization_frames=d.get("stabilization_frames") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.ZONE_DRAW_ARENA, lambda d: gui.canvas_manager.start_main_arena_drawing()
        )
        event_bus.subscribe(
            UIEvents.ZONE_DRAW_ROI, lambda d: gui.canvas_manager.start_roi_drawing()
        )
        event_bus.subscribe(
            UIEvents.ZONE_TOGGLE_VIEW,
            lambda d: gui.analysis_view_controller.toggle_canvas_view(),
        )

        # ROI Templates
        event_bus.subscribe(
            UIEvents.ZONE_TEMPLATE_APPLY,
            lambda d: gui._on_apply_roi_template(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_TEMPLATE_SAVE,
            lambda d: gui.roi_template_manager.save_template(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_TEMPLATE_IMPORT,
            lambda d: gui.dialog_manager.import_and_apply_roi_template(),
        )

        def _clear_applied_templates(d: dict) -> None:
            gui.roi_template_manager.clear_applied_template_drawings()

        event_bus.subscribe(
            UIEvents.ZONE_TEMPLATE_CLEAR_APPLIED,
            _clear_applied_templates,
        )

        # Video Selector
        event_bus.subscribe(
            UIEvents.ZONE_VIDEO_SEARCH_CHANGED,
            lambda d: gui._filter_video_tree(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_VIDEO_REFRESH,
            lambda d: gui.video_selector_manager._populate_video_selector_tree(filter_text=None),
        )
        event_bus.subscribe(
            UIEvents.ZONE_VIDEO_DOUBLE_CLICK,
            lambda d: gui.canvas_manager.load_selected_video_frame(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_VIDEO_FRAME_LOAD,
            lambda d: gui.canvas_manager.load_selected_video_frame(),
        )

        # Zone List
        event_bus.subscribe(
            UIEvents.ZONE_AQUARIUM_SELECTED,
            lambda d: gui.canvas_manager.update_zone_listbox(),
        )
        # Processing mode change (parallel vs sequential for multi-aquarium)
        event_bus.subscribe(
            UIEvents.ZONE_PROCESSING_MODE_CHANGED,
            lambda d: gui.canvas_manager.update_processing_mode(
                d.get("sequential", False) if isinstance(d, dict) else False
            ),
        )
        event_bus.subscribe(
            UIEvents.ZONE_LIST_ITEM_DOUBLE_CLICK,
            lambda d: gui.canvas_manager.edit_selected_zone_vertices(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_LIST_ITEM_RIGHT_CLICK,
            lambda d: gui.menu_manager.show_roi_context_menu(
                x=d.get("x") if isinstance(d, dict) else 0,
                y=d.get("y") if isinstance(d, dict) else 0,
                item_id=d.get("item_id") if isinstance(d, dict) else None,
            ),
        )

        # Interactive Editing
        event_bus.subscribe(UIEvents.ZONE_SAVE_ARENA, lambda d: gui.canvas_manager.save_arena())
        event_bus.subscribe(
            UIEvents.ZONE_DISCARD_ARENA, lambda d: gui.canvas_manager.discard_arena()
        )
        event_bus.subscribe(
            UIEvents.ZONE_FINISH_DRAWING,
            lambda d: gui.canvas_manager.event_handler.on_canvas_double_click(None),
        )
        event_bus.subscribe(
            UIEvents.ZONE_CONCLUDE_VIDEO,
            lambda d: gui.zone_control_builder._on_conclude_video(),
        )

        # Zone Context Menu Actions (Copy/Paste/Delete)
        event_bus.subscribe(
            UIEvents.ZONE_COPY_ZONES,
            lambda d: gui.canvas_manager.copy_zones_from_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.ZONE_PASTE_ZONES,
            lambda d: gui.canvas_manager.paste_zones_to_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )
        event_bus.subscribe(
            UIEvents.ZONE_DELETE_ZONES,
            lambda d: gui.canvas_manager.delete_zones_from_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )

        # Multi-Aquarium Success
        event_bus.subscribe(
            UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS,
            lambda d: gui.canvas_manager.on_multi_auto_detect_success(
                d if isinstance(d, dict) else {}
            ),
        )

        # Multi-Aquarium Assignment Dialog (Triggered by CanvasManager)
        event_bus.subscribe(
            UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
            self._on_show_aquarium_assignment_dialog,
        )

        # ROI Settings
        event_bus.subscribe(
            UIEvents.DETECTOR_UPDATE_PARAMETERS,
            lambda d: gui._on_apply_roi_settings(d if isinstance(d, dict) else {}),
        )

    def _on_show_aquarium_assignment_dialog(self, data: dict) -> None:
        """Handle ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG event.

        Opens the assignment dialog and publishes completion event if confirmed.
        """
        print("[DIAGNOSTIC] _on_show_aquarium_assignment_dialog called")
        print(f"[DIAGNOSTIC] data={data}")

        if not self.gui or not isinstance(data, dict):
            print("[DIAGNOSTIC] returning early - no gui or not dict")
            return

        gui = self._require_gui()

        video_path = data.get("video_path")
        print(f"[DIAGNOSTIC] video_path={video_path}")

        self.log.info(
            "aquarium_assignment_dialog.showing",
            video_path=video_path,
            available_groups=data.get("available_groups", []),
        )

        print("[DIAGNOSTIC] calling dialog_manager.show_aquarium_assignment_dialog")
        configs, apply_to_all = gui.dialog_manager.show_aquarium_assignment_dialog(
            available_groups=data.get("available_groups", []),
            video_path=video_path,
            multi_aquarium_config=data.get("multi_aquarium_config"),
        )
        print(f"[DIAGNOSTIC] dialog returned configs={configs}, apply_to_all={apply_to_all}")

        self.log.info(
            "aquarium_assignment_dialog.result",
            has_configs=bool(configs),
            apply_to_all=apply_to_all,
            video_path=video_path,
        )

        if configs:
            # Convert AquariumConfig objects to dicts for serialization
            configs_as_dicts = []
            for c in configs:
                if hasattr(c, "model_dump"):
                    # Pydantic v2
                    configs_as_dicts.append(c.model_dump())
                elif hasattr(c, "dict"):
                    # Pydantic v1
                    configs_as_dicts.append(c.dict())
                elif isinstance(c, dict):
                    configs_as_dicts.append(c)
                else:
                    # Fallback: convert attributes manually
                    configs_as_dicts.append(
                        {
                            "aquarium_id": getattr(c, "aquarium_id", 0),
                            "group": getattr(c, "group", ""),
                            "subject_id": getattr(c, "subject_id", ""),
                            "day": getattr(c, "day", "1"),
                        }
                    )

            self.log.info(
                "aquarium_assignment_dialog.publishing_completion",
                video_path=video_path,
                configs_count=len(configs_as_dicts),
            )

            self.publish_event(
                UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
                {
                    "video_path": video_path,
                    "configs": configs_as_dicts,
                    "apply_to_all": apply_to_all,
                },
            )

    # --- High-Level UI Action Handlers ---

    def publish_event(self, event_type: UIEvents, data: dict | None = None) -> bool:
        """Publish an event through the event bus.

        Args:
            event_type: UIEvents enum member identifying the event.
            data: Optional dictionary with event data.

        Returns:
            True if event was successfully published, False otherwise.
        """
        if not self.validate_event_payload(event_type, data or {}):
            return False

        if not self.event_bus:
            return False

        self.event_bus.publish(Event(type=event_type, data=data or {}))
        return True

    def validate_event_payload(self, event_type: UIEvents, data: dict) -> bool:
        """Validate the payload for specific events to ensure contract integrity.

        Args:
            event_type: UIEvents enum member identifying the event.
            data: Payload data.

        Returns:
            True if valid, False otherwise.
        """
        if event_type == UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED:
            if not isinstance(data.get("configs"), list):
                self.log.error("event_validation.configs_not_list", event=event_type)
                return False
            if "video_path" not in data:
                self.log.error("event_validation.missing_video_path", event=event_type)
                return False
        elif event_type == UIEvents.ZONE_AQUARIUM_SELECTED:
            if not isinstance(data.get("aquarium_id"), int):
                self.log.error("event_validation.aquarium_id_not_int", event=event_type)
                return False
        elif event_type == UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS:
            if not isinstance(data.get("polygons"), list):
                self.log.error("event_validation.polygons_not_list", event=event_type)
                return False
        return True

    def handle_analyze_single_video_clicked(self) -> None:
        """Handle the 'Analyze Single Video' action.

        Opens the SingleVideoConfigDialog to configure analysis parameters,
        then publishes the VIDEO_ANALYZE_SINGLE event with the configuration.
        """
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.START")

        if not self.gui:
            self.log.error("event_dispatcher.handle_analyze_single_video_clicked.no_gui")
            return

        gui = self._require_gui()

        # Import the dialog
        from zebtrack.ui.dialogs import SingleVideoConfigDialog

        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.dialog_imported")

        # Get settings from controller
        settings = None
        if hasattr(gui, "controller") and gui.controller:
            settings = getattr(gui.controller, "settings", None)
        self.log.info(
            "event_dispatcher.handle_analyze_single_video_clicked.settings_retrieved",
            has_settings=bool(settings),
        )

        # Open configuration dialog
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.opening_dialog")
        dialog = SingleVideoConfigDialog(gui.root, settings_obj=settings)
        self.log.info(
            "event_dispatcher.handle_analyze_single_video_clicked.dialog_closed",
            has_result=bool(dialog.result),
        )

        if not dialog.result:
            self.log.info("event_dispatcher.handle_analyze_single_video_clicked.user_cancelled")
            return  # User cancelled

        # Get configuration from dialog
        config = dialog.result
        video_path = config.get("video_path")
        self.log.info(
            "event_dispatcher.handle_analyze_single_video_clicked.config_retrieved",
            video_path=video_path,
            has_config=bool(config),
        )

        if not video_path:
            self.log.warning("event_dispatcher.handle_analyze_single_video_clicked.no_video_path")
            return

        # Publish the event for single video analysis with full configuration
        self.log.info(
            "event_dispatcher.handle_analyze_single_video_clicked.publishing_event",
            event_name=UIEvents.VIDEO_ANALYZE_SINGLE,
            video_path=video_path,
        )
        self.publish_event(
            UIEvents.VIDEO_ANALYZE_SINGLE, {"video_path": video_path, "config": config}
        )
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.event_published")

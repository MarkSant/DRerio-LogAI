"""Dispatcher de eventos para roteamento de eventos do EventBus.

Handles both Core-side dispatching (routing commands to orchestrators)
and UI-side dispatching (routing UI updates to widgets).
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui.event_bus import EventType
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.ui.components.event_bus import EventBus
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class EventDispatcher:
    """Dispatcher para rotear eventos do EventBus para handlers apropriados.

    Adapta-se tanto ao uso no MainViewModel (Core) quanto na ApplicationGUI (UI).
    """

    # Modos de passagem de parâmetros
    MODE_NO_PARAMS = "no_params"
    MODE_KWARGS_ALL = "kwargs_all"
    MODE_KWARGS_GET = "kwargs_get"
    MODE_POSITIONAL = "positional"
    MODE_POSITIONAL_OPTIONAL = "positional_optional"

    def __init__(self, context: "EventBus | ApplicationGUI | None"):
        """Inicializa o dispatcher de eventos.

        Args:
            context: Pode ser uma instância de EventBus (Core usage)
                     ou ApplicationGUI (UI usage).
        """
        self.log = structlog.get_logger()
        self.handlers: dict[str, Callable] = {}

        # Detect context type
        self.gui: ApplicationGUI | None = None
        self.event_bus: EventBus | None = None

        if context is None:
            self.event_bus = None
        elif hasattr(context, "subscribe") and callable(getattr(context, "subscribe", None)):
            # Context behaves like EventBus (preferred branch to keep mocks working)
            self.event_bus = context
        elif hasattr(context, "event_bus"):
            # Context is likely ApplicationGUI
            self.gui = context
            self.event_bus = getattr(context, "event_bus", None)
        else:
            # Fallback/Unknown - treat as raw event bus reference
            self.event_bus = context

    # --- Core Dispatching Methods (Used by MainViewModel) ---

    def register_handler(
        self,
        event_name: str,
        handler: Callable,
        param_names: list[str] | None = None,
        mode: str = MODE_NO_PARAMS,
    ) -> None:
        """Registra um handler para um evento específico."""
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
        """Cria função dispatcher que adapta event data para handler."""

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

    def register_direct_handler(self, event_name: str, handler: Callable) -> None:
        """Registra handler direto (sem adaptação de parâmetros)."""
        if not self.event_bus:
            return
        self.event_bus.subscribe(event_name, handler)
        self.handlers[event_name] = handler

    def unregister_handler(self, event_name: str) -> None:
        """Remove handler registrado anteriormente, se existir."""
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

        # Handlers that need access to GUI instance
        # Example: self.gui.update_status(...)
        self.event_bus.subscribe(
            Events.UI_SETUP_INTERACTIVE_POLYGON,
            lambda data: self._handle_setup_interactive_polygon(
                data.get("polygon") if isinstance(data, dict) else None
            ),
        )

    def subscribe_to_ui_events(self) -> None:
        """Subscribe to UI-related events."""
        if not self.gui or not self.event_bus:
            return

        # Import UIEvents to use constants

        # Navigation & Lifecycle
        self.event_bus.subscribe(
            Events.UI_NAVIGATE_TO_WELCOME, lambda d: self.gui.widget_factory.create_welcome_frame()
        )

        self.event_bus.subscribe(
            Events.UI_NAVIGATE_TO_PROJECT_VIEW,
            lambda d: self.gui._create_main_control_frame(),
        )

        self.event_bus.subscribe(
            "project:closed",
            lambda d: self.gui.state_synchronizer._destroy_notebook_and_main_controls(),
        )

        # Generic UI updates
        self.event_bus.subscribe(
            Events.UI_SHOW_INFO,
            lambda d: self.gui.dialog_manager.show_info(
                d.get("title", "Info") if isinstance(d, dict) else "Info",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )
        self.event_bus.subscribe(
            Events.UI_SHOW_WARNING,
            lambda d: self.gui.dialog_manager.show_warning(
                d.get("title", "Aviso") if isinstance(d, dict) else "Aviso",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )
        self.event_bus.subscribe(
            Events.UI_SHOW_ERROR,
            lambda d: self.gui.dialog_manager.show_error(
                d.get("title", "Erro") if isinstance(d, dict) else "Erro",
                d.get("message", "") if isinstance(d, dict) else "",
            ),
        )

        # External Triggers
        self.event_bus.subscribe(
            Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
            lambda d: self.gui.dialog_manager.show_external_trigger_notice(
                d.get("session_label", "") if isinstance(d, dict) else "",
                **(
                    {k: v for k, v in d.items() if k != "session_label"}
                    if isinstance(d, dict)
                    else {}
                ),
            ),
        )
        self.event_bus.subscribe(
            Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE,
            lambda d: self.gui.dialog_manager.clear_external_trigger_notice(),
        )

        # Status updates
        self.event_bus.subscribe(
            Events.UI_SET_STATUS,
            lambda d: self.gui.status_var.set(d.get("message", "") if isinstance(d, dict) else ""),
        )

        # View navigation
        self.event_bus.subscribe(
            Events.UI_SELECT_TAB,
            lambda d: self.gui.notebook.select(
                getattr(self.gui, f"{d.get('tab_name') if isinstance(d, dict) else ''}_frame", 0)
            )
            if self.gui and self.gui.notebook
            else None,
        )

        # Single video zone setup (Decoupling from MainViewModel)
        self.event_bus.subscribe(
            "ui:setup_zone_definition_for_single_video",
            self._handle_setup_zone_definition_for_single_video,
        )

        # Analysis Updates
        self.event_bus.subscribe(
            Events.UI_UPDATE_PROCESSING_STATS,
            lambda d: self.gui.state_synchronizer.update_processing_stats(
                **d.get("stats", {}) if isinstance(d, dict) else {}
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_SOCIAL_SUMMARY,
            lambda d: self.gui.state_synchronizer.update_social_summary(
                **d if isinstance(d, dict) else {}
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
            lambda d: self.gui.state_synchronizer.update_analysis_task_status(
                **d.get("payload", {}) if isinstance(d, dict) else {}
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_DETECTION_OVERLAY,
            lambda d: self.gui.update_detection_overlay(
                detections=d.get("detections") if isinstance(d, dict) else None,
                report=d.get("report") if isinstance(d, dict) else None,
            ),
        )

        # Project View Updates
        self.event_bus.subscribe(
            Events.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: self.gui.project_view_manager.on_video_hierarchy_snapshot_updated(
                d.get("snapshot", []) if isinstance(d, dict) else []
            ),
        )
        self.event_bus.subscribe(
            Events.UI_REFRESH_PROJECT_VIEWS,
            lambda d: self.gui.project_view_manager.refresh_project_views(
                reason=d.get("reason") if isinstance(d, dict) else None,
                append_summary=d.get("append_summary", False) if isinstance(d, dict) else False,
                immediate=d.get("immediate", False) if isinstance(d, dict) else False,
            ),
        )

        # Weight Management
        self.event_bus.subscribe(
            Events.UI_SET_ACTIVE_WEIGHT,
            lambda d: self.gui.set_active_weight_in_dropdown(
                d.get("weight_name") if isinstance(d, dict) else None
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_OPENVINO_STATUS,
            lambda d: self.gui.update_openvino_status_display(
                str(d.get("status")) if isinstance(d, dict) and d.get("status") else "Unknown"
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_OPENVINO_CHECKBOX,
            lambda d: self.gui.update_openvino_checkbox(
                bool(d.get("is_checked")) if isinstance(d, dict) else False
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_WEIGHTS_LIST,
            lambda d: self.gui.update_weights_dropdown(
                list(d.get("weights", [])) if isinstance(d, dict) else []
            ),
        )

        # Arduino / Hardware
        self.event_bus.subscribe(
            Events.UI_UPDATE_ARDUINO_STATUS,
            lambda d: self.gui.arduino_dashboard_widget.update_status(
                bool(d.get("connected")) if isinstance(d, dict) else False,
                str(d.get("port")) if isinstance(d, dict) and d.get("port") else None,
            )
            if self.gui.arduino_dashboard_widget
            else None,
        )
        self.event_bus.subscribe(
            Events.UI_APPEND_ARDUINO_LOG,
            lambda d: self.gui.arduino_dashboard_widget.append_log(
                str(d.get("message") or "") if isinstance(d, dict) else ""
            )
            if self.gui.arduino_dashboard_widget
            else None,
        )

        # View Navigation & Modes
        def _handle_navigate_to_analysis(d):
            log.info("event_dispatcher.navigate_to_analysis_view.received")
            if not self.gui:
                return
            self.gui.start_analysis_view_mode()

        log.info(
            "event_dispatcher.subscribing_navigation",
            event_name=Events.UI_NAVIGATE_TO_ANALYSIS_VIEW,
            event_bus_id=id(self.event_bus),
        )
        self.event_bus.subscribe(Events.UI_NAVIGATE_TO_ANALYSIS_VIEW, _handle_navigate_to_analysis)
        self.event_bus.subscribe(
            Events.UI_NAVIGATE_FROM_ANALYSIS_VIEW, lambda d: self.gui.stop_analysis_view_mode()
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_PROCESSING_MODE,
            self._handle_update_processing_mode,
        )

        # General UI
        self.event_bus.subscribe(
            Events.UI_UPDATE_BUTTON_STATE,
            lambda d: self.gui.update_button_state(
                d.get("button_name") if isinstance(d, dict) else None,
                d.get("state") if isinstance(d, dict) else None,
            ),
        )
        self.event_bus.subscribe(
            Events.UI_DISPLAY_FRAME,
            lambda d: self.gui.canvas_manager.update_video_frame(
                d.get("frame") if isinstance(d, dict) else None,  # type: ignore
                d.get("detections") if isinstance(d, dict) else None,
            ),
        )
        self.event_bus.subscribe(
            Events.UI_DISPLAY_VIDEO_FRAME,
            lambda d: self.gui.canvas_manager.display_roi_video_frame(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )

        # Zone Updates
        self.event_bus.subscribe(
            Events.UI_REDRAW_ZONES,
            lambda d: self.gui.canvas_manager.redraw_zones_from_project_data(
                d.get("zone_data") if isinstance(d, dict) else None
            ),
        )
        self.event_bus.subscribe(
            Events.UI_UPDATE_ZONE_LIST, lambda d: self.gui.canvas_manager.update_zone_listbox()
        )

        # Weight Management Interactive Requests
        self.event_bus.subscribe(
            Events.UI_REQUEST_WEIGHT_TYPE,
            lambda d: self.gui.handle_request_weight_type(
                str(d.get("filepath")) if isinstance(d, dict) and d.get("filepath") else ""
            ),
        )
        self.event_bus.subscribe(
            Events.UI_REQUEST_WEIGHT_ACTION,
            lambda d: self.gui.handle_request_weight_action(
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

        report = data.get("report")
        self.gui.state_synchronizer.update_processing_mode(report)

    def _handle_setup_interactive_polygon(self, polygon_data) -> None:
        """Handle legacy interactive polygon requests from the event bus."""
        if not self.gui:
            return

        polygon = polygon_data
        if polygon is None:
            polygon = []

        self.gui.setup_interactive_polygon(polygon)

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
        video_path = data.get("video_path")
        config = data.get("config")
        if video_path and config:
            if hasattr(self.gui, "setup_zone_definition_for_single_video"):
                self.log.info(
                    "event_dispatcher._handle_setup_zone_definition_for_single_video.calling_gui_method"
                )
                self.gui.setup_zone_definition_for_single_video(video_path, config)
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

        # Drawing Actions
        self.event_bus.subscribe(
            Events.ZONE_AUTO_DETECT_CLICKED,
            lambda d: self.gui._on_auto_detect_clicked(
                stabilization_frames=d.get("stabilization_frames") if isinstance(d, dict) else None
            ),
        )
        self.event_bus.subscribe(
            Events.ZONE_DRAW_ARENA, lambda d: self.gui.canvas_manager.start_main_arena_drawing()
        )
        self.event_bus.subscribe(
            Events.ZONE_DRAW_ROI, lambda d: self.gui.canvas_manager.start_roi_drawing()
        )
        self.event_bus.subscribe(Events.ZONE_TOGGLE_VIEW, lambda d: self.gui._toggle_canvas_view())

        # ROI Templates
        self.event_bus.subscribe(
            Events.ZONE_TEMPLATE_APPLY, lambda d: self.gui._on_apply_roi_template()
        )
        self.event_bus.subscribe(
            Events.ZONE_TEMPLATE_SAVE, lambda d: self.gui._on_save_roi_template()
        )
        self.event_bus.subscribe(
            Events.ZONE_TEMPLATE_IMPORT, lambda d: self.gui._on_import_and_apply_roi_template()
        )

        # Video Selector
        self.event_bus.subscribe(
            Events.ZONE_VIDEO_SEARCH_CHANGED, lambda d: self.gui._filter_video_tree()
        )
        self.event_bus.subscribe(
            Events.ZONE_VIDEO_REFRESH, lambda d: self.gui._refresh_video_selector_tree()
        )
        self.event_bus.subscribe(
            Events.ZONE_VIDEO_DOUBLE_CLICK,
            lambda d: self.gui.canvas_manager.load_selected_video_frame(),
        )
        self.event_bus.subscribe(
            Events.ZONE_VIDEO_FRAME_LOAD,
            lambda d: self.gui.canvas_manager.load_selected_video_frame(),
        )

        # Zone List
        self.event_bus.subscribe(
            Events.ZONE_AQUARIUM_SELECTED,
            lambda d: self.gui.canvas_manager.update_zone_listbox(),
        )
        # Processing mode change (parallel vs sequential for multi-aquarium)
        self.event_bus.subscribe(
            Events.ZONE_PROCESSING_MODE_CHANGED,
            lambda d: self.gui.canvas_manager.update_processing_mode(
                d.get("sequential", False) if isinstance(d, dict) else False
            ),
        )
        self.event_bus.subscribe(
            Events.ZONE_LIST_ITEM_DOUBLE_CLICK,
            lambda d: self.gui.canvas_manager.edit_selected_zone_vertices(),
        )
        self.event_bus.subscribe(
            Events.ZONE_LIST_ITEM_RIGHT_CLICK,
            lambda d: self.gui.menu_manager.show_roi_context_menu(
                x=d.get("x") if isinstance(d, dict) else 0,
                y=d.get("y") if isinstance(d, dict) else 0,
                item_id=d.get("item_id") if isinstance(d, dict) else None,
            ),
        )

        # Interactive Editing
        self.event_bus.subscribe(
            Events.ZONE_SAVE_ARENA, lambda d: self.gui.canvas_manager.save_arena()
        )
        self.event_bus.subscribe(
            Events.ZONE_DISCARD_ARENA, lambda d: self.gui.canvas_manager.discard_arena()
        )
        self.event_bus.subscribe(
            Events.ZONE_FINISH_DRAWING,
            lambda d: self.gui.canvas_manager.event_handler.on_canvas_double_click(None),
        )
        self.event_bus.subscribe(
            "zone.conclude_video",
            lambda d: self.gui.zone_control_builder._on_conclude_video(),
        )

        # Zone Context Menu Actions (Copy/Paste/Delete)
        self.event_bus.subscribe(
            Events.ZONE_COPY_ZONES,
            lambda d: self.gui.canvas_manager.copy_zones_from_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )
        self.event_bus.subscribe(
            Events.ZONE_PASTE_ZONES,
            lambda d: self.gui.canvas_manager.paste_zones_to_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )
        self.event_bus.subscribe(
            Events.ZONE_DELETE_ZONES,
            lambda d: self.gui.canvas_manager.delete_zones_from_video(
                d.get("video_path") if isinstance(d, dict) else None
            ),
        )

        # Multi-Aquarium Success
        self.event_bus.subscribe(
            Events.ZONE_MULTI_AUTO_DETECT_SUCCESS,
            lambda d: self.gui.canvas_manager.on_multi_auto_detect_success(
                d if isinstance(d, dict) else {}
            ),
        )

        # Multi-Aquarium Assignment Dialog (Triggered by CanvasManager)
        self.event_bus.subscribe(
            Events.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
            self._on_show_aquarium_assignment_dialog,
        )

        # ROI Settings
        self.event_bus.subscribe(
            Events.DETECTOR_UPDATE_PARAMETERS,
            lambda d: self.gui._on_apply_roi_settings(d if isinstance(d, dict) else {}),
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

        video_path = data.get("video_path")
        print(f"[DIAGNOSTIC] video_path={video_path}")

        self.log.info(
            "aquarium_assignment_dialog.showing",
            video_path=video_path,
            available_groups=data.get("available_groups", []),
        )

        print("[DIAGNOSTIC] calling dialog_manager.show_aquarium_assignment_dialog")
        configs, apply_to_all = self.gui.dialog_manager.show_aquarium_assignment_dialog(
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
                Events.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED,
                {
                    "video_path": video_path,
                    "configs": configs_as_dicts,
                    "apply_to_all": apply_to_all,
                },
            )

    def schedule_event_bus_poll(self) -> None:
        """Schedule the event bus polling loop."""
        if not self.gui:
            return
        self.gui.root.after(self.gui._event_bus_poll_interval_ms, self.poll_event_bus)

    def poll_event_bus(self) -> None:
        """Poll the event bus for pending events."""
        if not self.gui:
            return

        if self.event_bus:
            # Check if it has a drain method (standard queue-based bus)
            if hasattr(self.event_bus, "drain"):
                # Process up to e.g. 20 events per tick to avoid freezing UI
                events = self.event_bus.drain(max_items=20)
                for event in events:
                    try:
                        if event.type == EventType.NAMED:
                            # Dispatch named event
                            if hasattr(self.event_bus, "dispatch_named_event"):
                                self.event_bus.dispatch_named_event(event.payload)
                        elif event.type == EventType.CALLABLE:
                            # Execute callable event
                            event.payload.execute()
                    except Exception as e:
                        self.log.error("event_dispatcher.poll_error", error=str(e))

            # Fallback for other implementations (process_events/process_queue)
            elif hasattr(self.event_bus, "process_events"):
                self.event_bus.process_events()
            elif hasattr(self.event_bus, "process_queue"):
                self.event_bus.process_queue()

        # Reschedule
        self.schedule_event_bus_poll()

    # --- High-Level UI Action Handlers ---

    def publish_event(self, event_name: str, data: dict | None = None) -> bool:
        """Publish a named event through the event bus.

        Args:
            event_name: Name of the event to publish
            data: Optional dictionary with event data

        Returns:
            True if event was successfully published, False otherwise
        """
        if not self.validate_event_payload(event_name, data or {}):
            return False

        if not self.event_bus:
            return False

        return self.event_bus.publish_event(event_name, data or {})

    def validate_event_payload(self, event_name: str, data: dict) -> bool:
        """Validate the payload for specific events to ensure contract integrity.

        Args:
            event_name: Name of the event.
            data: Payload data.

        Returns:
            True if valid, False otherwise.
        """
        if event_name == Events.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED:
            if not isinstance(data.get("configs"), list):
                self.log.error("event_validation.configs_not_list", event=event_name)
                return False
            if "video_path" not in data:
                self.log.error("event_validation.missing_video_path", event=event_name)
                return False
        elif event_name == Events.ZONE_AQUARIUM_SELECTED:
            if not isinstance(data.get("aquarium_id"), int):
                self.log.error("event_validation.aquarium_id_not_int", event=event_name)
                return False
        elif event_name == Events.ZONE_MULTI_AUTO_DETECT_SUCCESS:
            if not isinstance(data.get("polygons"), list):
                self.log.error("event_validation.polygons_not_list", event=event_name)
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

        # Import the dialog
        from zebtrack.ui.dialogs import SingleVideoConfigDialog

        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.dialog_imported")

        # Get settings from controller
        settings = None
        if hasattr(self.gui, "controller") and self.gui.controller:
            settings = getattr(self.gui.controller, "settings", None)
        self.log.info(
            "event_dispatcher.handle_analyze_single_video_clicked.settings_retrieved",
            has_settings=bool(settings),
        )

        # Open configuration dialog
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.opening_dialog")
        dialog = SingleVideoConfigDialog(self.gui.root, settings_obj=settings)
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
            event_name=Events.VIDEO_ANALYZE_SINGLE,
            video_path=video_path,
        )
        self.publish_event(
            Events.VIDEO_ANALYZE_SINGLE, {"video_path": video_path, "config": config}
        )
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.event_published")

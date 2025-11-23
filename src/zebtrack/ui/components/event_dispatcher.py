"""Dispatcher de eventos para roteamento de eventos do EventBus.

Handles both Core-side dispatching (routing commands to orchestrators)
and UI-side dispatching (routing UI updates to widgets).
"""

from typing import TYPE_CHECKING, Callable

import structlog

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
            # Fallback/Unknown – treat as raw event bus reference
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
        pass

    def subscribe_to_ui_events(self) -> None:
        """Subscribe to UI-related events."""
        if not self.gui or not self.event_bus:
            return

        # Generic UI updates
        self.event_bus.subscribe(Events.UI_SHOW_INFO,
            lambda d: self.gui.dialog_manager.show_info(d.get("title", "Info"), d.get("message", "")))
        self.event_bus.subscribe(Events.UI_SHOW_WARNING,
            lambda d: self.gui.dialog_manager.show_warning(d.get("title", "Aviso"), d.get("message", "")))
        self.event_bus.subscribe(Events.UI_SHOW_ERROR,
            lambda d: self.gui.dialog_manager.show_error(d.get("title", "Erro"), d.get("message", "")))

        # External Triggers
        self.event_bus.subscribe(Events.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
            lambda d: self.gui.dialog_manager.show_external_trigger_notice(
                d.get("session_label", ""),
                **{k: v for k, v in d.items() if k != "session_label"}
            ))
        self.event_bus.subscribe(Events.UI_CLEAR_EXTERNAL_TRIGGER_NOTICE,
            lambda d: self.gui.dialog_manager.clear_external_trigger_notice())

        # Status updates
        self.event_bus.subscribe(Events.UI_SET_STATUS,
            lambda d: self.gui.status_var.set(d.get("message", "")))

        # View navigation
        self.event_bus.subscribe(Events.UI_SELECT_TAB,
            lambda d: self.gui.notebook.select(getattr(self.gui, f"{d.get('tab_name')}_frame", 0)))

        # Single video zone setup (Decoupling from MainViewModel)
        self.event_bus.subscribe(
            "ui:setup_zone_definition_for_single_video",
            self._handle_setup_zone_definition_for_single_video
        )

        # Analysis Updates
        self.event_bus.subscribe(Events.UI_UPDATE_PROCESSING_STATS,
            lambda d: self.gui.state_synchronizer.update_processing_stats(**d))
        self.event_bus.subscribe(Events.UI_UPDATE_SOCIAL_SUMMARY,
            lambda d: self.gui.state_synchronizer.update_social_summary(**d))
        self.event_bus.subscribe(Events.UI_UPDATE_ANALYSIS_TASK_STATUS,
            lambda d: self.gui.state_synchronizer.update_analysis_task_status(**d.get("payload", {})))

        # Project View Updates
        self.event_bus.subscribe(Events.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: self.gui.project_view_manager.on_video_hierarchy_snapshot_updated(d.get("snapshot", [])))
        self.event_bus.subscribe(Events.UI_REFRESH_PROJECT_VIEWS,
            lambda d: self.gui.project_view_manager.refresh_project_views(
                reason=d.get("reason"),
                append_summary=d.get("append_summary", False),
                immediate=d.get("immediate", False)
            ))

    def _handle_setup_zone_definition_for_single_video(self, data: dict) -> None:
        """Handler for single video zone setup event."""
        if not self.gui: return
        video_path = data.get("video_path")
        config = data.get("config")
        if video_path and config:
            if hasattr(self.gui, "setup_zone_definition_for_single_video"):
                self.gui.setup_zone_definition_for_single_video(video_path, config)
            else:
                self.log.error("gui.missing_method", method="setup_zone_definition_for_single_video")

    def subscribe_zone_component_events(self) -> None:
        """Subscribe to events emitted by ZoneControlsWidget."""
        if not self.gui or not self.event_bus: return

        # Drawing Actions
        self.event_bus.subscribe(Events.ZONE_AUTO_DETECT_CLICKED,
            lambda d: self.gui._on_auto_detect_clicked(stabilization_frames=d.get("stabilization_frames")))
        self.event_bus.subscribe(Events.ZONE_DRAW_ARENA,
            lambda d: self.gui.canvas_manager.start_main_arena_drawing())
        self.event_bus.subscribe(Events.ZONE_DRAW_ROI,
            lambda d: self.gui.canvas_manager.start_roi_drawing())
        self.event_bus.subscribe(Events.ZONE_TOGGLE_VIEW,
            lambda d: self.gui._toggle_canvas_view())

        # ROI Templates
        self.event_bus.subscribe(Events.ZONE_TEMPLATE_APPLY,
            lambda d: self.gui._on_apply_roi_template())
        self.event_bus.subscribe(Events.ZONE_TEMPLATE_SAVE,
            lambda d: self.gui._on_save_roi_template())
        self.event_bus.subscribe(Events.ZONE_TEMPLATE_IMPORT,
            lambda d: self.gui._on_import_and_apply_roi_template())

        # Video Selector
        self.event_bus.subscribe(Events.ZONE_VIDEO_SEARCH_CHANGED,
            lambda d: self.gui._filter_video_tree())
        self.event_bus.subscribe(Events.ZONE_VIDEO_REFRESH,
            lambda d: self.gui._refresh_video_selector_tree())
        self.event_bus.subscribe(Events.ZONE_VIDEO_DOUBLE_CLICK,
             lambda d: self.gui.canvas_manager.load_selected_video_frame())
        self.event_bus.subscribe(Events.ZONE_VIDEO_FRAME_LOAD,
             lambda d: self.gui.canvas_manager.load_selected_video_frame())

        # Zone List
        self.event_bus.subscribe(Events.ZONE_LIST_ITEM_DOUBLE_CLICK,
             lambda d: self.gui.canvas_manager.edit_selected_zone_vertices())
        self.event_bus.subscribe(Events.ZONE_LIST_ITEM_RIGHT_CLICK,
             lambda d: self.gui.menu_manager.show_roi_context_menu(
                 x=d.get("x"), y=d.get("y"), item_id=d.get("item_id")
             ))

        # Interactive Editing
        self.event_bus.subscribe(Events.ZONE_SAVE_ARENA,
             lambda d: self.gui.canvas_manager.save_arena())
        self.event_bus.subscribe(Events.ZONE_DISCARD_ARENA,
             lambda d: self.gui.canvas_manager.discard_arena())

        # ROI Settings
        self.event_bus.subscribe(Events.ZONE_APPLY_ROI_SETTINGS,
            lambda d: self.gui._on_apply_roi_settings())

    def schedule_event_bus_poll(self) -> None:
        """Schedule the event bus polling loop."""
        if not self.gui: return
        self.gui.root.after(self.gui._event_bus_poll_interval_ms, self.poll_event_bus)

    def poll_event_bus(self) -> None:
        """Poll the event bus for pending events."""
        if not self.gui: return

        if self.event_bus:
            # Assuming EventBus has a process_events or similar method for Tkinter integration
            # If EventBus is purely callback-based (immediate), this might just be a keep-alive
            # Checking EventBus implementation: usually direct calls don't need polling
            # UNLESS we are crossing threads.
            # If EventBus uses a queue, we need to process it.
            if hasattr(self.event_bus, "process_events"):
                self.event_bus.process_events()
            elif hasattr(self.event_bus, "process_queue"):
                self.event_bus.process_queue()

        # Reschedule
        self.schedule_event_bus_poll()

"""Dispatcher de eventos para roteamento de eventos do EventBusV2.

Handles both Core-side dispatching (routing commands to orchestrators)
and UI-side dispatching (routing UI updates to widgets).
"""

from collections.abc import Callable
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.ui import payloads as payloads
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI
else:
    ApplicationGUI = Any

log = structlog.get_logger()


def _payload_to_dict(payload: payloads.EventPayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if is_dataclass(payload) and not isinstance(payload, type):
        return {field.name: getattr(payload, field.name) for field in fields(payload)}
    return {}


def _payload_get(payload: payloads.EventPayload | dict[str, Any], key: str, default=None):
    if is_dataclass(payload) and not isinstance(payload, type):
        return getattr(payload, key, default)
    if isinstance(payload, dict):
        return payload.get(key, default)
    return default


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

        # Audit Erro 2 round 6 (2026-05-25): pending payload queues. If the
        # analysis_display_widget is not yet built when an event arrives
        # (e.g. the tab was constructed lazily or the user navigated away),
        # we stash the LAST payload so we can re-apply it as soon as the
        # widget becomes available. Single-slot per event type so we never
        # apply stale data.
        self._pending_analysis_metadata: Any | None = None
        self._pending_processing_stats: dict[str, Any] | None = None
        self._pending_processing_mode: Any | None = None

    def _require_gui(self) -> "ApplicationGUI":
        if self.gui is None:
            raise RuntimeError("EventDispatcher requires ApplicationGUI context for UI events.")
        return self.gui

    @staticmethod
    def _finish_drawing_is_interactive_edit(gui: Any) -> bool:
        """True when "Finalizar Desenho" should commit an interactive edit.

        An interactive edit is active when an editing zone is set (arena/ROI)
        AND there are edited polygon points. In that case the finish action must
        save the edited points (``save_arena``) instead of re-completing a fresh
        drawing (``on_canvas_double_click``), which would revert the polygon.
        """
        cm = getattr(gui, "canvas_manager", None)
        editing = bool(
            getattr(cm, "current_editing_zone", None) or getattr(gui, "current_editing_zone", None)
        )
        has_edited_points = bool(getattr(gui, "edited_polygon_points", None))
        return editing and has_edited_points

    def _run_on_ui_thread(self, callback: Callable[[], None]) -> None:
        """Schedule callback on Tk main thread when possible.

        Falls back to direct execution when root/after is unavailable.
        """
        gui = self._require_gui()
        root = getattr(gui, "root", None)
        if root is not None and hasattr(root, "after"):
            try:
                root.after(0, callback)
                return
            except Exception:
                self.log.debug("event_dispatcher.ui_after_fallback", exc_info=True)
        callback()

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

        def dispatcher(payload: payloads.EventPayload) -> None:
            data = _payload_to_dict(payload)
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
            lambda data: self._handle_setup_interactive_polygon(_payload_get(data, "polygon")),
        )

    def subscribe_to_ui_events(self) -> None:  # noqa: C901
        """Subscribe to UI-related events.

        Cyclomatic complexity (~22) sits just above the project's strict
        threshold of 20 because this is the central UI event wiring table —
        breaking it apart would scatter related subscriptions and make the
        bus surface harder to audit. Suppressed deliberately.
        """
        if not self.gui or not self.event_bus:
            return

        gui = self._require_gui()
        event_bus = self.event_bus

        # Import UIEvents to use constants

        # Navigation & Lifecycle
        def _navigate_welcome(d: payloads.EventPayload) -> None:
            gui.widget_factory.create_welcome_frame()

        event_bus.subscribe(UIEvents.NAVIGATE_TO_WELCOME, _navigate_welcome)
        event_bus.subscribe(UIEvents.UI_NAVIGATE_TO_WELCOME, _navigate_welcome)

        def _navigate_project_view(d: payloads.EventPayload) -> None:
            gui.root.after(0, gui.project_initializer.load_project_view)

        event_bus.subscribe(UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW, _navigate_project_view)

        def _on_project_closed(d: payloads.EventPayload) -> None:
            gui.state_synchronizer._destroy_notebook_and_main_controls()

        event_bus.subscribe(UIEvents.PROJECT_CLOSED, _on_project_closed)

        # Generic UI updates — schedule via root.after so the event bus handler
        # returns immediately and is not counted as "slow" by the timing monitor.
        def _show_info(d: payloads.EventPayload) -> None:
            gui.root.after(
                0,
                lambda: gui.dialog_manager.show_info(
                    _payload_get(d, "title", "Info"),
                    _payload_get(d, "message", ""),
                ),
            )

        def _show_warning(d: payloads.EventPayload) -> None:
            gui.root.after(
                0,
                lambda: gui.dialog_manager.show_warning(
                    _payload_get(d, "title", "Aviso"),
                    _payload_get(d, "message", ""),
                ),
            )

        def _show_error(d: payloads.EventPayload) -> None:
            gui.root.after(
                0,
                lambda: gui.dialog_manager.show_error(
                    _payload_get(d, "title", "Erro"),
                    _payload_get(d, "message", ""),
                ),
            )

        event_bus.subscribe(UIEvents.UI_SHOW_INFO, _show_info)
        event_bus.subscribe(UIEvents.UI_SHOW_WARNING, _show_warning)
        event_bus.subscribe(UIEvents.UI_SHOW_ERROR, _show_error)

        # External Triggers
        event_bus.subscribe(
            UIEvents.UI_SHOW_EXTERNAL_TRIGGER_NOTICE,
            lambda d: gui.dialog_manager.show_external_trigger_notice(
                _payload_get(d, "session_label", "") or _payload_get(d, "folder_name", ""),
                **(
                    {
                        k: v
                        for k, v in _payload_to_dict(d).items()
                        if k not in ("session_label", "folder_name")
                    }
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
            lambda d: gui.status_var.set(_payload_get(d, "message", "")),
        )

        # View navigation
        event_bus.subscribe(
            UIEvents.UI_SELECT_TAB,
            lambda d: gui.notebook.select(
                getattr(gui, f"{_payload_get(d, 'tab_name', '')}_frame", 0)
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
        # Audit Erro 2 round 6 (2026-05-25): stash the LAST stats payload so
        # ``drain_pending_to_widget`` can replay it once the analysis tab is
        # finally rendered. Without this, frames published before the tab
        # was built were dropped silently and the labels stuck on "-".
        def _on_processing_stats(d) -> None:
            stats = _payload_get(d, "stats", {}) or {}
            self._pending_processing_stats = dict(stats) if isinstance(stats, dict) else None
            widget = getattr(self.gui, "analysis_display_widget", None)
            if widget is None:
                log.debug(
                    "event_dispatcher.processing_stats.queued_widget_missing",
                    has_stats=bool(stats),
                )
                return
            gui.state_synchronizer.update_processing_stats(**stats)

        event_bus.subscribe(
            UIEvents.UI_UPDATE_PROCESSING_STATS,
            _on_processing_stats,
        )

        # Audit Erro 2 round 4 (2026-05-25): wrap with diagnostics. The
        # publish from live_camera_session_coordinator was reaching the
        # event bus (publisher log confirms data), but the widget never
        # received it. We log at THREE points so the next run pinpoints
        # where the chain breaks: (1) subscriber lambda invoked,
        # (2) UI-thread callback dispatched, (3) controller method actually
        # called. If only (1) appears, the after(0,...) wrapper is failing.
        # If (1)+(2) appear but not (3), the controller reference is stale.
        def _on_analysis_metadata(d) -> None:
            try:
                payload_metadata = _payload_get(d, "metadata")
                log.info(
                    "event_dispatcher.analysis_metadata.received_in_subscriber",
                    has_gui=self.gui is not None,
                    has_controller=bool(getattr(self.gui, "analysis_view_controller", None)),
                    metadata_keys=list(payload_metadata.keys())
                    if isinstance(payload_metadata, dict)
                    else None,
                )
            # except Exception justified: telemetry must never raise into bus.
            except Exception:
                log.debug(
                    "event_dispatcher.analysis_metadata.diag_log_failed",
                    exc_info=True,
                )

            # Audit Erro 2 round 6 (2026-05-25): stash the LAST metadata
            # payload so ``drain_pending_to_widget`` can replay it once the
            # widget is finally rendered.
            self._pending_analysis_metadata = d

            def _dispatch(payload=d) -> None:
                try:
                    log.info(
                        "event_dispatcher.analysis_metadata.ui_thread_dispatched",
                    )
                    controller = getattr(self.gui, "analysis_view_controller", None)
                    if controller is None:
                        log.warning(
                            "event_dispatcher.analysis_metadata.controller_missing",
                        )
                        return
                    controller.update_analysis_metadata(metadata=_payload_get(payload, "metadata"))
                # except Exception justified: surface UI failures explicitly
                # rather than silently dropping into the Tk callback eater.
                except Exception as exc:
                    log.error(
                        "event_dispatcher.analysis_metadata.dispatch_failed",
                        error=str(exc),
                        exc_info=True,
                    )

            self._run_on_ui_thread(_dispatch)

        event_bus.subscribe(
            UIEvents.UI_UPDATE_ANALYSIS_METADATA,
            _on_analysis_metadata,
        )
        # Audit Erro 2 round 5 (2026-05-25): the diagnostic logs round 4
        # added didn't appear in user logs — confirm subscription was
        # actually registered. Also register a SECOND, sync-direct handler
        # as a redundant safety net: if the async one is silently dropping,
        # this one still updates the StringVars.
        log.info(
            "event_dispatcher.subscribed_to_analysis_metadata",
            event_bus_id=id(event_bus),
            event_name=str(UIEvents.UI_UPDATE_ANALYSIS_METADATA),
        )

        def _on_analysis_metadata_backup(d) -> None:
            """Backup handler scheduled on the UI thread via ``root.after(0, ...)``.

            Round 5 originally invoked Tkinter ``StringVar.set`` from the
            publisher thread as a "safety net" — Copilot review (PR #388,
            comment 3300599873) correctly flagged that this violates the
            project rule "worker → UI must go through root.after(0, ...)"
            and can intermittently crash/hang Tk. The backup is now also
            UI-thread-scheduled; if the original async dispatch silently
            fails (e.g. controller attr missing during a tab switch), this
            second one still runs through the Tk event loop and updates the
            StringVars from the main thread.
            """

            def _apply(payload=d) -> None:
                try:
                    payload_metadata = _payload_get(payload, "metadata") or {}
                    log.info(
                        "event_dispatcher.analysis_metadata.backup_invoked",
                        has_data=bool(payload_metadata),
                        keys=list(payload_metadata.keys())
                        if isinstance(payload_metadata, dict)
                        else None,
                    )
                    widget = getattr(self.gui, "analysis_display_widget", None)
                    if widget is None:
                        log.warning("event_dispatcher.analysis_metadata.backup_widget_missing")
                        return
                    group = payload_metadata.get("group") or "Sem Grupo"
                    day = (
                        payload_metadata.get("day")
                        or payload_metadata.get("day_label")
                        or "Sem Dia"
                    )
                    subject = (
                        payload_metadata.get("subject")
                        or payload_metadata.get("subject_id")
                        or "Não informado"
                    )
                    if hasattr(widget, "set_metadata"):
                        widget.set_metadata(
                            group=str(group),
                            day=str(day),
                            subject=str(subject),
                        )
                    profile = payload_metadata.get("profile") or "default"
                    if hasattr(widget, "set_profile"):
                        widget.set_profile(str(profile))
                # except Exception justified: backup must surface failure to
                # logs rather than abort the publish.
                except Exception as exc:
                    log.error(
                        "event_dispatcher.analysis_metadata.backup_failed",
                        error=str(exc),
                        exc_info=True,
                    )

            self._run_on_ui_thread(_apply)

        event_bus.subscribe(
            UIEvents.UI_UPDATE_ANALYSIS_METADATA,
            _on_analysis_metadata_backup,
        )

        event_bus.subscribe(
            UIEvents.UI_UPDATE_SOCIAL_SUMMARY,
            lambda d: gui.state_synchronizer.update_social_summary(**_payload_to_dict(d)),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
            lambda d: gui.state_synchronizer.update_analysis_task_status(**_payload_to_dict(d)),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_DETECTION_OVERLAY,
            lambda d: gui.analysis_view_controller.update_detection_overlay(
                detections=_payload_get(d, "detections"),
                report=_payload_get(d, "report"),
            ),
        )

        # Project View Updates
        event_bus.subscribe(
            UIEvents.UI_VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
            lambda d: gui.video_selector_manager.on_video_hierarchy_snapshot_updated(
                _payload_get(d, "snapshot", [])
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_REFRESH_PROJECT_VIEWS,
            lambda d: gui.video_selector_manager.refresh_project_views(
                reason=_payload_get(d, "reason"),
                append_summary=_payload_get(d, "append_summary", False),
                immediate=_payload_get(d, "immediate", False),
            ),
        )

        # Weight Management
        event_bus.subscribe(
            UIEvents.UI_SET_ACTIVE_WEIGHT,
            lambda d: self._run_on_ui_thread(
                lambda: gui.weight_hardware_manager.set_active_weight_in_dropdown(
                    _payload_get(d, "weight_name")
                )
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_OPENVINO_STATUS,
            lambda d: gui.weight_hardware_manager.update_openvino_status_display(
                str(_payload_get(d, "status")) if _payload_get(d, "status") else "Unknown"
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
            lambda d: self._run_on_ui_thread(
                lambda: gui.weight_hardware_manager.update_openvino_checkbox(
                    bool(_payload_get(d, "is_checked", False))
                )
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_WEIGHTS_LIST,
            lambda d: gui.weight_hardware_manager.update_weights_dropdown(
                list(_payload_get(d, "weights", []))
            ),
        )

        # Arduino / Hardware
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ARDUINO_STATUS,
            lambda d: gui.arduino_dashboard_widget.update_status(
                bool(_payload_get(d, "connected", False)),
                str(_payload_get(d, "port")) if _payload_get(d, "port") else None,
            )
            if gui.arduino_dashboard_widget
            else None,
        )
        event_bus.subscribe(
            UIEvents.UI_APPEND_ARDUINO_LOG,
            lambda d: gui.arduino_dashboard_widget.append_log(str(_payload_get(d, "message") or ""))
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
                _payload_get(d, "button_name"),
                _payload_get(d, "state"),
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_DISPLAY_FRAME,
            lambda d: gui.canvas_manager.update_video_frame(
                _payload_get(d, "frame"),  # type: ignore[arg-type]  # frame is Any from payload
                _payload_get(d, "detections"),
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_DISPLAY_VIDEO_FRAME,
            lambda d: gui.canvas_manager.display_roi_video_frame(_payload_get(d, "video_path")),
        )

        # Zone Updates
        event_bus.subscribe(
            UIEvents.UI_REDRAW_ZONES,
            lambda d: gui.canvas_manager.redraw_zones_from_project_data(
                _payload_get(d, "zone_data")
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_UPDATE_ZONE_LIST, lambda d: gui.canvas_manager.update_zone_listbox()
        )

        # Weight Management Interactive Requests
        event_bus.subscribe(
            UIEvents.UI_REQUEST_WEIGHT_TYPE,
            lambda d: gui.weight_hardware_manager.handle_request_weight_type(
                str(_payload_get(d, "filepath")) if _payload_get(d, "filepath") else ""
            ),
        )
        event_bus.subscribe(
            UIEvents.UI_REQUEST_WEIGHT_ACTION,
            lambda d: gui.weight_hardware_manager.handle_request_weight_action(
                str(_payload_get(d, "filepath")) if _payload_get(d, "filepath") else "",
                str(_payload_get(d, "weight_type")) if _payload_get(d, "weight_type") else "",
            ),
        )

    def _handle_update_processing_mode(self, data: payloads.EventPayload) -> None:
        """Handle UI_UPDATE_PROCESSING_MODE event.

        Expected payload: {"report": ProcessingReport}

        Audit Erro 2 round 6 (2026-05-25): stash the last payload so
        ``drain_pending_to_widget`` can re-apply it after the tab is built.
        """
        # Stash before any guard so the drain path always has the latest.
        self._pending_processing_mode = data

        if not self.gui:
            return

        gui = self._require_gui()
        if getattr(gui, "analysis_display_widget", None) is None:
            log.debug("event_dispatcher.processing_mode.queued_widget_missing")
            return
        report = _payload_get(data, "report")
        gui.state_synchronizer.update_processing_mode(report)

    def drain_pending_to_widget(self) -> None:
        """Re-apply the last stashed analysis-tab payloads.

        Audit Erro 2 round 6 (2026-05-25): the live session publishes
        metadata + stats + tracking-mode events at session start, but the
        ``analysis_display_widget`` may not exist yet (lazy tab build, or
        the user navigated away). Without replay, the labels stuck on
        "Grupo: --" / "Modo de rastreamento: --" / "Frames: -" forever.
        Call this from ``ApplicationGUI`` (or wherever the widget is set)
        right after the widget reference becomes available.
        """
        if self.gui is None:
            return
        widget = getattr(self.gui, "analysis_display_widget", None)
        if widget is None:
            return

        state_sync = getattr(self.gui, "state_synchronizer", None)
        controller = getattr(self.gui, "analysis_view_controller", None)

        # 1) Metadata: prefer the controller path, fall back to the widget
        # directly (same logic the regular subscriber uses).
        if self._pending_analysis_metadata is not None:
            payload = self._pending_analysis_metadata
            metadata = _payload_get(payload, "metadata") or {}
            try:
                if controller is not None:
                    controller.update_analysis_metadata(metadata=metadata)
                elif hasattr(widget, "set_metadata") and isinstance(metadata, dict):
                    widget.set_metadata(
                        group=str(metadata.get("group") or "Sem Grupo"),
                        day=str(metadata.get("day") or metadata.get("day_label") or "Sem Dia"),
                        subject=str(
                            metadata.get("subject") or metadata.get("subject_id") or "Não informado"
                        ),
                    )
                log.info(
                    "event_dispatcher.drain.analysis_metadata_applied",
                    via="controller" if controller else "widget_set_metadata",
                )
            # except Exception justified: drain best-effort.
            except Exception as exc:
                log.error(
                    "event_dispatcher.drain.analysis_metadata_failed",
                    error=str(exc),
                    exc_info=True,
                )

        # 2) Processing stats: replay through state_synchronizer.
        if self._pending_processing_stats is not None and state_sync is not None:
            try:
                state_sync.update_processing_stats(**self._pending_processing_stats)
                log.info(
                    "event_dispatcher.drain.processing_stats_applied",
                    keys=list(self._pending_processing_stats.keys()),
                )
            # except Exception justified: drain best-effort.
            except Exception as exc:
                log.error(
                    "event_dispatcher.drain.processing_stats_failed",
                    error=str(exc),
                    exc_info=True,
                )

        # 3) Tracking mode: replay through state_synchronizer.
        if self._pending_processing_mode is not None and state_sync is not None:
            try:
                report = _payload_get(self._pending_processing_mode, "report")
                if hasattr(state_sync, "update_processing_mode"):
                    state_sync.update_processing_mode(report)
                log.info("event_dispatcher.drain.processing_mode_applied")
            # except Exception justified: drain best-effort.
            except Exception as exc:
                log.error(
                    "event_dispatcher.drain.processing_mode_failed",
                    error=str(exc),
                    exc_info=True,
                )

    def _handle_setup_interactive_polygon(self, polygon_data) -> None:
        """Handle legacy interactive polygon requests from the event bus."""
        if not self.gui:
            return

        gui = self._require_gui()
        polygon = polygon_data if polygon_data is not None else []

        import numpy as np

        polygon_array = np.array(polygon, dtype=float)
        gui.canvas_manager.setup_interactive_polygon(polygon_array)

    def _handle_setup_zone_definition_for_single_video(self, data: payloads.EventPayload) -> None:
        """Handler for single video zone setup event."""
        payload = _payload_to_dict(data)
        self.log.info(
            "event_dispatcher._handle_setup_zone_definition_for_single_video.called",
            has_gui=bool(self.gui),
            video_path=payload.get("video_path"),
        )
        if not self.gui:
            self.log.error("event_dispatcher._handle_setup_zone_definition_for_single_video.no_gui")
            return
        gui = self._require_gui()
        video_path = payload.get("video_path")
        config = payload.get("config")
        if video_path and config is not None:
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
                has_config=config is not None,
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
                stabilization_frames=_payload_get(d, "stabilization_frames")
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

        def _clear_applied_templates(_: payloads.EventPayload) -> None:
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
                _payload_get(d, "sequential", False)
            ),
        )
        event_bus.subscribe(
            UIEvents.ZONE_LIST_ITEM_DOUBLE_CLICK,
            lambda d: gui.canvas_manager.edit_selected_zone_vertices(),
        )
        event_bus.subscribe(
            UIEvents.ZONE_LIST_ITEM_RIGHT_CLICK,
            lambda d: gui.menu_manager.show_roi_context_menu(
                x=_payload_get(d, "x", 0),
                y=_payload_get(d, "y", 0),
                item_id=_payload_get(d, "item_id"),
            ),
        )

        # Interactive Editing
        event_bus.subscribe(UIEvents.ZONE_SAVE_ARENA, lambda d: gui.canvas_manager.save_arena())
        event_bus.subscribe(
            UIEvents.ZONE_DISCARD_ARENA, lambda d: gui.canvas_manager.discard_arena()
        )

        def _handle_finish_drawing(d):
            # Em modo de EDIÇÃO interativa (ex.: polígono reutilizado e movido),
            # "Finalizar Desenho" deve COMITAR a edição — salvar os vértices na
            # nova posição (mesmo caminho de "Salvar Edição"). Usar
            # on_canvas_double_click aqui reverteria o polígono ao estado salvo
            # (ele opera sobre o desenho-em-andamento, não sobre
            # edited_polygon_points), descartando o arraste do usuário.
            if EventDispatcher._finish_drawing_is_interactive_edit(gui):
                gui.canvas_manager.save_arena()
                if hasattr(gui, "set_status"):
                    gui.set_status("✓ Desenho finalizado e edição salva na nova posição.")
            else:
                gui.canvas_manager.event_handler.on_canvas_double_click(None)
                if hasattr(gui, "set_status"):
                    gui.set_status(
                        "✓ Desenho finalizado. Clique em 'Salvar Edição' para confirmar."
                    )

        event_bus.subscribe(UIEvents.ZONE_FINISH_DRAWING, _handle_finish_drawing)
        event_bus.subscribe(
            UIEvents.ZONE_CONCLUDE_VIDEO,
            lambda d: gui.zone_control_builder._on_conclude_video(),
        )

        # Zone Context Menu Actions (Copy/Paste/Delete)
        event_bus.subscribe(
            UIEvents.ZONE_COPY_ZONES,
            lambda d: gui.canvas_manager.copy_zones_from_video(_payload_get(d, "video_path")),
        )
        event_bus.subscribe(
            UIEvents.ZONE_PASTE_ZONES,
            lambda d: gui.canvas_manager.paste_zones_to_video(_payload_get(d, "video_path")),
        )
        event_bus.subscribe(
            UIEvents.ZONE_DELETE_ZONES,
            lambda d: gui.canvas_manager.delete_zones_from_video(_payload_get(d, "video_path")),
        )

        # Multi-Aquarium Success
        event_bus.subscribe(
            UIEvents.ZONE_MULTI_AUTO_DETECT_SUCCESS,
            lambda d: gui.canvas_manager.on_multi_auto_detect_success(_payload_to_dict(d)),
        )

        # Multi-Aquarium Assignment Dialog (Triggered by CanvasManager)
        event_bus.subscribe(
            UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
            self._on_show_aquarium_assignment_dialog,
        )

        # ROI Settings
        event_bus.subscribe(
            UIEvents.DETECTOR_UPDATE_PARAMETERS,
            self._on_apply_roi_settings,
        )

    def _on_apply_roi_settings(self, data: payloads.EventPayload) -> None:
        """Handle DETECTOR_UPDATE_PARAMETERS event.

        Applies ROI inclusion settings via the hardware ViewModel.
        """
        gui = self._require_gui()
        if not gui:
            return

        params = _payload_to_dict(data)
        if params and gui.controller:
            gui.controller.hardware_vm.update_detector_parameters(params)

    def _on_show_aquarium_assignment_dialog(self, data: payloads.EventPayload) -> None:
        """Handle ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG event.

        Opens the assignment dialog and publishes completion event if confirmed.
        """
        if not self.gui:
            return

        payload = _payload_to_dict(data)

        gui = self._require_gui()

        video_path = payload.get("video_path")

        self.log.info(
            "aquarium_assignment_dialog.showing",
            video_path=video_path,
            available_groups=payload.get("available_groups", []),
        )
        configs, apply_to_all = gui.dialog_manager.show_aquarium_assignment_dialog(
            available_groups=payload.get("available_groups", []),
            video_path=video_path,
            multi_aquarium_config=payload.get("multi_aquarium_config"),
            entry_metadata=payload.get("entry_metadata"),
        )

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
                payloads.ZoneAquariumAssignmentCompletedPayload(
                    configs=configs_as_dicts,
                    apply_to_all=apply_to_all,
                    video_path=video_path or "",
                ),
            )

    # --- High-Level UI Action Handlers ---

    def publish_event(
        self, event_type: UIEvents, data: payloads.EventPayload | dict | None = None
    ) -> bool:
        """Publish an event through the event bus.

        Args:
            event_type: UIEvents enum member identifying the event.
            data: Optional dictionary with event data.

        Returns:
            True if event was successfully published, False otherwise.
        """
        if not self.validate_event_payload(event_type, _payload_to_dict(data or {})):
            return False

        if not self.event_bus:
            return False

        self.event_bus.publish(event_type, data)
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
        dialog = SingleVideoConfigDialog(
            gui.root,
            settings_obj=settings,
            event_bus=gui.event_bus,
        )
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
            UIEvents.VIDEO_ANALYZE_SINGLE,
            payloads.VideoAnalyzeSinglePayload(video_path=video_path, config=config),
        )
        self.log.info("event_dispatcher.handle_analyze_single_video_clicked.event_published")

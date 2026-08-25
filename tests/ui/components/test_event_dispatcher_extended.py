"""Extended unit tests for ui/components/event_dispatcher.py."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.components.event_dispatcher import (
    EventDispatcher,
    _payload_get,
    _payload_to_dict,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@dataclass
class SamplePayload:
    video_path: str

    frame_count: int = 100

    group: str = "Control"


class TestEventDispatcherHelpers:
    def test_payload_to_dict_with_dict(self):
        data = {"key": "val", "num": 42}
        assert _payload_to_dict(data) == data

    def test_payload_to_dict_with_dataclass(self):
        payload = SamplePayload(video_path="/path/v.mp4", frame_count=100)
        d = _payload_to_dict(payload)
        assert d == {"video_path": "/path/v.mp4", "frame_count": 100, "group": "Control"}

    def test_payload_to_dict_with_other_object(self):
        assert _payload_to_dict("string_payload") == {}  # type: ignore[arg-type]
        assert _payload_to_dict(None) == {}  # type: ignore[arg-type]

    def test_payload_get_with_dict(self):
        data = {"a": 1, "b": 2}
        assert _payload_get(data, "a") == 1
        assert _payload_get(data, "c", default=99) == 99

    def test_payload_get_with_dataclass(self):
        payload = SamplePayload(video_path="/path/v.mp4", frame_count=50)
        assert _payload_get(payload, "video_path") == "/path/v.mp4"
        assert _payload_get(payload, "frame_count") == 50
        assert _payload_get(payload, "non_existent", default="def") == "def"

    def test_payload_get_with_fallback(self):
        assert _payload_get(12345, "a", default="none") == "none"  # type: ignore[arg-type]


class TestEventDispatcherModes:
    def test_init_with_none_context(self):
        dispatcher = EventDispatcher(None)
        assert dispatcher.event_bus is None
        assert dispatcher.gui is None

    def test_init_with_event_bus(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        assert dispatcher.event_bus is bus

    def test_require_gui_raises_when_none(self):
        dispatcher = EventDispatcher(None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()

    def test_mode_no_params(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.APP_CLOSE, handler, mode=EventDispatcher.MODE_NO_PARAMS
        )
        bus.publish(UIEvents.APP_CLOSE, {})

        handler.assert_called_once_with()

    def test_mode_kwargs_all(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES, handler, mode=EventDispatcher.MODE_KWARGS_ALL
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with(video_path="/path/v.mp4")

    def test_mode_kwargs_get(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path"],
            mode=EventDispatcher.MODE_KWARGS_GET,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with(video_path="/path/v.mp4")

    def test_mode_positional(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path"],
            mode=EventDispatcher.MODE_POSITIONAL,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with("/path/v.mp4")

    def test_mode_positional_optional(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()

        dispatcher.register_handler(
            UIEvents.ZONE_COPY_ZONES,
            handler,
            param_names=["video_path", "missing_param"],
            mode=EventDispatcher.MODE_POSITIONAL_OPTIONAL,
        )
        bus.publish(UIEvents.ZONE_COPY_ZONES, {"video_path": "/path/v.mp4"})

        handler.assert_called_once_with("/path/v.mp4", None)

    def test_handler_exception_is_caught_and_logged(self):
        bus = EventBusV2()
        dispatcher = EventDispatcher(bus)
        bad_handler = MagicMock(side_effect=ValueError("Handler failed"))

        dispatcher.register_handler(
            UIEvents.APP_CLOSE, bad_handler, mode=EventDispatcher.MODE_NO_PARAMS
        )
        # Should not raise exception out of publish
        bus.publish(UIEvents.APP_CLOSE, {})
        bad_handler.assert_called_once()

    def test_has_meaningful_analysis_metadata(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "A"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": "01"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "Zeb1"}) is True
        assert (
            EventDispatcher._has_meaningful_analysis_metadata({"group": None, "day": ""}) is False
        )
        assert EventDispatcher._has_meaningful_analysis_metadata({}) is False

    def test_finish_drawing_is_interactive_edit(self):
        mock_gui = MagicMock()
        mock_gui.canvas_manager.current_editing_zone = "arena"
        mock_gui.edited_polygon_points = [(0, 0), (10, 10)]
        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is True

        mock_gui.edited_polygon_points = []
        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is False


@dataclass
class SamplePayloadPart3:
    project_id: str

    count: int


class TestEventDispatcherExtended3:
    def test_payload_modes_constants(self):
        assert EventDispatcher.MODE_NO_PARAMS == "no_params"
        assert EventDispatcher.MODE_KWARGS_ALL == "kwargs_all"
        assert EventDispatcher.MODE_KWARGS_GET == "kwargs_get"
        assert EventDispatcher.MODE_POSITIONAL == "positional"
        assert EventDispatcher.MODE_POSITIONAL_OPTIONAL == "positional_optional"

    def test_payload_to_dict_with_dict_and_dataclass(self):
        d = {"name": "test", "value": 10}
        assert _payload_to_dict(d) == d

        sample = SamplePayloadPart3(project_id="prj_1", count=42)
        res = _payload_to_dict(sample)
        assert res == {"project_id": "prj_1", "count": 42}

        assert _payload_to_dict("invalid_type") == {}

    def test_payload_get_with_dict_and_dataclass(self):
        d = {"alpha": "val1"}
        assert _payload_get(d, "alpha") == "val1"
        assert _payload_get(d, "beta", "default_val") == "default_val"

        sample = SamplePayloadPart3(project_id="prj_2", count=99)
        assert _payload_get(sample, "project_id") == "prj_2"
        assert _payload_get(sample, "missing_field", "fallback") == "fallback"

    def test_require_gui_raises_when_gui_is_none(self):
        dispatcher = EventDispatcher(context=None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()


class TestEventDispatcherExtended4:
    def test_context_detection_gui(self):
        gui = MagicMock()
        gui.event_bus = MagicMock()
        del gui.subscribe  # ensure it's treated as gui

        dispatcher = EventDispatcher(gui)
        assert dispatcher.gui is gui
        assert dispatcher.event_bus is gui.event_bus

    def test_context_detection_event_bus(self):
        eb = MagicMock()
        eb.subscribe = MagicMock()

        dispatcher = EventDispatcher(eb)
        assert dispatcher.gui is None
        assert dispatcher.event_bus is eb

    def test_require_gui_guard(self):
        dispatcher = EventDispatcher(None)
        with pytest.raises(RuntimeError, match="requires ApplicationGUI"):
            dispatcher._require_gui()


@dataclass
class MockPayload:
    param1: str

    param2: int


class TestEventDispatcherExtended5:
    def test_payload_to_dict_dict(self):
        d = {"name": "unit_test", "code": 100}
        assert _payload_to_dict(d) == d

    def test_payload_to_dict_dataclass(self):
        payload = MockPayload(param1="hello", param2=42)
        converted = _payload_to_dict(payload)
        assert converted == {"param1": "hello", "param2": 42}

    def test_payload_to_dict_invalid(self):
        assert _payload_to_dict(None) == {}
        assert _payload_to_dict("string_payload") == {}
        assert _payload_to_dict(12345) == {}

    def test_payload_get_dataclass(self):
        payload = MockPayload(param1="test_val", param2=10)
        assert _payload_get(payload, "param1") == "test_val"
        assert _payload_get(payload, "param2") == 10
        assert _payload_get(payload, "nonexistent", "fallback") == "fallback"

    def test_initial_handlers_empty(self):
        dispatcher = EventDispatcher(context=None)
        assert dispatcher.handlers == {}
        assert dispatcher.event_bus is None
        assert dispatcher.gui is None


class TestEventDispatcherExtended6:
    def test_has_meaningful_analysis_metadata_empty(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({}) is False
        assert EventDispatcher._has_meaningful_analysis_metadata({"unknown": "val"}) is False

    def test_has_meaningful_analysis_metadata_valid(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "Control"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": "1"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "FishA"}) is True

    def test_finish_drawing_is_interactive_edit(self):
        gui = MagicMock()
        gui.canvas_manager.current_editing_zone = "zone_1"
        gui.edited_polygon_points = [(10, 10), (20, 20)]

        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is True

        gui.edited_polygon_points = []
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is False

    def test_run_on_ui_thread_fallback(self):
        dispatcher = object.__new__(EventDispatcher)
        gui = MagicMock()
        gui.root = None
        dispatcher.gui = gui

        called = False

        def cb():
            nonlocal called
            called = True

        dispatcher._run_on_ui_thread(cb)
        assert called is True


class TestEventDispatcherExtended7:
    def test_require_gui_raises_when_none(self):
        dispatcher = object.__new__(EventDispatcher)
        dispatcher.gui = None

        with pytest.raises(RuntimeError, match="requires ApplicationGUI context"):
            dispatcher._require_gui()

    def test_require_gui_returns_gui(self):
        dispatcher = object.__new__(EventDispatcher)
        mock_gui = MagicMock()
        dispatcher.gui = mock_gui

        assert dispatcher._require_gui() is mock_gui

    def test_finish_drawing_is_interactive_edit_no_points(self):
        mock_gui = MagicMock()
        mock_gui.current_editing_zone = "arena"
        mock_gui.edited_polygon_points = []

        assert EventDispatcher._finish_drawing_is_interactive_edit(mock_gui) is False

    def test_has_meaningful_analysis_metadata_keys(self):
        assert EventDispatcher._has_meaningful_analysis_metadata({"group": "Control"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"day": 1}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"subject": "Fish1"}) is True
        assert EventDispatcher._has_meaningful_analysis_metadata({"extra_field": "val"}) is False


@dataclass
class SamplePayloadPart8:
    name: str

    count: int


class TestEventDispatcherExtended8:
    def test_payload_to_dict_dataclass(self):
        sample = SamplePayloadPart8(name="test", count=5)
        d = _payload_to_dict(sample)
        assert d == {"name": "test", "count": 5}

    def test_payload_to_dict_dict(self):
        sample = {"a": 1, "b": 2}
        assert _payload_to_dict(sample) == {"a": 1, "b": 2}

    def test_payload_to_dict_fallback(self):
        assert _payload_to_dict("non_dict") == {}

    def test_payload_get_dataclass(self):
        sample = SamplePayloadPart8(name="zebrafish", count=10)
        assert _payload_get(sample, "name") == "zebrafish"
        assert _payload_get(sample, "missing", "default") == "default"

    def test_payload_get_dict(self):
        sample = {"val": 42}
        assert _payload_get(sample, "val") == 42
        assert _payload_get(sample, "nonexistent", 0) == 0


class TestEventDispatcherExtended9:
    def test_event_dispatcher_init_empty_handlers(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)

        assert dispatcher.handlers == {}
        assert dispatcher.event_bus is bus

    def test_event_dispatcher_gui_context_detection(self):
        gui = MagicMock(spec=["event_bus"])
        gui.event_bus = MagicMock()
        dispatcher = EventDispatcher(gui)
        assert dispatcher.gui is gui
        assert dispatcher.event_bus is gui.event_bus

    def test_event_dispatcher_handlers_dict_access(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)
        handler = MagicMock()
        dispatcher.handlers["CUSTOM_EVENT"] = handler

        assert "CUSTOM_EVENT" in dispatcher.handlers
        assert dispatcher.handlers["CUSTOM_EVENT"] is handler


class TestEventDispatcherExtended10:
    def test_event_dispatcher_none_context(self):
        dispatcher = EventDispatcher(None)
        assert dispatcher.gui is None
        assert dispatcher.event_bus is None
        assert dispatcher.handlers == {}

    def test_event_dispatcher_with_event_bus_context(self):
        bus = MagicMock()
        dispatcher = EventDispatcher(bus)
        assert dispatcher.event_bus is bus
        assert dispatcher.gui is None

    def test_event_dispatcher_handlers_dict_operations(self):
        dispatcher = EventDispatcher(None)
        handler_fn = MagicMock()
        dispatcher.handlers["custom_event"] = handler_fn
        assert "custom_event" in dispatcher.handlers
        assert dispatcher.handlers["custom_event"] == handler_fn

    def test_payload_to_dict_with_dict(self):
        data = {"key": "value"}
        assert _payload_to_dict(data) == {"key": "value"}

    def test_payload_get_with_dict(self):
        data = {"key": "value"}
        assert _payload_get(data, "key") == "value"
        assert _payload_get(data, "missing", default=123) == 123


# ---------------------------------------------------------------------------
# Worker-thread safety: these two events arrive off the Tk main thread.
# ---------------------------------------------------------------------------


class _DeferringRoot:
    """Tk root stub that QUEUES ``after`` callbacks instead of running them.

    A MagicMock root would swallow the difference: ``root.after(0, cb)`` records
    the call and never runs ``cb``, so a handler that mutates Tk directly and one
    that marshals correctly look identical. Queuing makes the distinction
    observable — nothing may happen before ``run_pending``.
    """

    def __init__(self) -> None:
        self.pending: list = []

    def after(self, _delay, callback):
        self.pending.append(callback)
        return "after#1"

    def run_pending(self) -> None:
        pending, self.pending = self.pending, []
        for callback in pending:
            callback()


def _marshalling_gui():
    return SimpleNamespace(
        root=_DeferringRoot(),
        status_var=MagicMock(),
        video_selector_manager=MagicMock(),
    )


def _dispatcher_with(gui):
    """Wire a real EventBusV2 into a stub GUI and subscribe the UI table."""
    bus = EventBusV2()
    gui.event_bus = bus
    dispatcher = EventDispatcher(gui)
    dispatcher.subscribe_to_ui_events()
    return dispatcher, bus


def test_set_status_is_marshalled_to_the_tk_thread():
    """``StringVar.set`` is a Tcl call; Tcl is single-threaded.

    Published from the ProcessingMonitor thread while reports are generated, and
    from LiveSessionManager during a live session.
    """
    gui = _marshalling_gui()
    _dispatcher, bus = _dispatcher_with(gui)

    bus.publish(UIEvents.UI_SET_STATUS, payloads.StatusPayload(message="Generating..."))

    gui.status_var.set.assert_not_called()
    gui.root.run_pending()
    gui.status_var.set.assert_called_once_with("Generating...")


def test_set_status_alias_is_marshalled_too():
    """``SET_STATUS`` (no ``UI_`` prefix) must get the SAME marshalled handler.

    The alias is published by progress_notifier, tracking_session_runner and
    analysis_control_view_model — all worker-thread call sites. Wiring it to a
    raw ``status_var.set`` would let the unsafe Tcl write back in through the
    side door while the prefixed name still looked fixed.
    """
    gui = _marshalling_gui()
    _dispatcher, bus = _dispatcher_with(gui)

    bus.publish(UIEvents.SET_STATUS, payloads.StatusPayload(message="Cancelling..."))

    gui.status_var.set.assert_not_called()
    gui.root.run_pending()
    gui.status_var.set.assert_called_once_with("Cancelling...")


def test_refresh_project_views_is_marshalled_to_the_tk_thread():
    """``refresh_project_views`` rebuilds Treeview rows synchronously."""
    gui = _marshalling_gui()
    _dispatcher, bus = _dispatcher_with(gui)

    bus.publish(
        UIEvents.UI_REFRESH_PROJECT_VIEWS,
        payloads.ProjectViewsRefreshRequestedPayload(reason="reg", immediate=True),
    )

    gui.video_selector_manager.refresh_project_views.assert_not_called()
    gui.root.run_pending()
    gui.video_selector_manager.refresh_project_views.assert_called_once_with(
        reason="reg", append_summary=False, immediate=True
    )


def test_refresh_payload_uses_immediate_not_imm():
    """``imm`` is a dead alias on the payload — nothing reads it.

    ``_ensure_single_video_registered`` was the lone publisher spelling it that
    way, so its "refresh now" request silently arrived as ``immediate=False``.
    """
    payload = payloads.ProjectViewsRefreshRequestedPayload(reason="reg", imm=True)
    gui = _marshalling_gui()
    _dispatcher, bus = _dispatcher_with(gui)

    bus.publish(UIEvents.UI_REFRESH_PROJECT_VIEWS, payload)
    gui.root.run_pending()

    _args, kwargs = gui.video_selector_manager.refresh_project_views.call_args
    assert kwargs["immediate"] is False, "imm= must not be mistaken for immediate="

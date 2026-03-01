from typing import Any, cast

import pytest

from zebtrack.ui import gui


class _Dummy:
    def __init__(self, *a, **k):
        pass


class _DummyWithBus(_Dummy):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.event_bus = None


class _EventDispatcherDummy(_DummyWithBus):
    def register_event_bus_handlers(self):
        return None

    def subscribe_to_ui_events(self):
        return None

    def schedule_event_bus_poll(self):
        return None


class _StateSynchronizerDummy(_Dummy):
    def subscribe_to_state_changes(self):
        return None


class _WidgetFactoryDummy(_Dummy):
    def create_welcome_frame(self):
        return None


class _MenuDummy(_Dummy):
    def create_menu_bar(self):
        return None


class _RootStub:
    def title(self, *a, **k):
        return None

    def protocol(self, *a, **k):
        return None

    def after(self, *a, **k):
        return None

    def configure(self, *a, **k):
        return None


@pytest.mark.gui
def test_application_gui_wiring(monkeypatch):
    # Replace heavy UI components with no-ops to validate wiring only
    monkeypatch.setattr(gui, "MenuManager", _MenuDummy)
    monkeypatch.setattr(gui, "CanvasManager", _Dummy)
    monkeypatch.setattr(gui, "StateSynchronizer", _StateSynchronizerDummy)
    monkeypatch.setattr(gui, "EventDispatcher", _EventDispatcherDummy)
    monkeypatch.setattr(gui, "ValidationManager", _Dummy)
    monkeypatch.setattr(gui, "DialogManager", _Dummy)
    monkeypatch.setattr(gui, "WidgetFactory", _WidgetFactoryDummy)
    monkeypatch.setattr(gui, "VideoSelectorTreeManager", _Dummy)
    monkeypatch.setattr(gui, "ReportsTreeManager", _Dummy)
    monkeypatch.setattr(gui, "UICoordinator", _Dummy)
    monkeypatch.setattr(gui, "DrawingStateManager", _Dummy)
    monkeypatch.setattr(gui, "PolygonDrawingService", _Dummy)
    monkeypatch.setattr(gui, "ROITemplateManager", _Dummy)
    monkeypatch.setattr(gui, "TabBuilder", _Dummy)
    monkeypatch.setattr(gui, "ZoneControlBuilder", _Dummy)
    monkeypatch.setattr(gui, "ButtonFactory", _Dummy)
    monkeypatch.setattr(gui, "PanelBuilder", _Dummy)

    root = _RootStub()
    controller = cast(Any, _Dummy())
    controller.on_close = lambda *a, **k: None

    from unittest.mock import MagicMock

    mock_event_bus = MagicMock()
    app = gui.ApplicationGUI(root=root, controller=controller, event_bus=mock_event_bus)

    assert app.root is root
    assert app.controller is controller
    assert hasattr(app, "event_bus_v2")

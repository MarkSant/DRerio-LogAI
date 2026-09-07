"""Tests for BaseWidget behavior."""

from tkinter import ttk
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus_v2 import UIEvents


class _DummyWidget(BaseWidget):
    def _build_ui(self) -> None:
        self.button = ttk.Button(self, text="Test")
        self.button.pack()


@pytest.mark.gui
def test_emit_event_without_bus(tkinter_root):
    widget = _DummyWidget(tkinter_root, event_bus=None)

    widget.emit_event(UIEvents.SHOW_INFO, {"a": 1})

    # No event bus, should not raise


@pytest.mark.gui
def test_emit_event_with_bus(tkinter_root):
    """emit_event with a UIEvents enum calls event_bus.publish(Event(...))."""
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)

    widget.emit_event(UIEvents.FRAME_ERROR, {"a": 1})

    event_bus.publish.assert_called_once_with(UIEvents.FRAME_ERROR, {"a": 1})


@pytest.mark.gui
def test_bind_callback_with_bus(tkinter_root):
    """bind_callback with a UIEvents enum calls event_bus.subscribe(UIEvents.XXX, handler)."""
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)
    handler = Mock()

    widget.bind_callback(UIEvents.FRAME_ERROR, handler)

    event_bus.subscribe.assert_called_once_with(UIEvents.FRAME_ERROR, handler)


@pytest.mark.gui
def test_set_enabled_updates_children(tkinter_root):
    widget = _DummyWidget(tkinter_root, event_bus=None)

    widget.set_enabled(False)
    assert str(widget.button.cget("state")) == "disabled"

    widget.set_enabled(True)
    assert str(widget.button.cget("state")) == "normal"


@pytest.mark.gui
def test_destroy_unsubscribes_what_the_widget_bound(tkinter_root):
    """A inscricao nao pode sobreviver ao widget.

    ``create_main_control_frame`` reconstroi o notebook inteiro a cada
    abertura/fechamento de projeto. Sem esta desinscricao o widget antigo
    continua assinado para sempre e o proximo evento entrega o payload a um
    objeto cuja arvore Tk nao existe mais -- o ``TclError: bad window path
    name`` que o bus publica como ``event_bus_v2.handler_failed``.
    """
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)
    handler = Mock()
    widget.bind_callback(UIEvents.FRAME_ERROR, handler)

    widget.destroy()

    event_bus.unsubscribe.assert_called_once_with(UIEvents.FRAME_ERROR, handler)


@pytest.mark.gui
def test_destroying_the_parent_unsubscribes_the_child(tkinter_root):
    """O caso REAL: ninguem destroi o painel, destroi-se a aba que o contem.

    Tk cascateia ``destroy()`` do pai para os filhos pelo lado Python, entao a
    desinscricao alcanca o widget mesmo quando so o container e destruido --
    que e exatamente o que ``tab_builder`` faz.
    """
    event_bus = Mock()
    container = ttk.Frame(tkinter_root)
    widget = _DummyWidget(container, event_bus=event_bus)
    handler = Mock()
    widget.bind_callback(UIEvents.FRAME_ERROR, handler)

    container.destroy()

    event_bus.unsubscribe.assert_called_once_with(UIEvents.FRAME_ERROR, handler)


@pytest.mark.gui
def test_destroy_only_drops_what_bind_callback_registered(tkinter_root):
    """Uma inscricao feita direto no bus por outro objeto nao e nossa para cancelar."""
    event_bus = Mock()
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)
    someone_elses = Mock()
    event_bus.subscribe(UIEvents.FRAME_ERROR, someone_elses)  # sem bind_callback

    widget.destroy()

    event_bus.unsubscribe.assert_not_called()


@pytest.mark.gui
def test_destroy_survives_a_bus_that_refuses_to_unsubscribe(tkinter_root):
    """Degrada: uma falha na limpeza nao pode impedir a destruicao do widget."""
    event_bus = Mock()
    event_bus.unsubscribe.side_effect = RuntimeError("bus caiu")
    widget = _DummyWidget(tkinter_root, event_bus=event_bus)
    widget.bind_callback(UIEvents.FRAME_ERROR, Mock())

    widget.destroy()  # nao levanta

    assert not widget.winfo_exists()


@pytest.mark.gui
def test_destroy_is_safe_without_a_bus(tkinter_root):
    widget = _DummyWidget(tkinter_root, event_bus=None)

    widget.destroy()

    assert not widget.winfo_exists()

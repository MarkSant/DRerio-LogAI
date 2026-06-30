"""GUI tests for ArduinoBindingsPanel (per-zone Arduino command editor)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TypeVar
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.components.arduino_bindings_panel import ArduinoBindingsPanel

_T = TypeVar("_T")


def _nn(value: _T | None) -> _T:
    """Assert a panel widget reference is built, narrowing Optional for mypy."""
    assert value is not None
    return value


def _make_controller(project_data, roi_names, *, project_type="live", project_path="/proj"):
    pm = MagicMock()
    pm.project_data = project_data
    pm.get_project_type.return_value = project_type
    pm.get_zone_data.return_value = SimpleNamespace(roi_names=roi_names)
    pm.project_path = project_path
    pm.save_project = MagicMock()
    return SimpleNamespace(project_manager=pm), pm


@pytest.mark.gui
class TestArduinoBindingsPanel:
    def test_hidden_when_arduino_disabled(self, tkinter_root):
        controller, _pm = _make_controller({"use_arduino": False}, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        # Editor frame not shown; note is shown instead.
        assert not _nn(panel._frame).winfo_ismapped()

    def test_populates_roi_dropdown_when_enabled(self, tkinter_root):
        controller, _pm = _make_controller({"use_arduino": True}, ["Direita", "Esquerda"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        assert list(_nn(panel._roi_combo)["values"]) == ["Direita", "Esquerda"]

    def test_add_binding_persists_and_saves(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, pm = _make_controller(pd, ["Direita"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("Direita")
        panel.enter_token.set("1")
        panel.exit_token.set("2")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [{"roi": "Direita", "on_enter": 1, "on_exit": 2}]
        pm.save_project.assert_called_once()
        assert len(_nn(panel._tree).get_children()) == 1

    def test_add_requires_at_least_one_token(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, pm = _make_controller(pd, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("A")
        panel.enter_token.set("")
        panel.exit_token.set("")
        panel._add_or_update()

        assert "arduino_bindings" not in pd
        pm.save_project.assert_not_called()

    def test_update_existing_roi_in_place(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, _pm = _make_controller(pd, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("A")
        panel.enter_token.set("1")
        panel._add_or_update()
        panel.roi_choice.set("A")
        panel.enter_token.set("5")
        panel.exit_token.set("6")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [{"roi": "A", "on_enter": 5, "on_exit": 6}]
        assert len(_nn(panel._tree).get_children()) == 1

    def test_clear_removes_all(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "A", "on_enter": 1, "on_exit": 2}]}
        controller, _pm = _make_controller(pd, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        assert len(_nn(panel._tree).get_children()) == 1

        panel._clear()
        assert pd["arduino_bindings"] == []
        assert len(_nn(panel._tree).get_children()) == 0

    def test_loads_existing_bindings(self, tkinter_root):
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "A", "on_enter": 1, "on_exit": 2},
                {"roi": "B", "on_enter": 3, "on_exit": 4},
            ],
        }
        controller, _pm = _make_controller(pd, ["A", "B"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        assert set(_nn(panel._tree).get_children()) == {"A", "B"}

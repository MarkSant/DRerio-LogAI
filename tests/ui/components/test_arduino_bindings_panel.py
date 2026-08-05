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


def _is_packed(widget) -> bool:
    """True when the widget is currently managed by pack().

    ``winfo_ismapped()`` is useless here: the panel is never gridded into a
    visible toplevel in tests, so every widget reports unmapped. The geometry
    manager, on the other hand, reflects pack()/pack_forget() exactly.
    """
    return bool(widget.winfo_manager())


def _make_controller(
    project_data,
    roi_names,
    *,
    project_type="live",
    project_path="/proj",
    arduino_manager=None,
):
    pm = MagicMock()
    pm.project_data = project_data
    pm.get_project_type.return_value = project_type
    pm.get_zone_data.return_value = SimpleNamespace(roi_names=roi_names)
    pm.project_path = project_path
    pm.save_project = MagicMock()
    return (
        SimpleNamespace(project_manager=pm, arduino_manager=arduino_manager, root=None),
        pm,
    )


def _fake_manager(acks_by_token, *, connected=True):
    """Stand-in ArduinoManager whose probe answers like the reference sketch."""
    manager = MagicMock()
    manager.is_connected.return_value = connected
    manager.probe_tokens.side_effect = lambda tokens, **kw: [
        (t, acks_by_token.get(t)) for t in tokens
    ]
    return manager


SKETCH_ACKS = {
    1: "Red LED 1 ON",
    2: "Red LED 1 OFF",
    3: "Blue LED ON",
    4: "Blue LED OFF",
    5: "Green LED ON",
    6: "Green LED OFF",
    7: "Red LED 2 ON",
    8: "Red LED 2 OFF",
}


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

    def test_out_of_range_token_rejected(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, pm = _make_controller(pd, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("A")
        panel.enter_token.set("999")  # > TOKEN_MAX (255) -> rejected, no save
        panel._add_or_update()

        assert "arduino_bindings" not in pd
        pm.save_project.assert_not_called()

    def test_non_numeric_token_rejected(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, pm = _make_controller(pd, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("A")
        panel.enter_token.set("abc")
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

    def test_conflict_warning_hidden_for_disjoint_tokens(self, tkinter_root):
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
        assert not _is_packed(_nn(panel._conflict_label))

    def test_conflict_warning_shown_for_ambiguous_token(self, tkinter_root):
        """Loading the off-by-one layout that latched a LED on must warn."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z2", "on_enter": 3, "on_exit": 4},
                {"roi": "Z3", "on_enter": 4, "on_exit": 5},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z2", "Z3"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        label = _nn(panel._conflict_label)
        assert _is_packed(label)
        text = label.cget("text")
        assert "4" in text
        assert "Z2" in text and "Z3" in text

    def test_probe_plan_flattens_bindings_in_order(self, tkinter_root):
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2},
                {"roi": "Z2", "on_enter": 3},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1", "Z2"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        assert panel._probe_plan() == [
            ("Z1", "enter", 1),
            ("Z1", "exit", 2),
            ("Z2", "enter", 3),
        ]

    def test_test_bindings_reports_correct_layout_as_ok(self, tkinter_root):
        """The canonical layout: every enter answers ON, every exit answers OFF."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2},
                {"roi": "Z2", "on_enter": 3, "on_exit": 4},
            ],
        }
        manager = _fake_manager(SKETCH_ACKS)
        controller, _pm = _make_controller(pd, ["Z1", "Z2"], arduino_manager=manager)
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        results = [
            (("Z1", "enter", 1), (1, "Red LED 1 ON")),
            (("Z1", "exit", 2), (2, "Red LED 1 OFF")),
        ]
        panel._finish_test(results, None)

        text = _nn(panel._test_output).cget("text")
        assert "✓" in text
        assert "⚠" not in text
        assert "Red LED 1 ON" in text

    def test_test_bindings_flags_the_inverted_layout(self, tkinter_root):
        """Regression: Z1=1/5 — the exit token answers 'Green LED ON'."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [{"roi": "Z1", "on_enter": 1, "on_exit": 5}],
        }
        manager = _fake_manager(SKETCH_ACKS)
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=manager)
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        results = [
            (("Z1", "enter", 1), (1, "Red LED 1 ON")),
            (("Z1", "exit", 5), (5, "Green LED ON")),
        ]
        panel._finish_test(results, None)

        text = _nn(panel._test_output).cget("text")
        assert "⚠" in text
        assert "Green LED ON" in text
        assert "1 problema(s)" in text

    def test_test_bindings_reports_missing_ack(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=_fake_manager({}))
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel._finish_test([(("Z1", "enter", 1), (1, None))], None)

        assert "sem resposta" in _nn(panel._test_output).cget("text")

    def test_test_bindings_without_arduino_connected(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        manager = _fake_manager(SKETCH_ACKS, connected=False)
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=manager)
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.test_bindings()

        assert "não conectado" in _nn(panel._test_output).cget("text")
        manager.probe_tokens.assert_not_called()

    def test_test_bindings_surfaces_probe_error(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=_fake_manager({}))
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel._finish_test(None, "sessão ao vivo em andamento")

        assert "sessão ao vivo" in _nn(panel._test_output).cget("text")
        # ttk returns a Tcl object here, not a plain str — compare the text form.
        assert str(_nn(panel._test_button).cget("state")) == "normal"

    def test_conflict_warning_clears_after_fixing_tokens(self, tkinter_root):
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z2", "on_enter": 3, "on_exit": 4},
                {"roi": "Z3", "on_enter": 4, "on_exit": 5},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z2", "Z3"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        assert _is_packed(_nn(panel._conflict_label))

        panel.roi_choice.set("Z3")
        panel.enter_token.set("5")
        panel.exit_token.set("6")
        panel._add_or_update()
        tkinter_root.update_idletasks()

        assert not _is_packed(_nn(panel._conflict_label))

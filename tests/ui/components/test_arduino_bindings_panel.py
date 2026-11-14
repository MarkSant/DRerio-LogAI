"""GUI tests for ArduinoBindingsPanel (per-zone Arduino command editor)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, TypeVar
from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection.detection_types import AquariumData, MultiAquariumZoneData
from zebtrack.core.services.arduino_bindings import ArduinoBinding
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
    aquarium_rois=None,
):
    """``aquarium_rois`` = one ROI-name list per aquarium (ids 0, 1, ...).

    ``None`` = a single-aquarium project: ``get_multi_aquarium_zone_data``
    answers ``None``, exactly like a live project without a split.
    """
    pm = MagicMock()
    pm.project_data = project_data
    pm.get_project_type.return_value = project_type
    pm.get_zone_data.return_value = SimpleNamespace(roi_names=roi_names)
    pm.project_path = project_path
    pm.save_project = MagicMock()
    pm.get_multi_aquarium_zone_data.return_value = (
        None
        if aquarium_rois is None
        else MultiAquariumZoneData(
            aquariums=[
                AquariumData(id=index, roi_names=list(names))
                for index, names in enumerate(aquarium_rois)
            ]
        )
    )
    # No ``root`` here on purpose: the panel schedules UI work through its own
    # ``self.after`` (it is a Tk widget), never through the controller.
    return SimpleNamespace(project_manager=pm, arduino_manager=arduino_manager), pm


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

        assert pd["arduino_bindings"] == [
            {"roi": "Direita", "on_enter": 1, "on_exit": 2, "label": None}
        ]
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

        assert pd["arduino_bindings"] == [{"roi": "A", "on_enter": 5, "on_exit": 6, "label": None}]
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
        assert set(_nn(panel._tree).get_children()) == {
            ArduinoBindingsPanel._row_iid(None, "A"),
            ArduinoBindingsPanel._row_iid(None, "B"),
        }

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

    def test_label_is_persisted_with_the_binding(self, tkinter_root):
        pd = {"use_arduino": True}
        controller, _pm = _make_controller(pd, ["Z1"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("Z1")
        panel.enter_token.set("1")
        panel.exit_token.set("2")
        panel.device_label.set("Choque")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": "Choque"}
        ]

    def test_blank_label_is_not_persisted(self, tkinter_root):
        # Annotated: inferred as dict[str, bool] otherwise, so indexing the
        # bindings list below fails type checking.
        pd: dict[str, Any] = {"use_arduino": True}
        controller, _pm = _make_controller(pd, ["Z1"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("Z1")
        panel.enter_token.set("1")
        panel.device_label.set("   ")
        panel._add_or_update()

        assert pd["arduino_bindings"][0]["label"] is None

    def test_selecting_a_row_loads_its_label(self, tkinter_root):
        pd = {
            "use_arduino": True,
            "arduino_bindings": [{"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": "Bomba"}],
        }
        controller, _pm = _make_controller(pd, ["Z1"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        _nn(panel._tree).selection_set(ArduinoBindingsPanel._row_iid(None, "Z1"))
        panel._on_select()

        assert panel.device_label.get() == "Bomba"
        assert panel.enter_token.get() == "1"

    def test_probe_plan_uses_the_label_when_present(self, tkinter_root):
        """The result lines must name what is wired, not the sketch's channel."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": "Choque"},
                {"roi": "Z2", "on_enter": 3},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1", "Z2"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        # The DEVICE leads and the ROI qualifies it: the operator reads the
        # line looking for what is physically wired, not for the zone id.
        assert panel._probe_plan() == [
            ("Choque [Z1]", "enter", 1),
            ("Choque [Z1]", "exit", 2),
            ("Z2", "enter", 3),
        ]

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

    def test_result_line_leads_with_the_device_not_the_firmware_name(self, tkinter_root):
        """The operator's "Dispositivo" must name the channel, not the sketch.

        "Red LED 1 ON" is printed by the sketch (Program_Final.ino) and is wrong
        the moment that pin drives a relay or a pump. It used to be appended
        bare, sitting exactly where a device name goes — and with an empty
        Device field it was the ONLY name on the line.
        """
        pd = {
            "use_arduino": True,
            "arduino_bindings": [{"roi": "Z1", "on_enter": 1, "label": "Choque"}],
        }
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=_fake_manager(SKETCH_ACKS))
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel._finish_test([(("Choque [Z1]", "enter", 1), (1, "Red LED 1 ON"))], None)

        text = _nn(panel._test_output).cget("text")
        # Device leads; the ACK is still shown but explicitly attributed.
        assert text.index("Choque") < text.index("Red LED 1 ON")
        assert "firmware" in text.lower()
        assert '"Red LED 1 ON"' in text

    def test_result_explains_where_the_quoted_name_comes_from(self, tkinter_root):
        """Otherwise the operator keeps expecting the Device field to change it."""
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=_fake_manager(SKETCH_ACKS))
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel._finish_test([(("Z1", "enter", 1), (1, "Red LED 1 ON"))], None)

        text = _nn(panel._test_output).cget("text")
        assert "sketch" in text.lower()
        assert "Device" in text

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
        assert "1 problem(s)" in text

    def test_test_bindings_reports_missing_ack(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=_fake_manager({}))
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel._finish_test([(("Z1", "enter", 1), (1, None))], None)

        assert "no reply" in _nn(panel._test_output).cget("text")

    def test_test_bindings_without_arduino_connected(self, tkinter_root):
        pd = {"use_arduino": True, "arduino_bindings": [{"roi": "Z1", "on_enter": 1}]}
        manager = _fake_manager(SKETCH_ACKS, connected=False)
        controller, _pm = _make_controller(pd, ["Z1"], arduino_manager=manager)
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.test_bindings()

        assert "not connected" in _nn(panel._test_output).cget("text")
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


@pytest.mark.gui
class TestEmptyProjectData:
    """A just-created project has ``project_data == {}`` — falsy, but the real one (#644).

    ``project_data or {}`` swapped that empty dict for a throwaway one, so the
    binding was written where nobody reads it, ``save_project()`` persisted a
    project without it and the status still said "Configuration saved.".
    """

    def test_binding_saved_on_an_empty_project_is_read_back(self, tkinter_root):
        controller, pm = _make_controller({}, ["Direita"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("Direita")
        panel.enter_token.set("1")
        panel.exit_token.set("2")
        panel._add_or_update()

        assert pm.project_data["arduino_bindings"] == [
            {"roi": "Direita", "on_enter": 1, "on_exit": 2, "label": None}
        ]
        pm.save_project.assert_called_once()

        # A fresh panel on the same project (e.g. after the tab is rebuilt)
        # must load what the first one saved.
        pm.project_data["use_arduino"] = True
        reopened = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        tree = _nn(reopened._tree)
        assert [
            ArduinoBindingsPanel._binding_from_row(tree.item(iid, "values")).roi
            for iid in tree.get_children()
        ] == ["Direita"]

    def test_without_project_data_the_panel_still_works(self, tkinter_root):
        """No ``project_data`` at all (no project open): no crash, nothing to persist into."""
        controller, pm = _make_controller(None, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("A")
        panel.enter_token.set("1")
        panel._add_or_update()

        assert pm.project_data is None


class TestSaveTargetsTheProjectDict:
    """Headless twin of ``TestEmptyProjectData`` (#644), so the mutation run sees it.

    The mutation runner excludes ``gui`` tests; this drives the real ``_save``
    on a widget-less instance (Tk widgets cannot be built headless).
    """

    def test_save_on_an_empty_project_writes_into_the_project_dict(self):
        pm = MagicMock()
        pm.project_data = {}
        pm.project_path = "/proj"
        panel = object.__new__(ArduinoBindingsPanel)
        panel.project_manager = pm
        panel._tree = None
        panel._status = None
        panel._conflict_label = None

        panel._save()

        assert pm.project_data == {"arduino_bindings": []}
        pm.save_project.assert_called_once()


@pytest.mark.gui
class TestPanelOutlivesItsWidgets:
    """A destroyed panel must go quiet, not raise into the caller's ``except``.

    ``tab_builder`` destroys the tab and rebuilds it, and
    ``ApplicationGUI._rebind_project_manager`` can fire in between while still
    holding the previous instance. That produced a full ``TclError`` traceback at
    WARNING on an ordinary project switch:

        bad window path name ".!notebook...!arduinobindingspanel.!label"

    A scary traceback for an expected lifecycle event trains the reader to ignore
    that log line — which is exactly where a REAL panel failure would appear.
    """

    def test_is_alive_flips_after_destroy(self, tkinter_root):
        controller, _pm = _make_controller({"use_arduino": False}, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)

        assert panel.is_alive() is True

        panel.destroy()
        tkinter_root.update_idletasks()

        assert panel.is_alive() is False

    def test_refresh_on_a_destroyed_panel_is_a_no_op(self, tkinter_root):
        controller, _pm = _make_controller({"use_arduino": False}, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        panel.destroy()
        tkinter_root.update_idletasks()

        panel.refresh()  # must not raise TclError

    def test_project_manager_replacement_on_a_destroyed_panel_is_quiet(self, tkinter_root):
        """The exact call path from the reported traceback."""
        controller, _pm = _make_controller({"use_arduino": False}, ["A"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        panel.destroy()
        tkinter_root.update_idletasks()

        new_manager = MagicMock()
        panel.on_project_manager_replaced(new_manager)  # must not raise

        assert panel.project_manager is new_manager, (
            "adopting the new manager must still happen — a panel that is "
            "rebuilt later would otherwise read the CLOSED project"
        )


@pytest.mark.gui
class TestAquariumScope:
    """Bindings scoped to one aquarium survive the panel (#701).

    The #656 backend gave each binding an optional ``aquarium_id``; the panel
    rebuilt the list from a table without that column, so ANY edit made in the
    panel rewrote the bindings unscoped — a device meant for aquarium 2 started
    answering aquarium 1 too, with nothing on screen saying so.
    """

    def test_aquarium_column_hidden_with_a_single_aquarium(self, tkinter_root):
        controller, _pm = _make_controller({"use_arduino": True}, ["Z1"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        assert "aquarium" not in _nn(panel._tree)["displaycolumns"]
        assert not _is_packed(_nn(panel._aquarium_row))

    def test_aquarium_column_shown_with_two_aquariums(self, tkinter_root):
        controller, _pm = _make_controller(
            {"use_arduino": True}, ["Z1"], aquarium_rois=[["Z1"], ["Z1"]]
        )
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        assert _nn(panel._tree)["displaycolumns"][0] == "aquarium"
        assert _is_packed(_nn(panel._aquarium_row))
        assert list(_nn(panel._aquarium_combo)["values"]) == ["All", "1", "2"]
        assert panel.aquarium_choice.get() == "All"

    def test_multi_aquarium_zones_come_from_the_live_reference_frame(self, tkinter_root):
        """Same key the live session reads (``live_camera_reference_frame.png``)."""
        controller, pm = _make_controller(
            {"use_arduino": True}, ["Z1"], aquarium_rois=[["Z1"], ["Z1"]]
        )
        ArduinoBindingsPanel(tkinter_root, controller)

        (path,), _kwargs = pm.get_multi_aquarium_zone_data.call_args
        assert str(path).replace("\\", "/") == "/proj/live_camera_reference_frame.png"

    def test_roi_list_follows_the_chosen_aquarium(self, tkinter_root):
        controller, _pm = _make_controller(
            {"use_arduino": True}, ["Z1", "Z2"], aquarium_rois=[["Z1", "Z2"], ["Z1", "Z3"]]
        )
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        combo = _nn(panel._roi_combo)

        # "All" offers every name once, in first-seen order.
        assert list(combo["values"]) == ["Z1", "Z2", "Z3"]

        panel.aquarium_choice.set("2")
        panel.refresh_roi_choices()
        assert list(combo["values"]) == ["Z1", "Z3"]

        panel.roi_choice.set("Z3")
        panel.aquarium_choice.set("1")
        panel.refresh_roi_choices()
        assert list(combo["values"]) == ["Z1", "Z2"]
        # Z3 does not exist in aquarium 1: the choice must not keep pointing at it.
        assert panel.roi_choice.get() == "Z1"

    def test_json_with_aquarium_id_survives_an_edit_from_the_panel(self, tkinter_root):
        """Load scoped bindings, edit one in the panel, save: nothing lost."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 1},
                {"roi": "Z2", "on_enter": 3, "on_exit": 4, "label": None},
            ],
        }
        controller, pm = _make_controller(
            pd, ["Z1", "Z2"], aquarium_rois=[["Z1", "Z2"], ["Z1", "Z2"]]
        )
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        _nn(panel._tree).selection_set(ArduinoBindingsPanel._row_iid(1, "Z1"))
        panel._on_select()
        assert panel.aquarium_choice.get() == "2"
        panel.device_label.set("Choque")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": "Choque", "aquarium_id": 1},
            {"roi": "Z2", "on_enter": 3, "on_exit": 4, "label": None},
        ]
        pm.save_project.assert_called_once()
        assert len(_nn(panel._tree).get_children()) == 2

    def test_scope_survives_saving_while_the_column_is_hidden(self, tkinter_root):
        """A scoped JSON opened where the split is not visible is still not rewritten."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 0},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1", "Z2"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.roi_choice.set("Z2")
        panel.aquarium_choice.set("All")
        panel.enter_token.set("3")
        panel.exit_token.set("4")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 0},
            {"roi": "Z2", "on_enter": 3, "on_exit": 4, "label": None},
        ]

    def test_editing_a_scoped_row_while_the_column_is_hidden_keeps_its_scope(self, tkinter_root):
        """Selecting the row fills the hidden picker; the edit must not unscope it."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 1},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1"])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        _nn(panel._tree).selection_set(ArduinoBindingsPanel._row_iid(1, "Z1"))
        panel._on_select()
        panel.exit_token.set("6")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 6, "label": None, "aquarium_id": 1},
        ]
        assert len(_nn(panel._tree).get_children()) == 1

    def test_homonymous_rois_in_two_aquariums_are_two_rows(self, tkinter_root):
        """Same ROI name, different aquarium: two bindings, never one overwritten row."""
        pd: dict[str, Any] = {"use_arduino": True}
        controller, _pm = _make_controller(pd, ["Z1"], aquarium_rois=[["Z1"], ["Z1"]])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.aquarium_choice.set("1")
        panel.roi_choice.set("Z1")
        panel.enter_token.set("1")
        panel.exit_token.set("2")
        panel._add_or_update()

        panel.aquarium_choice.set("2")
        panel.roi_choice.set("Z1")
        panel.enter_token.set("3")
        panel.exit_token.set("4")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 0},
            {"roi": "Z1", "on_enter": 3, "on_exit": 4, "label": None, "aquarium_id": 1},
        ]
        assert len(_nn(panel._tree).get_children()) == 2

        # Re-opening the project loads both rows back, not the last one only.
        reopened = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()
        assert set(_nn(reopened._tree).get_children()) == {
            ArduinoBindingsPanel._row_iid(0, "Z1"),
            ArduinoBindingsPanel._row_iid(1, "Z1"),
        }

    def test_updating_one_aquarium_leaves_the_homonym_alone(self, tkinter_root):
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "on_exit": 2, "aquarium_id": 0},
                {"roi": "Z1", "on_enter": 3, "on_exit": 4, "aquarium_id": 1},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1"], aquarium_rois=[["Z1"], ["Z1"]])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        panel.aquarium_choice.set("2")
        panel.roi_choice.set("Z1")
        panel.enter_token.set("5")
        panel.exit_token.set("6")
        panel._add_or_update()

        assert pd["arduino_bindings"] == [
            {"roi": "Z1", "on_enter": 1, "on_exit": 2, "label": None, "aquarium_id": 0},
            {"roi": "Z1", "on_enter": 5, "on_exit": 6, "label": None, "aquarium_id": 1},
        ]

    def test_conflict_across_aquariums_is_still_reported(self, tkinter_root):
        """One serial line, one firmware: a token's role is global, not per aquarium."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 3, "on_exit": 4, "aquarium_id": 0},
                {"roi": "Z1", "on_enter": 4, "on_exit": 5, "aquarium_id": 1},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1"], aquarium_rois=[["Z1"], ["Z1"]])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        label = _nn(panel._conflict_label)
        assert _is_packed(label)
        assert "4" in label.cget("text")

    def test_probe_plan_names_the_aquarium(self, tkinter_root):
        """Two Z1 lines in the test output must say which aquarium each one is."""
        pd = {
            "use_arduino": True,
            "arduino_bindings": [
                {"roi": "Z1", "on_enter": 1, "aquarium_id": 0},
                {"roi": "Z1", "on_enter": 3, "aquarium_id": 1, "label": "Bomba"},
                {"roi": "Z2", "on_enter": 5},
            ],
        }
        controller, _pm = _make_controller(pd, ["Z1", "Z2"], aquarium_rois=[["Z1"], ["Z1"]])
        panel = ArduinoBindingsPanel(tkinter_root, controller)
        tkinter_root.update_idletasks()

        assert panel._probe_plan() == [
            ("Z1 (aquarium 1)", "enter", 1),
            ("Bomba [Z1 (aquarium 2)]", "enter", 3),
            ("Z2", "enter", 5),
        ]


class TestRowRoundTrip:
    """Headless twin of ``TestAquariumScope`` (#701), so the mutation run sees it.

    The mutation runner excludes ``gui`` tests. The row helpers are the whole
    table <-> binding conversion; they need no widget.
    """

    @pytest.mark.parametrize("aquarium_id", [None, 0, 1])
    def test_row_round_trip_keeps_the_aquarium(self, aquarium_id):
        binding = ArduinoBinding(
            roi="Z1", on_enter=1, on_exit=2, label="Choque", aquarium_id=aquarium_id
        )

        row = ArduinoBindingsPanel._row_values(binding)

        assert ArduinoBindingsPanel._binding_from_row(row) == binding

    def test_row_values_read_back_as_tk_returns_them(self):
        """ttk hands numeric-looking cells back as ints: ``"0"`` comes back ``0``."""
        binding = ArduinoBindingsPanel._binding_from_row((0, "1", "Z1", "", 1, 2))

        assert binding.aquarium_id == 0
        assert (binding.on_enter, binding.on_exit, binding.label) == (1, 2, None)

    def test_unscoped_row_reads_back_unscoped(self):
        binding = ArduinoBindingsPanel._binding_from_row(("", "All", "Z1", "", "1", ""))

        assert binding.aquarium_id is None
        assert binding.on_exit is None

    def test_row_iid_separates_aquariums(self):
        iids = {
            ArduinoBindingsPanel._row_iid(None, "Z1"),
            ArduinoBindingsPanel._row_iid(0, "Z1"),
            ArduinoBindingsPanel._row_iid(1, "Z1"),
        }

        assert len(iids) == 3

    def test_row_iid_separates_rois(self):
        assert ArduinoBindingsPanel._row_iid(0, "Z1") != ArduinoBindingsPanel._row_iid(0, "Z2")

    def test_aquarium_choice_parses_back_to_the_id(self):
        panel = object.__new__(ArduinoBindingsPanel)
        panel._aquarium_ids = [None, 0, 1]

        assert panel._aquarium_id_for_choice("All") is None
        assert panel._aquarium_id_for_choice("1") == 0
        assert panel._aquarium_id_for_choice("2") == 1
        # Unknown text (stale choice after the split changed) is the safe "All".
        assert panel._aquarium_id_for_choice("7") is None

    def test_hidden_picker_reads_a_selected_rows_number_back(self):
        """Single view: the number came from a scoped row and must stay its id."""
        panel = object.__new__(ArduinoBindingsPanel)
        panel._aquarium_ids = [None]

        assert panel._aquarium_id_for_choice("2") == 1
        assert panel._aquarium_id_for_choice("1") == 0
        assert panel._aquarium_id_for_choice("All") is None
        assert panel._aquarium_id_for_choice("0") is None

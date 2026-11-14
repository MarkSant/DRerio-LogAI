from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.global_model_configuration_panel import GlobalModelConfigurationPanel
from zebtrack.ui.event_bus_v2 import UIEvents

pytestmark = pytest.mark.gui


@pytest.fixture
def global_config_controller():
    return SimpleNamespace(
        ui_event_bus=Mock(),
        view=None,
    )


def test_global_model_configuration_panel_refresh_callback_runs(global_config_controller):
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel._refresh_weight_choices = Mock()
    panel._populate_weights_treeview = Mock()  # type: ignore[method-assign]
    panel._populate_slot_comboboxes = Mock()  # type: ignore[method-assign]
    panel.controller = global_config_controller

    panel._refresh_weights_catalog()

    panel._refresh_weight_choices.assert_called_once_with()


def test_global_model_configuration_panel_openvino_toggle_publishes_event(global_config_controller):
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel.controller = global_config_controller
    panel.use_openvino_var = Mock()
    panel.use_openvino_var.get.return_value = True
    panel.device_combobox = Mock()

    panel._on_openvino_toggled_local()

    event = global_config_controller.ui_event_bus.publish.call_args.args[0]
    assert event.type is UIEvents.MODEL_SET_OPENVINO
    assert event.data.use_openvino is True
    assert event.data.dialog is panel
    panel.device_combobox.configure.assert_called_once_with(state="readonly")


def test_global_model_configuration_panel_updates_status_label() -> None:
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel.openvino_status_var = Mock()

    panel.update_openvino_status_label("enabled")

    panel.openvino_status_var.set.assert_called_once_with("enabled")


# ---------------------------------------------------------------------------
# Change Target: picked from a read-only list, tokens unchanged
# ---------------------------------------------------------------------------


def test_target_from_label_maps_labels_to_the_stored_tokens() -> None:
    from zebtrack.ui.components.global_model_configuration_panel import (
        _target_from_label,
        _target_labels,
    )

    for token, label in _target_labels().items():
        assert _target_from_label(label) == token
    assert set(_target_labels()) == {"aquarium", "zebrafish"}
    assert _target_from_label("aquario") is None
    assert _target_from_label("") is None


def _panel_with_selection(global_config_controller, details):
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel.controller = global_config_controller
    panel._selected_weight_details = Mock(return_value=("w.pt", details))  # type: ignore[method-assign]
    panel.after = Mock()  # type: ignore[method-assign]
    return panel


def test_change_target_publishes_the_chosen_token(global_config_controller):
    panel = _panel_with_selection(global_config_controller, {"target": "aquarium"})
    panel._ask_target = Mock(return_value="zebrafish")  # type: ignore[method-assign]

    panel._on_change_target()

    panel._ask_target.assert_called_once_with("w.pt", "aquarium")
    event = global_config_controller.ui_event_bus.publish.call_args.args[0]
    assert event.type is UIEvents.MODEL_RECLASSIFY_TARGET
    assert (event.data.name, event.data.target) == ("w.pt", "zebrafish")


@pytest.mark.parametrize("answer", [None, "aquarium"])
def test_change_target_cancel_or_same_target_publishes_nothing(global_config_controller, answer):
    panel = _panel_with_selection(global_config_controller, {"target": "aquarium"})
    panel._ask_target = Mock(return_value=answer)  # type: ignore[method-assign]

    panel._on_change_target()

    global_config_controller.ui_event_bus.publish.assert_not_called()


def test_target_dialog_offers_only_the_two_labels(tkinter_root, monkeypatch):
    from tkinter import simpledialog

    from zebtrack.ui.components.global_model_configuration_panel import (
        TargetChoiceDialog,
        _target_labels,
    )

    monkeypatch.setattr(simpledialog.Dialog, "wait_window", lambda self, window=None: None)
    dialog = TargetChoiceDialog(tkinter_root, weight_name="w.pt", current="aquarium")
    try:
        assert dialog.combo is not None and dialog.choice is not None
        assert list(dialog.combo["values"]) == list(_target_labels().values())
        assert str(dialog.combo.cget("state")) == "readonly"
        assert dialog.choice.get() == _target_labels()["aquarium"]
        dialog.choice.set(_target_labels()["zebrafish"])
        dialog.apply()
        assert dialog.result == "zebrafish"
    finally:
        dialog.destroy()


# ---------------------------------------------------------------------------
# Class roles button (weight scope)
# ---------------------------------------------------------------------------


def test_class_roles_opens_the_weight_editor(global_config_controller, monkeypatch):
    import zebtrack.ui.components.global_model_configuration_panel as module

    dialog_cls = Mock()
    monkeypatch.setattr(module, "ClassRolesDialog", dialog_cls)
    controller = SimpleNamespace(
        ui_event_bus=Mock(), weight_manager=Mock(), model_service=Mock(), settings=Mock()
    )
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel.controller = controller
    panel._selected_weight_name = Mock(return_value="rat.pt")  # type: ignore[method-assign]

    assert panel._on_class_roles() is dialog_cls.return_value

    dialog_cls.assert_called_once_with(
        panel,
        weight_name="rat.pt",
        weight_manager=controller.weight_manager,
        model_service=controller.model_service,
        settings_obj=controller.settings,
        event_bus=controller.ui_event_bus,
    )


def test_class_roles_without_selection_or_service(monkeypatch):
    import zebtrack.ui.components.global_model_configuration_panel as module

    dialog_cls = Mock()
    showerror = Mock()
    monkeypatch.setattr(module, "ClassRolesDialog", dialog_cls)
    monkeypatch.setattr(module.messagebox, "showerror", showerror)
    panel = GlobalModelConfigurationPanel.__new__(GlobalModelConfigurationPanel)
    panel.controller = SimpleNamespace(model_service=None, weight_manager=Mock())

    panel._selected_weight_name = Mock(return_value=None)  # type: ignore[method-assign]
    assert panel._on_class_roles() is None
    showerror.assert_not_called()

    panel._selected_weight_name = Mock(return_value="rat.pt")  # type: ignore[method-assign]
    assert panel._on_class_roles() is None
    showerror.assert_called_once()
    dialog_cls.assert_not_called()

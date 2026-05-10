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
    panel._populate_weights_treeview = Mock()
    panel._populate_slot_comboboxes = Mock()
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

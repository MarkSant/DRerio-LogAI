"""Tests for UIStateController weight and status helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.coordinators.ui_state_coordinator import UIStateController
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import (
    UIRequestWeightActionPayload,
    UIRequestWeightTypePayload,
    UISetActiveWeightPayload,
    UIUpdateOpenVinoCheckboxPayload,
    UIUpdateWeightsListPayload,
)


@pytest.fixture
def controller():
    ui_event_bus = Mock()
    state_manager = Mock()
    ui_coordinator = Mock()
    project_manager = Mock()
    weight_manager = Mock()
    detector_service = Mock()
    model_service = Mock()
    settings = Mock()
    detector_coordinator = Mock()
    project_workflow_service = Mock()

    main_view_model = SimpleNamespace(
        get_all_weight_names=Mock(return_value=["w1", "w2"]),
        active_weight_name="w1",
        use_openvino=False,
        _using_project_overrides=False,
    )

    return UIStateController(
        root=Mock(),
        ui_event_bus=ui_event_bus,
        state_manager=state_manager,
        ui_coordinator=ui_coordinator,
        project_manager=project_manager,
        weight_manager=weight_manager,
        detector_service=detector_service,
        model_service=model_service,
        settings=settings,
        detector_coordinator=detector_coordinator,
        project_workflow_service=project_workflow_service,
        main_view_model=main_view_model,
    )


def test_manage_weights_publishes_event(controller):
    controller.manage_weights()

    controller.ui_event_bus.publish.assert_called_once_with(
        Event(type=UIEvents.UI_OPEN_MANAGE_WEIGHTS_DIALOG)
    )


def test_add_new_weight_success_updates_ui(controller):
    controller.set_active_weight = Mock()

    controller.add_new_weight("/tmp/w3.pt", set_as_default=True, weight_type="seg")

    controller.weight_manager.add_weight.assert_called_once()
    calls = controller.ui_event_bus.publish.call_args_list
    assert calls[0].args[0] == Event(
        type=UIEvents.UI_UPDATE_WEIGHTS_LIST,
        data=UIUpdateWeightsListPayload(weights=["w1", "w2"]),
    )
    assert calls[1].args[0] == Event(
        type=UIEvents.UI_SET_ACTIVE_WEIGHT,
        data=UISetActiveWeightPayload(weight_name="w3.pt"),
    )
    controller.set_active_weight.assert_called_once_with("w3.pt")


def test_add_new_weight_error_publishes_error(controller):
    controller.weight_manager.add_weight.side_effect = ValueError("bad")

    controller.add_new_weight("/tmp/w3.pt", set_as_default=True, weight_type="seg")

    event_obj = controller.ui_event_bus.publish.call_args[0][0]
    assert event_obj.type == UIEvents.UI_SHOW_ERROR


def test_delete_weight_success_publishes_updates(controller):
    controller.set_active_weight = Mock()
    controller.weight_manager.get_default_weight.return_value = ("default.pt", "seg")

    controller.delete_weight("w1")

    controller.weight_manager.delete_weight.assert_called_once_with("w1")
    calls = controller.ui_event_bus.publish.call_args_list
    assert calls[0].args[0] == Event(
        type=UIEvents.UI_UPDATE_WEIGHTS_LIST,
        data=UIUpdateWeightsListPayload(weights=["w1", "w2"]),
    )
    assert calls[1].args[0] == Event(
        type=UIEvents.UI_SET_ACTIVE_WEIGHT,
        data=UISetActiveWeightPayload(weight_name="default.pt"),
    )
    controller.set_active_weight.assert_called_once_with("default.pt", None)


def test_load_new_weight_requests_file(controller):
    controller.load_new_weight(filepath=None)

    controller.ui_event_bus.publish.assert_called_once_with(
        Event(type=UIEvents.UI_REQUEST_WEIGHT_FILE)
    )


def test_load_new_weight_requests_type(controller):
    controller.weight_manager._classify_weight_type.return_value = None

    controller.load_new_weight(filepath="/tmp/w.pt", weight_type=None)

    controller.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_REQUEST_WEIGHT_TYPE,
            data=UIRequestWeightTypePayload(filepath=str(Path("/tmp/w.pt"))),
        )
    )


def test_load_new_weight_requests_action(controller):
    controller.weight_manager._classify_weight_type.return_value = "seg"

    controller.load_new_weight(filepath="/tmp/w.pt", weight_type=None, choice=None)

    controller.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_REQUEST_WEIGHT_ACTION,
            data=UIRequestWeightActionPayload(weight_type="seg", filepath=str(Path("/tmp/w.pt"))),
        )
    )


def test_load_new_weight_choice_yes(controller):
    controller.add_new_weight = Mock()

    controller.load_new_weight(filepath="/tmp/w.pt", weight_type="seg", choice="yes")

    args = controller.add_new_weight.call_args.kwargs
    assert args["set_as_default"] is True
    assert args["weight_type"] == "seg"


def test_load_new_weight_choice_no(controller):
    controller.add_new_weight = Mock()

    controller.load_new_weight(filepath="/tmp/w.pt", weight_type="seg", choice="no")

    args = controller.add_new_weight.call_args.kwargs
    assert args["set_as_default"] is False
    assert args["weight_type"] == "seg"


def test_set_openvino_usage_publishes_and_updates(controller):
    controller.convert_active_weight_to_openvino = Mock()
    controller.update_openvino_status = Mock()
    controller.main_view_model.active_weight_name = "w1"

    controller.set_openvino_usage(True, dialog="dlg")

    controller.ui_event_bus.publish.assert_called_once_with(
        Event(
            type=UIEvents.UI_UPDATE_OPENVINO_CHECKBOX,
            data=UIUpdateOpenVinoCheckboxPayload(is_checked=True),
        )
    )
    controller.convert_active_weight_to_openvino.assert_called_once_with("dlg")
    controller.update_openvino_status.assert_called_once_with("dlg")

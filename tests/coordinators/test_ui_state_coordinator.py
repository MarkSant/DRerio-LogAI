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
        get_openvino_status=Mock(return_value="status"),
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


def test_manage_weights_method_removed(controller):
    """``manage_weights`` was removed in TASK-065 — catalog inlined in CalibrationDialog."""
    assert not hasattr(controller, "manage_weights")


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


def test__schedule_on_ui(controller):
    from unittest.mock import Mock

    func = Mock()
    controller._schedule_on_ui(func, 1, a=2)
    controller.ui_coordinator.schedule.assert_called_once_with(func, 1, a=2)


def test_refresh_project_views_no_view(controller):
    controller.view = None
    controller.refresh_project_views()


def test_refresh_project_views_with_view(controller):
    from unittest.mock import Mock

    mock_view = Mock()
    controller.view = mock_view
    controller.refresh_project_views(reason="test", append_summary=True, immediate=False)
    controller.ui_coordinator.schedule.assert_called_once_with(
        mock_view.refresh_project_views, "test", append_summary=True, immediate=False
    )


def test__publish_processing_mode_override(controller):
    from zebtrack.core.video.processing_mode import ProcessingMode
    from zebtrack.ui.event_bus_v2 import UIEvents

    controller._publish_processing_mode(mode_override=ProcessingMode.SINGLE_SUBJECT)
    calls = controller.ui_event_bus.publish.call_args_list
    assert len(calls) == 1
    event_obj = calls[0].args[0]
    assert event_obj.type == UIEvents.UI_UPDATE_PROCESSING_MODE
    assert event_obj.data.report.mode == ProcessingMode.SINGLE_SUBJECT


def test__publish_processing_mode_fallback(controller):
    from zebtrack.core.video.processing_mode import ProcessingMode

    controller.main_view_model.processing_coordinator = None
    controller.main_view_model._active_processing_mode = ProcessingMode.MULTI_TRACK
    controller._publish_processing_mode()
    calls = controller.ui_event_bus.publish.call_args_list
    assert calls[0].args[0].data.report.mode == ProcessingMode.MULTI_TRACK


def test_convert_active_weight_to_openvino_success(controller):
    controller.main_view_model.active_weight_name = "w1"
    controller.convert_active_weight_to_openvino(None)
    controller.model_service.convert_to_openvino.assert_called_once_with("w1")
    calls = controller.ui_event_bus.publish.call_args_list
    # Should publish 'Converting...' then 'Conversion check finished...'
    assert len(calls) == 3  # includes update_openvino_status


def test_convert_active_weight_to_openvino_error(controller):
    from zebtrack.core.services.weight_manager import OpenVINOExportError
    from zebtrack.ui.event_bus_v2 import UIEvents

    controller.main_view_model.active_weight_name = "w1"
    controller.model_service.convert_to_openvino.side_effect = OpenVINOExportError("err")
    controller.convert_active_weight_to_openvino(None)
    calls = controller.ui_event_bus.publish.call_args_list
    assert any(c.args[0].type == UIEvents.UI_SHOW_ERROR for c in calls)


def test_update_openvino_status(controller):
    from unittest.mock import Mock

    controller.main_view_model.get_openvino_status.return_value = "status"
    dialog = Mock()
    controller.update_openvino_status(dialog)
    dialog.update_openvino_status_label.assert_called_once_with("status")


def test_set_openvino_usage_updates_device_and_config(controller):
    from unittest.mock import Mock

    controller.main_view_model.use_openvino = False
    controller.main_view_model.active_weight_name = "w1"
    settings_obj = Mock()
    controller.main_view_model.settings_obj = settings_obj
    controller.convert_active_weight_to_openvino = Mock()
    controller.update_openvino_status = Mock()

    controller.set_openvino_usage(True, dialog="dlg", device="GPU")

    assert controller.main_view_model.use_openvino is True
    assert settings_obj.openvino.device == "GPU"
    assert settings_obj.openvino.device_batch == "GPU"
    controller.convert_active_weight_to_openvino.assert_called_once_with("dlg")
    controller.update_openvino_status.assert_called_once_with("dlg")


class TestSetupDetectorZones:
    def test_configure_zones_fails(self, controller):
        controller.detector_coordinator.configure_zones.return_value = False
        controller.setup_detector_zones()
        controller.project_manager.get_zone_data.assert_not_called()

    def test_configure_zones_no_polygon_prerecorded(self, controller):
        controller.detector_coordinator.configure_zones.return_value = True
        mock_zone = Mock(polygon=[])
        controller.project_manager.get_zone_data.return_value = mock_zone
        controller.project_manager.get_project_type.return_value = "pre-recorded"
        controller.project_manager.get_next_video.return_value = "v1.mp4"

        controller.setup_detector_zones()

        event_types = [c.args[0].type for c in controller.ui_event_bus.publish.call_args_list]
        assert UIEvents.UI_SELECT_TAB in event_types
        assert UIEvents.UI_DISPLAY_VIDEO_FRAME in event_types
        assert UIEvents.UI_SHOW_ERROR in event_types


class TestApplyRoiTemplate:
    def test_no_active_video(self, controller):
        controller.project_manager.get_active_zone_video.return_value = None
        controller.apply_roi_template({"name": "T1"})
        event_obj = controller.ui_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.UI_SHOW_WARNING

    def test_apply_success(self, controller):
        controller.project_manager.get_active_zone_video.return_value = "v1.mp4"
        controller.project_manager.load_roi_template.return_value = Mock()
        controller.project_manager.project_path = "/proj"
        controller.setup_detector_zones = Mock()

        controller.apply_roi_template({"name": "T1", "location": "loc", "file": "f.json"})

        controller.project_manager.save_zone_data.assert_called_once()
        controller.setup_detector_zones.assert_called_once()
        event_types = [c.args[0].type for c in controller.ui_event_bus.publish.call_args_list]
        assert UIEvents.UI_REDRAW_ZONES in event_types
        assert UIEvents.UI_UPDATE_ZONE_LIST in event_types
        assert UIEvents.UI_SHOW_INFO in event_types

    def test_apply_file_not_found(self, controller):
        controller.project_manager.get_active_zone_video.return_value = "v1.mp4"
        controller.project_manager.load_roi_template.side_effect = FileNotFoundError("missing")

        controller.apply_roi_template({"name": "T1"})

        event_obj = controller.ui_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.UI_SHOW_ERROR

    def test_apply_generic_exception(self, controller):
        controller.project_manager.get_active_zone_video.return_value = "v1.mp4"
        controller.project_manager.load_roi_template.side_effect = RuntimeError("error")

        controller.apply_roi_template({"name": "T1"})

        event_obj = controller.ui_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.UI_SHOW_ERROR


class TestUpdateMainArena:
    def test_update_main_arena_success(self, controller):
        mock_zone = Mock()
        controller.project_manager.get_zone_data.return_value = mock_zone
        controller.setup_detector_zones = Mock()

        controller.update_main_arena([[0, 0], [10, 10]])

        assert mock_zone.polygon == [[0, 0], [10, 10]]
        controller.project_manager.save_zone_data.assert_called_once_with(mock_zone)
        controller.setup_detector_zones.assert_called_once()


class TestUserFeedback:
    def test_show_post_creation_guide_view_suppressed(self, controller):
        controller.view = Mock(suppress_post_creation_guide=True)
        controller._show_post_creation_guide({})
        controller.project_workflow_service.generate_post_creation_guide.assert_not_called()

    def test_show_post_creation_guide_generates_guide(self, controller):
        controller.view = Mock(suppress_post_creation_guide=False)
        controller.project_workflow_service.generate_post_creation_guide.return_value = {
            "title": "Welcome",
            "message": "Start here",
        }

        controller._show_post_creation_guide({})

        event_obj = controller.ui_event_bus.publish.call_args[0][0]
        assert event_obj.type == UIEvents.UI_SHOW_INFO

    def test_show_cancel_feedback(self, controller):
        controller.view = Mock()
        controller.main_view_model._cancel_feedback_displayed = False

        controller._show_cancel_feedback()

        assert controller.main_view_model._cancel_feedback_displayed is True
        controller.ui_coordinator.update_view.assert_called_once_with(
            controller.view, "stop_analysis_view_mode"
        )
        controller.ui_coordinator.set_status.assert_called_once()

"""Tests for HardwareStatusViewModel."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel


@pytest.fixture
def view_model():
    detector_service = SimpleNamespace(detector=None)
    model_service = Mock()
    detector_setup_coordinator = Mock()
    model_diagnostics_coordinator = Mock()
    weight_manager = Mock()
    # Default: no runtime overrides — `get_default_weights_summary` consults
    # this *before* `get_default_weight_for` so the unconfigured Mock would
    # otherwise return a non-iterable child and break unpacking.
    weight_manager.get_runtime_slot_override.return_value = (None, None)
    # Phase 4.7: Replaced session_coordinator with 3 focused coordinators
    recording_session_coordinator = Mock()
    live_camera_session_coordinator = Mock()
    live_calibration_coordinator = Mock()
    state_manager = Mock()
    state_manager.get_detector_state.return_value = SimpleNamespace(detector_initialized=True)

    dependencies = SimpleNamespace(
        detector_service=detector_service,
        model_service=model_service,
        detector_setup_coordinator=detector_setup_coordinator,
        model_diagnostics_coordinator=model_diagnostics_coordinator,
        weight_manager=weight_manager,
        recording_session_coordinator=recording_session_coordinator,
        live_camera_session_coordinator=live_camera_session_coordinator,
        live_calibration_coordinator=live_calibration_coordinator,
        state_manager=state_manager,
        settings_obj=Mock(),
    )

    detector_setup_coordinator.setup_detector.return_value = (True, None)
    bootstrap_result = SimpleNamespace(
        legacy_coordinators={"detector_coordinator": detector_setup_coordinator},
        hardware=SimpleNamespace(
            arduino_manager=Mock(),
            active_weight_name="weights.pt",
            use_openvino=True,
        ),
        ui_state_controller=Mock(),
    )

    event_bus = Mock()

    return HardwareStatusViewModel(
        cast(Any, dependencies),
        cast(Any, bootstrap_result),
        event_bus,
    )


def test_detector_property_round_trip(view_model):
    detector = Mock()

    view_model.detector = detector

    assert view_model.detector is detector


def test_detector_initialized_from_state(view_model):
    assert view_model.detector_initialized is True


def test_setup_detector_delegates(view_model):
    assert view_model.setup_detector(temp_animal_method="seg") is True

    view_model.detector_setup_coordinator.setup_detector.assert_called_once_with(
        animal_method="seg",
        use_openvino=True,
        active_weight_name="weights.pt",
        perspective=None,
    )


def test_update_and_get_detector_parameters(view_model):
    view_model.detector_setup_coordinator.update_detector_parameters.return_value = True
    view_model.detector_setup_coordinator.get_detector_parameters.return_value = {"x": 1}

    assert view_model.update_detector_parameters({"x": 1}) is True
    assert view_model.get_current_detector_parameters() == {"x": 1}


def test_restore_detector_defaults_global(view_model):
    view_model.detector_setup_coordinator.get_factory_detector_parameters.return_value = {"a": 1}
    view_model.detector_setup_coordinator.update_detector_parameters.return_value = True

    assert view_model.restore_detector_defaults(scope="global") is True

    view_model.detector_setup_coordinator.update_detector_parameters.assert_called_once_with(
        params={"a": 1}, scope="global", reset_overrides=True
    )


def test_restore_detector_defaults_project(view_model):
    view_model.detector_setup_coordinator.update_detector_parameters.return_value = True

    assert view_model.restore_detector_defaults(scope="project") is True

    view_model.detector_setup_coordinator.update_detector_parameters.assert_called_once_with(
        params={}, scope="project", reset_overrides=True
    )


def test_restore_detector_defaults_invalid_scope(view_model):
    assert view_model.restore_detector_defaults(scope="other") is False


def test_get_all_weight_names(view_model):
    view_model.model_service.get_all_weight_names.return_value = ["w1", "w2"]

    assert view_model.get_all_weight_names() == ["w1", "w2"]


def test_get_openvino_status(view_model):
    view_model.model_service.get_openvino_status.return_value = "ready"

    assert view_model.get_openvino_status() == "ready"
    view_model.model_service.get_openvino_status.assert_called_once_with(
        weight_name="weights.pt", use_openvino=True
    )


def test_get_openvino_cache_status_default(view_model):
    view_model.model_service.check_openvino_conversion_status.return_value = {"status": "ok"}

    assert view_model.get_openvino_cache_status() == {"status": "ok"}


def test_ui_state_controller_weight_actions(view_model):
    view_model.set_active_weight("w1", dialog="d")
    view_model.set_openvino_usage(True, dialog="d")
    view_model.update_openvino_status(dialog="d")
    view_model.load_new_weight(path="p")
    view_model.add_new_weight("p", True, "det")
    view_model.delete_weight("w1")

    ui_state = view_model.ui_state_controller
    ui_state.set_active_weight.assert_called_once_with("w1", "d")
    ui_state.set_openvino_usage.assert_called_once_with(True, "d", device=None)
    ui_state.update_openvino_status.assert_called_once_with("d")
    ui_state.load_new_weight.assert_called_once_with(path="p")
    ui_state.add_new_weight.assert_called_once_with("p", True, "det")
    ui_state.delete_weight.assert_called_once_with("w1")
    # `manage_weights` was removed in TASK-065 (catalog inlined in CalibrationDialog).
    assert not hasattr(view_model, "manage_weights")


def test_run_model_diagnostic_injects_active_weight(view_model):
    config = {"mode": "full"}

    view_model.run_model_diagnostic(config)

    view_model.model_diagnostics_coordinator.run_model_diagnostic.assert_called_once_with(
        {"mode": "full", "active_weight_name": "weights.pt"}
    )


def test_handle_request_weight_file_calls_ui_state(view_model):
    with patch("tkinter.filedialog.askopenfilename", return_value="/tmp/w.pt"):
        view_model.handle_request_weight_file()

    view_model.ui_state_controller.load_new_weight.assert_called_once_with(filepath="/tmp/w.pt")


def test_handle_request_weight_file_no_selection(view_model):
    with patch("tkinter.filedialog.askopenfilename", return_value=""):
        view_model.handle_request_weight_file()

    view_model.ui_state_controller.load_new_weight.assert_not_called()


def test_start_live_session_and_recording_delegates(view_model):
    view_model.start_live_session(mode="live")
    view_model.start_recording(mode="rec")
    view_model.stop_recording()

    view_model.live_camera_session_coordinator.start_live_session.assert_called_once_with(
        mode="live"
    )
    view_model.recording_session_coordinator.start_recording.assert_called_once_with(mode="rec")
    view_model.recording_session_coordinator.stop_recording.assert_called_once()


# ----------------------------------------------------------------------
# get_default_weights_summary (TASK-065)
# ----------------------------------------------------------------------


def _summary_lookup(view_model, *, scope: str = "global") -> dict[tuple[str, str], str | None]:
    return {
        (method, target): name
        for _label, method, target, name in view_model.get_default_weights_summary(scope=scope)
    }


def test_get_default_weights_summary_global_returns_all_four_slots(view_model):
    """Global scope must list every (method x target) slot, even empty ones."""
    view_model.weight_manager.get_default_weight_for.side_effect = lambda method, target: {
        ("det", "aquarium"): ("aq_det.pt", {}),
        ("seg", "aquarium"): (None, None),
        ("det", "zebrafish"): (None, None),
        ("seg", "zebrafish"): ("an_seg.pt", {}),
    }[(method, target)]

    summary = view_model.get_default_weights_summary(scope="global")

    assert len(summary) == 4
    lookup = _summary_lookup(view_model, scope="global")
    assert lookup[("det", "aquarium")] == "aq_det.pt"
    assert lookup[("seg", "zebrafish")] == "an_seg.pt"
    assert lookup[("seg", "aquarium")] is None
    assert lookup[("det", "zebrafish")] is None


def test_get_default_weights_summary_project_filters_to_two_slots(view_model):
    """Project scope returns exactly the 2 slots picked by ModelSelectionSettings."""
    view_model.settings.model_selection.aquarium_method = "seg"
    view_model.settings.model_selection.animal_method = "det"
    view_model.weight_manager.get_default_weight_for.side_effect = lambda method, target: {
        ("seg", "aquarium"): ("aq_seg.pt", {}),
        ("det", "zebrafish"): ("an_det.pt", {}),
    }.get((method, target), (None, None))

    summary = view_model.get_default_weights_summary(scope="project")

    assert len(summary) == 2
    methods_targets = {(method, target) for _label, method, target, _name in summary}
    assert methods_targets == {("seg", "aquarium"), ("det", "zebrafish")}


def test_get_default_weights_summary_project_falls_back_when_settings_missing(view_model):
    """If model_selection is unreadable, fall back to the full 4-slot view."""
    # Make attribute access raise to mimic broken settings.
    view_model.settings.model_selection = SimpleNamespace()
    view_model.weight_manager.get_default_weight_for.return_value = (None, None)

    summary = view_model.get_default_weights_summary(scope="project")

    assert len(summary) == 4


def test_get_default_weights_summary_prefers_runtime_override(view_model):
    """Project-scoped weights set via runtime overrides (e.g. from the wizard)
    must win over the global ``is_default_*`` flag. Without this, the main
    control panel keeps showing the catalog's lateral defaults even after the
    user picks top-down models in the wizard.
    """
    view_model.settings.model_selection.aquarium_method = "seg"
    view_model.settings.model_selection.animal_method = "seg"

    # Global defaults point at lateral weights.
    view_model.weight_manager.get_default_weight_for.side_effect = lambda method, target: {
        ("seg", "aquarium"): ("lateral_aq.pt", {}),
        ("seg", "zebrafish"): ("lateral_an.pt", {}),
    }.get((method, target), (None, None))

    # Project-scoped override resolves to top-down weights.
    view_model.weight_manager.get_runtime_slot_override.side_effect = lambda method, target: {
        ("seg", "aquarium"): ("topdown_aq.pt", {"path": "/w/topdown_aq.pt"}),
        ("seg", "zebrafish"): ("topdown_an.pt", {"path": "/w/topdown_an.pt"}),
    }.get((method, target), (None, None))

    summary = view_model.get_default_weights_summary(scope="project")

    lookup = {(method, target): name for _label, method, target, name in summary}
    assert lookup[("seg", "aquarium")] == "topdown_aq.pt"
    assert lookup[("seg", "zebrafish")] == "topdown_an.pt"


def test_get_default_weights_summary_falls_back_to_global_default_without_override(view_model):
    """When no runtime override exists for a slot, fall back to the catalog default."""
    view_model.weight_manager.get_runtime_slot_override.return_value = (None, None)
    view_model.weight_manager.get_default_weight_for.side_effect = lambda method, target: (
        f"{method}_{target}_default.pt",
        {},
    )

    summary = view_model.get_default_weights_summary(scope="global")
    lookup = {(method, target): name for _label, method, target, name in summary}

    assert lookup[("det", "aquarium")] == "det_aquarium_default.pt"
    assert lookup[("seg", "zebrafish")] == "seg_zebrafish_default.pt"


# ---------------------------------------------------------------------------
# Arduino UI bridge (regression: dashboard stayed disconnected / silent)
# ---------------------------------------------------------------------------


def _published(event_bus_mock):
    """Return list of (event_type, payload) from a mocked bus.publish."""
    from zebtrack.ui.event_bus_v2 import UIEvents  # noqa: F401

    out = []
    for call in event_bus_mock.publish.call_args_list:
        event = call.args[0] if call.args else call.kwargs.get("event")
        out.append((event.type, event.data))
    return out


def test_on_arduino_status_change_publishes_status_event(view_model):
    from zebtrack.ui.event_bus_v2 import UIEvents

    view_model.on_arduino_status_change(True, "COM3")

    published = _published(view_model.ui_event_bus)
    types = [t for t, _ in published]
    assert UIEvents.UI_UPDATE_ARDUINO_STATUS in types
    payload = next(d for t, d in published if t == UIEvents.UI_UPDATE_ARDUINO_STATUS)
    assert payload.connected is True
    assert payload.port == "COM3"


def test_log_arduino_event_publishes_log_event(view_model):
    from zebtrack.ui.event_bus_v2 import UIEvents

    view_model.log_arduino_event("Arduino conectado na porta COM3.")

    published = _published(view_model.ui_event_bus)
    payload = next(d for t, d in published if t == UIEvents.UI_APPEND_ARDUINO_LOG)
    assert "COM3" in payload.message


def test_on_arduino_command_sent_publishes_command_and_log(view_model):
    from zebtrack.ui.event_bus_v2 import UIEvents

    view_model.on_arduino_command_sent(7, True, "zone")

    published = _published(view_model.ui_event_bus)
    types = [t for t, _ in published]
    assert UIEvents.UI_UPDATE_ARDUINO_COMMAND in types
    assert UIEvents.UI_APPEND_ARDUINO_LOG in types
    cmd_payload = next(d for t, d in published if t == UIEvents.UI_UPDATE_ARDUINO_COMMAND)
    assert cmd_payload.command == 7
    assert cmd_payload.success is True


class TestArduinoReleasedOnProjectSwitch:
    """The serial connection is PROJECT-scoped and nothing used to close it.

    ``initialize_live_components`` opens the port from
    ``project_data["use_arduino"]`` / ``["arduino_port"]``. The only
    ``disconnect()`` in the codebase ran at application exit, so after closing a
    live project the port stayed open, both daemon threads kept running and the
    dashboard stayed green — for a project that no longer exists, and often for
    one that never asked for an Arduino.
    """

    def test_connected_manager_is_disconnected(self, view_model):
        manager = Mock()
        manager.is_connected.return_value = True
        view_model.arduino_manager = manager

        view_model._on_project_manager_replaced({"new_manager": Mock()})

        manager.disconnect.assert_called_once()

    def test_the_manager_reference_survives(self, view_model):
        """``disconnect()``, never ``_shutdown_arduino_manager()``.

        The latter drops the reference, and the next project would find
        ``hardware_vm.arduino_manager is None`` and never reconnect.
        """
        manager = Mock()
        manager.is_connected.return_value = True
        view_model.arduino_manager = manager

        view_model._on_project_manager_replaced({"new_manager": Mock()})

        assert view_model.arduino_manager is manager
        manager.shutdown.assert_not_called()

    def test_already_disconnected_is_a_no_op(self, view_model):
        manager = Mock()
        manager.is_connected.return_value = False
        view_model.arduino_manager = manager

        view_model._on_project_manager_replaced({"new_manager": Mock()})

        manager.disconnect.assert_not_called()

    def test_no_manager_is_a_no_op(self, view_model):
        view_model.arduino_manager = None

        view_model._on_project_manager_replaced({"new_manager": Mock()})

    def test_a_serial_failure_never_blocks_the_close(self, view_model):
        manager = Mock()
        manager.is_connected.return_value = True
        manager.disconnect.side_effect = OSError("port vanished")
        view_model.arduino_manager = manager

        view_model._on_project_manager_replaced({"new_manager": Mock()})

        assert view_model.arduino_manager is manager

    def test_a_failing_connectivity_probe_never_blocks_the_close(self, view_model):
        manager = Mock()
        manager.is_connected.side_effect = OSError("probe failed")
        view_model.arduino_manager = manager

        view_model._on_project_manager_replaced({"new_manager": Mock()})

        manager.disconnect.assert_not_called()


# ---------------------------------------------------------------------------
# Detector coordinator: absent-coordinator fallbacks and exact forwarding
# ---------------------------------------------------------------------------


def test_detector_calls_degrade_without_a_coordinator(view_model):
    view_model.detector_setup_coordinator = None

    assert view_model.setup_detector() is False
    assert view_model.update_detector_parameters({"conf": 0.5}) is False
    assert view_model.get_current_detector_parameters() == {}
    assert view_model.restore_detector_defaults() is False


def test_setup_detector_forwards_perspective_and_reports_the_coordinator_verdict(view_model):
    view_model.detector_setup_coordinator.setup_detector.return_value = (False, "w.pt")

    assert view_model.setup_detector("det", perspective="top") is False

    view_model.detector_setup_coordinator.setup_detector.assert_called_once_with(
        animal_method="det",
        use_openvino=True,
        active_weight_name="weights.pt",
        perspective="top",
    )


def test_update_detector_parameters_forwards_keyword_arguments(view_model):
    view_model.detector_setup_coordinator.update_detector_parameters.return_value = True

    assert view_model.update_detector_parameters({"conf": 0.5}, scope="project") is True

    view_model.detector_setup_coordinator.update_detector_parameters.assert_called_once_with(
        {"conf": 0.5}, scope="project"
    )


# ---------------------------------------------------------------------------
# Arduino bridge: payloads, messages and failure isolation
# ---------------------------------------------------------------------------


def test_arduino_bus_failures_never_break_the_serial_loop(view_model):
    view_model.ui_event_bus.publish.side_effect = RuntimeError("bus down")

    view_model.log_arduino_event("x")  # must not raise
    view_model.on_arduino_status_change(False, None)
    view_model.on_arduino_command_sent(1, True, "manual")

    assert view_model.ui_event_bus.publish.call_count == 4


def test_arduino_bridge_without_a_bus_publishes_nothing(view_model):
    bus = view_model.ui_event_bus
    view_model.ui_event_bus = None

    view_model.log_arduino_event("x")
    view_model.on_arduino_status_change(True, "COM3")
    view_model.on_arduino_command_sent(1, True, "manual")

    bus.publish.assert_not_called()


def test_arduino_events_carry_the_hardware_view_model_as_source(view_model):
    view_model.on_arduino_status_change(False, None)

    event = view_model.ui_event_bus.publish.call_args.args[0]
    assert event.source == "hardware_status_view_model"
    assert (event.data.connected, event.data.port) == (False, None)


def test_command_sent_logs_success_with_command_and_source(view_model):
    view_model.on_arduino_command_sent(7, True, "zone")

    published = _published(view_model.ui_event_bus)
    command, log_line = published[0][1], published[1][1]
    assert (command.command, command.success, command.source) == (7, True, "zone")
    assert log_line.message == "Command 7 sent (zone)"


def test_command_sent_logs_failure_distinctly(view_model):
    view_model.on_arduino_command_sent(9, False, "roi")

    published = _published(view_model.ui_event_bus)
    assert published[0][1].success is False
    assert published[1][1].message == "Command 9 failed (roi)"


def test_shutdown_arduino_manager_shuts_down_and_drops_every_reference(view_model):
    manager = view_model.arduino_manager
    view_model.arduino = object()

    view_model._shutdown_arduino_manager()

    manager.shutdown.assert_called_once_with()
    assert view_model.arduino_manager is None
    assert view_model.arduino is None


def test_shutdown_arduino_manager_drops_references_even_when_shutdown_raises(view_model):
    view_model.arduino_manager.shutdown.side_effect = OSError("busy")

    view_model._shutdown_arduino_manager()  # must not raise

    assert view_model.arduino_manager is None


def test_shutdown_arduino_manager_without_a_manager_is_a_noop(view_model):
    view_model.arduino_manager = None

    view_model._shutdown_arduino_manager()

    assert view_model.arduino_manager is None


# ---------------------------------------------------------------------------
# Weight catalogue
# ---------------------------------------------------------------------------


def test_weight_queries_degrade_without_a_model_service(view_model):
    view_model.model_service = None

    assert view_model.get_all_weight_names() == []
    assert view_model.get_weight_details("w.pt") is None
    assert view_model.get_openvino_cache_status("w.pt") == {"status": "unknown"}


def test_get_weight_details_forwards_the_name(view_model):
    view_model.model_service.get_weight_details.return_value = {"type": "seg"}

    assert view_model.get_weight_details("w.pt") == {"type": "seg"}
    view_model.model_service.get_weight_details.assert_called_once_with("w.pt")


def _catalogue(view_model, details: dict[str, dict | None]) -> None:
    view_model.model_service.get_all_weight_names.return_value = list(details)
    view_model.model_service.get_weight_details.side_effect = lambda name: details[name]


def test_weight_names_for_slot_prefers_the_exact_method_and_target(view_model):
    _catalogue(
        view_model,
        {
            "a.pt": {"type": "seg", "target": "aquarium"},
            "b.pt": {"type": "seg", "target": "zebrafish"},
            "c.pt": {"type": "det", "target": "zebrafish"},
            "d.pt": {"type": "seg", "target": "zebrafish"},
        },
    )

    assert view_model.get_weight_names_for_slot("seg", "zebrafish") == ["b.pt", "d.pt"]


def test_weight_names_for_slot_falls_back_to_the_method_when_no_target_matches(view_model):
    _catalogue(
        view_model,
        {
            "a.pt": {"type": "seg", "target": "aquarium"},
            "c.pt": {"type": "det", "target": "zebrafish"},
            "e.pt": {"type": "seg"},
        },
    )

    assert view_model.get_weight_names_for_slot("seg", "zebrafish") == ["a.pt", "e.pt"]


def test_weight_names_for_slot_skips_weights_without_details_and_can_be_empty(view_model):
    _catalogue(view_model, {"a.pt": None, "b.pt": {"type": "det", "target": "aquarium"}})

    assert view_model.get_weight_names_for_slot("seg", "aquarium") == []


def test_default_weight_summary_labels_each_slot(view_model):
    view_model.weight_manager.get_default_weight_for.return_value = (None, None)

    summary = view_model.get_default_weights_summary()

    assert summary == [
        ("🔲 Arena (det)", "det", "aquarium", None),
        ("🔲 Arena (seg)", "seg", "aquarium", None),
        ("🐾 Animal (det)", "det", "zebrafish", None),
        ("🐾 Animal (seg)", "seg", "zebrafish", None),
    ]


def test_default_weight_summary_without_a_weight_manager_lists_empty_slots(view_model):
    view_model.weight_manager = None

    summary = view_model.get_default_weights_summary()

    assert [(m, t, n) for _l, m, t, n in summary] == [
        ("det", "aquarium", None),
        ("seg", "aquarium", None),
        ("det", "zebrafish", None),
        ("seg", "zebrafish", None),
    ]


def test_default_weight_summary_with_a_manager_lacking_runtime_overrides(view_model):
    view_model.weight_manager = SimpleNamespace(
        get_default_weight_for=lambda method, target: (f"{method}-{target}.pt", {})
    )

    summary = view_model.get_default_weights_summary()

    assert [n for *_rest, n in summary] == [
        "det-aquarium.pt",
        "seg-aquarium.pt",
        "det-zebrafish.pt",
        "seg-zebrafish.pt",
    ]


def test_default_weight_summary_project_scope_needs_both_methods(view_model):
    view_model.settings.model_selection = SimpleNamespace(aquarium_method="seg", animal_method=None)
    view_model.weight_manager.get_default_weight_for.return_value = (None, None)

    assert len(view_model.get_default_weights_summary(scope="project")) == 4


def test_default_weight_summary_project_scope_survives_unreadable_settings(view_model):
    class Broken:
        @property
        def model_selection(self):
            raise RuntimeError("settings not loaded")

    view_model.settings = Broken()
    view_model.weight_manager.get_default_weight_for.return_value = (None, None)

    assert len(view_model.get_default_weights_summary(scope="project")) == 4


def test_default_weight_summary_project_scope_picks_the_label_of_each_method(view_model):
    view_model.settings.model_selection.aquarium_method = "det"
    view_model.settings.model_selection.animal_method = "seg"
    view_model.weight_manager.get_default_weight_for.return_value = (None, None)

    summary = view_model.get_default_weights_summary(scope="project")

    assert [(label, m, t) for label, m, t, _n in summary] == [
        ("🔲 Arena (det)", "det", "aquarium"),
        ("🐾 Animal (seg)", "seg", "zebrafish"),
    ]


def test_openvino_status_passes_an_empty_name_when_no_weight_is_active(view_model):
    view_model.active_weight_name = None
    view_model.use_openvino = False
    view_model.model_service.get_openvino_status.return_value = "off"

    assert view_model.get_openvino_status() == "off"
    view_model.model_service.get_openvino_status.assert_called_once_with(
        weight_name="", use_openvino=False
    )


def test_openvino_cache_status_prefers_the_explicit_weight_over_the_active_one(view_model):
    view_model.model_service.check_openvino_conversion_status.return_value = {"status": "ok"}

    view_model.get_openvino_cache_status("other.pt")
    view_model.get_openvino_cache_status()

    assert [
        c.args for c in view_model.model_service.check_openvino_conversion_status.call_args_list
    ] == [
        ("other.pt",),
        ("weights.pt",),
    ]


def test_openvino_cache_status_with_no_weight_at_all_asks_for_the_empty_name(view_model):
    view_model.active_weight_name = None

    view_model.get_openvino_cache_status()

    view_model.model_service.check_openvino_conversion_status.assert_called_once_with("")


def test_set_openvino_usage_forwards_the_device(view_model):
    view_model.set_openvino_usage(True, dialog="d", device="GPU")

    view_model.ui_state_controller.set_openvino_usage.assert_called_once_with(
        True, "d", device="GPU"
    )


def test_run_model_diagnostic_without_a_coordinator_leaves_the_config_alone(view_model):
    view_model.model_diagnostics_coordinator = None
    config = {"mode": "full"}

    view_model.run_model_diagnostic(config)

    assert config == {"mode": "full"}


# ---------------------------------------------------------------------------
# Weight maintenance (4-target architecture)
# ---------------------------------------------------------------------------


def test_set_default_weight_for_forwards_method_and_target(view_model):
    view_model.weight_manager.set_default_weight_for.return_value = True

    assert view_model.set_default_weight_for("a.pt", method="seg", target="aquarium") is True

    view_model.weight_manager.set_default_weight_for.assert_called_once_with(
        "a.pt", method="seg", target="aquarium"
    )


def test_reclassify_weight_target_forwards_to_set_weight_target(view_model):
    view_model.weight_manager.set_weight_target.return_value = True

    assert view_model.reclassify_weight_target("a.pt", "zebrafish") is True

    view_model.weight_manager.set_weight_target.assert_called_once_with("a.pt", "zebrafish")


def test_weight_maintenance_degrades_without_a_weight_manager(view_model):
    view_model.weight_manager = None

    assert view_model.set_default_weight_for("a.pt", method="seg", target="aquarium") is False
    assert view_model.reclassify_weight_target("a.pt", "zebrafish") is False
    assert view_model.clear_openvino_cache() == {"cleared": [], "locked": [], "orphans_locked": []}
    assert view_model.rescan_weights_folder() == 0
    assert view_model.reset_weights_registry() == 0
    assert view_model.validate_weight_files() == {}
    assert view_model.convert_weight_to_openvino("a.pt") is None


def test_clear_openvino_cache_returns_the_managers_report(view_model):
    report = {"cleared": ["a"], "locked": ["b", "c"], "orphans_locked": []}
    view_model.weight_manager.clear_openvino_cache.return_value = report

    assert view_model.clear_openvino_cache("a.pt") is report
    view_model.weight_manager.clear_openvino_cache.assert_called_once_with("a.pt")


def test_rescan_reset_and_validate_return_the_managers_values(view_model):
    view_model.weight_manager.rescan_source_folder.return_value = 3
    view_model.weight_manager.reset_registry.return_value = 7
    view_model.weight_manager.validate_weight_files.return_value = {"a.pt": True, "b.pt": False}

    assert view_model.rescan_weights_folder() == 3
    assert view_model.reset_weights_registry() == 7
    assert view_model.validate_weight_files() == {"a.pt": True, "b.pt": False}


def test_convert_weight_to_openvino_returns_the_path_or_none_on_failure(view_model):
    view_model.weight_manager.convert_to_openvino.return_value = "/ov/a_openvino_model"
    assert view_model.convert_weight_to_openvino("a.pt") == "/ov/a_openvino_model"

    view_model.weight_manager.convert_to_openvino.side_effect = RuntimeError("export failed")
    assert view_model.convert_weight_to_openvino("a.pt") is None


class TestForceBenchmark:
    def test_reports_the_recommendation_as_a_dict(self, view_model):
        rec = SimpleNamespace(
            backend="openvino",
            device_live="GPU",
            device_batch="CPU",
            estimated_fps_live=42.5,
            openvino_precision="FP16",
        )
        with patch(
            "zebtrack.utils.hardware_benchmark.get_or_run_benchmark",
            return_value=SimpleNamespace(recommendation=rec),
        ) as bench:
            result = view_model.force_benchmark()

        bench.assert_called_once_with(force_rerun=True, quick_mode=True)
        assert result == {
            "backend": "openvino",
            "device_live": "GPU",
            "device_batch": "CPU",
            "fps_live": 42.5,
            "precision": "FP16",
        }

    def test_without_a_recommendation_every_field_is_empty(self, view_model):
        with patch(
            "zebtrack.utils.hardware_benchmark.get_or_run_benchmark",
            return_value=SimpleNamespace(recommendation=None),
        ):
            result = view_model.force_benchmark()

        assert result == {
            "backend": None,
            "device_live": None,
            "device_batch": None,
            "fps_live": 0.0,
            "precision": None,
        }

    def test_a_probe_failure_returns_none_instead_of_raising(self, view_model):
        with patch(
            "zebtrack.utils.hardware_benchmark.get_or_run_benchmark",
            side_effect=RuntimeError("no GPU"),
        ):
            assert view_model.force_benchmark() is None


# ---------------------------------------------------------------------------
# Recording / live sessions
# ---------------------------------------------------------------------------


def test_live_camera_analysis_returns_the_coordinators_result(view_model):
    view_model.live_camera_session_coordinator.start_live_camera_analysis.return_value = "dlg"

    assert view_model.start_live_camera_analysis(2) == "dlg"
    view_model.live_camera_session_coordinator.start_live_camera_analysis.assert_called_once_with(2)


def test_live_project_session_forwards_every_argument(view_model):
    coordinator = view_model.live_camera_session_coordinator
    coordinator.start_live_project_session.return_value = True

    result = view_model.start_live_project_session(
        2,
        "Grupo_A",
        "Sujeito_1",
        120.0,
        camera_index_override=3,
        camera_friendly_name_override="USB cam",
    )

    assert result is True
    coordinator.start_live_project_session.assert_called_once_with(
        day=2,
        group="Grupo_A",
        subject="Sujeito_1",
        duration_s=120.0,
        camera_index_override=3,
        camera_friendly_name_override="USB cam",
    )


def test_session_calls_degrade_without_coordinators(view_model):
    view_model.live_camera_session_coordinator = None
    view_model.recording_session_coordinator = None

    assert view_model.start_live_camera_analysis() is None
    assert view_model.start_live_project_session(1, "g", "s") is None
    view_model.start_live_session(mode="x")  # must not raise
    view_model.start_recording()
    view_model.stop_recording()


def test_recording_service_prefers_the_explicit_one_over_the_coordinators(view_model):
    from_coordinator = SimpleNamespace(is_recording=False)
    explicit = SimpleNamespace(is_recording=True)
    view_model.recording_session_coordinator = SimpleNamespace(recording_service=from_coordinator)

    assert view_model.recording_service is from_coordinator

    view_model.recording_service = explicit

    assert view_model.recording_service is explicit


def test_recording_service_is_none_when_nothing_provides_one(view_model):
    view_model.recording_session_coordinator = None

    assert view_model.recording_service is None

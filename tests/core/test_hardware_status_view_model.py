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


def test_toggle_recording_starts_when_not_recording(view_model):
    view_model.recording_session_coordinator.recording_service = SimpleNamespace(is_recording=False)

    view_model.toggle_recording()

    view_model.recording_session_coordinator.start_recording.assert_called_once()


def test_toggle_recording_stops_when_recording(view_model):
    view_model.recording_session_coordinator.recording_service = SimpleNamespace(is_recording=True)

    view_model.toggle_recording()

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

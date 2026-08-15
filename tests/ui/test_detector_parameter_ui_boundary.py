"""The UI must turn a rejected detector parameter into a visible dialog.

Companion to ``tests/test_detector_parameter_error_boundary.py``, which pins
the exception types down at the coordinator. These pin down the other half:
that each of the three call sites into
``hardware_vm.update_detector_parameters`` actually catches what that call
raises, instead of letting it reach Tk's ``report_callback_exception``.

The assertion that matters in every one of these is ``no exception escaped``.
``showerror was called`` alone would pass against a panel that shows a dialog
and then re-raises.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from zebtrack.coordinators.detector_setup_coordinator import DetectorSetupCoordinatorError
from zebtrack.core.exceptions import ValidationError
from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.event_bus_v2 import UIEvents

pytestmark = pytest.mark.gui


REJECTED = ValidationError("Invalid detector parameter: conf_threshold must be between 0.0 and 1.0")
BROKEN = DetectorSetupCoordinatorError("Failed to update detector parameters: plugin exploded")


# =============================================================================
# ModelDiagnosticsPanel — the "Apply" button
# =============================================================================


@pytest.fixture
def diagnostics_controller():
    hardware_vm = SimpleNamespace(
        get_current_detector_parameters=Mock(
            return_value={
                "confidence_threshold": 0.25,
                "nms_threshold": 0.5,
                "track_threshold": 0.25,
                "match_threshold": 0.95,
                "track_buffer": 90,
                "max_center_distance": 400.0,
                "iou_threshold": 0.05,
                "use_bytetrack": True,
            }
        ),
        update_detector_parameters=Mock(return_value=True),
        restore_detector_defaults=Mock(return_value=True),
        get_all_weight_names=Mock(return_value=["weights.pt"]),
        get_default_weights_summary=Mock(return_value=[]),
        active_weight_name="weights.pt",
    )
    return SimpleNamespace(
        hardware_vm=hardware_vm,
        project_vm=SimpleNamespace(
            resolve_project_model_settings=Mock(return_value=("weights.pt", False))
        ),
        project_manager=SimpleNamespace(project_data={}),
        ui_event_bus=Mock(),
    )


def _panel(tkinter_root, controller):
    from zebtrack.ui.components.model_diagnostics_panel import ModelDiagnosticsPanel

    return ModelDiagnosticsPanel(tkinter_root, controller, scope="global")


def test_rejected_parameter_shows_the_reason(tkinter_root, diagnostics_controller) -> None:
    """The researcher sees WHY the value was refused, not a silent no-op."""
    diagnostics_controller.hardware_vm.update_detector_parameters.side_effect = REJECTED
    panel = _panel(tkinter_root, diagnostics_controller)

    with (
        patch("tkinter.messagebox.showerror") as mock_error,
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        panel._apply_detector_parameters()  # must not raise

    mock_info.assert_not_called()
    mock_error.assert_called_once()
    assert "conf_threshold must be between 0.0 and 1.0" in mock_error.call_args.args[1]


def test_operational_failure_shows_a_generic_message(tkinter_root, diagnostics_controller) -> None:
    """Internal text names services and plugins; it belongs in the log."""
    diagnostics_controller.hardware_vm.update_detector_parameters.side_effect = BROKEN
    panel = _panel(tkinter_root, diagnostics_controller)

    with (
        patch("tkinter.messagebox.showerror") as mock_error,
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        panel._apply_detector_parameters()  # must not raise

    mock_info.assert_not_called()
    mock_error.assert_called_once()
    assert "plugin exploded" not in mock_error.call_args.args[1]


def test_valid_parameters_still_confirm(tkinter_root, diagnostics_controller) -> None:
    """Regression guard: the boundary must not swallow the success path."""
    panel = _panel(tkinter_root, diagnostics_controller)

    with (
        patch("tkinter.messagebox.showerror") as mock_error,
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        panel._apply_detector_parameters()

    mock_error.assert_not_called()
    mock_info.assert_called_once()


# =============================================================================
# EventDispatcher — the DETECTOR_UPDATE_PARAMETERS subscriber
# =============================================================================


def _dispatcher_with_gui(side_effect) -> tuple[Any, Any]:
    """Dispatcher over a fake GUI — no real Tk widget is created."""
    hardware_vm = MagicMock()
    hardware_vm.update_detector_parameters.side_effect = side_effect
    gui: Any = SimpleNamespace(
        event_bus=MagicMock(),
        dialog_manager=MagicMock(),
        controller=SimpleNamespace(hardware_vm=hardware_vm, ui_event_bus=MagicMock()),
    )
    dispatcher: Any = EventDispatcher(gui.event_bus)
    dispatcher.gui = gui
    return dispatcher, gui


def test_dispatcher_publishes_the_rejection() -> None:
    """This runs inside an EventBusV2 subscriber — an escape reaches stderr only."""
    dispatcher, gui = _dispatcher_with_gui(REJECTED)

    dispatcher._on_apply_roi_settings({"confidence_threshold": 1.5})  # must not raise

    published = gui.controller.ui_event_bus.publish.call_args.args[0]
    assert published.type is UIEvents.UI_SHOW_ERROR
    assert "conf_threshold" in published.data.message


def test_dispatcher_publishes_a_generic_message_for_internal_failures() -> None:
    dispatcher, gui = _dispatcher_with_gui(BROKEN)

    dispatcher._on_apply_roi_settings({"confidence_threshold": 0.3})  # must not raise

    published = gui.controller.ui_event_bus.publish.call_args.args[0]
    assert published.type is UIEvents.UI_SHOW_ERROR
    assert "plugin exploded" not in published.data.message


def test_dispatcher_stays_quiet_when_the_update_succeeds() -> None:
    dispatcher, gui = _dispatcher_with_gui(None)
    gui.controller.hardware_vm.update_detector_parameters.return_value = True

    dispatcher._on_apply_roi_settings({"confidence_threshold": 0.3})

    gui.controller.ui_event_bus.publish.assert_not_called()


# =============================================================================
# ApplicationGUI._on_apply_roi_settings — the backward-compat stub
# =============================================================================


def _fake_gui(side_effect):
    """The stub is called unbound, so a namespace stands in for the widget."""
    hardware_vm = MagicMock()
    hardware_vm.update_detector_parameters.side_effect = side_effect
    return SimpleNamespace(
        controller=SimpleNamespace(hardware_vm=hardware_vm),
        dialog_manager=MagicMock(),
    )


def test_gui_stub_reports_the_rejection() -> None:
    from zebtrack.ui.gui import ApplicationGUI

    gui = _fake_gui(REJECTED)

    ApplicationGUI._on_apply_roi_settings(gui, {"confidence_threshold": 1.5})  # must not raise

    gui.dialog_manager.show_error.assert_called_once()
    assert "conf_threshold" in gui.dialog_manager.show_error.call_args.args[1]


def test_gui_stub_reports_internal_failures_generically() -> None:
    from zebtrack.ui.gui import ApplicationGUI

    gui = _fake_gui(BROKEN)

    ApplicationGUI._on_apply_roi_settings(gui, {"confidence_threshold": 0.3})  # must not raise

    gui.dialog_manager.show_error.assert_called_once()
    assert "plugin exploded" not in gui.dialog_manager.show_error.call_args.args[1]

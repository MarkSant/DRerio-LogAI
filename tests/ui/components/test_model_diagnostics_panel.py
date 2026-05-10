from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.model_diagnostics_panel import ModelDiagnosticsPanel
from zebtrack.ui.event_bus_v2 import UIEvents

pytestmark = pytest.mark.gui


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
        get_all_weight_names=Mock(return_value=["weights.pt", "alt.pt"]),
        get_default_weights_summary=Mock(
            return_value=[
                ("🐠 Aquário (det)", "det", "aquarium", "weights.pt"),
                ("🐟 Animal (seg)", "seg", "zebrafish", "seg_project.pt"),
            ]
        ),
        active_weight_name="weights.pt",
    )
    project_vm = SimpleNamespace(
        resolve_project_model_settings=Mock(return_value=("weights.pt", False))
    )
    project_manager = SimpleNamespace(
        project_data={
            "model_overrides": {
                "slot_weights": {"seg:zebrafish": "seg_project.pt"},
            }
        }
    )
    return SimpleNamespace(
        hardware_vm=hardware_vm,
        project_vm=project_vm,
        project_manager=project_manager,
        ui_event_bus=Mock(),
    )


def test_model_diagnostics_panel_global_builds_weight_selector(
    tkinter_root, diagnostics_controller
):
    panel = ModelDiagnosticsPanel(tkinter_root, diagnostics_controller, scope="global")

    assert panel.weights_dropdown is not None
    assert panel.model_test_dropdown is not None
    assert panel.active_weight_var.get() == "weights.pt"


def test_model_diagnostics_panel_project_builds_effective_weight_selector(
    tkinter_root, diagnostics_controller
):
    panel = ModelDiagnosticsPanel(tkinter_root, diagnostics_controller, scope="project")

    assert panel.weights_dropdown is not None
    assert "🐠 Aquário (det): weights.pt" in panel.weights_dropdown["values"]
    assert "🐟 Animal (seg): seg_project.pt" in panel.weights_dropdown["values"]
    assert "Pesos efetivos deste projeto:" in panel.project_weight_summary_var.get()


def test_run_diagnostic_publishes_event(tkinter_root, diagnostics_controller):
    panel = ModelDiagnosticsPanel(tkinter_root, diagnostics_controller, scope="global")
    panel.diagnostic_video_path = "C:/tmp/video.mp4"

    with patch("tkinter.messagebox.showerror") as mock_error:
        panel._run_diagnostic_test()

    mock_error.assert_not_called()
    published_event = diagnostics_controller.ui_event_bus.publish.call_args.args[0]
    assert published_event.type is UIEvents.MODEL_RUN_DIAGNOSTIC
    assert published_event.data.config["video_path"] == "C:/tmp/video.mp4"
    assert published_event.data.config["model_to_test"] == "YOLO (PyTorch)"


def test_apply_detector_parameters_uses_scope(tkinter_root, diagnostics_controller):
    panel = ModelDiagnosticsPanel(tkinter_root, diagnostics_controller, scope="project")

    with patch("tkinter.messagebox.showinfo"):
        panel._apply_detector_parameters()

    payload = diagnostics_controller.hardware_vm.update_detector_parameters.call_args.args[0]
    assert payload["scope"] == "project"


def test_project_diagnostic_includes_selected_effective_weight(
    tkinter_root, diagnostics_controller
):
    panel = ModelDiagnosticsPanel(tkinter_root, diagnostics_controller, scope="project")
    panel.diagnostic_video_path = "C:/tmp/video.mp4"
    panel.active_weight_var.set("🐟 Animal (seg): seg_project.pt")

    with patch("tkinter.messagebox.showerror") as mock_error:
        panel._run_diagnostic_test()

    mock_error.assert_not_called()
    published_event = diagnostics_controller.ui_event_bus.publish.call_args.args[0]
    assert published_event.data.config["active_weight_name"] == "seg_project.pt"

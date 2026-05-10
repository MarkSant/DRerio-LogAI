from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.project_model_configuration_panel import ProjectModelConfigurationPanel

pytestmark = pytest.mark.gui


@pytest.fixture
def project_config_controller():
    detector_state = SimpleNamespace(active_weight_name="weights.pt", use_openvino=False)
    project_vm = SimpleNamespace(
        get_calibration_scope_info=Mock(return_value={"project_loaded": True}),
        resolve_project_model_settings=Mock(return_value=("weights.pt", False)),
        save_project_model_slot_overrides=Mock(),
        handle_calibration_copy_to_project=Mock(),
    )

    def get_weight_names_for_slot(method, target):
        mapping = {
            ("det", "aquarium"): ["weights.pt", "alt_det.pt"],
            ("seg", "zebrafish"): ["seg.pt", "alt_seg.pt"],
        }
        return mapping[(method, target)]

    return SimpleNamespace(
        project_manager=SimpleNamespace(
            project_data={
                "model_overrides": {
                    "slot_weights": {},
                    "use_openvino": None,
                }
            }
        ),
        project_vm=project_vm,
        hardware_vm=SimpleNamespace(
            get_default_weights_summary=Mock(
                return_value=[
                    ("🐠 Aquário (det)", "det", "aquarium", "weights.pt"),
                    ("🐟 Animal (seg)", "seg", "zebrafish", "seg.pt"),
                ]
            ),
            get_weight_names_for_slot=Mock(side_effect=get_weight_names_for_slot),
        ),
        state_manager=SimpleNamespace(get_detector_state=Mock(return_value=detector_state)),
        view=SimpleNamespace(project_diagnostics_panel=None),
    )


def test_project_model_configuration_panel_builds_controls(tkinter_root, project_config_controller):
    panel = ProjectModelConfigurationPanel(tkinter_root, project_config_controller)

    assert len(panel.slot_weight_dropdowns) == 2
    assert "🐠 Aquário (det): weights.pt" in panel.effective_weight_var.get()
    assert "🐟 Animal (seg): seg.pt" in panel.defaults_summary_var.get()


def test_project_model_configuration_panel_saves_preferences(
    tkinter_root, project_config_controller
):
    panel = ProjectModelConfigurationPanel(tkinter_root, project_config_controller)
    panel.slot_weight_choices["det:aquarium"].set("alt_det.pt")
    panel.slot_weight_choices["seg:zebrafish"].set("alt_seg.pt")
    panel.openvino_choice.set(panel.OPENVINO_ON)

    with patch("tkinter.messagebox.showinfo"):
        panel._save_project_preferences()

    project_config_controller.project_vm.save_project_model_slot_overrides.assert_called_once_with(
        {"det:aquarium": "alt_det.pt", "seg:zebrafish": "alt_seg.pt"},
        True,
    )


def test_project_model_configuration_panel_copies_globals(tkinter_root, project_config_controller):
    panel = ProjectModelConfigurationPanel(tkinter_root, project_config_controller)

    with patch("tkinter.messagebox.showinfo"):
        panel._copy_globals_to_project()

    project_config_controller.project_vm.handle_calibration_copy_to_project.assert_called_once()

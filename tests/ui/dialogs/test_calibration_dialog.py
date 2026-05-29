from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

import pytest

from zebtrack.ui.dialogs.calibration_dialog import CalibrationDialog

pytestmark = pytest.mark.gui


def test_get_calibration_section_title_for_global_configuration_mode() -> None:
    dialog = CalibrationDialog.__new__(CalibrationDialog)
    dialog.scope = "global"
    dialog.show_diagnostics = False

    assert dialog._get_calibration_section_title() == "📐 Configuração Global de Modelos"


def test_get_scope_action_text_hides_project_save_action() -> None:
    dialog = CalibrationDialog.__new__(CalibrationDialog)

    assert dialog._get_scope_action_text({"project_loaded": True, "scope": "project"}) is None


def test_build_project_tools_ui_creates_split_tabs() -> None:
    dialog = CalibrationDialog.__new__(CalibrationDialog)
    dialog.controller = SimpleNamespace()
    parent = Mock()

    with (
        patch("zebtrack.ui.dialogs.calibration_dialog.ttk.Label") as mock_label,
        patch("zebtrack.ui.dialogs.calibration_dialog.ttk.Notebook") as mock_notebook_class,
        patch("zebtrack.ui.dialogs.calibration_dialog.ttk.Frame") as mock_frame,
        patch(
            "zebtrack.ui.dialogs.calibration_dialog.ProjectModelConfigurationPanel"
        ) as mock_config,
        patch("zebtrack.ui.dialogs.calibration_dialog.ModelDiagnosticsPanel") as mock_diag,
    ):
        notebook = Mock()
        mock_notebook_class.return_value = notebook
        mock_frame.side_effect = [Mock(), Mock()]
        mock_config.return_value = Mock()
        mock_diag.return_value = Mock()

        dialog._build_project_tools_ui(parent)

    mock_label.assert_called_once()
    assert notebook.add.call_args_list[0].kwargs["text"] == "Config. Modelo IA"
    assert notebook.add.call_args_list[1].kwargs["text"] == "Diagnóstico Modelo IA"
    mock_config.assert_called_once_with(ANY, dialog.controller)
    mock_diag.assert_called_once_with(ANY, dialog.controller, scope="project")


def test_build_global_calibration_ui_composes_panels() -> None:
    dialog = CalibrationDialog.__new__(CalibrationDialog)
    dialog.controller = SimpleNamespace()
    dialog.show_diagnostics = True
    parent = Mock()

    with (
        patch("zebtrack.ui.dialogs.calibration_dialog.ttk.LabelFrame") as mock_labelframe,
        patch(
            "zebtrack.ui.dialogs.calibration_dialog.GlobalModelConfigurationPanel"
        ) as mock_config,
        patch("zebtrack.ui.dialogs.calibration_dialog.ModelDiagnosticsPanel") as mock_diag,
    ):
        mock_labelframe.return_value = Mock()
        mock_config_panel = Mock()
        mock_diag_panel = Mock()
        mock_config.return_value = mock_config_panel
        mock_diag.return_value = mock_diag_panel

        dialog._build_global_calibration_ui(parent)

    mock_config.assert_called_once_with(parent, dialog.controller)
    mock_diag.assert_called_once_with(ANY, dialog.controller, scope="global", parent_dialog=dialog)
    mock_config_panel.set_weight_refresh_callback.assert_called_once_with(
        mock_diag_panel.refresh_weight_options
    )


def test_build_global_calibration_ui_hides_diagnostics_when_disabled() -> None:
    dialog = CalibrationDialog.__new__(CalibrationDialog)
    dialog.controller = SimpleNamespace()
    dialog.show_diagnostics = False
    parent = Mock()

    with (
        patch(
            "zebtrack.ui.dialogs.calibration_dialog.GlobalModelConfigurationPanel"
        ) as mock_config,
        patch("zebtrack.ui.dialogs.calibration_dialog.ModelDiagnosticsPanel") as mock_diag,
    ):
        mock_config.return_value = Mock()

        dialog._build_global_calibration_ui(parent)

    mock_config.assert_called_once_with(parent, dialog.controller)
    mock_diag.assert_not_called()

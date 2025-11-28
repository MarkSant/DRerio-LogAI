from unittest.mock import MagicMock, patch

import pytest

from zebtrack.ui.components.roi_template_manager import ROITemplateManager


@pytest.fixture
def mock_gui(tkinter_root):
    gui = MagicMock()
    gui.root = tkinter_root
    # Updated mock structure to reflect Phase 6 changes
    gui.zone_controls = MagicMock()
    gui.zone_controls.roi_template_combobox = MagicMock()
    return gui


@pytest.fixture
def mock_pm():
    return MagicMock()


@pytest.fixture
def manager(mock_pm, mock_gui):
    return ROITemplateManager(mock_pm, mock_gui)


def test_refresh_templates(manager, mock_pm, mock_gui):
    mock_pm.list_roi_templates.return_value = [
        {"name": "T1", "location": "project", "file": "t1.json"},
        {"name": "T2", "location": "global", "file": "t2.json"},
    ]

    with patch("zebtrack.ui.components.roi_template_manager.Path") as MockPath:
        MockPath.return_value.exists.return_value = True
        MockPath.return_value.is_file.return_value = True

        manager.refresh_templates()

        assert len(manager._cache) == 2
        # Verify values set via item assignment
        # Note: display names include prefixes
        expected_values = ["📁 T1", "🌐 T2"]
        mock_gui.zone_controls.roi_template_combobox.__setitem__.assert_any_call(
            "values", expected_values
        )

        # Verify state configuration
        mock_gui.zone_controls.roi_template_combobox.configure.assert_called_with(state="readonly")


def test_apply_template(manager, mock_pm, mock_gui):
    manager._cache = [
        {"name": "T1", "display_name": "T1", "location": "project", "file": "t1.json"}
    ]
    manager.template_var.set("T1")

    mock_pm.get_active_zone_video.return_value = "video.mp4"
    mock_pm.load_roi_template.return_value = MagicMock()

    with patch("zebtrack.ui.components.roi_template_manager.Path") as MockPath:
        MockPath.return_value.exists.return_value = True

        result = manager.apply_template()

        assert result is True
        mock_pm.load_roi_template.assert_called()
        mock_pm.save_zone_data.assert_called()
        mock_gui.controller.setup_detector_zones.assert_called()


def test_delete_template(manager, mock_pm, mock_gui):
    manager._cache = [
        {"name": "T1", "display_name": "T1", "location": "project", "file": "t1.json"}
    ]
    manager.template_var.set("T1")

    mock_gui.ask_ok_cancel.return_value = True

    result = manager.delete_template()

    assert result is True
    mock_pm.delete_roi_template.assert_called()


def test_save_template(manager, mock_pm, mock_gui):
    mock_pm.get_zone_data.return_value = MagicMock(polygon=[(0, 0)], roi_polygons=[])
    mock_pm.project_path = "path"

    mock_gui._show_template_save_dialog.return_value = {
        "name": "NewT",
        "save_arena": True,
        "save_rois": True,
        "save_location": "project",
        "custom_path": None,
    }

    mock_pm.save_roi_template.return_value = {"name": "NewT"}

    with patch("zebtrack.ui.components.roi_template_manager.Path") as MockPath:
        MockPath.return_value.exists.return_value = True
        manager.save_template()

    mock_pm.save_roi_template.assert_called()
    mock_gui.show_info.assert_called()

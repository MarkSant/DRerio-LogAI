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
        mock_gui.dialog_manager.show_warning.assert_called()


def test_delete_template(manager, mock_pm, mock_gui):
    manager._cache = [
        {"name": "T1", "display_name": "T1", "location": "project", "file": "t1.json"}
    ]
    manager.template_var.set("T1")

    mock_gui.dialog_manager.ask_ok_cancel.return_value = True

    result = manager.delete_template()

    assert result is True
    mock_pm.delete_roi_template.assert_called()


def test_save_template(manager, mock_pm, mock_gui):
    mock_pm.get_zone_data.return_value = MagicMock(polygon=[(0, 0)], roi_polygons=[])
    mock_pm.project_path = "path"

    dialog_result = {
        "name": "NewT",
        "save_arena": True,
        "save_rois": True,
        "save_location": "project",
        "custom_path": None,
    }

    mock_pm.save_roi_template.return_value = {"name": "NewT"}

    with (
        patch("zebtrack.ui.components.roi_template_manager.Path") as MockPath,
        patch("zebtrack.ui.dialogs.SaveROITemplateDialog") as MockDialog,
    ):
        MockPath.return_value.exists.return_value = True
        MockDialog.return_value.result = dialog_result
        manager.save_template()

    mock_pm.save_roi_template.assert_called()
    mock_gui.dialog_manager.show_info.assert_called()


def test_get_selected_template_returns_match(manager):
    manager._cache = [
        {"name": "T1", "display_name": "📁 T1", "location": "project", "file": "t1.json"}
    ]
    manager.template_var.set("📁 T1")

    selected = manager.get_selected_template()

    assert selected is not None
    assert selected["name"] == "T1"


def test_apply_template_no_selection(manager, mock_gui):
    manager._cache = []
    manager.template_var.set("")

    result = manager.apply_template()

    assert result is False
    mock_gui.dialog_manager.show_warning.assert_called_once()


def test_apply_template_no_active_video(manager, mock_pm, mock_gui):
    manager._cache = [
        {"name": "T1", "display_name": "T1", "location": "project", "file": "t1.json"}
    ]
    manager.template_var.set("T1")
    mock_pm.get_active_zone_video.return_value = None
    mock_gui.pending_single_video_path = None

    result = manager.apply_template()

    assert result is False
    mock_gui.dialog_manager.show_warning.assert_called_once()


def test_validate_template_file_fixes_path(manager, tmp_path):
    templates_dir = tmp_path / ".zebtrack" / "templates"
    templates_dir.mkdir(parents=True)
    template_path = templates_dir / "t.json"
    template_path.write_text("{}")

    bad_path = str(template_path).replace(".zebtrack", ",zebtrack")
    template = {"file": bad_path}

    assert manager._validate_template_file(template) is True
    assert template["file"] == str(template_path)


def test_select_template_by_metadata_slug(manager):
    manager._cache = [
        {
            "name": "Template",
            "display_name": "🌐 Template",
            "location": "global",
            "slug": "template-slug",
        }
    ]

    manager.select_template_by_metadata({"slug": "template-slug"})

    assert manager.template_var.get() == "🌐 Template"


def test_import_template_error_shows_message(manager, mock_pm, mock_gui):
    with patch(
        "zebtrack.ui.components.roi_template_manager.filedialog.askopenfilename",
        return_value="/path/to/template.json",
    ):
        mock_pm.import_roi_template.side_effect = RuntimeError("boom")

        manager.import_template()

    mock_gui.dialog_manager.show_error.assert_called_once()


def test_update_combobox_values_falls_back_to_gui_combobox(mock_pm, tkinter_root):
    gui = MagicMock()
    gui.root = tkinter_root
    gui.zone_controls = None
    gui.roi_template_combobox = MagicMock()

    manager = ROITemplateManager(mock_pm, gui)
    manager._update_combobox_values(["📁 Local"])

    gui.roi_template_combobox.__setitem__.assert_called_once_with("values", ["📁 Local"])
    gui.roi_template_combobox.configure.assert_called_once_with(state="readonly")

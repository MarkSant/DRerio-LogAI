"""Tests for DialogManager component."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.components.dialog_manager import DialogManager
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture(autouse=True)
def block_all_dialogs():
    """Automatically block ALL dialog windows for all tests in this file."""
    with (
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.askyesno", return_value=False),
        patch("tkinter.messagebox.askokcancel", return_value=False),
        patch("tkinter.messagebox.askyesnocancel", return_value=None),
    ):
        yield


@pytest.fixture
def mock_validation_manager():
    """Create a mock ValidationManager."""
    vm = Mock()
    return vm


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    controller = Mock()
    controller.project_manager = Mock()
    controller.project_manager.project_path = "/path/to/project"
    controller.project_manager.project_data = {"experiment_days": [1, 2, 3]}
    controller.project_manager.get_active_zone_video = Mock(return_value=None)
    controller.project_manager.get_zone_data = Mock()
    controller.project_manager.import_roi_template = Mock()
    controller.project_manager.save_zone_data = Mock()
    controller.project_manager.set_active_zone_video = Mock()
    controller.settings = Mock()
    controller.hardware_vm = Mock()
    controller.hardware_vm.use_openvino = False
    controller.hardware_vm.active_weight_name = "test_weight"
    controller.hardware_vm.get_openvino_status = Mock(return_value="disabled")
    controller.setup_detector_zones = Mock()
    controller.global_calibration_session = Mock()
    controller.project_calibration_session = Mock()
    return controller


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBusV2."""
    return Mock()


@pytest.fixture
def mock_gui(tkinter_root, mock_validation_manager, mock_controller):
    """Create a mock ApplicationGUI instance."""
    gui = Mock()
    gui.root = tkinter_root
    gui.validation_manager = mock_validation_manager
    gui.controller = mock_controller
    gui.project_manager = mock_controller.project_manager
    gui.state_manager = Mock()
    gui.event_dispatcher = Mock()
    gui.event_bus = Mock()

    # Canvas manager
    gui.canvas_manager = Mock()
    gui.canvas_manager.redraw_zones_from_project_data = Mock()

    # UI elements (legacy - some tests may still reference these directly)
    gui.progress_frame = Mock()
    gui.progress_frame.winfo_viewable = Mock(return_value=False)
    gui.progress_frame.pack = Mock()
    gui.progress_bar = {"value": 0}
    gui.cancel_proc_btn = Mock()
    gui.video_container = Mock()
    gui.notebook = Mock()
    gui.zone_tab_frame = Mock()

    # Analysis display widget (new structure - show_progress_bar uses this)
    gui.analysis_display_widget = Mock()
    gui.analysis_display_widget.progress_frame = Mock()
    gui.analysis_display_widget.progress_frame.winfo_viewable = Mock(return_value=False)
    gui.analysis_display_widget.progress_frame.pack = Mock()
    gui.analysis_display_widget.progress_bar = {"value": 0}
    gui.analysis_display_widget.cancel_btn = Mock()
    gui.analysis_display_widget.video_container = Mock()

    # External trigger notice
    gui.external_trigger_notice_label = Mock()
    gui.external_trigger_notice_label.config = Mock()
    gui.external_trigger_notice_label.cget = Mock(
        side_effect=lambda x: "#FFFFFF" if x == "background" else "#000000"
    )
    gui.external_trigger_notice_var = Mock()
    gui.external_trigger_notice_var.set = Mock()
    gui._external_notice_default_bg = "#FFFFFF"
    gui._external_notice_default_fg = "#000000"

    # Methods
    gui.update_openvino_checkbox = Mock()
    gui.set_active_weight_in_dropdown = Mock()
    gui.update_openvino_status_display = Mock()
    gui.weight_hardware_manager = Mock()
    gui.roi_template_manager = Mock()
    gui.roi_template_manager.refresh_templates = Mock()
    gui.roi_template_manager.select_template_by_metadata = Mock()
    gui.update_zone_listbox = Mock()
    gui._refresh_zone_indicators = Mock()
    gui._enable_roi_button_if_arena_exists = Mock()
    gui._format_day_display = Mock(side_effect=lambda x: f"{int(x):02d}" if x else "")
    gui.apply_pending_readiness_snapshot = Mock()
    gui._build_video_hierarchy_snapshot = Mock(return_value={})

    # Variables
    gui.pending_single_video_path = None
    gui.pending_single_video_config = None
    gui._overview_video_index = {}

    return gui


@pytest.fixture
def dialog_manager(mock_gui, mock_event_bus):
    """Create a DialogManager instance for testing."""
    return DialogManager(mock_gui, event_bus_v2=mock_event_bus)


@pytest.mark.gui
class TestDialogManagerInitialization:
    """Tests for DialogManager initialization."""

    def test_initialization(self, dialog_manager, mock_gui, mock_event_bus):
        """Test that DialogManager initializes correctly."""
        assert dialog_manager.gui is mock_gui
        assert dialog_manager.event_bus_v2 is mock_event_bus

    def test_initialization_with_real_gui(self, tkinter_root):
        """Test initialization with minimal real gui object."""
        gui = Mock()
        gui.root = tkinter_root
        manager = DialogManager(gui)
        assert manager.gui is gui
        assert manager.event_bus_v2 is None


@pytest.mark.gui
class TestMessageBoxWrappers:
    """Tests for MessageBox wrapper methods."""

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_show_error(self, mock_messagebox, dialog_manager):
        """Test show_error displays error message box."""
        dialog_manager.show_error("Error Title", "Error message")

        mock_messagebox.showerror.assert_called_once_with("Error Title", "Error message")

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_show_warning(self, mock_messagebox, dialog_manager):
        """Test show_warning displays warning message box."""
        dialog_manager.show_warning("Warning Title", "Warning message")

        mock_messagebox.showwarning.assert_called_once_with("Warning Title", "Warning message")

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_show_info(self, mock_messagebox, dialog_manager):
        """Test show_info displays info message box."""
        dialog_manager.show_info("Info Title", "Info message")

        mock_messagebox.showinfo.assert_called_once_with("Info Title", "Info message")

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_ok_cancel_returns_true(self, mock_messagebox, dialog_manager):
        """Test ask_ok_cancel returns True when OK clicked."""
        mock_messagebox.askokcancel.return_value = True

        result = dialog_manager.ask_ok_cancel("Confirm", "Are you sure?")

        assert result is True
        mock_messagebox.askokcancel.assert_called_once_with("Confirm", "Are you sure?")

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_ok_cancel_returns_false(self, mock_messagebox, dialog_manager):
        """Test ask_ok_cancel returns False when Cancel clicked."""
        mock_messagebox.askokcancel.return_value = False

        result = dialog_manager.ask_ok_cancel("Confirm", "Are you sure?")

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_returns_true(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no returns True when Yes clicked."""
        mock_messagebox.askyesno.return_value = True

        result = dialog_manager.ask_yes_no("Question", "Proceed?")

        assert result is True
        mock_messagebox.askyesno.assert_called_once_with("Question", "Proceed?", icon="question")

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_returns_false(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no returns False when No clicked."""
        mock_messagebox.askyesno.return_value = False

        result = dialog_manager.ask_yes_no("Question", "Proceed?")

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_with_custom_icon(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no with custom icon."""
        mock_messagebox.askyesno.return_value = True

        result = dialog_manager.ask_yes_no("Warning", "Delete?", icon="warning")

        mock_messagebox.askyesno.assert_called_once_with("Warning", "Delete?", icon="warning")
        assert result is True

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_cancel_returns_true(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no_cancel returns True when Yes clicked."""
        mock_messagebox.askyesnocancel.return_value = True

        result = dialog_manager.ask_yes_no_cancel("Save?", "Save changes?")

        assert result is True
        mock_messagebox.askyesnocancel.assert_called_once_with(
            "Save?", "Save changes?", icon="question"
        )

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_cancel_returns_false(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no_cancel returns False when No clicked."""
        mock_messagebox.askyesnocancel.return_value = False

        result = dialog_manager.ask_yes_no_cancel("Save?", "Save changes?")

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_cancel_returns_none(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no_cancel returns None when Cancel clicked."""
        mock_messagebox.askyesnocancel.return_value = None

        result = dialog_manager.ask_yes_no_cancel("Save?", "Save changes?")

        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_ask_yes_no_cancel_with_custom_icon(self, mock_messagebox, dialog_manager):
        """Test ask_yes_no_cancel with custom icon."""
        mock_messagebox.askyesnocancel.return_value = True

        dialog_manager.ask_yes_no_cancel("Exit?", "Exit app?", icon="warning")

        mock_messagebox.askyesnocancel.assert_called_once_with("Exit?", "Exit app?", icon="warning")


@pytest.mark.gui
class TestFileDialogs:
    """Tests for file dialog methods."""

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_directory_returns_path(self, mock_filedialog, dialog_manager):
        """Test ask_directory returns selected directory."""
        mock_filedialog.askdirectory.return_value = "/path/to/directory"

        result = dialog_manager.ask_directory("Select Directory")

        assert result == "/path/to/directory"
        mock_filedialog.askdirectory.assert_called_once_with(title="Select Directory")

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_directory_returns_empty_on_cancel(self, mock_filedialog, dialog_manager):
        """Test ask_directory returns empty string on cancel."""
        mock_filedialog.askdirectory.return_value = ""

        result = dialog_manager.ask_directory("Select Directory")

        assert result == ""

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_directory_with_initial_dir(self, mock_filedialog, dialog_manager):
        """Test ask_directory with initial directory."""
        mock_filedialog.askdirectory.return_value = "/selected/path"

        dialog_manager.ask_directory("Select Directory", initial_dir="/initial/path")

        mock_filedialog.askdirectory.assert_called_once_with(
            title="Select Directory", initialdir="/initial/path"
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filename_returns_path(self, mock_filedialog, dialog_manager):
        """Test ask_open_filename returns selected file."""
        mock_filedialog.askopenfilename.return_value = "/path/to/file.txt"
        filetypes = [("Text files", "*.txt"), ("All files", "*.*")]

        result = dialog_manager.ask_open_filename("Select File", filetypes)

        assert result == "/path/to/file.txt"
        mock_filedialog.askopenfilename.assert_called_once_with(
            title="Select File", filetypes=filetypes
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filename_returns_empty_on_cancel(self, mock_filedialog, dialog_manager):
        """Test ask_open_filename returns empty string on cancel."""
        mock_filedialog.askopenfilename.return_value = ""
        filetypes = [("Text files", "*.txt")]

        result = dialog_manager.ask_open_filename("Select File", filetypes)

        assert result == ""

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filename_with_initial_dir(self, mock_filedialog, dialog_manager):
        """Test ask_open_filename with initial directory."""
        mock_filedialog.askopenfilename.return_value = "/path/to/file.txt"
        filetypes = [("Text files", "*.txt")]

        dialog_manager.ask_open_filename("Select File", filetypes, initial_dir="/initial/dir")

        mock_filedialog.askopenfilename.assert_called_once_with(
            title="Select File", filetypes=filetypes, initialdir="/initial/dir"
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filenames_returns_multiple_files(self, mock_filedialog, dialog_manager):
        """Test ask_open_filenames returns multiple selected files."""
        mock_filedialog.askopenfilenames.return_value = (
            "/path/to/file1.txt",
            "/path/to/file2.txt",
        )
        filetypes = [("Text files", "*.txt")]

        result = dialog_manager.ask_open_filenames("Select Files", filetypes)

        assert result == ("/path/to/file1.txt", "/path/to/file2.txt")
        mock_filedialog.askopenfilenames.assert_called_once_with(
            title="Select Files", filetypes=filetypes
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filenames_returns_empty_on_cancel(self, mock_filedialog, dialog_manager):
        """Test ask_open_filenames returns empty tuple on cancel."""
        mock_filedialog.askopenfilenames.return_value = ()
        filetypes = [("Text files", "*.txt")]

        result = dialog_manager.ask_open_filenames("Select Files", filetypes)

        assert result == ()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filenames_with_initial_dir(self, mock_filedialog, dialog_manager):
        """Test ask_open_filenames with initial directory."""
        mock_filedialog.askopenfilenames.return_value = ("/path/to/file.txt",)
        filetypes = [("Text files", "*.txt")]

        dialog_manager.ask_open_filenames("Select Files", filetypes, initial_dir="/initial/dir")

        mock_filedialog.askopenfilenames.assert_called_once_with(
            title="Select Files", filetypes=filetypes, initialdir="/initial/dir"
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_save_filename_returns_path(self, mock_filedialog, dialog_manager):
        """Test ask_save_filename returns selected save path."""
        mock_filedialog.asksaveasfilename.return_value = "/path/to/save.txt"

        result = dialog_manager.ask_save_filename(
            title="Save File",
            filetypes=[("Text files", "*.txt")],
            defaultextension=".txt",
        )

        assert result == "/path/to/save.txt"
        mock_filedialog.asksaveasfilename.assert_called_once_with(
            title="Save File",
            filetypes=[("Text files", "*.txt")],
            defaultextension=".txt",
        )

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_save_filename_returns_empty_on_cancel(self, mock_filedialog, dialog_manager):
        """Test ask_save_filename returns empty string on cancel."""
        mock_filedialog.asksaveasfilename.return_value = ""

        result = dialog_manager.ask_save_filename(title="Save File")

        assert result == ""

    @patch("zebtrack.ui.components.dialog_manager.simpledialog")
    def test_ask_string_returns_input(self, mock_simpledialog, dialog_manager):
        """Test ask_string returns user input."""
        mock_simpledialog.askstring.return_value = "User Input"

        result = dialog_manager.ask_string("Enter Name", "Name:")

        assert result == "User Input"
        mock_simpledialog.askstring.assert_called_once_with(
            "Enter Name", "Name:", initialvalue=None
        )

    @patch("zebtrack.ui.components.dialog_manager.simpledialog")
    def test_ask_string_returns_none_on_cancel(self, mock_simpledialog, dialog_manager):
        """Test ask_string returns None on cancel."""
        mock_simpledialog.askstring.return_value = None

        result = dialog_manager.ask_string("Enter Name", "Name:")

        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.simpledialog")
    def test_ask_string_with_initial_value(self, mock_simpledialog, dialog_manager):
        """Test ask_string with initial value."""
        mock_simpledialog.askstring.return_value = "Modified Value"

        dialog_manager.ask_string("Enter Name", "Name:", initialvalue="Initial")

        mock_simpledialog.askstring.assert_called_once_with(
            "Enter Name", "Name:", initialvalue="Initial"
        )


@pytest.mark.gui
class TestCalibrationDialogs:
    """Tests for calibration dialog methods."""

    @patch("zebtrack.ui.dialogs.calibration_dialog.CalibrationDialog")
    def test_open_global_calibration_window(
        self, mock_calibration_dialog, dialog_manager, mock_controller
    ):
        """Test opening global calibration window."""
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        mock_controller.global_calibration_session.return_value = mock_context

        dialog_manager.open_global_calibration_window()

        mock_controller.global_calibration_session.assert_called_once()
        mock_calibration_dialog.assert_called_once_with(dialog_manager.gui.root, mock_controller)

    @patch("zebtrack.ui.dialogs.calibration_dialog.CalibrationDialog")
    def test_open_project_calibration_window_no_project(
        self, mock_calibration_dialog, dialog_manager, mock_controller
    ):
        """Test opening project calibration when no project loaded."""
        mock_controller.project_manager.project_path = None

        with patch.object(dialog_manager, "show_warning") as mock_warning:
            dialog_manager.open_project_calibration_window()

        mock_warning.assert_called_once()
        mock_calibration_dialog.assert_not_called()

    @patch("zebtrack.ui.dialogs.calibration_dialog.CalibrationDialog")
    def test_open_project_calibration_window_success(
        self, mock_calibration_dialog, dialog_manager, mock_controller, mock_gui
    ):
        """Test opening project calibration window successfully."""
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        mock_controller.project_calibration_session.return_value = mock_context

        dialog_manager.open_project_calibration_window()

        mock_controller.project_calibration_session.assert_called_once()
        mock_calibration_dialog.assert_called_once_with(mock_gui.root, mock_controller)
        mock_gui.weight_hardware_manager.update_openvino_checkbox.assert_called_once_with(False)
        mock_gui.weight_hardware_manager.set_active_weight_in_dropdown.assert_called_once_with(
            "test_weight"
        )
        mock_gui.weight_hardware_manager.update_openvino_status_display.assert_called_once_with(
            "disabled"
        )


@pytest.mark.gui
class TestROITemplateDialogs:
    """Tests for ROI template dialog methods."""

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.SaveROITemplateDialog")
    def test_show_template_save_dialog_returns_result(self, mock_dialog_class, dialog_manager):
        """Test show_template_save_dialog returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {"name": "Template1", "save_arena": True}
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.show_template_save_dialog(
            has_arena=True,
            has_rois=True,
            allow_project=True,
            initial_name="Default",
        )

        assert result == {"name": "Template1", "save_arena": True}
        mock_dialog_class.assert_called_once_with(
            dialog_manager.gui.root,
            default_name="Default",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.SaveROITemplateDialog")
    def test_show_template_save_dialog_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test show_template_save_dialog returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.show_template_save_dialog(
            has_arena=True, has_rois=False, allow_project=False, initial_name="Test"
        )

        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_roi_template_cancelled(self, mock_filedialog, dialog_manager):
        """Test import_roi_template when user cancels file selection."""
        mock_filedialog.askopenfilename.return_value = ""

        dialog_manager.import_roi_template()

        dialog_manager.gui.controller.project_manager.import_roi_template.assert_not_called()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_roi_template_success(self, mock_filedialog, dialog_manager, mock_gui):
        """Test successful ROI template import."""
        mock_filedialog.askopenfilename.return_value = "/path/to/template.json"
        metadata = {"name": "Imported Template", "includes_arena": True}
        mock_gui.controller.project_manager.import_roi_template.return_value = metadata

        with patch.object(dialog_manager, "show_info") as mock_info:
            dialog_manager.import_roi_template()

        mock_gui.controller.project_manager.import_roi_template.assert_called_once_with(
            "/path/to/template.json"
        )
        mock_gui.roi_template_manager.refresh_templates.assert_called_once()
        mock_gui.roi_template_manager.select_template_by_metadata.assert_called_once_with(metadata)
        mock_info.assert_called_once()
        assert "Imported Template" in mock_info.call_args[0][1]

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_roi_template_no_project_manager(
        self, mock_filedialog, dialog_manager, mock_gui
    ):
        """Test import_roi_template when project_manager is None."""
        mock_gui.controller.project_manager = None

        dialog_manager.import_roi_template()

        mock_filedialog.askopenfilename.assert_not_called()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_and_apply_roi_template_cancelled(self, mock_filedialog, dialog_manager):
        """Test import_and_apply_roi_template when user cancels."""
        mock_filedialog.askopenfilename.return_value = ""

        dialog_manager.import_and_apply_roi_template()

        dialog_manager.gui.canvas_manager.redraw_zones_from_project_data.assert_not_called()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_and_apply_roi_template_no_active_video(
        self, mock_filedialog, dialog_manager, mock_gui
    ):
        """Test import_and_apply when no active video."""
        mock_filedialog.askopenfilename.return_value = "/path/to/template.json"
        mock_gui.controller.project_manager.get_active_zone_video.return_value = None
        mock_gui.pending_single_video_path = None

        with patch.object(dialog_manager, "show_warning") as mock_warning:
            dialog_manager.import_and_apply_roi_template()

        mock_warning.assert_called_once()
        assert "Selecione um vídeo" in mock_warning.call_args[0][1]

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_and_apply_roi_template_success(
        self, mock_filedialog, dialog_manager, mock_gui, tmp_path, mock_event_bus
    ):
        """Test successful import and apply of ROI template with event bus."""
        # Create temporary template file
        template_file = tmp_path / "template.json"
        template_data = {
            "polygon": [[100, 100], [200, 100], [200, 200], [100, 200]],
            "roi_polygons": [[[120, 120], [180, 180]]],
            "roi_names": ["ROI_1"],
            "roi_colors": [[255, 0, 0]],
        }
        import json

        with open(template_file, "w") as f:
            json.dump(template_data, f)

        mock_filedialog.askopenfilename.return_value = str(template_file)
        mock_gui.controller.project_manager.get_active_zone_video.return_value = (
            "/path/to/video.mp4"
        )
        metadata = {"name": "Applied Template"}
        mock_gui.controller.project_manager.import_roi_template.return_value = metadata

        with patch.object(dialog_manager, "show_info") as mock_info:
            dialog_manager.import_and_apply_roi_template()

        mock_gui.controller.project_manager.save_zone_data.assert_called_once()
        mock_gui.controller.setup_detector_zones.assert_called_once()
        # Removed direct call assertions
        # mock_gui.canvas_manager.redraw_zones_from_project_data.assert_called_once()
        # mock_gui.update_zone_listbox.assert_called_once()
        mock_info.assert_called_once()

        # Verify Event Bus publishing
        assert mock_event_bus.publish.call_count >= 1
        # Check for ZONES_UPDATED event
        calls = mock_event_bus.publish.call_args_list
        zones_updated_call = next(
            (call for call in calls if call[0][0].type == UIEvents.ZONES_UPDATED), None
        )
        assert zones_updated_call is not None


@pytest.mark.gui
class TestAnalysisDialogs:
    """Tests for analysis dialog methods."""

    @patch("zebtrack.ui.dialogs.center_periphery_dialog.CenterPeripheryDialog")
    def test_open_center_periphery_dialog_returns_result(self, mock_dialog_class, dialog_manager):
        """Test open_center_periphery_dialog returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {"method": "percentage", "value": 50}
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_center_periphery_dialog()

        assert result == {"method": "percentage", "value": 50}
        mock_dialog_class.assert_called_once_with(dialog_manager.gui.root)

    @patch("zebtrack.ui.dialogs.center_periphery_dialog.CenterPeripheryDialog")
    def test_open_center_periphery_dialog_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test open_center_periphery_dialog returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_center_periphery_dialog()

        assert result is None

    @patch("zebtrack.ui.dialogs.template_dialog.TemplateDialog")
    def test_open_template_rois_dialog_returns_result(self, mock_dialog_class, dialog_manager):
        """Test open_template_rois_dialog returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {"template_type": "grid", "rows": 3, "cols": 3}
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_template_rois_dialog()

        assert result == {"template_type": "grid", "rows": 3, "cols": 3}
        mock_dialog_class.assert_called_once_with(dialog_manager.gui.root)

    @patch("zebtrack.ui.dialogs.template_dialog.TemplateDialog")
    def test_open_template_rois_dialog_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test open_template_rois_dialog returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_template_rois_dialog()

        assert result is None

    @patch("zebtrack.ui.dialogs.single_video_config_dialog.SingleVideoConfigDialog")
    def test_open_single_video_config_dialog_returns_result(
        self, mock_dialog_class, dialog_manager, mock_controller
    ):
        """Test open_single_video_config_dialog returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {
            "analysis_interval_frames": 20,
            "display_interval_frames": 15,
        }
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_single_video_config_dialog()

        assert result == {
            "analysis_interval_frames": 20,
            "display_interval_frames": 15,
        }
        mock_dialog_class.assert_called_once_with(
            dialog_manager.gui.root,
            settings_obj=mock_controller.settings,
            event_bus=dialog_manager.gui.event_bus,
        )

    @patch("zebtrack.ui.dialogs.single_video_config_dialog.SingleVideoConfigDialog")
    def test_open_single_video_config_dialog_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test open_single_video_config_dialog returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.open_single_video_config_dialog()

        assert result is None


@pytest.mark.gui
class TestProjectAndRecordingDialogs:
    """Tests for project and recording dialog methods."""

    @patch("zebtrack.ui.dialogs.pending_videos_dialog.PendingVideosDialog")
    def test_show_pending_videos_dialog_returns_result(
        self, mock_dialog_class, dialog_manager, mock_gui, mock_event_bus
    ):
        """Test show_pending_videos_dialog returns dialog result and publishes event."""
        mock_dialog = Mock()
        mock_dialog.result = {"selected_videos": ["/path/to/video.mp4"]}
        mock_dialog_class.return_value = mock_dialog

        ready_with_trajectory = [{"path": "/video1.mp4"}]
        ready_with_zones = [{"path": "/video2.mp4"}]
        arena_only: list[dict[str, object]] = []
        without_arena: list[dict[str, object]] = []

        result = dialog_manager.show_pending_videos_dialog(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        assert result == {"selected_videos": ["/path/to/video.mp4"]}
        mock_dialog_class.assert_called_once()

        # Verify Event Bus publishing
        assert mock_event_bus.publish.call_count >= 1
        calls = mock_event_bus.publish.call_args_list
        readiness_updated_call = next(
            (call for call in calls if call[0][0].type == UIEvents.READINESS_SNAPSHOT_UPDATED), None
        )
        assert readiness_updated_call is not None

    @patch("zebtrack.ui.dialogs.pending_videos_dialog.PendingVideosDialog")
    def test_show_pending_videos_dialog_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test show_pending_videos_dialog returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.show_pending_videos_dialog(
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
        )

        assert result is None

    @patch("zebtrack.ui.dialogs.start_recording_dialog.StartRecordingDialog")
    def test_ask_recording_details_unified_no_experiment_days(
        self, mock_dialog_class, dialog_manager, mock_controller
    ):
        """Test ask_recording_details_unified when no experiment_days configured."""
        mock_controller.project_manager.project_data = {}

        with patch.object(dialog_manager, "show_error") as mock_error:
            result = dialog_manager.ask_recording_details_unified()

        assert result is None
        mock_error.assert_called_once()
        mock_dialog_class.assert_not_called()

    @patch("zebtrack.ui.dialogs.start_recording_dialog.StartRecordingDialog")
    def test_ask_recording_details_unified_returns_result(
        self, mock_dialog_class, dialog_manager, mock_controller
    ):
        """Test ask_recording_details_unified returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {"day": 1, "group": "G1", "subject": 1}
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.ask_recording_details_unified()

        assert result == {"day": 1, "group": "G1", "subject": 1}
        mock_dialog_class.assert_called_once_with(
            dialog_manager.gui.root, mock_controller.project_manager
        )

    @patch("zebtrack.ui.dialogs.start_recording_dialog.StartRecordingDialog")
    def test_ask_recording_details_unified_returns_none_on_cancel(
        self, mock_dialog_class, dialog_manager
    ):
        """Test ask_recording_details_unified returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.ask_recording_details_unified()

        assert result is None

    @patch("zebtrack.ui.dialogs.missing_metadata_dialog.MissingMetadataDialog")
    def test_ask_missing_metadata_returns_result(self, mock_dialog_class, dialog_manager):
        """Test ask_missing_metadata returns dialog result."""
        mock_dialog = Mock()
        mock_dialog.result = {"day": 2, "group": "G2", "subject": 3}
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.ask_missing_metadata("exp_123")

        assert result == {"day": 2, "group": "G2", "subject": 3}
        mock_dialog_class.assert_called_once_with(dialog_manager.gui.root, "exp_123")

    @patch("zebtrack.ui.dialogs.missing_metadata_dialog.MissingMetadataDialog")
    def test_ask_missing_metadata_returns_none_on_cancel(self, mock_dialog_class, dialog_manager):
        """Test ask_missing_metadata returns None when cancelled."""
        mock_dialog = Mock()
        mock_dialog.result = None
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.ask_missing_metadata("exp_123")

        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_open_project_workflow_cancelled(self, mock_filedialog, dialog_manager):
        """Test open_project_workflow when user cancels directory selection."""
        mock_filedialog.askdirectory.return_value = ""

        dialog_manager.open_project_workflow()

        dialog_manager.gui.event_dispatcher.publish_event.assert_not_called()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_open_project_workflow_success(self, mock_filedialog, dialog_manager, mock_gui):
        """Test successful project workflow opening."""
        mock_filedialog.askdirectory.return_value = "/path/to/project"

        dialog_manager.open_project_workflow()

        mock_gui.event_dispatcher.publish_event.assert_called_once_with(
            UIEvents.PROJECT_OPEN, {"project_path": "/path/to/project"}
        )


@pytest.mark.gui
class TestConfirmationDialogs:
    """Tests for confirmation dialog methods."""

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_delete_roi_template_confirmed(self, mock_messagebox, dialog_manager):
        """Test confirm_delete_roi_template when user confirms."""
        mock_messagebox.askyesno.return_value = True

        result = dialog_manager.confirm_delete_roi_template(
            "Template1", "/path/to/template.json", "Global"
        )

        assert result is True
        mock_messagebox.askyesno.assert_called_once()
        call_args = mock_messagebox.askyesno.call_args
        assert "Template1" in call_args[0][1]
        assert "Global" in call_args[0][1]
        assert call_args[1]["icon"] == "warning"

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_delete_roi_template_cancelled(self, mock_messagebox, dialog_manager):
        """Test confirm_delete_roi_template when user cancels."""
        mock_messagebox.askyesno.return_value = False

        result = dialog_manager.confirm_delete_roi_template(
            "Template1", "/path/to/template.json", "Project"
        )

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_remove_roi_confirmed(self, mock_messagebox, dialog_manager):
        """Test confirm_remove_roi when user confirms."""
        mock_messagebox.askyesno.return_value = True

        result = dialog_manager.confirm_remove_roi("ROI_1")

        assert result is True
        mock_messagebox.askyesno.assert_called_once()
        call_args = mock_messagebox.askyesno.call_args
        assert "ROI_1" in call_args[0][1]
        assert call_args[1]["icon"] == "warning"

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_remove_roi_cancelled(self, mock_messagebox, dialog_manager):
        """Test confirm_remove_roi when user cancels."""
        mock_messagebox.askyesno.return_value = False

        result = dialog_manager.confirm_remove_roi("ROI_2")

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_save_polygon_before_analysis_save(self, mock_messagebox, dialog_manager):
        """Test confirm_save_polygon_before_analysis when user chooses to save."""
        mock_messagebox.askyesnocancel.return_value = True

        result = dialog_manager.confirm_save_polygon_before_analysis()

        assert result is True
        mock_messagebox.askyesnocancel.assert_called_once()

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_save_polygon_before_analysis_discard(self, mock_messagebox, dialog_manager):
        """Test confirm_save_polygon_before_analysis when user discards changes."""
        mock_messagebox.askyesnocancel.return_value = False

        result = dialog_manager.confirm_save_polygon_before_analysis()

        assert result is False

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_confirm_save_polygon_before_analysis_cancel(self, mock_messagebox, dialog_manager):
        """Test confirm_save_polygon_before_analysis when user cancels."""
        mock_messagebox.askyesnocancel.return_value = None

        result = dialog_manager.confirm_save_polygon_before_analysis()

        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_offer_zone_reuse_accepted(
        self, mock_messagebox, dialog_manager, mock_gui, mock_event_bus
    ):
        """Test offer_zone_reuse when user accepts."""
        mock_messagebox.askyesno.return_value = True

        # Mock ProjectManager methods - need to return different values for different videos
        def has_zone_data_side_effect(video_path):
            if video_path == "video1.mp4":
                return False  # Current video has NO zones
            elif video_path == "video2.mp4":
                return True  # Last video HAS zones
            return False

        mock_gui.controller.project_manager.has_zone_data.side_effect = has_zone_data_side_effect
        mock_gui.controller.project_manager.get_last_zone_video.return_value = "video2.mp4"
        mock_gui.controller.project_manager.clone_zone_data_from_video.return_value = {}
        mock_gui.controller.project_manager.save_zone_data.return_value = None
        mock_gui.controller.project_manager.copy_zone_parquet_files.return_value = []
        mock_gui._zone_prompt_history = set()

        with patch.object(dialog_manager, "show_warning") as mock_warning:
            dialog_manager.offer_zone_reuse("video1.mp4")
            assert mock_warning.call_count >= 1

        mock_messagebox.askyesno.assert_called_once()
        call_args = mock_messagebox.askyesno.call_args
        assert "video1.mp4" in call_args[0][1]
        assert "video2.mp4" in call_args[0][1]
        assert call_args[1]["icon"] == "question"

        # Verify Event Bus publishing
        assert mock_event_bus.publish.call_count >= 3
        calls = mock_event_bus.publish.call_args_list
        event_types = [call[0][0].type for call in calls]
        assert UIEvents.ZONES_UPDATED in event_types
        assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in event_types
        assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_types

    @patch("zebtrack.ui.components.dialog_manager.messagebox")
    def test_offer_zone_reuse_declined(
        self, mock_messagebox, dialog_manager, mock_gui, mock_event_bus
    ):
        """Test offer_zone_reuse when user declines."""
        mock_messagebox.askyesno.return_value = False

        # Mock ProjectManager methods - same logic as accepted test
        def has_zone_data_side_effect(video_path):
            if video_path == "video1.mp4":
                return False  # Current video has NO zones
            elif video_path == "video2.mp4":
                return True  # Last video HAS zones
            return False

        mock_gui.controller.project_manager.has_zone_data.side_effect = has_zone_data_side_effect
        mock_gui.controller.project_manager.get_last_zone_video.return_value = "video2.mp4"
        mock_gui._zone_prompt_history = set()

        dialog_manager.offer_zone_reuse("video1.mp4")

        mock_messagebox.askyesno.assert_called_once()

        # Verify Event Bus publishing (should refresh project views and tree but NOT zones)
        assert mock_event_bus.publish.call_count >= 2
        calls = mock_event_bus.publish.call_args_list
        event_types = [call[0][0].type for call in calls]
        assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_types
        assert UIEvents.VIDEO_TREE_REFRESH_REQUESTED in event_types
        # ZONES_UPDATED should NOT be fired if declined (unless we cleared zones, which we did)
        # Wait, code says: pm.clear_zone_data_for_video(video_path, persist=False)
        # But it does NOT publish ZONES_UPDATED in the 'else' block in my implementation.
        # Let's check implementation again.
        # Implementation 'else' block:
        # self.event_bus_v2.publish(Event(type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED...))
        # self.event_bus_v2.publish(Event(type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED...))
        # No ZONES_UPDATED. So assertions above are correct.


@pytest.mark.gui
class TestNotificationDialogs:
    """Tests for notification dialog methods."""

    def test_show_external_trigger_notice_basic(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice with basic details."""
        dialog_manager.show_external_trigger_notice("gravação")

        mock_gui.external_trigger_notice_var.set.assert_called_once()
        message = mock_gui.external_trigger_notice_var.set.call_args[0][0]
        assert "gravação" in message

    def test_show_external_trigger_notice_with_metadata(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice with full metadata."""
        dialog_manager.show_external_trigger_notice(
            "análise", day=2, group="G1", cobaia=5, port="COM3"
        )

        mock_gui.external_trigger_notice_var.set.assert_called_once()
        message = mock_gui.external_trigger_notice_var.set.call_args[0][0]
        assert "análise" in message
        assert "Dia 02" in message
        assert "Grupo G1" in message
        assert "Sujeito 5" in message
        assert "Porta COM3" in message

    def test_show_external_trigger_notice_no_label(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice when label is None."""
        mock_gui.external_trigger_notice_label = None

        # Should not raise exception
        dialog_manager.show_external_trigger_notice("test")

    def test_show_external_trigger_notice_sets_colors(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice sets highlight colors."""
        dialog_manager.show_external_trigger_notice("test")

        mock_gui.external_trigger_notice_label.config.assert_called_once()
        config_call = mock_gui.external_trigger_notice_label.config.call_args
        assert "background" in config_call[1]
        assert "foreground" in config_call[1]

    def test_clear_external_trigger_notice(self, dialog_manager, mock_gui):
        """Test clear_external_trigger_notice clears message."""
        dialog_manager.clear_external_trigger_notice()

        mock_gui.external_trigger_notice_var.set.assert_called_once_with("")
        mock_gui.external_trigger_notice_label.config.assert_called_once()

    def test_clear_external_trigger_notice_no_label(self, dialog_manager, mock_gui):
        """Test clear_external_trigger_notice when label is None."""
        mock_gui.external_trigger_notice_label = None

        # Should not raise exception
        dialog_manager.clear_external_trigger_notice()

    def test_clear_external_trigger_notice_restores_colors(self, dialog_manager, mock_gui):
        """Test clear_external_trigger_notice restores default colors."""
        dialog_manager.clear_external_trigger_notice()

        config_call = mock_gui.external_trigger_notice_label.config.call_args
        assert "background" in config_call[1]
        assert "foreground" in config_call[1]


@pytest.mark.gui
class TestGridCellClick:
    """Tests for experimental grid cell click handling."""

    @patch("zebtrack.ui.dialogs.subject_selection_dialog.SubjectSelectionDialog")
    def test_handle_grid_cell_click_fallback_live(self, mock_dialog, dialog_manager, mock_gui):
        """Fallback path should start live session when project type is live."""
        dialog_instance = Mock()
        dialog_instance.result = 2
        mock_dialog.return_value = dialog_instance

        mock_gui.controller.live_batch_coordinator = None
        mock_gui.controller.live_camera_session_coordinator = None
        mock_gui.controller.project_manager.get_completed_sessions.return_value = []
        mock_gui.controller.project_manager.project_data["subjects_per_group"] = 3
        mock_gui.controller.project_manager.get_project_type.return_value = "live"
        mock_gui.controller.hardware_vm.start_live_project_session = Mock(return_value=True)
        mock_gui.widget_factory = Mock()

        dialog_manager.handle_grid_cell_click(1, "G1")

        mock_gui.controller.hardware_vm.start_live_project_session.assert_called_once_with(
            day=1, group="G1", subject="2"
        )
        mock_gui.widget_factory.render_progress_grid.assert_called_once()

    @patch("zebtrack.ui.dialogs.block_detail_dialog.BlockDetailDialog")
    def test_handle_grid_cell_click_batch_dialog(self, mock_dialog, dialog_manager, mock_gui):
        """Batch-aware path should open BlockDetailDialog and refresh grid."""
        mock_gui.controller.live_batch_coordinator = Mock()
        mock_gui.controller.live_camera_session_coordinator = Mock()
        mock_gui.widget_factory = Mock()

        dialog_manager.handle_grid_cell_click(2, "GroupA")

        mock_dialog.assert_called_once()
        mock_gui.widget_factory.render_progress_grid.assert_called_once()


@pytest.mark.gui
class TestChangeRoiColor:
    """Tests for change_roi_color."""

    @patch("zebtrack.ui.dialogs.color_selection_dialog.ColorSelectionDialog")
    def test_change_roi_color_no_selection(self, mock_dialog, dialog_manager, mock_gui):
        """No selection should exit early without opening dialog."""
        listbox = Mock()
        listbox.selection.return_value = []
        mock_gui.zone_listbox = listbox

        dialog_manager.change_roi_color()

        mock_dialog.assert_not_called()

    @patch("zebtrack.ui.dialogs.color_selection_dialog.ColorSelectionDialog")
    def test_change_roi_color_dialog_cancelled(self, mock_dialog, dialog_manager, mock_gui):
        """Cancelled dialog should not update data."""
        listbox = Mock()
        listbox.selection.return_value = ["roi1"]
        listbox.item.return_value = {"values": ["ROI 1"]}
        mock_gui.zone_listbox = listbox

        dialog_instance = Mock()
        dialog_instance.result = None
        mock_dialog.return_value = dialog_instance

        dialog_manager.change_roi_color()

        mock_gui.controller.project_manager.save_zone_data.assert_not_called()

    @patch("zebtrack.ui.dialogs.color_selection_dialog.ColorSelectionDialog")
    def test_change_roi_color_success(self, mock_dialog, dialog_manager, mock_gui, mock_event_bus):
        """Successful color change should update zone data and publish events."""
        listbox = Mock()
        listbox.selection.return_value = ["roi1"]
        listbox.item.return_value = {"values": ["📍 ROI 1"]}
        mock_gui.zone_listbox = listbox

        dialog_instance = Mock()
        dialog_instance.result = {"rgb": "#112233", "name": "Azul"}
        mock_dialog.return_value = dialog_instance

        zone_data = SimpleNamespace(roi_names=["ROI 1"], roi_colors=["#000000"])
        mock_gui._zone_context_service = Mock()
        mock_gui._zone_context_service.get_zone_data_for_active_context = Mock(
            return_value=zone_data
        )

        dialog_manager.change_roi_color()

        assert zone_data.roi_colors[0] == "#112233"
        mock_gui.controller.project_manager.save_zone_data.assert_called_once_with(zone_data)
        mock_gui.set_status.assert_called_once()

        event_types = [call[0][0].type for call in mock_event_bus.publish.call_args_list]
        assert UIEvents.ZONES_UPDATED in event_types
        assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_types


@pytest.mark.gui
class TestUtilityMethods:
    """Tests for utility methods."""

    def test_show_progress_bar_initially_hidden(self, dialog_manager, mock_gui):
        """Test show_progress_bar when progress frame is hidden."""
        dialog_manager.show_progress_bar()

        mock_gui.analysis_display_widget.progress_frame.pack.assert_called_once()
        assert mock_gui.analysis_display_widget.progress_bar["value"] == 0
        mock_gui.analysis_display_widget.cancel_btn.config.assert_called_once_with(state="normal")

    def test_show_progress_bar_already_visible(self, dialog_manager, mock_gui):
        """Test show_progress_bar when progress frame already visible."""
        mock_gui.analysis_display_widget.progress_frame.winfo_viewable.return_value = True

        dialog_manager.show_progress_bar()

        # Should still enable cancel button
        mock_gui.analysis_display_widget.cancel_btn.config.assert_called_once_with(state="normal")

    def test_show_progress_bar_with_video_container(self, dialog_manager, mock_gui):
        """Test show_progress_bar packs before video container."""
        dialog_manager.show_progress_bar()

        pack_call = mock_gui.analysis_display_widget.progress_frame.pack.call_args
        assert "before" in pack_call[1]
        assert pack_call[1]["before"] == mock_gui.analysis_display_widget.video_container

    def test_show_progress_bar_no_video_container(self, dialog_manager, mock_gui):
        """Test show_progress_bar when video container is None."""
        mock_gui.analysis_display_widget.video_container = None

        dialog_manager.show_progress_bar()

        pack_call = mock_gui.analysis_display_widget.progress_frame.pack.call_args
        assert "before" not in pack_call[1]

    @patch("zebtrack.ui.components.dialog_manager.os.startfile")
    def test_open_path_in_explorer_windows(self, mock_startfile, dialog_manager, monkeypatch):
        """Test open_path_in_explorer on Windows."""
        monkeypatch.setattr(sys, "platform", "win32")

        dialog_manager.open_path_in_explorer("/path/to/directory")

        mock_startfile.assert_called_once_with("/path/to/directory")

    @patch("zebtrack.ui.components.dialog_manager.subprocess.Popen")
    def test_open_path_in_explorer_macos(self, mock_popen, dialog_manager, monkeypatch):
        """Test open_path_in_explorer on macOS."""
        monkeypatch.setattr(sys, "platform", "darwin")

        dialog_manager.open_path_in_explorer("/path/to/directory")

        mock_popen.assert_called_once_with(["open", "/path/to/directory"])

    @patch("zebtrack.ui.components.dialog_manager.subprocess.Popen")
    def test_open_path_in_explorer_linux(self, mock_popen, dialog_manager, monkeypatch):
        """Test open_path_in_explorer on Linux."""
        monkeypatch.setattr(sys, "platform", "linux")

        dialog_manager.open_path_in_explorer("/path/to/directory")

        mock_popen.assert_called_once_with(["xdg-open", "/path/to/directory"])

    @patch("zebtrack.ui.components.dialog_manager.subprocess.Popen")
    def test_open_path_in_explorer_error(self, mock_popen, dialog_manager, monkeypatch):
        """Test open_path_in_explorer handles errors."""
        monkeypatch.setattr(sys, "platform", "linux")
        mock_popen.side_effect = Exception("Command failed")

        with patch.object(dialog_manager, "show_error") as mock_error:
            dialog_manager.open_path_in_explorer("/path/to/directory")

        mock_error.assert_called_once()
        error_message = mock_error.call_args[0][1]
        assert "/path/to/directory" in error_message


@pytest.mark.gui
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.SaveROITemplateDialog")
    def test_show_template_save_dialog_empty_result_dict(self, mock_dialog_class, dialog_manager):
        """Test show_template_save_dialog with empty result dict returns None."""
        mock_dialog = Mock()
        mock_dialog.result = {}  # Empty result dict is treated as cancellation (returns None)
        mock_dialog_class.return_value = mock_dialog

        result = dialog_manager.show_template_save_dialog(
            has_arena=False, has_rois=False, allow_project=False, initial_name=""
        )

        # Empty dict is treated as cancellation
        assert result is None

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_roi_template_error_handling(self, mock_filedialog, dialog_manager, mock_gui):
        """Test import_roi_template handles import errors gracefully."""
        mock_filedialog.askopenfilename.return_value = "/path/to/template.json"
        mock_gui.controller.project_manager.import_roi_template.side_effect = Exception(
            "Import failed"
        )

        with patch.object(dialog_manager, "show_error") as mock_error:
            dialog_manager.import_roi_template()

        mock_error.assert_called_once()
        assert "Import failed" in str(mock_error.call_args)

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_import_and_apply_with_pending_video_activation_failure(
        self, mock_filedialog, dialog_manager, mock_gui
    ):
        """Test import_and_apply when pending video activation fails."""
        mock_filedialog.askopenfilename.return_value = "/path/to/template.json"
        mock_gui.controller.project_manager.get_active_zone_video.return_value = None
        mock_gui.pending_single_video_path = "/pending/video.mp4"
        mock_gui.controller.project_manager.set_active_zone_video.side_effect = Exception(
            "Activation failed"
        )

        # Should still try to import even if activation fails
        import json

        template_data = {"polygon": [[0, 0], [1, 1]]}

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                template_data
            )

            # This should handle the exception and continue
            with patch.object(dialog_manager, "show_warning"):
                dialog_manager.import_and_apply_roi_template()

    def test_show_external_trigger_notice_config_exception(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice handles config exceptions."""
        mock_gui.external_trigger_notice_label.config.side_effect = Exception("Config failed")

        # Should not raise exception
        dialog_manager.show_external_trigger_notice("test")

    def test_clear_external_trigger_notice_config_exception(self, dialog_manager, mock_gui):
        """Test clear_external_trigger_notice handles config exceptions."""
        mock_gui.external_trigger_notice_label.config.side_effect = Exception("Config failed")

        # Should not raise exception
        dialog_manager.clear_external_trigger_notice()

    def test_show_progress_bar_no_progress_frame(self, dialog_manager, mock_gui):
        """Test show_progress_bar when progress_frame is None."""
        mock_gui.progress_frame = None

        # Should not raise exception
        dialog_manager.show_progress_bar()

    def test_show_progress_bar_no_cancel_button(self, dialog_manager, mock_gui):
        """Test show_progress_bar when cancel_proc_btn is None."""
        mock_gui.cancel_proc_btn = None

        # Should not raise exception
        dialog_manager.show_progress_bar()

    @patch("zebtrack.ui.components.dialog_manager.filedialog")
    def test_ask_open_filename_with_all_parameters(self, mock_filedialog, dialog_manager):
        """Test ask_open_filename with all possible parameters."""
        mock_filedialog.askopenfilename.return_value = "/selected/file.json"
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]

        result = dialog_manager.ask_open_filename(
            "Open File", filetypes, initial_dir="/initial/dir"
        )

        assert result == "/selected/file.json"
        mock_filedialog.askopenfilename.assert_called_once_with(
            title="Open File", filetypes=filetypes, initialdir="/initial/dir"
        )

    @patch("zebtrack.ui.components.dialog_manager.simpledialog")
    def test_ask_string_with_empty_initial_value(self, mock_simpledialog, dialog_manager):
        """Test ask_string with empty initial value."""
        mock_simpledialog.askstring.return_value = "User Input"

        result = dialog_manager.ask_string("Title", "Prompt:", initialvalue="")

        assert result == "User Input"
        mock_simpledialog.askstring.assert_called_once_with("Title", "Prompt:", initialvalue="")

    def test_show_external_trigger_notice_partial_metadata(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice with full metadata (day, group, cobaia)."""
        # Need all three: day, group, and cobaia for them to appear
        dialog_manager.show_external_trigger_notice("test", day=1, group="G1", cobaia="C1")

        message = mock_gui.external_trigger_notice_var.set.call_args[0][0]
        assert "Dia 01" in message or "Dia 1" in message  # Format may vary
        assert "Grupo G1" in message
        assert "Sujeito C1" in message

    def test_show_external_trigger_notice_only_port(self, dialog_manager, mock_gui):
        """Test show_external_trigger_notice with only port."""
        dialog_manager.show_external_trigger_notice("test", port="COM5")

        message = mock_gui.external_trigger_notice_var.set.call_args[0][0]
        assert "Porta COM5" in message

    @patch("zebtrack.ui.dialogs.calibration_dialog.CalibrationDialog")
    def test_open_project_calibration_updates_ui_elements(
        self, mock_calibration_dialog, dialog_manager, mock_controller, mock_gui
    ):
        """Test that open_project_calibration_window updates all UI elements."""
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        mock_controller.project_calibration_session.return_value = mock_context
        mock_controller.hardware_vm.use_openvino = True
        mock_controller.hardware_vm.active_weight_name = "custom_weight"
        mock_controller.hardware_vm.get_openvino_status.return_value = "enabled"

        dialog_manager.open_project_calibration_window()

        mock_gui.weight_hardware_manager.update_openvino_checkbox.assert_called_once_with(True)
        mock_gui.weight_hardware_manager.set_active_weight_in_dropdown.assert_called_once_with(
            "custom_weight"
        )
        mock_gui.weight_hardware_manager.update_openvino_status_display.assert_called_once_with(
            "enabled"
        )

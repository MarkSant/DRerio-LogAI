"""
Tests for high complexity dialogs (Batch 1).

Tests the following dialogs:
- CalibrationDialog (983 lines)
- CreateProjectDialog (508 lines)
- ManageWeightsDialog (300+ lines)
- StartRecordingDialog (200+ lines)
- SingleVideoConfigDialog (250+ lines)

These tests cover:
- Initialization
- Input validation
- OK/Cancel/Apply button behavior
- State persistence
- Error handling
- Integration with controller
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.dialogs import (
    CalibrationDialog,
    CreateProjectDialog,
    ManageWeightsDialog,
    SingleVideoConfigDialog,
    StartRecordingDialog,
)


@pytest.fixture(autouse=True)
def prevent_dialog_blocking():
    """Prevent dialogs from blocking by patching wait_window and all messageboxes."""
    with (
        patch("tkinter.simpledialog.Dialog.wait_window"),
        patch("tkinter.Toplevel.withdraw"),
        patch("tkinter.messagebox.showerror"),
        patch("tkinter.messagebox.showwarning"),
        patch("tkinter.messagebox.showinfo"),
        patch("tkinter.messagebox.askyesno", return_value=False),
        patch("tkinter.messagebox.askokcancel", return_value=False),
        patch("tkinter.messagebox.askyesnocancel", return_value=None),
    ):
        yield


@pytest.fixture
def mock_controller():
    """Create a mock controller with common methods."""
    controller = Mock()
    controller.project_manager = Mock()
    controller.project_manager.project_data = {}
    controller.weight_manager = Mock()
    controller.weight_manager.get_default_seg_weight = Mock(return_value=("weight1.pt", None))
    controller.weight_manager.get_default_det_weight = Mock(return_value=("weight2.pt", None))
    controller.weight_manager.get_weight_details = Mock(return_value={"type": "seg"})
    controller.ui_event_bus = Mock()
    controller.ui_event_bus.publish_event = Mock()
    controller.get_calibration_scope_info = Mock(
        return_value={
            "scope": "global",
            "label": "Escopo Global",
            "detail": "Configurações globais",
            "project_loaded": False,
        }
    )
    controller.get_all_weight_names = Mock(return_value=["weight1.pt", "weight2.pt"])
    controller.active_weight_name = "weight1.pt"
    controller.use_openvino = False
    controller.get_openvino_status = Mock(return_value="Desativado")
    controller.get_current_detector_parameters = Mock(
        return_value={
            "confidence_threshold": 0.25,
            "nms_threshold": 0.50,
            "track_threshold": 0.25,
            "match_threshold": 0.15,
        }
    )
    controller.get_global_model_defaults = Mock(
        return_value={"active_weight": "weight1.pt", "use_openvino": False}
    )
    controller.resolve_project_model_settings = Mock(return_value=("weight1.pt", False))
    return controller


@pytest.fixture
def mock_project_manager():
    """Create a mock project manager."""
    pm = Mock()
    pm.project_data = {
        "experiment_days": 5,
        "groups": ["Control", "Treatment"],
        "subjects_per_group": 3,
    }
    pm.get_last_session_details = Mock(return_value=(1, "Control"))
    return pm


# ==================== CalibrationDialog Tests ====================


@pytest.mark.gui
class TestCalibrationDialog:
    """Tests for CalibrationDialog."""

    def test_init_global_scope(self, tkinter_root, mock_controller):
        """Test initialization with global scope."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        assert dialog.controller == mock_controller
        assert dialog.scope == "global"
        assert dialog.calibration_section is not None
        assert dialog.preferences_section is None  # Not shown for global scope

    def test_init_project_scope(self, tkinter_root, mock_controller):
        """Test initialization with project scope."""
        mock_controller.get_calibration_scope_info.return_value = {
            "scope": "project",
            "label": "Escopo: Projeto",
            "detail": "Configurações do projeto",
            "project_loaded": True,
            "project_name": "TestProject",
        }

        dialog = CalibrationDialog(tkinter_root, mock_controller)

        assert dialog.scope == "project"
        assert dialog.calibration_section is not None
        assert dialog.preferences_section is not None

    def test_weight_dropdown_populated(self, tkinter_root, mock_controller):
        """Test that weight dropdown is populated correctly."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        # Force UI build
        dialog._build_calibration_section()

        assert dialog.weights_dropdown is not None
        assert dialog.active_weight_var.get() == "weight1.pt"

    def test_weight_selection_event(self, tkinter_root, mock_controller):
        """Test weight selection publishes event."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog._build_calibration_section()

        dialog.active_weight_var.set("weight2.pt")
        dialog._on_weight_selected_local()

        mock_controller.ui_event_bus.publish_event.assert_called()

    def test_openvino_toggle(self, tkinter_root, mock_controller):
        """Test OpenVINO checkbox toggle."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog._build_calibration_section()

        dialog.use_openvino_var.set(True)
        dialog._on_openvino_toggled_local()

        mock_controller.ui_event_bus.publish_event.assert_called()

    def test_detector_parameters_validation_success(self, tkinter_root, mock_controller):
        """Test successful detector parameter validation."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        dialog.confidence_threshold_var.set("0.30")
        dialog.nms_threshold_var.set("0.45")
        dialog.track_threshold_var.set("0.20")
        dialog.match_threshold_var.set("0.10")

        mock_controller.update_detector_parameters = Mock(return_value=True)

        with patch("tkinter.messagebox.showinfo") as mock_info:
            dialog._apply_detector_parameters()
            mock_info.assert_called_once()

    def test_detector_parameters_validation_invalid_range(self, tkinter_root, mock_controller):
        """Test detector parameter validation with invalid range."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        dialog.confidence_threshold_var.set("1.5")  # Invalid: > 1.0

        with patch("tkinter.messagebox.showerror") as mock_error:
            dialog._apply_detector_parameters()
            mock_error.assert_called_once()

    def test_detector_parameters_validation_non_numeric(self, tkinter_root, mock_controller):
        """Test detector parameter validation with non-numeric input."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        dialog.confidence_threshold_var.set("invalid")

        with patch("tkinter.messagebox.showerror") as mock_error:
            dialog._apply_detector_parameters()
            mock_error.assert_called_once()

    def test_restore_detector_defaults(self, tkinter_root, mock_controller):
        """Test restoring detector defaults."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        mock_controller.restore_detector_defaults = Mock(return_value=True)

        with patch("tkinter.messagebox.showinfo"):
            dialog._restore_detector_defaults()
            mock_controller.restore_detector_defaults.assert_called_once()

    def test_diagnostic_video_selection(self, tkinter_root, mock_controller):
        """Test diagnostic video file selection."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)

        test_path = "/path/to/video.mp4"
        with patch("tkinter.filedialog.askopenfilename", return_value=test_path):
            dialog._select_diagnostic_video()

        assert dialog.diagnostic_video_path == test_path
        assert "video.mp4" in dialog.video_path_label_var.get()

    def test_run_diagnostic_test_no_video(self, tkinter_root, mock_controller):
        """Test running diagnostic without selecting video."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog.diagnostic_video_path = ""

        with patch("tkinter.messagebox.showerror") as mock_error:
            dialog._run_diagnostic_test()
            mock_error.assert_called_once()

    def test_run_diagnostic_test_invalid_frames(self, tkinter_root, mock_controller):
        """Test running diagnostic with invalid frame count."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog.diagnostic_video_path = "/path/to/video.mp4"
        dialog.frames_to_analyze_var.set("-5")  # Invalid

        with patch("tkinter.messagebox.showerror") as mock_error:
            dialog._run_diagnostic_test()
            mock_error.assert_called_once()

    def test_run_diagnostic_test_success(self, tkinter_root, mock_controller):
        """Test successful diagnostic test run."""
        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog.diagnostic_video_path = "/path/to/video.mp4"
        dialog.frames_to_analyze_var.set("10")
        dialog.confidence_threshold_var.set("0.25")

        dialog._run_diagnostic_test()

        mock_controller.ui_event_bus.publish_event.assert_called()

    def test_project_preferences_save(self, tkinter_root, mock_controller):
        """Test saving project preferences."""
        mock_controller.get_calibration_scope_info.return_value = {
            "scope": "project",
            "label": "Escopo: Projeto",
            "detail": "Configurações do projeto",
            "project_loaded": True,
            "project_name": "TestProject",
        }
        mock_controller.save_project_model_overrides = Mock()

        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog._build_preferences_section()

        dialog.weight_choice.set("weight2.pt")
        dialog.openvino_choice.set("on")

        with patch("tkinter.messagebox.showinfo"):
            dialog._save_project_preferences()
            mock_controller.save_project_model_overrides.assert_called_once_with("weight2.pt", True)

    def test_project_preferences_restore(self, tkinter_root, mock_controller):
        """Test restoring project preferences from saved state."""
        mock_controller.get_calibration_scope_info.return_value = {
            "scope": "project",
            "label": "Escopo: Projeto",
            "detail": "Configurações do projeto",
            "project_loaded": True,
        }
        mock_controller.project_manager.project_data = {
            "model_overrides": {
                "active_weight": "weight2.pt",
                "use_openvino": True,
            }
        }

        dialog = CalibrationDialog(tkinter_root, mock_controller)
        dialog._build_preferences_section()

        dialog._restore_project_preferences()

        assert dialog.weight_choice.get() == "weight2.pt"
        assert dialog.openvino_choice.get() == "on"


# ==================== CreateProjectDialog Tests ====================


@pytest.mark.gui
class TestCreateProjectDialog:
    """Tests for CreateProjectDialog."""

    def test_init(self, tkinter_root):
        """Test initialization."""
        dialog = CreateProjectDialog(tkinter_root)

        assert dialog.project_path is None
        assert dialog.result is None
        assert dialog.project_type_var.get() == "pre-recorded"

    def test_default_values(self, tkinter_root):
        """Test default values are set correctly."""
        dialog = CreateProjectDialog(tkinter_root)

        assert dialog.num_aquariums_var.get() == "1"
        assert dialog.animals_per_aquarium_var.get() == "1"
        assert dialog.aquarium_width_var.get() == "10.0"
        assert dialog.aquarium_height_var.get() == "10.0"
        assert dialog.analysis_interval_var.get() == "10"
        assert dialog.display_interval_var.get() == "10"

    def test_select_path(self, tkinter_root):
        """Test project path selection."""
        dialog = CreateProjectDialog(tkinter_root)

        test_path = "/test/project/path"
        with patch("tkinter.filedialog.askdirectory", return_value=test_path):
            dialog._select_path()

        assert dialog.path_entry.get() == test_path

    def test_select_video_files(self, tkinter_root):
        """Test video file selection."""
        dialog = CreateProjectDialog(tkinter_root)

        # Create temporary video files
        with tempfile.TemporaryDirectory() as tmpdir:
            video1 = os.path.join(tmpdir, "video1.mp4")
            video2 = os.path.join(tmpdir, "video2.mp4")
            open(video1, "a").close()  # Create empty files
            open(video2, "a").close()

            test_files = (video1, video2)
            with patch("tkinter.filedialog.askopenfilenames", return_value=test_files):
                dialog._select_video_files()

            assert len(dialog.video_paths) == 2
            assert "2 arquivo(s)" in dialog.video_list_var.get()

    def test_select_video_folder(self, tkinter_root):
        """Test video folder selection."""
        dialog = CreateProjectDialog(tkinter_root)

        test_folder = "/path/to/videos"
        with patch("tkinter.filedialog.askdirectory", return_value=test_folder):
            with patch("os.path.isdir", return_value=True):
                dialog._select_video_folder()

        assert test_folder in dialog.video_paths
        assert "1 pasta(s)" in dialog.video_list_var.get()

    def test_project_type_switch_to_live(self, tkinter_root):
        """Test switching project type to live."""
        dialog = CreateProjectDialog(tkinter_root)

        dialog.project_type_var.set("live")
        dialog._update_project_type_options()

        assert dialog.video_files_button["state"] == "disabled"
        assert "Não aplicável" in dialog.video_list_var.get()

    def test_num_groups_change(self, tkinter_root):
        """Test group name entry enabling/disabling."""
        dialog = CreateProjectDialog(tkinter_root)

        dialog.num_groups_var.set("3")
        dialog._on_num_groups_change()

        # First 3 entries should be enabled
        for i in range(3):
            assert str(dialog.group_name_entries[i]["state"]) != "disabled"

        # Remaining should be disabled
        for i in range(3, 6):
            assert str(dialog.group_name_entries[i]["state"]) == "disabled"

    def test_validate_missing_path(self, tkinter_root):
        """Test validation fails with missing path."""
        dialog = CreateProjectDialog(tkinter_root)

        dialog.project_name_var.set("TestProject")
        # Path not set

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result == 0

    def test_validate_missing_project_name(self, tkinter_root):
        """Test validation fails with missing project name."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.path_entry.insert(0, tmpdir)
            dialog.project_name_var.set("")  # Empty name

            with patch("tkinter.messagebox.showerror"):
                result = dialog.validate()

        assert result == 0

    def test_validate_missing_videos_prerecorded(self, tkinter_root):
        """Test validation fails for pre-recorded without videos."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.path_entry.insert(0, tmpdir)
            dialog.project_name_var.set("TestProject")
            dialog.project_type_var.set("pre-recorded")
            # No videos selected

            with patch("tkinter.messagebox.showerror"):
                result = dialog.validate()

        assert result == 0

    def test_validate_invalid_calibration(self, tkinter_root):
        """Test validation fails with invalid calibration values."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.path_entry.insert(0, tmpdir)
            dialog.project_name_var.set("TestProject")
            dialog.project_type_var.set("live")  # Skip video validation
            dialog.num_aquariums_var.set("-1")  # Invalid

            with patch("tkinter.messagebox.showerror"):
                result = dialog.validate()

        assert result == 0

    def test_validate_success_prerecorded(self, tkinter_root):
        """Test successful validation for pre-recorded project."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.path_entry.insert(0, tmpdir)
            dialog.project_name_var.set("TestProject")
            dialog.project_type_var.set("pre-recorded")
            dialog.video_paths = ["/path/to/video.mp4"]

            with patch("os.path.isfile", return_value=True):
                result = dialog.validate()

        assert result == 1

    def test_validate_success_live(self, tkinter_root):
        """Test successful validation for live project."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.path_entry.insert(0, tmpdir)
            dialog.project_name_var.set("TestProject")
            dialog.project_type_var.set("live")
            dialog.total_days_var.set("5")
            dialog.subjects_per_group_var.set("3")
            dialog.num_groups_var.set("2")
            dialog.group_name_vars[0].set("Control")
            dialog.group_name_vars[1].set("Treatment")

            result = dialog.validate()

        assert result == 1

    def test_apply_creates_result(self, tkinter_root):
        """Test apply() creates proper result dictionary."""
        dialog = CreateProjectDialog(tkinter_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            dialog.project_path = os.path.join(tmpdir, "TestProject")
            dialog.project_type_var.set("pre-recorded")
            dialog.video_paths = ["/path/to/video.mp4"]
            dialog.num_aquariums_var.set("2")
            dialog.animals_per_aquarium_var.set("3")

            dialog.apply()

        assert dialog.result is not None
        assert dialog.result["project_path"] == dialog.project_path
        assert dialog.result["num_aquariums"] == 2
        assert dialog.result["animals_per_aquarium"] == 3
        assert dialog.result["use_single_subject_tracker"] is False  # 3 animals


# ==================== ManageWeightsDialog Tests ====================


@pytest.mark.gui
class TestManageWeightsDialog:
    """Tests for ManageWeightsDialog."""

    def test_init(self, tkinter_root, mock_controller):
        """Test initialization."""
        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        assert dialog.controller == mock_controller
        assert dialog.listbox is not None

    def test_populate_list(self, tkinter_root, mock_controller):
        """Test weight list population."""
        mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "weight1.pt",
            None,
        )
        mock_controller.weight_manager.get_default_det_weight.return_value = (
            "weight2.pt",
            None,
        )
        mock_controller.weight_manager.get_weight_details.side_effect = [
            {"type": "seg"},
            {"type": "det"},
        ]

        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        # Check that items were added
        items = dialog.listbox.get_children()
        assert len(items) == 2

    def test_set_default_seg_success(self, tkinter_root, mock_controller):
        """Test setting default seg weight."""
        mock_controller.weight_manager.get_weight_details.return_value = {"type": "seg"}
        mock_controller.weight_manager.set_default_weight_by_type = Mock()
        mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "weight1.pt",
            None,
        )
        mock_controller.weight_manager.get_default_det_weight.return_value = (
            "weight2.pt",
            None,
        )

        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        # Select first item
        items = dialog.listbox.get_children()
        if items:
            dialog.listbox.selection_set(items[0])

        with patch("tkinter.messagebox.showinfo"):
            dialog.set_default_seg()

        mock_controller.weight_manager.set_default_weight_by_type.assert_called_once()

    def test_set_default_seg_wrong_type(self, tkinter_root, mock_controller):
        """Test setting default seg weight with det-type weight."""
        mock_controller.weight_manager.get_weight_details.return_value = {"type": "det"}
        mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "weight1.pt",
            None,
        )
        mock_controller.weight_manager.get_default_det_weight.return_value = (
            "weight2.pt",
            None,
        )

        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        # Select first item
        items = dialog.listbox.get_children()
        if items:
            dialog.listbox.selection_set(items[0])

        with patch("tkinter.messagebox.showwarning") as mock_warn:
            dialog.set_default_seg()
            mock_warn.assert_called_once()

    def test_set_default_det_success(self, tkinter_root, mock_controller):
        """Test setting default det weight."""
        mock_controller.weight_manager.get_weight_details.return_value = {"type": "det"}
        mock_controller.weight_manager.set_default_weight_by_type = Mock()
        mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "weight1.pt",
            None,
        )
        mock_controller.weight_manager.get_default_det_weight.return_value = (
            "weight2.pt",
            None,
        )

        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        # Select first item
        items = dialog.listbox.get_children()
        if items:
            dialog.listbox.selection_set(items[0])

        with patch("tkinter.messagebox.showinfo"):
            dialog.set_default_det()

        mock_controller.weight_manager.set_default_weight_by_type.assert_called_once()

    def test_delete_weight(self, tkinter_root, mock_controller):
        """Test deleting a weight."""
        mock_controller.weight_manager.get_default_seg_weight.return_value = (
            "weight1.pt",
            None,
        )
        mock_controller.weight_manager.get_default_det_weight.return_value = (
            "weight2.pt",
            None,
        )
        mock_controller.weight_manager.get_weight_details.return_value = {"type": "seg"}

        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        # Select first item
        items = dialog.listbox.get_children()
        if items:
            dialog.listbox.selection_set(items[0])

        with patch("tkinter.messagebox.askyesno", return_value=True):
            dialog.delete()

        mock_controller.ui_event_bus.publish_event.assert_called()

    def test_get_selected_item_no_selection(self, tkinter_root, mock_controller):
        """Test getting selected item when nothing is selected."""
        dialog = ManageWeightsDialog(tkinter_root, mock_controller)

        with patch("tkinter.messagebox.showwarning") as mock_warn:
            result = dialog.get_selected_item_name()

        assert result is None
        mock_warn.assert_called_once()


# ==================== StartRecordingDialog Tests ====================


@pytest.mark.gui
class TestStartRecordingDialog:
    """Tests for StartRecordingDialog."""

    def test_init(self, tkinter_root, mock_project_manager):
        """Test initialization."""
        dialog = StartRecordingDialog(tkinter_root, mock_project_manager)

        assert dialog.pm == mock_project_manager
        assert dialog.result is None

    def test_initial_values_from_last_session(self, tkinter_root, mock_project_manager):
        """Test that initial values are set from last session."""
        mock_project_manager.get_last_session_details.return_value = (3, "Treatment")

        dialog = StartRecordingDialog(tkinter_root, mock_project_manager)

        assert dialog.day_var.get() == "3"
        assert dialog.group_var.get() == "Treatment"

    def test_validate_success(self, tkinter_root, mock_project_manager):
        """Test successful validation."""
        dialog = StartRecordingDialog(tkinter_root, mock_project_manager)

        dialog.day_var.set("1")
        dialog.group_var.set("Control")
        dialog.subject_var.set("1")

        result = dialog.validate()
        assert result is True

    def test_validate_missing_fields(self, tkinter_root, mock_project_manager):
        """Test validation fails with missing fields."""
        dialog = StartRecordingDialog(tkinter_root, mock_project_manager)

        dialog.day_var.set("")  # Missing day

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result is False

    def test_apply_creates_result(self, tkinter_root, mock_project_manager):
        """Test apply() creates proper result dictionary."""
        dialog = StartRecordingDialog(tkinter_root, mock_project_manager)

        dialog.day_var.set("2")
        dialog.group_var.set("Control")
        dialog.subject_var.set("3")

        dialog.apply()

        assert dialog.result is not None
        assert dialog.result["day"] == 2
        assert dialog.result["group"] == "Control"
        assert dialog.result["cobaia"] == "3"


# ==================== SingleVideoConfigDialog Tests ====================


@pytest.mark.gui
class TestSingleVideoConfigDialog:
    """Tests for SingleVideoConfigDialog."""

    def test_init(self, tkinter_root):
        """Test initialization."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        assert dialog.result is None
        assert dialog.source_type_var.get() == "video"

    def test_default_values(self, tkinter_root):
        """Test default values are set correctly."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        assert dialog.num_aquariums_var.get() == "1"
        assert dialog.animals_per_aquarium_var.get() == "1"
        assert dialog.analysis_interval_var.get() == "10"
        assert dialog.display_interval_var.get() == "10"
        assert dialog.aquarium_method_var.get() in ["seg", "det"]

    def test_source_type_switch_to_camera(self, tkinter_root):
        """Test switching source type to camera."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("camera")
        dialog._on_source_type_changed()

        # Camera container should be visible
        assert dialog.camera_select_container.winfo_manager() == "pack"

    def test_browse_video(self, tkinter_root):
        """Test video file browsing."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        test_path = "/path/to/video.mp4"
        with patch("tkinter.filedialog.askopenfilename", return_value=test_path):
            dialog._browse_video()

        assert dialog.video_path_var.get() == test_path

    def test_detect_cameras_success(self, tkinter_root):
        """Test camera detection success."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        mock_cameras = [
            {"index": 0, "description": "Webcam 1"},
            {"index": 1, "description": "Webcam 2"},
        ]

        with patch(
            "zebtrack.core.wizard_service.WizardService.detect_available_cameras",
            return_value=mock_cameras,
        ):
            with patch("tkinter.messagebox.showinfo"):
                dialog._detect_cameras()

        assert len(dialog.camera_index_map) == 2
        assert "Webcam 1" in dialog.camera_index_map

    def test_detect_cameras_none_found(self, tkinter_root):
        """Test camera detection when no cameras found."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        with patch(
            "zebtrack.core.wizard_service.WizardService.detect_available_cameras",
            return_value=[],
        ):
            with patch("tkinter.messagebox.showinfo") as mock_info:
                dialog._detect_cameras()
                mock_info.assert_called_once()

        assert len(dialog.camera_index_map) == 0

    def test_validate_no_video_selected(self, tkinter_root):
        """Test validation fails when no video is selected."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("video")
        dialog.video_path_var.set("")  # No video

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result is False

    def test_validate_no_camera_selected(self, tkinter_root):
        """Test validation fails when no camera is selected."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("camera")
        dialog.camera_selection_var.set("")  # No camera

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result is False

    def test_validate_invalid_smoothing_window(self, tkinter_root):
        """Test validation fails with even smoothing window."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("video")
        dialog.video_path_var.set("/path/to/video.mp4")
        dialog.smoothing_window_var.set("4")  # Even number (invalid)

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result is False

    def test_validate_invalid_polyorder(self, tkinter_root):
        """Test validation fails with polyorder >= window."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("video")
        dialog.video_path_var.set("/path/to/video.mp4")
        dialog.smoothing_window_var.set("5")
        dialog.smoothing_polyorder_var.set("5")  # >= window (invalid)

        with patch("tkinter.messagebox.showerror"):
            result = dialog.validate()

        assert result is False

    def test_validate_success_video(self, tkinter_root):
        """Test successful validation for video source."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("video")
        dialog.video_path_var.set("/path/to/video.mp4")
        dialog.smoothing_window_var.set("5")
        dialog.smoothing_polyorder_var.set("2")

        result = dialog.validate()
        assert result is True

    def test_validate_success_camera(self, tkinter_root):
        """Test successful validation for camera source."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("camera")
        dialog.camera_selection_var.set("Webcam 1")
        dialog.camera_index_map = {"Webcam 1": 0}
        dialog.smoothing_window_var.set("5")
        dialog.smoothing_polyorder_var.set("2")

        result = dialog.validate()
        assert result is True

    def test_apply_creates_result_video(self, tkinter_root):
        """Test apply() creates proper result for video source."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("video")
        dialog.video_path_var.set("/path/to/video.mp4")
        dialog.num_aquariums_var.set("2")
        dialog.animals_per_aquarium_var.set("1")

        dialog.apply()

        assert dialog.result is not None
        assert dialog.result["source_type"] == "video"
        assert dialog.result["video_path"] == "/path/to/video.mp4"
        assert dialog.result["camera_index"] is None
        assert dialog.result["num_aquariums"] == 2
        assert dialog.result["use_single_subject_tracker"] is True  # 1 animal

    def test_apply_creates_result_camera(self, tkinter_root):
        """Test apply() creates proper result for camera source."""
        dialog = SingleVideoConfigDialog(tkinter_root)

        dialog.source_type_var.set("camera")
        dialog.camera_selection_var.set("Webcam 1")
        dialog.camera_index_map = {"Webcam 1": 0}
        dialog.num_aquariums_var.set("1")

        dialog.apply()

        assert dialog.result is not None
        assert dialog.result["source_type"] == "camera"
        assert dialog.result["camera_index"] == 0
        assert dialog.result["video_path"] is None

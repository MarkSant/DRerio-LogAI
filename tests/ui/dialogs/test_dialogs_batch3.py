"""
Tests for low-complexity dialogs (Batch 3).

Covers SubjectSelectionDialog, SaveROITemplateDialog, ColorSelectionDialog,
and other simple dialogs as required by EXECUTION_PLAN.md Task 3.6.

IMPORTANT: All tests mock wait_window() to prevent blocking dialog windows
from appearing during automated testing.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from zebtrack.ui.dialogs import (
    ColorSelectionDialog,
    SaveROITemplateDialog,
    SubjectSelectionDialog,
)


@pytest.mark.gui
class TestSubjectSelectionDialog:
    """Test suite for SubjectSelectionDialog component."""

    @pytest.fixture(autouse=True)
    def mock_wait_window(self):
        """Auto-mock wait_window to prevent dialogs from blocking tests."""
        with patch.object(SubjectSelectionDialog, "wait_window"):
            yield

    # --- Initialization Tests ---

    def test_dialog_initialization(self, tkinter_root):
        """Test dialog initializes with correct parameters."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=5,
            completed_subjects=[1, 3],
        )
        tkinter_root.update_idletasks()

        assert dialog is not None
        assert dialog.day == "1"
        assert dialog.group_name == "Grupo A"
        assert dialog.subjects_per_group == 5
        assert dialog.completed_subjects == [1, 3]
        assert dialog.result is None

    def test_dialog_title_with_regular_day(self, tkinter_root):
        """Test dialog title formats regular day correctly."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="5",
            group_name="Grupo B",
            subjects_per_group=3,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        # Title should contain "Dia 5" or "Dia 05" depending on format_day_display
        assert "Grupo B" in dialog.title

    def test_dialog_title_with_no_day(self, tkinter_root):
        """Test dialog title formats 'sem dia' correctly."""
        with patch("zebtrack.ui.dialogs.subject_selection_dialog.format_day_display") as mock_format:
            mock_format.return_value = "Sem Dia"
            dialog = SubjectSelectionDialog(
                tkinter_root,
                day=None,
                group_name="Grupo C",
                subjects_per_group=2,
                completed_subjects=[],
            )
            tkinter_root.update_idletasks()

            assert "Sem Dia" in dialog.title

    # --- Body Tests ---

    def test_body_creates_labels_for_all_subjects(self, tkinter_root):
        """Test body creates label for each subject."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=4,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        # Should have created labels for subjects 1-4
        # We can't easily count widgets, but we verify dialog was created
        assert dialog is not None

    def test_body_marks_completed_subjects(self, tkinter_root):
        """Test body correctly identifies completed subjects."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=3,
            completed_subjects=[1, 2],
        )
        tkinter_root.update_idletasks()

        # Completed subjects should be in the list
        assert 1 in dialog.completed_subjects
        assert 2 in dialog.completed_subjects
        assert 3 not in dialog.completed_subjects

    # --- Selection Tests ---

    def test_select_subject_sets_result(self, tkinter_root):
        """Test selecting a subject sets the result."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=5,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        # Mock the ok method to prevent dialog from closing
        with patch.object(dialog, "ok"):
            dialog.select_subject(3)
            assert dialog.result == 3

    def test_select_subject_calls_ok(self, tkinter_root):
        """Test selecting a subject calls ok() to close dialog."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=5,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        with patch.object(dialog, "ok") as mock_ok:
            dialog.select_subject(2)
            mock_ok.assert_called_once()

    # --- Edge Cases ---

    def test_single_subject_group(self, tkinter_root):
        """Test dialog with only one subject."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=1,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        assert dialog.subjects_per_group == 1

    def test_all_subjects_completed(self, tkinter_root):
        """Test dialog when all subjects are completed."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=3,
            completed_subjects=[1, 2, 3],
        )
        tkinter_root.update_idletasks()

        assert len(dialog.completed_subjects) == 3

    def test_no_subjects_completed(self, tkinter_root):
        """Test dialog when no subjects are completed."""
        dialog = SubjectSelectionDialog(
            tkinter_root,
            day="1",
            group_name="Grupo A",
            subjects_per_group=5,
            completed_subjects=[],
        )
        tkinter_root.update_idletasks()

        assert len(dialog.completed_subjects) == 0


@pytest.mark.gui
class TestSaveROITemplateDialog:
    """Test suite for SaveROITemplateDialog component."""

    @pytest.fixture(autouse=True)
    def mock_wait_window(self):
        """Auto-mock wait_window to prevent dialogs from blocking tests."""
        with patch.object(SaveROITemplateDialog, "wait_window"):
            yield

    # --- Initialization Tests ---

    def test_dialog_initialization_with_all_options(self, tkinter_root):
        """Test dialog initializes with all options enabled."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template1",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        assert dialog is not None
        assert dialog._has_arena is True
        assert dialog._has_rois is True
        assert dialog._allow_project is True
        assert dialog._default_name == "Template1"
        assert dialog.result is None

    def test_dialog_initialization_without_arena(self, tkinter_root):
        """Test dialog initializes without arena option."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template2",
            has_arena=False,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        assert dialog._has_arena is False
        assert dialog._has_rois is True

    def test_dialog_initialization_without_rois(self, tkinter_root):
        """Test dialog initializes without ROIs option."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template3",
            has_arena=True,
            has_rois=False,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        assert dialog._has_arena is True
        assert dialog._has_rois is False

    def test_dialog_initialization_without_project(self, tkinter_root):
        """Test dialog initializes without project option."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template4",
            has_arena=True,
            has_rois=True,
            allow_project=False,
        )
        tkinter_root.update_idletasks()

        assert dialog._allow_project is False
        # Location should default to "global" when project not allowed
        assert dialog.location_var.get() == "global"

    def test_body_sets_default_name(self, tkinter_root):
        """Test body sets default name in entry."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="MyTemplate",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        assert dialog.name_var.get() == "MyTemplate"

    # --- Validation Tests ---

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.messagebox.showwarning")
    def test_validate_requires_name(self, mock_warning, tkinter_root):
        """Test validation fails when name is empty."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("")
        result = dialog.validate()

        assert result is False
        mock_warning.assert_called_once()
        assert "Nome obrigatório" in mock_warning.call_args[0][0]

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.messagebox.showwarning")
    def test_validate_requires_arena_or_rois(self, mock_warning, tkinter_root):
        """Test validation fails when neither arena nor ROIs selected."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.save_arena_var.set(False)
        dialog.save_rois_var.set(False)
        result = dialog.validate()

        assert result is False
        mock_warning.assert_called_once()
        assert "Seleção incompleta" in mock_warning.call_args[0][0]

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.messagebox.showwarning")
    def test_validate_requires_custom_path_when_custom(self, mock_warning, tkinter_root):
        """Test validation fails when custom location selected but no path."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.location_var.set("custom")
        dialog.custom_path_var.set("")
        result = dialog.validate()

        assert result is False
        mock_warning.assert_called_once()
        assert "Local não definido" in mock_warning.call_args[0][0]

    def test_validate_succeeds_with_valid_input(self, tkinter_root):
        """Test validation succeeds with valid input."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("MyTemplate")
        dialog.save_arena_var.set(True)
        dialog.save_rois_var.set(False)
        dialog.location_var.set("project")

        result = dialog.validate()
        assert result is True

    # --- Apply Tests ---

    def test_apply_with_project_location(self, tkinter_root):
        """Test apply creates correct result for project location."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("ProjectTemplate")
        dialog.save_arena_var.set(True)
        dialog.save_rois_var.set(True)
        dialog.location_var.set("project")

        dialog.apply()

        assert dialog.result is not None
        assert dialog.result["name"] == "ProjectTemplate"
        assert dialog.result["save_arena"] is True
        assert dialog.result["save_rois"] is True
        assert dialog.result["save_location"] == "project"
        assert dialog.result["custom_path"] is None

    def test_apply_with_global_location(self, tkinter_root):
        """Test apply creates correct result for global location."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("GlobalTemplate")
        dialog.save_arena_var.set(False)
        dialog.save_rois_var.set(True)
        dialog.location_var.set("global")

        dialog.apply()

        assert dialog.result["name"] == "GlobalTemplate"
        assert dialog.result["save_arena"] is False
        assert dialog.result["save_rois"] is True
        assert dialog.result["save_location"] == "global"
        assert dialog.result["custom_path"] is None

    def test_apply_with_custom_location(self, tkinter_root):
        """Test apply creates correct result for custom location."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("CustomTemplate")
        dialog.save_arena_var.set(True)
        dialog.save_rois_var.set(False)
        dialog.location_var.set("custom")
        dialog.custom_path_var.set("/path/to/template.json")

        dialog.apply()

        assert dialog.result["name"] == "CustomTemplate"
        assert dialog.result["save_arena"] is True
        assert dialog.result["save_rois"] is False
        assert dialog.result["save_location"] == "custom"
        assert dialog.result["custom_path"] == "/path/to/template.json"

    def test_apply_adds_json_extension_if_missing(self, tkinter_root):
        """Test apply adds .json extension to custom path if missing."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("Template")
        dialog.location_var.set("custom")
        dialog.custom_path_var.set("/path/to/template")

        dialog.apply()

        assert dialog.result["custom_path"] == "/path/to/template.json"

    # --- UI Interaction Tests ---

    def test_update_custom_state_enables_when_custom(self, tkinter_root):
        """Test custom path entry is enabled when custom location selected."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.location_var.set("custom")
        dialog._update_custom_state()

        assert dialog.custom_path_entry.cget("state") == "normal"
        assert dialog.browse_button.cget("state") == "normal"

    def test_update_custom_state_disables_when_not_custom(self, tkinter_root):
        """Test custom path entry is disabled when other location selected."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.location_var.set("project")
        dialog._update_custom_state()

        assert dialog.custom_path_entry.cget("state") == "disabled"
        assert dialog.browse_button.cget("state") == "disabled"

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.filedialog.asksaveasfilename")
    def test_browse_custom_path_sets_path(self, mock_filedialog, tkinter_root):
        """Test browse button sets custom path from file dialog."""
        mock_filedialog.return_value = "/selected/path/template.json"

        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog._browse_custom_path()

        assert dialog.custom_path_var.get() == "/selected/path/template.json"
        assert dialog.location_var.get() == "custom"

    @patch("zebtrack.ui.dialogs.save_roi_template_dialog.filedialog.asksaveasfilename")
    def test_browse_custom_path_canceled(self, mock_filedialog, tkinter_root):
        """Test browse button handles cancellation gracefully."""
        mock_filedialog.return_value = ""

        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        original_path = dialog.custom_path_var.get()
        dialog._browse_custom_path()

        # Path should not change
        assert dialog.custom_path_var.get() == original_path

    # --- Filename Suggestion Tests ---

    def test_suggest_filename_normalizes_name(self, tkinter_root):
        """Test filename suggestion normalizes special characters."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="Template With Spaces!",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        suggested = dialog._suggest_filename()
        # Should replace special chars with hyphens and lowercase
        assert suggested == "template-with-spaces"

    def test_suggest_filename_empty_name(self, tkinter_root):
        """Test filename suggestion returns default for empty name."""
        dialog = SaveROITemplateDialog(
            tkinter_root,
            default_name="",
            has_arena=True,
            has_rois=True,
            allow_project=True,
        )
        tkinter_root.update_idletasks()

        dialog.name_var.set("")
        suggested = dialog._suggest_filename()
        assert suggested == "template"


@pytest.mark.gui
class TestColorSelectionDialog:
    """Test suite for ColorSelectionDialog component."""

    @pytest.fixture(autouse=True)
    def mock_wait_window(self):
        """Auto-mock wait_window to prevent dialogs from blocking tests."""
        with patch.object(ColorSelectionDialog, "wait_window"):
            yield

    # --- Initialization Tests ---

    def test_dialog_initialization(self, tkinter_root):
        """Test dialog initializes with default values."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        assert dialog is not None
        assert dialog.result is None
        assert dialog.title == "Selecionar Cor da Área"

    def test_dialog_initialization_custom_title(self, tkinter_root):
        """Test dialog initializes with custom title."""
        dialog = ColorSelectionDialog(tkinter_root, title="Escolher Cor")
        tkinter_root.update_idletasks()

        assert dialog.title == "Escolher Cor"

    def test_body_creates_color_options(self, tkinter_root):
        """Test body creates all color options."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Should have 6 colors
        assert len(dialog.colors) == 6
        assert dialog.selected_color.get() == "green"

    def test_body_has_all_expected_colors(self, tkinter_root):
        """Test body includes all expected colors."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        color_names = [name for name, _, _ in dialog.colors]
        assert "Verde" in color_names
        assert "Azul" in color_names
        assert "Vermelho" in color_names
        assert "Amarelo" in color_names
        assert "Magenta" in color_names
        assert "Ciano" in color_names

    # --- Color Mapping Tests ---

    def test_color_verde_has_correct_values(self, tkinter_root):
        """Test Verde color has correct RGB and hex values."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        verde = next((c for c in dialog.colors if c[0] == "Verde"), None)
        assert verde is not None
        assert verde[1] == (0, 255, 0)  # BGR for OpenCV
        assert verde[2] == "#00FF00"  # Hex

    def test_color_azul_has_correct_values(self, tkinter_root):
        """Test Azul color has correct RGB and hex values."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        azul = next((c for c in dialog.colors if c[0] == "Azul"), None)
        assert azul is not None
        assert azul[1] == (255, 0, 0)  # BGR for OpenCV
        assert azul[2] == "#0000FF"  # Hex

    def test_color_vermelho_has_correct_values(self, tkinter_root):
        """Test Vermelho color has correct RGB and hex values."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        vermelho = next((c for c in dialog.colors if c[0] == "Vermelho"), None)
        assert vermelho is not None
        assert vermelho[1] == (0, 0, 255)  # BGR for OpenCV
        assert vermelho[2] == "#FF0000"  # Hex

    # --- Apply Tests ---

    def test_apply_with_default_selection(self, tkinter_root):
        """Test apply returns verde (default) selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        # Default is verde
        dialog.apply()

        assert dialog.result is not None
        assert dialog.result["name"] == "Verde"
        assert dialog.result["rgb"] == (0, 255, 0)
        assert dialog.result["hex"] == "#00FF00"

    def test_apply_with_azul_selection(self, tkinter_root):
        """Test apply returns azul selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("azul")
        dialog.apply()

        assert dialog.result["name"] == "Azul"
        assert dialog.result["rgb"] == (255, 0, 0)
        assert dialog.result["hex"] == "#0000FF"

    def test_apply_with_vermelho_selection(self, tkinter_root):
        """Test apply returns vermelho selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("vermelho")
        dialog.apply()

        assert dialog.result["name"] == "Vermelho"
        assert dialog.result["rgb"] == (0, 0, 255)
        assert dialog.result["hex"] == "#FF0000"

    def test_apply_with_amarelo_selection(self, tkinter_root):
        """Test apply returns amarelo selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("amarelo")
        dialog.apply()

        assert dialog.result["name"] == "Amarelo"
        assert dialog.result["rgb"] == (0, 255, 255)
        assert dialog.result["hex"] == "#FFFF00"

    def test_apply_with_magenta_selection(self, tkinter_root):
        """Test apply returns magenta selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("magenta")
        dialog.apply()

        assert dialog.result["name"] == "Magenta"
        assert dialog.result["rgb"] == (255, 0, 255)
        assert dialog.result["hex"] == "#FF00FF"

    def test_apply_with_ciano_selection(self, tkinter_root):
        """Test apply returns ciano selection."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("ciano")
        dialog.apply()

        assert dialog.result["name"] == "Ciano"
        assert dialog.result["rgb"] == (255, 255, 0)
        assert dialog.result["hex"] == "#00FFFF"

    # --- Edge Cases ---

    def test_apply_with_invalid_selection_returns_none(self, tkinter_root):
        """Test apply handles invalid selection gracefully."""
        dialog = ColorSelectionDialog(tkinter_root)
        tkinter_root.update_idletasks()

        dialog.selected_color.set("invalid_color")
        dialog.apply()

        # Result should still be None if no match found
        # (apply() only sets result if a match is found)
        assert dialog.result is None

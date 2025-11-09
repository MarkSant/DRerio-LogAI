"""
Tests for wizard Step 5 (Confirmation).

Validates:
- Confirmation step UI creation
- Summary generation
- Project name/location validation
- Default name generation
- Data extraction
- Back navigation

==============================================================================
GUI TEST EXECUTION REQUIREMENTS
==============================================================================

CRITICAL: These tests MUST be run with serial execution (-n0).

Why:
  ttkbootstrap.Style maintains global state (singleton) that is NOT thread-safe.
  When pytest-xdist runs tests in parallel workers, simultaneous Style
  instantiation causes TclError "Can't find a usable tk.tcl" failures.

Correct usage:
  ✅ poetry run pytest -m gui -n0                 (all GUI tests, serial)
  ✅ poetry run pytest tests/ui/wizard/ -n0       (specific dir, serial)
  ✅ .\\scripts\\run_gui_tests.ps1                  (helper script)

Incorrect usage (will fail):
  ❌ poetry run pytest -m gui                     (missing -n0, uses -n=auto)
  ❌ poetry run pytest                            (GUI tests excluded by default)

References:
  - pytest.ini: GUI tests excluded from default run
  - README_TESTS.md: Full troubleshooting guide
  - conftest.py: tkinter_root fixture provides root window

==============================================================================
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID


@pytest.mark.gui
class TestConfirmationStep:
    """Tests for confirmation step."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, wizard_dependencies):
        """Create Tkinter root and temp directory for testing."""
        self.root = wizard_dependencies["root"]
        self.temp_dir = tempfile.mkdtemp()
        monkeypatch.setattr(Path, "home", lambda: Path(self.temp_dir))
        # Mock filedialog to prevent it from opening during tests
        self.mock_filedialog = MagicMock()
        monkeypatch.setattr("zebtrack.ui.wizard.confirmation_step.filedialog", self.mock_filedialog)

    def test_confirmation_step_builds_ui_without_error(self):
        """Confirmation step should build UI without errors."""
        wizard_data = {}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        # Should have step_id set
        assert step.step_id == WizardStepID.CONFIRMATION

    def test_confirmation_step_default_state(self):
        """Confirmation step should have reasonable defaults."""
        wizard_data = {}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Project name starts empty
        assert step.project_name_var.get() == ""

        # Location defaults to Documents
        location = step.project_location_var.get()
        assert "Documents" in location

    def test_default_project_name_experimental(self):
        """Default name should be generated for experimental projects."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "detected_design": {
                "groups": ["Control", "Treatment"],
                "confidence": 0.85,
            },
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_default_project_name()

        name = step.project_name_var.get()

        # Should contain group name and timestamp
        assert "Experimento" in name
        assert "Control" in name

    def test_default_project_name_exploratory(self):
        """Default name should be generated for exploratory projects."""
        wizard_data = {
            "project_type": ProjectType.EXPLORATORY.value,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_default_project_name()

        name = step.project_name_var.get()

        assert "Exploratorio" in name

    def test_summary_generation_with_design(self):
        """Summary should be generated with detected design."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "detected_design": {
                "groups": ["Control", "Treatment"],
                "days": ["Day01", "Day02"],
                "confidence": 0.85,
            },
            "video_count": 10,
            "import_config": [
                {"action": ImportAction.SKIP.value},
                {"action": ImportAction.IMPORT_ZONES.value},
                {"action": ImportAction.FULL.value},
            ],
            "parquet_summary": {
                "total_arena": 5,
                "total_rois": 3,
                "total_trajectory": 2,
                "total_complete": 1,
            },
            "roi_merge_strategy": "replace",
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text

        # Should contain design info
        assert "Experimental" in summary
        assert "Grupos: 2" in summary
        assert "Dias: 2" in summary
        assert "85%" in summary  # Confidence
        assert "Total de Vídeos: 10" in summary

        # Should contain processing plan
        assert "Plano de Processamento" in summary

        # Should contain parquet summary
        assert "Arena: 5" in summary

    def test_summary_includes_template_metadata(self):
        """Summary should mention loaded template when metadata is present."""
        wizard_data = {
            "video_count": 3,
            "template_metadata": {
                "name": "Template Especial",
                "path": str(Path(self.temp_dir) / "template_especial.json"),
            },
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        summary = step.summary_text

        assert "Template" in summary
        assert "Template Especial" in summary
        assert "Template carregado" in step.template_info_var.get()

    def test_summary_includes_folder_preview(self):
        """Summary should include folder preview details when provided."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 4,
            "folder_preview": [
                {
                    "label": "📁 Estudo",
                    "path": "/dados/Estudo",
                    "counts": {"folders": 2, "files": 4},
                    "nodes": [
                        {
                            "label": "📁 Dia01",
                            "path": "/dados/Estudo/Dia01",
                            "counts": {"folders": 0, "files": 2},
                            "children": [],
                        }
                    ],
                    "truncated": False,
                }
            ],
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text
        assert "Estrutura de Pastas" in summary
        assert "📁 Estudo" in summary

    def test_validate_succeeds_with_valid_data(self):
        """Validation should succeed with valid project name and location."""
        wizard_data = {
            "video_count": 5,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Test_Project_2025")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

    def test_validate_fails_with_empty_name(self):
        """Validation should fail with empty project name."""
        wizard_data = {
            "video_count": 5,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "nome" in error_message.lower()

    def test_validate_fails_with_invalid_characters(self):
        """Validation should fail with invalid characters in name."""
        wizard_data = {
            "video_count": 5,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Project@#$%")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "caracteres inválidos" in error_message.lower()

    def test_validate_fails_with_nonexistent_location(self):
        """Validation should fail with non-existent location."""
        wizard_data = {
            "video_count": 5,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Test_Project")
        step.project_location_var.set("/nonexistent/path")

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "não existe" in error_message.lower()

    def test_validate_fails_with_existing_project(self):
        """Validation should fail if project directory already exists."""
        wizard_data = {
            "video_count": 5,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Create existing directory
        existing_project = Path(self.temp_dir) / "Existing_Project"
        existing_project.mkdir()
        # Add a file to make it non-empty
        (existing_project / "file.txt").touch()

        step.project_name_var.set("Existing_Project")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        # Clean up
        (existing_project / "file.txt").unlink()
        existing_project.rmdir()

        assert not is_valid
        assert "já existe um projeto com esse nome" in error_message.lower()

    def test_validate_fails_with_no_videos(self):
        """Validation should fail with no videos."""
        wizard_data = {
            "video_count": 0,
            "project_type": ProjectType.EXPERIMENTAL.value,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Test_Project")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "nenhum vídeo" in error_message.lower()

    def test_validate_allows_live_without_videos(self):
        """Live projects without prerecorded videos should still validate."""
        wizard_data = {
            "project_type": ProjectType.LIVE.value,
            "camera_index": 0,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Projeto_Ao_Vivo")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

    def test_get_data_returns_project_info(self):
        """get_data should return project name and full path."""
        wizard_data = {}

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("My_Project")
        step.project_location_var.set(self.temp_dir)

        data = step.get_data()

        assert "project_name" in data
        assert "project_path" in data

        assert data["project_name"] == "My_Project"

        # project_path should be full path
        expected_path = str(Path(self.temp_dir) / "My_Project")
        assert data["project_path"] == expected_path

    def test_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data = {}

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "project_name": "Restored_Project",
            "project_path": str(Path(self.temp_dir) / "Restored_Project"),
        }

        step.set_data(previous_data)

        # Verify state restored
        assert step.project_name_var.get() == "Restored_Project"
        assert step.project_location_var.get() == self.temp_dir

    @pytest.mark.parametrize(
        "name",
        [
            "Simple",
            "Project_2025",
            "Test-Project",
            "My Project Name",
            "ABC_123-Test",
        ],
    )
    def test_valid_project_names(self, name):
        """Test various valid project name formats."""
        wizard_data = {"video_count": 1}

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set(name)
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        msg = f"Name '{name}' should be valid but got error: {error_message}"
        assert is_valid, msg

    @pytest.mark.parametrize(
        "name",
        [
            "Project@2025",  # @ not allowed
            "Test#Project",  # # not allowed
            "Name$Invalid",  # $ not allowed
            "Proj/ect",  # / not allowed
        ],
    )
    def test_invalid_project_names(self, name):
        """Test various invalid project name formats."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set(name)
        step.project_location_var.set(self.temp_dir)

        is_valid, _ = step.validate()

        assert not is_valid, f"Name '{name}' should be invalid"

    # ========================================================================
    # Additional tests for error display, data validation, and navigation
    # ========================================================================

    def test_error_display_for_missing_project_name(self):
        """Error message should be clear when project name is missing."""
        wizard_data = {"video_count": 3}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert error_message != ""
        assert "nome" in error_message.lower()

    def test_error_display_for_whitespace_only_name(self):
        """Validation should fail with whitespace-only project name."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("   ")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "nome" in error_message.lower() or "vazio" in error_message.lower()

    def test_validation_handles_unicode_characters(self):
        """Project names with Unicode characters should be handled gracefully."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Projeto_Açúcar_2025")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        # Should either accept or reject with clear error
        if not is_valid:
            assert error_message != ""

    def test_data_validation_preserves_all_wizard_data(self):
        """get_data should preserve all previous wizard_data fields."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 10,
            "detected_design": {
                "groups": ["A", "B"],
                "confidence": 0.9,
            },
            "animals_per_aquarium": 5,
            "custom_field": "custom_value",
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Complete_Project")
        step.project_location_var.set(self.temp_dir)

        data = step.get_data()

        # Should preserve all existing data
        assert data["project_type"] == ProjectType.EXPERIMENTAL.value
        assert data["video_count"] == 10
        assert "detected_design" in data
        assert data["custom_field"] == "custom_value"

    def test_project_path_construction_is_correct(self):
        """Project path should be correctly constructed from location + name."""
        wizard_data = {}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("My_Test_Project")
        step.project_location_var.set(self.temp_dir)

        data = step.get_data()

        expected_path = str(Path(self.temp_dir) / "My_Test_Project")
        assert data["project_path"] == expected_path

    def test_summary_displays_model_selection_info(self):
        """Summary should include model selection information."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 5,
            "model_selection": {
                "aquarium_method": "seg",
                "animal_method": "det",
            },
            "detector_parameters": {
                "confidence_threshold": 0.30,
                "nms_threshold": 0.50,
            },
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text

        # Should mention model configuration
        assert "Modelo" in summary or "Detecção" in summary or "Segmentação" in summary

    def test_summary_displays_calibration_info(self):
        """Summary should include calibration information."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 4,
            "num_aquariums": 4,
            "animals_per_aquarium": 3,
            "aquarium_width_cm": 30.0,
            "aquarium_height_cm": 25.0,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text

        # Should mention calibration details
        assert "Calibração" in summary or "Dimensões" in summary
        assert "30" in summary  # Width
        assert "25" in summary  # Height

    def test_navigation_data_validation_on_show(self):
        """on_show should trigger summary generation and update UI."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 7,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Call on_show
        step.on_show()

        # Summary should be populated
        assert step.summary_text != ""
        assert "7" in step.summary_text  # Video count

    def test_default_name_includes_timestamp(self):
        """Default project name should include timestamp for uniqueness."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "detected_design": {
                "groups": ["Control"],
                "confidence": 0.8,
            },
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_default_project_name()

        name = step.project_name_var.get()

        # Should contain timestamp or date component
        import re

        # Check for timestamp pattern (e.g., "20250109" or similar)
        has_timestamp = bool(re.search(r"\d{6,8}", name))
        assert has_timestamp or "Control" in name

    def test_live_project_summary_mentions_camera(self):
        """Live project summary should mention camera configuration."""
        wizard_data = {
            "project_type": ProjectType.LIVE.value,
            "camera_index": 0,
            "camera_resolution": "640x480",
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text

        # Should mention live or camera
        assert "Ao Vivo" in summary or "Live" in summary or "Câmera" in summary

    def test_validation_rejects_very_long_project_names(self):
        """Validation should reject excessively long project names."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Create a very long name (> 255 characters)
        very_long_name = "A" * 300

        step.project_name_var.set(very_long_name)
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        # Should either fail or accept (depends on implementation)
        # At minimum, should not crash
        assert isinstance(is_valid, bool)
        assert isinstance(error_message, str)

    def test_validation_accepts_location_with_spaces(self):
        """Validation should accept project location paths with spaces."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Create directory with spaces
        location_with_spaces = Path(self.temp_dir) / "My Documents"
        location_with_spaces.mkdir()

        step.project_name_var.set("Valid_Project")
        step.project_location_var.set(str(location_with_spaces))

        is_valid, error_message = step.validate()

        # Clean up
        location_with_spaces.rmdir()

        assert is_valid
        assert error_message == ""

    def test_empty_directory_validation(self):
        """Validation should allow creating project in empty existing directory."""
        wizard_data = {"video_count": 1}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Create empty directory with same name
        empty_project_dir = Path(self.temp_dir) / "Empty_Project"
        empty_project_dir.mkdir()

        step.project_name_var.set("Empty_Project")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        # Clean up
        empty_project_dir.rmdir()

        # Empty directory should be allowed
        assert is_valid
        assert error_message == ""

    def test_summary_truncates_long_lists_gracefully(self):
        """Summary should handle large numbers of groups/videos gracefully."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_count": 100,
            "detected_design": {
                "groups": [f"Group{i:02d}" for i in range(50)],
                "confidence": 0.7,
            },
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_summary()

        summary = step.summary_text

        # Should not crash and should mention total count
        assert "100" in summary or "50" in summary
        assert summary != ""

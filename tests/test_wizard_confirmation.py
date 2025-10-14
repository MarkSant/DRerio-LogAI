"""
Tests for wizard Step 5 (Confirmation).

Validates:
- Confirmation step UI creation
- Summary generation
- Project name/location validation
- Default name generation
- Data extraction
- Back navigation
"""

import tempfile
import unittest
from pathlib import Path
from tkinter import TclError, Tk

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID


class TestConfirmationStep(unittest.TestCase):
    """Tests for confirmation step."""

    def setUp(self):
        """Create Tkinter root and temp directory for testing."""
        try:
            self.root = Tk()
            self.root.withdraw()  # Hide window during tests
        except TclError as exc:  # pragma: no cover - environment guard
            self.skipTest(f"Tkinter not available: {exc}")

        # Create temporary directory for project location
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Destroy Tkinter root and clean up temp files."""
        # Clean up temp directory
        Path(self.temp_dir).rmdir()

        self.root.destroy()

    def test_confirmation_step_builds_ui_without_error(self):
        """Confirmation step should build UI without errors."""
        wizard_data = {}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        self.assertEqual(step.step_id, WizardStepID.CONFIRMATION)

    def test_confirmation_step_default_state(self):
        """Confirmation step should have reasonable defaults."""
        wizard_data = {}
        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        # Project name starts empty
        self.assertEqual(step.project_name_var.get(), "")

        # Location defaults to Documents
        location = step.project_location_var.get()
        self.assertIn("Documents", location)

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
        self.assertIn("Experimento", name)
        self.assertIn("Control", name)

    def test_default_project_name_exploratory(self):
        """Default name should be generated for exploratory projects."""
        wizard_data = {
            "project_type": ProjectType.EXPLORATORY.value,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()
        step._generate_default_project_name()

        name = step.project_name_var.get()

        self.assertIn("Exploratorio", name)

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
        self.assertIn("Experimental", summary)
        self.assertIn("Grupos: 2", summary)
        self.assertIn("Dias: 2", summary)
        self.assertIn("85%", summary)  # Confidence
        self.assertIn("Total de Vídeos: 10", summary)

        # Should contain processing plan
        self.assertIn("Plano de Processamento", summary)

        # Should contain parquet summary
        self.assertIn("Arena: 5", summary)

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

        self.assertIn("Template", summary)
        self.assertIn("Template Especial", summary)
        self.assertIn("Template carregado", step.template_info_var.get())

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
        self.assertIn("Estrutura de Pastas", summary)
        self.assertIn("📁 Estudo", summary)

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

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

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

        self.assertFalse(is_valid)
        self.assertIn("nome", error_message.lower())

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

        self.assertFalse(is_valid)
        self.assertIn("caracteres inválidos", error_message.lower())

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

        self.assertFalse(is_valid)
        self.assertIn("não existe", error_message.lower())

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

        step.project_name_var.set("Existing_Project")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        # Clean up
        existing_project.rmdir()

        self.assertFalse(is_valid)
        self.assertIn("já existe", error_message.lower())

    def test_validate_fails_with_no_videos(self):
        """Validation should fail with no videos."""
        wizard_data = {
            "video_count": 0,
        }

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("Test_Project")
        step.project_location_var.set(self.temp_dir)

        is_valid, error_message = step.validate()

        self.assertFalse(is_valid)
        self.assertIn("nenhum vídeo", error_message.lower())

    def test_get_data_returns_project_info(self):
        """get_data should return project name and full path."""
        wizard_data = {}

        step = ConfirmationStep(self.root, wizard_data)
        step.build_ui()

        step.project_name_var.set("My_Project")
        step.project_location_var.set(self.temp_dir)

        data = step.get_data()

        self.assertIn("project_name", data)
        self.assertIn("project_path", data)

        self.assertEqual(data["project_name"], "My_Project")

        # project_path should be full path
        expected_path = str(Path(self.temp_dir) / "My_Project")
        self.assertEqual(data["project_path"], expected_path)

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
        self.assertEqual(step.project_name_var.get(), "Restored_Project")
        self.assertEqual(step.project_location_var.get(), self.temp_dir)

    def test_valid_project_names(self):
        """Test various valid project name formats."""
        wizard_data = {"video_count": 1}

        valid_names = [
            "Simple",
            "Project_2025",
            "Test-Project",
            "My Project Name",
            "ABC_123-Test",
        ]

        for name in valid_names:
            with self.subTest(name=name):
                step = ConfirmationStep(self.root, wizard_data)
                step.build_ui()

                step.project_name_var.set(name)
                step.project_location_var.set(self.temp_dir)

                is_valid, error_message = step.validate()

                msg = f"Name '{name}' should be valid but got error: {error_message}"
                self.assertTrue(is_valid, msg)

    def test_invalid_project_names(self):
        """Test various invalid project name formats."""
        wizard_data = {"video_count": 1}

        invalid_names = [
            "Project@2025",  # @ not allowed
            "Test#Project",  # # not allowed
            "Name$Invalid",  # $ not allowed
            "Proj/ect",  # / not allowed
        ]

        for name in invalid_names:
            with self.subTest(name=name):
                step = ConfirmationStep(self.root, wizard_data)
                step.build_ui()

                step.project_name_var.set(name)
                step.project_location_var.set(self.temp_dir)

                is_valid, error_message = step.validate()

                self.assertFalse(is_valid, f"Name '{name}' should be invalid")


if __name__ == "__main__":
    unittest.main()

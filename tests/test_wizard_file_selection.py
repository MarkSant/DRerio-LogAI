"""
Tests for wizard Step 2 (File Selection).

Validates:
- File selection UI creation
- Folder selection UI creation
- Data extraction
- Validation (at least 1 video required)
- Back navigation with data restoration
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from tkinter import TclError, Tk

from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep


class TestFileSelectionStep(unittest.TestCase):
    """Tests for file selection step."""

    def setUp(self):
        """Create Tkinter root and temporary files for testing."""
        try:
            self.root = Tk()
            self.root.withdraw()  # Hide window during tests
        except TclError as exc:  # pragma: no cover - environment guard
            self.skipTest(f"Tkinter not available: {exc}")

        # Create temporary directory with mock video files
        self.temp_dir = tempfile.mkdtemp()
        self.video1 = Path(self.temp_dir) / "video1.mp4"
        self.video2 = Path(self.temp_dir) / "video2.mp4"
        self.video1.touch()
        self.video2.touch()

    def tearDown(self):
        """Destroy Tkinter root and clean up temp files."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Clean up all child widgets but DON'T destroy root
        # Destroying Tk root pollutes ttkbootstrap Style singleton
        try:
            for widget in list(self.root.winfo_children()):
                try:
                    widget.destroy()
                except Exception:
                    pass
        except Exception:
            pass

    def test_file_selection_step_builds_ui_without_error(self):
        """File selection step should build UI without errors."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        self.assertEqual(step.step_id, WizardStepID.FILE_SELECTION)

    def test_file_selection_step_default_data_is_empty(self):
        """File selection step defaults to no videos selected."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        self.assertEqual(data["video_paths"], [])
        self.assertEqual(data["summary"]["total_files"], 0)
        self.assertEqual(data["summary"]["total_folders"], 0)
        self.assertEqual(data["summary"]["total_paths"], 0)
        self.assertEqual(data["folder_preview"], [])

    def test_file_selection_step_validate_fails_when_no_videos(self):
        """Validation should fail when no videos are selected."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        is_valid, error_message = step.validate()

        self.assertFalse(is_valid)
        self.assertIn("pelo menos um arquivo", error_message.lower())

    def test_file_selection_step_validate_succeeds_with_file(self):
        """Validation should succeed when at least one file is selected."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Manually add a video file
        step.video_paths = [str(self.video1)]

        is_valid, error_message = step.validate()

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

    def test_file_selection_step_validate_succeeds_with_folder(self):
        """Validation should succeed when a folder is selected."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Manually add a folder
        step.video_paths = [self.temp_dir]

        is_valid, error_message = step.validate()

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

    def test_file_selection_step_validate_fails_with_nonexistent_path(self):
        """Validation should fail when selected path doesn't exist."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Add a non-existent path
        step.video_paths = ["/nonexistent/path/video.mp4"]

        is_valid, error_message = step.validate()

        self.assertFalse(is_valid)
        self.assertIn("não exist", error_message.lower())

    def test_file_selection_step_get_data_with_mixed_selection(self):
        """get_data should correctly count files and folders."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Add mixed: 1 file + 1 folder
        step.video_paths = [str(self.video1), self.temp_dir]

        data = step.get_data()

        self.assertEqual(len(data["video_paths"]), 2)
        self.assertEqual(data["summary"]["total_files"], 1)
        self.assertEqual(data["summary"]["total_folders"], 1)
        self.assertEqual(data["summary"]["total_paths"], 2)
        self.assertTrue(data["folder_preview"])

    def test_file_selection_step_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "video_paths": [str(self.video1), str(self.video2)],
            "summary": {
                "total_files": 2,
                "total_folders": 0,
                "total_paths": 2,
            },
        }

        step.set_data(previous_data)

        # Verify UI restored
        self.assertEqual(step.video_paths, [str(self.video1), str(self.video2)])

        # Verify listbox updated
        self.assertEqual(step.paths_listbox.size(), 2)

    def test_file_selection_step_clear_selection(self):
        """Clear selection should remove all paths."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Add some paths
        step.video_paths = [str(self.video1), str(self.video2)]
        step._update_display()

        # Clear selection
        step._clear_selection()

        # Verify cleared
        self.assertEqual(step.video_paths, [])
        self.assertEqual(step.paths_listbox.size(), 0)
        self.assertIn("Nenhum", step.summary_var.get())

    def test_file_selection_step_display_update(self):
        """Display should update correctly when paths are added."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        # Initially empty
        self.assertIn("Nenhum", step.summary_var.get())

        # Add file
        step.video_paths = [str(self.video1)]
        step._update_display()

        # Summary should show 1 file
        self.assertIn("1 arquivo(s)", step.summary_var.get())

        # Add folder
        step.video_paths.append(self.temp_dir)
        step._update_display()

        # Summary should show 1 file + 1 folder
        summary = step.summary_var.get()
        self.assertIn("1 arquivo(s)", summary)
        self.assertIn("1 pasta(s)", summary)

    def test_file_selection_step_folder_preview_tree_populates(self):
        """Folder preview tree should reflect selected directory structure."""
        wizard_data = {}
        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()

        nested_dir = Path(self.temp_dir) / "Day01"
        nested_dir.mkdir()
        (nested_dir / "Subject_S01.mp4").touch()

        step.video_paths = [self.temp_dir]
        step._update_display()

        preview = step.folder_preview_data
        self.assertTrue(preview)
        self.assertIsNotNone(step.folder_tree)
        folder_tree = step.folder_tree
        assert folder_tree is not None
        self.assertGreater(len(folder_tree.get_children()), 0)
        root_entry = preview[0]
        self.assertEqual(root_entry["counts"]["folders"], 1)
        self.assertEqual(root_entry["counts"]["files"], 3)


if __name__ == "__main__":
    unittest.main()

"""
Tests for wizard Step 3 (Detection & Validation).

Validates:
- Detection step UI creation
- File scanning integration
- Design detection patterns
- Confidence calculation
- Data extraction
- Back navigation
"""

import tempfile
import unittest
from pathlib import Path
from tkinter import Tk
from unittest.mock import patch

from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID


class TestDetectionStep(unittest.TestCase):
    """Tests for detection step."""

    def setUp(self):
        """Create Tkinter root for testing."""
        self.root = Tk()
        self.root.withdraw()  # Hide window during tests

        # Create temp directory structure for pattern testing
        self.temp_dir = Path(tempfile.mkdtemp())

        # Pattern 1: Groups as folders
        (self.temp_dir / "Control").mkdir()
        (self.temp_dir / "Treatment").mkdir()
        (self.temp_dir / "Control" / "Day01").mkdir(parents=True)
        (self.temp_dir / "Treatment" / "Day01").mkdir(parents=True)

        # Create mock video files
        self.video1 = self.temp_dir / "Control" / "Day01" / "Subject01.mp4"
        self.video2 = self.temp_dir / "Treatment" / "Day01" / "Subject02.mp4"
        self.video1.touch()
        self.video2.touch()

    def tearDown(self):
        """Destroy Tkinter root and clean up temp files."""
        # Clean up temp files
        for path in [self.video1, self.video2]:
            if path.exists():
                path.unlink()

        # Clean up directories
        for path in [
            self.temp_dir / "Control" / "Day01",
            self.temp_dir / "Treatment" / "Day01",
            self.temp_dir / "Control",
            self.temp_dir / "Treatment",
            self.temp_dir,
        ]:
            if path.exists() and path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

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

    def test_detection_step_builds_ui_without_error(self):
        """Detection step should build UI without errors."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        self.assertEqual(step.step_id, WizardStepID.DETECTION_VALIDATION)

    def test_detection_step_default_state_is_empty(self):
        """Detection step defaults to empty state."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        self.assertEqual(step.scanned_videos, [])
        self.assertIsNone(step.detected_design)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_runs_scan_on_show(self, mock_scan):
        """Detection step should run scan when shown."""
        # Mock scan results
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Trigger on_show (which calls _run_detection)
        step.on_show()

        # Verify scan was called
        mock_scan.assert_called_once_with([str(self.video1)])

        # Verify results stored
        self.assertEqual(len(step.scanned_videos), 1)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_validate_fails_when_no_videos(self, mock_scan):
        """Validation should fail when no videos found."""
        mock_scan.return_value = []

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        is_valid, error_message = step.validate()

        self.assertFalse(is_valid)
        self.assertIn("nenhum vídeo", error_message.lower())

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_validate_succeeds_with_videos(self, mock_scan):
        """Validation should succeed when videos are found."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        is_valid, error_message = step.validate()

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

    def test_detection_step_pattern_groups_as_folders(self):
        """Pattern detection should identify groups from folder structure."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Test pattern detection
        paths = [self.video1, self.video2]
        result = step._pattern_groups_as_folders(paths)

        # Should detect Control and Treatment groups
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Control", result["groups"])
        self.assertIn("Treatment", result["groups"])
        self.assertGreater(result["confidence"], 0.0)

    def test_detection_step_pattern_filename_based(self):
        """Filename-based pattern should extract groups from filenames."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Create paths with group info in filename
        paths = [
            Path("/some/path/Control_Day01_S01.mp4"),
            Path("/some/path/Treatment_Day01_S02.mp4"),
            Path("/some/path/Control_Day02_S01.mp4"),
        ]

        result = step._pattern_filename_based(paths)

        # Should detect Control and Treatment
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Control", result["groups"])
        self.assertIn("Treatment", result["groups"])
        self.assertEqual(result["pattern_used"], "filename_based")

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_parquet_summary_calculation(self, mock_scan):
        """Parquet summary should correctly count existing files."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False,
                "has_complete_data": False,
            },
            {
                "path": str(self.video2),
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
                "has_complete_data": True,
            },
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1), str(self.video2)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        summary = step._calculate_parquet_summary()

        self.assertEqual(summary["total_arena"], 2)
        self.assertEqual(summary["total_rois"], 2)
        self.assertEqual(summary["total_trajectory"], 1)
        self.assertEqual(summary["total_complete"], 1)

    @patch.object(DetectionStep, "_detect_design")
    def test_custom_regex_from_editor_recalculates_design(self, mock_detect):
        """Custom regex updates from the editor should refresh the design promptly."""
        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1)],
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        step.scanned_videos = [
            {
                "path": str(self.video1),
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        new_design = {
            "groups": ["RegexGroup"],
            "days": ["Day01"],
            "subjects_per_group": {"RegexGroup": ["Mouse01"]},
            "pattern_used": "custom_regex",
            "confidence": 0.9,
            "group_display_names": {"RegexGroup": "Regex Group"},
        }

        mock_detect.return_value = new_design

        result = step._handle_custom_regex_from_editor(
            {
                "group_pattern": "RegexGroup",
                "day_pattern": None,
                "subject_pattern": None,
            }
        )

        mock_detect.assert_called_once_with([str(self.video1)])
        self.assertEqual(result, new_design)
        self.assertEqual(step.detected_design, new_design)
        self.assertIsNotNone(step.custom_regex_patterns)
        self.assertIn("regex personalizado aplicado", step.status_var.get().lower())

        display_text = step.results_text.get("1.0", "end-1c")
        self.assertIn("Regex Group", display_text)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_get_data(self, mock_scan):
        """get_data should return complete detection results."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        data = step.get_data()

        self.assertIn("scanned_videos", data)
        self.assertIn("detected_design", data)
        self.assertIn("video_count", data)
        self.assertIn("parquet_summary", data)

        self.assertEqual(data["video_count"], 1)
        self.assertEqual(len(data["scanned_videos"]), 1)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_exploratory_skips_design_detection(self, mock_scan):
        """Exploratory projects should skip design detection."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPLORATORY.value,
            "video_paths": [str(self.video1)],
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        # Design detection should be None for exploratory
        self.assertIsNone(step.detected_design)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_set_data_restores_ui(self, mock_scan):
        """set_data should restore UI from previously collected data."""
        mock_scan.return_value = []

        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "scanned_videos": [
                {
                    "path": str(self.video1),
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                    "has_complete_data": False,
                }
            ],
            "detected_design": {
                "groups": ["Control", "Treatment"],
                "days": ["Day01"],
                "subjects_per_group": {},
                "confidence": 0.75,
                "pattern_used": "groups_as_folders",
            },
            "video_count": 1,
            "parquet_summary": {
                "total_arena": 1,
                "total_rois": 0,
                "total_trajectory": 0,
                "total_complete": 0,
            },
        }

        step.set_data(previous_data)

        # Verify state restored
        self.assertEqual(len(step.scanned_videos), 1)
        self.assertIsNotNone(step.detected_design)
        assert step.detected_design is not None
        self.assertEqual(step.detected_design["confidence"], 0.75)


if __name__ == "__main__":
    unittest.main()

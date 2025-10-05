"""
Integration tests for the complete wizard flow.

Tests the entire 5-step wizard data flow, step interactions,
and data persistence across steps.

Note: WizardDialog is a modal Dialog and cannot be fully tested in unit tests.
These tests focus on step-to-step data flow and integration logic.
"""

import tempfile
import unittest
from pathlib import Path
from tkinter import Tk
from unittest.mock import patch

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep
from zebtrack.ui.wizard.import_config_step import ImportConfigStep


class TestWizardIntegration(unittest.TestCase):
    """End-to-end integration tests for the complete wizard."""

    def setUp(self):
        """Create Tkinter root for testing."""
        self.root = Tk()
        self.root.withdraw()  # Hide window during tests

        # Create temp directory and files
        self.temp_dir = Path(tempfile.mkdtemp())
        self.video1 = self.temp_dir / "Control" / "Day01" / "Subject01.mp4"
        self.video2 = self.temp_dir / "Treatment" / "Day01" / "Subject02.mp4"
        self.video1.parent.mkdir(parents=True)
        self.video2.parent.mkdir(parents=True)
        self.video1.touch()
        self.video2.touch()

    def tearDown(self):
        """Clean up temp files and destroy Tkinter root."""
        # Clean up temp files
        for path in [self.video1, self.video2]:
            if path.exists():
                path.unlink()

        # Clean up directories
        for path in [
            self.video1.parent,
            self.video2.parent,
            self.temp_dir / "Control",
            self.temp_dir / "Treatment",
            self.temp_dir,
        ]:
            if path.exists() and path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

        self.root.destroy()

    def test_step1_to_step2_data_flow(self):
        """Test data flow from Discovery to File Selection."""
        wizard_data = {}

        # Step 1: Discovery
        step1 = DiscoveryStep(self.root, wizard_data)
        step1.build_ui()
        step1.project_type_var.set(ProjectType.EXPERIMENTAL.value)
        step1.folder_organization_var.set(1)
        step1.parquet_scope_var.set(2)  # zones

        # Extract data
        data1 = step1.get_data()
        wizard_data.update(data1)

        # Verify Step 1 data
        self.assertEqual(wizard_data["project_type"], ProjectType.EXPERIMENTAL.value)
        self.assertEqual(wizard_data["parquet_import_scope"], "zones")
        self.assertTrue(wizard_data["has_folder_structure"])

        # Step 2 should be able to access this data
        step2 = FileSelectionStep(self.root, wizard_data)
        step2.build_ui()

        # Step 2 doesn't directly use Step 1 data, but it's available
        self.assertIn("project_type", step2.wizard_data)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_step2_to_step3_data_flow(self, mock_scan):
        """Test data flow from File Selection to Detection."""
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
        }

        # Step 2: File Selection
        step2 = FileSelectionStep(self.root, wizard_data)
        step2.build_ui()
        step2.video_paths = [str(self.video1)]

        data2 = step2.get_data()
        wizard_data.update(data2)

        # Verify Step 2 data
        self.assertEqual(len(wizard_data["video_paths"]), 1)

        # Step 3: Detection uses Step 2 data
        step3 = DetectionStep(self.root, wizard_data)
        step3.build_ui()
        step3.on_show()  # Triggers scan

        data3 = step3.get_data()
        wizard_data.update(data3)

        # Verify Step 3 data
        self.assertIn("scanned_videos", wizard_data)
        self.assertEqual(len(wizard_data["scanned_videos"]), 1)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_step3_to_step4_data_flow(self, mock_scan):
        """Test data flow from Detection to Import Config."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "parquet_import_scope": "zones",
            "video_paths": [str(self.video1)],
        }

        # Step 3: Detection
        step3 = DetectionStep(self.root, wizard_data)
        step3.build_ui()
        step3.on_show()

        data3 = step3.get_data()
        wizard_data.update(data3)

        # Step 4: Import Config uses Step 3 data
        step4 = ImportConfigStep(self.root, wizard_data)
        step4.build_ui()
        step4.on_show()  # Computes smart defaults

        # Verify smart defaults applied correctly
        self.assertEqual(len(step4.video_configs), 1)
        # Should be IMPORT_ZONES based on parquet_import_scope="zones"
        action_value = step4.video_configs[0]["action"]
        self.assertEqual(action_value, ImportAction.IMPORT_ZONES.value)

        data4 = step4.get_data()
        wizard_data.update(data4)

        # Verify Step 4 data
        self.assertIn("import_config", wizard_data)
        self.assertEqual(len(wizard_data["import_config"]), 1)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_step4_to_step5_data_flow(self, mock_scan):
        """Test data flow from Import Config to Confirmation."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
                "has_complete_data": True,
            }
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "parquet_import_scope": "all",
            "video_paths": [str(self.video1)],
            "video_count": 1,
            "detected_design": {
                "groups": ["Control", "Treatment"],
                "confidence": 0.85,
            },
            "parquet_summary": {
                "total_arena": 1,
                "total_rois": 1,
                "total_trajectory": 1,
                "total_complete": 1,
            },
        }

        # Step 4: Import Config
        step4 = ImportConfigStep(self.root, wizard_data)
        step4.build_ui()
        step4.on_show()

        data4 = step4.get_data()
        wizard_data.update(data4)

        # Step 5: Confirmation uses all wizard data
        step5 = ConfirmationStep(self.root, wizard_data)
        step5.build_ui()
        step5.on_show()  # Generates summary

        # Verify summary was generated
        self.assertIn("Design:", step5.summary_text)
        self.assertIn("Experimental", step5.summary_text)

        # Verify default project name generated
        self.assertIn("Experimento", step5.project_name_var.get())

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_complete_wizard_flow_experimental(self, mock_scan):
        """Test complete wizard flow for experimental project through all 5 steps."""
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
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            },
        ]

        wizard_data = {}

        # Step 1: Discovery
        step1 = DiscoveryStep(self.root, wizard_data)
        step1.build_ui()
        step1.project_type_var.set(ProjectType.EXPERIMENTAL.value)
        step1.folder_organization_var.set(1)
        step1.parquet_scope_var.set(2)  # zones
        wizard_data.update(step1.get_data())

        # Step 2: File Selection
        step2 = FileSelectionStep(self.root, wizard_data)
        step2.build_ui()
        step2.video_paths = [str(self.video1), str(self.video2)]
        wizard_data.update(step2.get_data())

        # Step 3: Detection
        step3 = DetectionStep(self.root, wizard_data)
        step3.build_ui()
        step3.on_show()
        wizard_data.update(step3.get_data())

        # Step 4: Import Config
        step4 = ImportConfigStep(self.root, wizard_data)
        step4.build_ui()
        step4.on_show()
        # Verify smart defaults
        self.assertEqual(len(step4.video_configs), 2)
        action_value = step4.video_configs[0]["action"]
        self.assertEqual(action_value, ImportAction.IMPORT_ZONES.value)
        self.assertEqual(step4.video_configs[1]["action"], ImportAction.FULL.value)
        wizard_data.update(step4.get_data())

        # Step 5: Confirmation
        step5 = ConfirmationStep(self.root, wizard_data)
        step5.build_ui()
        step5.on_show()
        step5.project_name_var.set("Test_Project")
        step5.project_location_var.set(str(self.temp_dir))
        wizard_data.update(step5.get_data())

        # Verify final wizard_data has all required fields
        self.assertEqual(wizard_data["project_type"], ProjectType.EXPERIMENTAL.value)
        self.assertIn("video_paths", wizard_data)
        self.assertIn("scanned_videos", wizard_data)
        self.assertIn("import_config", wizard_data)
        self.assertIn("project_name", wizard_data)
        self.assertIn("project_path", wizard_data)
        self.assertEqual(len(wizard_data["import_config"]), 2)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_complete_wizard_flow_exploratory(self, mock_scan):
        """Test complete wizard flow for exploratory project."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
        ]

        wizard_data = {}

        # Step 1: Discovery (exploratory)
        step1 = DiscoveryStep(self.root, wizard_data)
        step1.build_ui()
        step1.project_type_var.set(ProjectType.EXPLORATORY.value)
        step1.parquet_scope_var.set(0)  # no parquets
        wizard_data.update(step1.get_data())

        # Verify folder fields NOT in data for exploratory
        self.assertEqual(wizard_data["project_type"], ProjectType.EXPLORATORY.value)
        self.assertNotIn("has_folder_structure", wizard_data)
        self.assertNotIn("folder_meaning", wizard_data)

        # Step 2: File Selection
        step2 = FileSelectionStep(self.root, wizard_data)
        step2.build_ui()
        step2.video_paths = [str(self.video1)]
        wizard_data.update(step2.get_data())

        # Step 3: Detection
        step3 = DetectionStep(self.root, wizard_data)
        step3.build_ui()
        step3.on_show()
        wizard_data.update(step3.get_data())
        # Should NOT have detected design for exploratory
        self.assertIsNone(step3.detected_design)

        # Step 4: Import Config
        step4 = ImportConfigStep(self.root, wizard_data)
        step4.build_ui()
        step4.on_show()
        # All should be FULL since no parquets
        self.assertEqual(step4.video_configs[0]["action"], ImportAction.FULL.value)
        wizard_data.update(step4.get_data())

        # Step 5: Confirmation
        step5 = ConfirmationStep(self.root, wizard_data)
        step5.build_ui()
        step5.on_show()
        wizard_data.update(step5.get_data())

        # Verify exploratory project name
        self.assertIn("Exploratorio", step5.project_name_var.get())

    def test_set_data_restores_state_across_all_steps(self):
        """Test that set_data works for all steps (back navigation)."""
        wizard_data = {}

        # Step 1: Create and extract data
        step1 = DiscoveryStep(self.root, wizard_data)
        step1.build_ui()
        step1.project_type_var.set(ProjectType.EXPERIMENTAL.value)
        step1.folder_organization_var.set(2)
        step1.parquet_scope_var.set(2)  # all
        data1 = step1.get_data()

        # Create new instance and restore
        step1_new = DiscoveryStep(self.root, wizard_data)
        step1_new.build_ui()
        step1_new.set_data(data1)

        # Verify restoration
        self.assertEqual(
            step1_new.project_type_var.get(),
            ProjectType.EXPERIMENTAL.value,
        )
        self.assertEqual(step1_new.folder_organization_var.get(), 2)
        self.assertEqual(step1_new.parquet_scope_var.get(), 2)


if __name__ == "__main__":
    unittest.main()

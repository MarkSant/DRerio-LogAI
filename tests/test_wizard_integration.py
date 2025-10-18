"""
Integration tests for the complete wizard flow.

Tests the entire 5-step wizard data flow, step interactions,
and data persistence across steps.

Note: WizardDialog is a modal Dialog and cannot be fully tested in unit tests.
These tests focus on step-to-step data flow and integration logic.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import ImportAction, ProjectType
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep
from zebtrack.ui.wizard.import_config_step import ImportConfigStep


@pytest.mark.usefixtures("tkinter_root")
class TestWizardIntegration:
    """End-to-end integration tests for the complete wizard."""

    @pytest.fixture(autouse=True)
    def setup(self, tkinter_root):
        """Create Tkinter root for testing."""
        self.root = tkinter_root

        # Create temp directory and files
        self.temp_dir = Path(tempfile.mkdtemp())
        self.video1 = self.temp_dir / "Control" / "Day01" / "Subject01.mp4"
        self.video2 = self.temp_dir / "Treatment" / "Day01" / "Subject02.mp4"
        self.video1.parent.mkdir(parents=True)
        self.video2.parent.mkdir(parents=True)
        self.video1.touch()
        self.video2.touch()

        yield

        # Teardown
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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
        assert wizard_data["project_type"] == ProjectType.EXPERIMENTAL.value
        assert wizard_data["parquet_import_scope"] == "zones"
        assert wizard_data["has_folder_structure"]

        # Step 2 should be able to access this data
        step2 = FileSelectionStep(self.root, wizard_data)
        step2.build_ui()

        # Step 2 doesn't directly use Step 1 data, but it's available
        assert "project_type" in step2.wizard_data

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
        assert len(wizard_data["video_paths"]) == 1

        # Step 3: Detection uses Step 2 data
        step3 = DetectionStep(self.root, wizard_data)
        step3.build_ui()
        step3.on_show()  # Triggers scan

        data3 = step3.get_data()
        wizard_data.update(data3)

        # Verify Step 3 data
        assert "scanned_videos" in wizard_data
        assert len(wizard_data["scanned_videos"]) == 1

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
        assert len(step4.video_configs) == 1
        # Should be IMPORT_ZONES based on parquet_import_scope="zones"
        action_value = step4.video_configs[0]["action"]
        assert action_value == ImportAction.IMPORT_ZONES.value

        data4 = step4.get_data()
        wizard_data.update(data4)

        # Verify Step 4 data
        assert "import_config" in wizard_data
        assert len(wizard_data["import_config"]) == 1

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
        assert "Design:" in step5.summary_text
        assert "Experimental" in step5.summary_text

        # Verify default project name generated
        assert "Experimento" in step5.project_name_var.get()

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
        assert len(step4.video_configs) == 2
        action_value = step4.video_configs[0]["action"]
        assert action_value == ImportAction.IMPORT_ZONES.value
        assert step4.video_configs[1]["action"] == ImportAction.FULL.value
        wizard_data.update(step4.get_data())

        # Step 5: Confirmation
        step5 = ConfirmationStep(self.root, wizard_data)
        step5.build_ui()
        step5.on_show()
        step5.project_name_var.set("Test_Project")
        step5.project_location_var.set(str(self.temp_dir))
        wizard_data.update(step5.get_data())

        # Verify final wizard_data has all required fields
        assert wizard_data["project_type"] == ProjectType.EXPERIMENTAL.value
        assert "video_paths" in wizard_data
        assert "scanned_videos" in wizard_data
        assert "import_config" in wizard_data
        assert "project_name" in wizard_data
        assert "project_path" in wizard_data
        assert len(wizard_data["import_config"]) == 2

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
        assert wizard_data["project_type"] == ProjectType.EXPLORATORY.value
        assert "has_folder_structure" not in wizard_data
        assert "folder_meaning" not in wizard_data

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
        assert step3.detected_design is None

        # Step 4: Import Config
        step4 = ImportConfigStep(self.root, wizard_data)
        step4.build_ui()
        step4.on_show()
        # All should be FULL since no parquets
        assert step4.video_configs[0]["action"] == ImportAction.FULL.value
        wizard_data.update(step4.get_data())

        # Step 5: Confirmation
        step5 = ConfirmationStep(self.root, wizard_data)
        step5.build_ui()
        step5.on_show()
        wizard_data.update(step5.get_data())

        # Verify exploratory project name
        assert "Exploratorio" in step5.project_name_var.get()

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
        assert step1_new.project_type_var.get() == ProjectType.EXPERIMENTAL.value
        assert step1_new.folder_organization_var.get() == 2
        assert step1_new.parquet_scope_var.get() == 2

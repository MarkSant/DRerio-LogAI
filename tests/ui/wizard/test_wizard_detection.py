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
from pathlib import Path
from unittest.mock import patch

import pytest

from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID


@pytest.mark.gui
class TestDetectionStep:
    """Tests for detection step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root for testing."""
        self.root = wizard_dependencies["root"]
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

        yield

        # Teardown
        for path in [self.video1, self.video2]:
            if path.exists():
                path.unlink()

        for path in [
            self.temp_dir / "Control" / "Day01",
            self.temp_dir / "Treatment" / "Day01",
            self.temp_dir / "Control",
            self.temp_dir / "Treatment",
        ]:
            if path.exists() and path.is_dir():
                path.rmdir()
        self.temp_dir.rmdir()

    def test_detection_step_builds_ui_without_error(self):
        """Detection step should build UI without errors."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.DETECTION_VALIDATION

    def test_detection_step_default_state_is_empty(self):
        """Detection step defaults to empty state."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        assert step.scanned_videos == []
        assert step.detected_design is None

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
        assert len(step.scanned_videos) == 1

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

        assert not is_valid
        assert "nenhum vídeo" in error_message.lower()

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

        assert is_valid
        assert error_message == ""

    def test_detection_step_pattern_groups_as_folders(self):
        """Pattern detection should identify groups from folder structure."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Test pattern detection
        paths = [self.video1, self.video2]
        result = step._pattern_groups_as_folders(paths)

        # Should detect Control and Treatment groups
        assert result is not None
        assert "Control" in result["groups"]
        assert "Treatment" in result["groups"]
        assert result["confidence"] > 0.0

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
        assert result is not None
        assert "Control" in result["groups"]
        assert "Treatment" in result["groups"]
        assert result["pattern_used"] == "filename_based"

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

        assert summary["total_arena"] == 2
        assert summary["total_rois"] == 2
        assert summary["total_trajectory"] == 1
        assert summary["total_complete"] == 1

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
        assert result == new_design
        assert step.detected_design == new_design
        assert step.custom_regex_patterns is not None
        assert "regex personalizado aplicado" in step.status_var.get().lower()

        display_text = step.results_text.get("1.0", "end-1c")
        assert "Regex Group" in display_text

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

        assert "scanned_videos" in data
        assert "detected_design" in data
        assert "video_count" in data
        assert "parquet_summary" in data

        assert data["video_count"] == 1
        assert len(data["scanned_videos"]) == 1

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
        assert step.detected_design is None

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
        assert len(step.scanned_videos) == 1
        assert step.detected_design is not None
        assert step.detected_design["confidence"] == 0.75

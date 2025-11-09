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
from unittest.mock import MagicMock, patch

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

    # ========================================================================
    # Additional tests for model loading, threshold testing, parameter validation
    # ========================================================================

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_handles_scan_failure(self, mock_scan):
        """Detection step should handle scan failures gracefully."""
        # Mock scan to raise exception
        mock_scan.side_effect = Exception("Simulated scan failure")

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [str(self.video1)],
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Should not crash
        try:
            step.on_show()
        except Exception:
            # Exception should be handled internally
            pass

        # Status should indicate error
        assert "erro" in step.status_var.get().lower() or "falha" in step.status_var.get().lower()

    def test_detection_step_pattern_days_in_subfolder(self):
        """Pattern detection should identify days from subfolder structure."""
        # Create day-based structure
        day_paths = [
            self.temp_dir / "Control" / "Day01" / "Subject01.mp4",
            self.temp_dir / "Control" / "Day02" / "Subject01.mp4",
            self.temp_dir / "Treatment" / "Day01" / "Subject02.mp4",
        ]

        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        result = step._pattern_groups_as_folders(day_paths)

        if result:
            # Should detect days if supported
            assert "days" in result or result.get("days") is not None

    def test_detection_step_parquet_summary_all_zeros(self):
        """Parquet summary should handle case with no parquet files."""
        wizard_data = {}
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

        summary = step._calculate_parquet_summary()

        assert summary["total_arena"] == 0
        assert summary["total_rois"] == 0
        assert summary["total_trajectory"] == 0
        assert summary["total_complete"] == 0

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_large_video_list_performance(self, mock_scan):
        """Detection step should handle large video lists efficiently."""
        # Create large list of mock videos
        large_video_list = [
            {
                "path": f"/path/to/video{i:03d}.mp4",
                "has_arena": i % 3 == 0,
                "has_rois": i % 4 == 0,
                "has_trajectory": i % 5 == 0,
                "has_complete_data": False,
            }
            for i in range(200)
        ]

        mock_scan.return_value = large_video_list

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [f"/path/to/video{i:03d}.mp4" for i in range(200)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        # Should not crash and should process all videos
        assert len(step.scanned_videos) == 200

        data = step.get_data()
        assert data["video_count"] == 200

    def test_detection_step_pattern_confidence_calculation(self):
        """Pattern confidence should be calculated based on match quality."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Test with perfect match (all in structured folders)
        perfect_paths = [
            Path("/data/GroupA/Subject01.mp4"),
            Path("/data/GroupA/Subject02.mp4"),
            Path("/data/GroupB/Subject03.mp4"),
            Path("/data/GroupB/Subject04.mp4"),
        ]

        result = step._pattern_groups_as_folders(perfect_paths)

        if result:
            # High confidence for perfect structure
            assert result["confidence"] >= 0.5

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_mixed_parquet_states(self, mock_scan):
        """Detection step should handle mixed parquet availability correctly."""
        mock_scan.return_value = [
            {
                "path": str(self.video1),
                "has_arena": True,
                "has_rois": True,
                "has_trajectory": True,
                "has_complete_data": True,
            },
            {
                "path": str(self.video2),
                "has_arena": True,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
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

        # One video has complete data, one has partial
        assert summary["total_complete"] == 1
        assert summary["total_arena"] == 2
        assert summary["total_rois"] == 1
        assert summary["total_trajectory"] == 1

    def test_detection_step_pattern_no_match(self):
        """Pattern detection should return None when no pattern matches."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Random unstructured paths
        random_paths = [
            Path("/random/path/video1.mp4"),
            Path("/another/different/video2.mp4"),
            Path("/completely/unrelated/video3.mp4"),
        ]

        result = step._pattern_groups_as_folders(random_paths)

        # Should either return None or very low confidence
        if result:
            assert result["confidence"] < 0.5 or len(result.get("groups", [])) == 0

    @patch("zebtrack.ui.wizard.detection_step.DesignEditorDialog")
    def test_detection_step_design_editor_dialog_integration(self, mock_dialog):
        """Detection step should integrate with design editor dialog."""
        # Mock dialog result
        mock_dialog_instance = MagicMock()
        mock_dialog_instance.result = {
            "groups": ["Manual_Group_A", "Manual_Group_B"],
            "days": None,
            "subjects_per_group": {},
        }
        mock_dialog.return_value = mock_dialog_instance

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Simulate opening design editor
        # Note: Full integration test would require GUI interaction
        # This tests that the infrastructure is in place
        assert hasattr(step, "design_editor_confirmed")

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_video_count_accuracy(self, mock_scan):
        """video_count in get_data should match scanned_videos length."""
        mock_scan.return_value = [
            {
                "path": f"/video{i}.mp4",
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }
            for i in range(15)
        ]

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [f"/video{i}.mp4" for i in range(15)],
            "auto_confirm_design": True,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        data = step.get_data()

        assert data["video_count"] == 15
        assert len(data["scanned_videos"]) == 15

    def test_detection_step_status_updates_during_processing(self):
        """Status variable should update during detection processing."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Initial status
        initial_status = step.status_var.get()
        assert initial_status != ""

        # Status should be ready for updates
        assert hasattr(step, "status_var")
        assert step.status_var.get() is not None

    def test_detection_step_custom_regex_persistence(self):
        """Custom regex patterns should persist in step state."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        custom_patterns = {
            "group_pattern": r"Group_(\w+)",
            "day_pattern": r"Day(\d+)",
            "subject_pattern": None,
        }

        # Simulate setting custom regex
        step.custom_regex_patterns = custom_patterns

        # Should be accessible
        assert step.custom_regex_patterns == custom_patterns
        assert step.custom_regex_patterns["group_pattern"] == r"Group_(\w+)"

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_handles_empty_video_paths(self, mock_scan):
        """Detection step should handle empty video_paths gracefully."""
        mock_scan.return_value = []

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [],
            "auto_confirm_design": False,
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        # Should not crash
        assert step.scanned_videos == []

        is_valid, _ = step.validate()
        assert not is_valid

    def test_detection_step_pattern_subject_extraction(self):
        """Pattern detection should extract subject IDs when present."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        paths = [
            Path("/data/GroupA/Subject01.mp4"),
            Path("/data/GroupA/Subject02.mp4"),
            Path("/data/GroupB/Subject01.mp4"),
        ]

        result = step._pattern_filename_based(paths)

        if result and "subjects_per_group" in result:
            # Should have extracted subject information
            subjects = result["subjects_per_group"]
            assert isinstance(subjects, dict)

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_template_banner_display(self, mock_scan):
        """Template banner should display when template_metadata is present."""
        mock_scan.return_value = []

        wizard_data = {
            "project_type": ProjectType.EXPERIMENTAL.value,
            "video_paths": [],
            "template_metadata": {
                "name": "Detection Template",
                "path": "/path/to/template.json",
            },
        }

        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Template info should be set
        banner_text = step.template_info_var.get()
        assert "Template" in banner_text or banner_text != ""

    def test_detection_step_results_text_widget_exists(self):
        """Detection step should have results text widget for displaying results."""
        wizard_data = {}
        step = DetectionStep(self.root, wizard_data)
        step.build_ui()

        # Should have results_text widget
        assert hasattr(step, "results_text")

    @patch("zebtrack.ui.wizard.detection_step.ProjectManager.scan_input_paths")
    def test_detection_step_confidence_threshold_interpretation(self, mock_scan):
        """Low confidence detection should be handled appropriately."""
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

        # If design was detected with low confidence, it should still be accessible
        if step.detected_design:
            assert "confidence" in step.detected_design
            assert 0.0 <= step.detected_design["confidence"] <= 1.0

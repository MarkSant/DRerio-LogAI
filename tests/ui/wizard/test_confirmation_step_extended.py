"""Extended unit tests for ui/wizard/confirmation_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.confirmation_step import ConfirmationStep


class TestConfirmationStepExtended:
    """Test ConfirmationStep summaries, preview rendering, and data extraction."""

    def test_render_folder_preview(self):
        step = object.__new__(ConfirmationStep)
        entry = {
            "label": "Session 1",
            "counts": {"folders": 2, "files": 5},
            "nodes": [
                {
                    "label": "Group A",
                    "children": [{"label": "video1.mp4"}],
                }
            ],
            "truncated": False,
        }
        lines = step._render_folder_preview(entry)
        assert any("Session 1" in line for line in lines)
        assert any("2 folders" in line for line in lines)
        assert any("5 files" in line for line in lines)
        assert any("Group A" in line for line in lines)

    def test_append_parquet_summary(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "parquet_summary": {
                "total_arena": 3,
                "total_rois": 3,
                "total_trajectory": 3,
                "total_complete": 3,
            },
            "parquet_import_scope": "Full project",
        }
        lines: list[str] = []
        step._append_parquet_summary(lines)
        assert any("Existing Parquets" in line for line in lines)
        assert any("Arena: 3" in line for line in lines)
        assert any("Complete: 3" in line for line in lines)

    def test_append_import_configuration(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "import_config": [
                {"import_arena": True, "import_rois": False, "import_trajectory": True},
                {"import_arena": True, "import_rois": True, "import_trajectory": False},
            ]
        }
        lines: list[str] = []
        step._append_import_configuration(lines)
        assert any("Import Configuration" in line for line in lines)
        assert any("Arena: 2 videos" in line for line in lines)
        assert any("ROIs: 1 video" in line for line in lines)
        assert any("Trajectory: 1 video" in line for line in lines)

    def test_append_roi_strategy(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "import_config": [{"import_rois": True}],
            "roi_merge_strategy": "replace",
        }
        lines: list[str] = []
        step._append_roi_strategy(lines)
        assert any("ROI Strategy" in line for line in lines)
        assert any("Replace existing ROIs" in line for line in lines)

    def test_append_detected_design(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "detected_design": {
                "groups": ["Control", "Treated"],
                "days": ["Dia_1", "Dia_2"],
                "confidence": 0.95,
            }
        }
        lines: list[str] = []
        step._append_detected_design(lines)
        assert any("Detected Design" in line for line in lines)
        assert any("Groups: 2" in line for line in lines)
        assert any("Days: 2" in line for line in lines)
        assert any("95%" in line for line in lines)

    def test_append_custom_regex_info(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "custom_regex_patterns": {
                "group_pattern": r"Grupo_(?P<group>\w+)",
                "day_pattern": r"Dia_(?P<day>\d+)",
                "subject_pattern": None,
            }
        }
        lines: list[str] = []
        step._append_custom_regex_info(lines)
        assert any("Custom Regex" in line for line in lines)
        assert any("Grupo_" in line for line in lines)
        assert any("—" in line for line in lines)

    def test_append_detection_settings(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "model_selection": {"aquarium_method": "det", "animal_method": "seg"},
            "weight_assignments": {"aquarium": "aq.pt", "animal": "zeb.pt"},
            "use_openvino": True,
            "detector_parameters": {
                "confidence_threshold": 0.25,
                "nms_threshold": 0.45,
                "track_threshold": 0.5,
                "match_threshold": 0.7,
            },
        }
        lines: list[str] = []
        step._append_detection_settings(lines)
        assert any("Detection Settings" in line for line in lines)
        assert any("Aquarium method" in line for line in lines)
        assert any("aq.pt" in line for line in lines)
        assert any("Enabled" in line for line in lines)
        assert any("conf=0.25" in line for line in lines)

    def test_append_calibration(self):
        step = object.__new__(ConfirmationStep)
        step.wizard_data = {
            "num_aquariums": 2,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 15.0,
            "aquarium_height_cm": 25.0,
        }
        lines: list[str] = []
        step._append_calibration(lines)
        assert any("Physical Calibration" in line for line in lines)
        assert any("Aquariums: 2" in line for line in lines)
        assert any("15.0 x 25.0 cm" in line for line in lines)

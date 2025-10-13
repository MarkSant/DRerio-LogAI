"""
Tests for wizard adapter - translation between wizard and controller formats.
"""

import unittest

from zebtrack.ui.wizard.enums import ImportAction, ProjectType
from zebtrack.ui.wizard.wizard_adapter import (
    adapt_wizard_data_to_controller_format,
    enrich_videos_with_design_metadata,
    extract_parquet_import_plan,
)


class TestWizardAdapter(unittest.TestCase):
    """Tests for wizard data adapter."""

    def test_adapt_minimal_wizard_data(self):
        """Adapter should handle minimal wizard data (no design, no parquets)."""
        wizard_data = {
            "wizard_schema_version": 1,
            "created_at": "2025-10-04T10:00:00Z",
            "project_type": ProjectType.EXPLORATORY.value,
            "project_name": "Test_Project",
            "project_path": "/path/to/Test_Project",
            "video_paths": ["/path/to/video1.mp4", "/path/to/video2.mp4"],
            "scanned_videos": [
                {"path": "/path/to/video1.mp4", "has_complete_data": False},
                {"path": "/path/to/video2.mp4", "has_complete_data": False},
            ],
            "has_parquets": False,
            "parquet_import_scope": None,
            "folder_preview": [],
        }

        result = adapt_wizard_data_to_controller_format(wizard_data)

        # Verify required controller fields
        self.assertEqual(result["project_path"], "/path/to/Test_Project")
        self.assertEqual(result["project_type"], "pre-recorded")
        self.assertEqual(len(result["video_files"]), 2)
        self.assertEqual(result["video_files"][0]["path"], "/path/to/video1.mp4")
        self.assertEqual(result["video_files"][0]["has_data"], False)

        # Verify defaults
        self.assertEqual(result["num_aquariums"], 1)
        self.assertEqual(result["animals_per_aquarium"], 1)
        self.assertEqual(result["analysis_interval_frames"], 10)
        self.assertTrue(result["use_single_subject_tracker"])

        # Verify no experimental design
        self.assertIsNone(result["experiment_days"])
        self.assertIsNone(result["num_groups"])

        # Verify wizard metadata preserved
        self.assertIn("_wizard_metadata", result)
        self.assertEqual(result["_wizard_metadata"]["wizard_schema_version"], 1)
        self.assertEqual(result["_wizard_metadata"].get("folder_preview"), [])

    def test_adapt_experimental_with_design(self):
        """Adapter should extract experimental design from detected_design."""
        wizard_data = {
            "wizard_schema_version": 1,
            "created_at": "2025-10-04T10:00:00Z",
            "project_type": ProjectType.EXPERIMENTAL.value,
            "project_name": "Experiment_Control",
            "project_path": "/path/to/Experiment_Control",
            "video_paths": ["/path/to/Control/Day01/S01.mp4"],
            "scanned_videos": [
                {"path": "/path/to/Control/Day01/S01.mp4", "has_complete_data": False},
            ],
            "has_folder_structure": True,
            "folder_meaning": "experimental",
            "has_parquets": False,
            "folder_preview": [
                {
                    "label": "📁 Experimento",
                    "path": "/path/to/Experiment_Control",
                    "counts": {"folders": 2, "files": 1},
                    "nodes": [],
                    "truncated": False,
                }
            ],
            "detected_design": {
                "groups": ["Control", "Treatment"],
                "days": ["Day01", "Day02"],
                "subjects_per_group": {
                    "Control": ["S01", "S02", "S03"],
                    "Treatment": ["S01", "S02", "S03"],
                },
                "confidence": 0.85,
                "pattern_used": "groups_as_folders",
            },
        }

        result = adapt_wizard_data_to_controller_format(wizard_data)

        # Verify experimental design extracted
        self.assertEqual(result["num_groups"], 2)
        self.assertEqual(result["group_names"], ["Control", "Treatment"])
        self.assertEqual(result["experiment_days"], 2)
        # subjects_per_group should be calculated from max of subjects dict
        self.assertEqual(result["subjects_per_group"], 3)  # max(3, 3) = 3
        self.assertTrue(result["use_single_subject_tracker"])

        # Verify per-video metadata enrichment
        first_video = result["video_files"][0]
        self.assertEqual(first_video["metadata"]["group"], "Control")
        self.assertEqual(first_video["metadata"]["day"], "Day01")
        self.assertEqual(first_video["metadata"]["day_label"], "01")
        self.assertEqual(first_video["metadata"]["subject"], "S01")

        # Verify metadata preserved
        self.assertIn("detected_design", result["_wizard_metadata"])
        metadata = result["_wizard_metadata"]["detected_design"]
        self.assertEqual(metadata["confidence"], 0.85)

        enriched_scanned = result["_wizard_metadata"]["scanned_videos"]
        self.assertEqual(enriched_scanned[0]["group"], "Control")
        self.assertEqual(enriched_scanned[0]["metadata"]["subject"], "S01")
        self.assertEqual(enriched_scanned[0]["metadata"]["day_label"], "01")
        folder_preview = result["_wizard_metadata"].get("folder_preview")
        self.assertIsNotNone(folder_preview)
        assert folder_preview is not None
        self.assertEqual(folder_preview[0]["counts"]["files"], 1)

    def test_adapt_with_parquet_import(self):
        """Adapter should preserve parquet import configuration."""
        wizard_data = {
            "wizard_schema_version": 1,
            "created_at": "2025-10-04T10:00:00Z",
            "project_type": ProjectType.EXPERIMENTAL.value,
            "project_name": "Import_Test",
            "project_path": "/path/to/Import_Test",
            "video_paths": ["/path/to/video1.mp4"],
            "scanned_videos": [
                {"path": "/path/to/video1.mp4", "has_complete_data": False},
            ],
            "has_parquets": True,
            "parquet_import_scope": "zones",
            "import_config": [
                {
                    "video": "/path/to/video1.mp4",
                    "import_arena": True,
                    "import_rois": True,
                    "import_trajectory": False,
                    "action": ImportAction.IMPORT_ZONES.value,
                }
            ],
            "roi_merge_strategy": "replace",
            "parquet_summary": {
                "total_arena": 1,
                "total_rois": 1,
                "total_trajectory": 0,
                "total_complete": 0,
            },
        }

        result = adapt_wizard_data_to_controller_format(wizard_data)

        # Verify import config preserved in metadata
        self.assertIn("import_config", result["_wizard_metadata"])
        self.assertEqual(len(result["_wizard_metadata"]["import_config"]), 1)
        self.assertEqual(
            result["_wizard_metadata"]["import_config"][0]["action"],
            ImportAction.IMPORT_ZONES.value,
        )
        self.assertEqual(result["_wizard_metadata"]["roi_merge_strategy"], "replace")

    def test_adapt_propagates_use_openvino_selection(self):
        """Adapter should propagate OpenVINO toggles to controller data."""
        wizard_data = {
            "wizard_schema_version": 3,
            "created_at": "2025-10-04T10:00:00Z",
            "project_type": ProjectType.EXPLORATORY.value,
            "project_name": "OpenVINO_Project",
            "project_path": "/path/to/OpenVINO_Project",
            "video_paths": ["/path/to/video1.mp4"],
            "scanned_videos": [
                {"path": "/path/to/video1.mp4", "has_complete_data": False}
            ],
            "use_openvino": True,
        }

        result = adapt_wizard_data_to_controller_format(wizard_data)

        self.assertTrue(result["use_openvino"])
        metadata = result.get("_wizard_metadata", {})
        self.assertTrue(metadata.get("use_openvino"))

    def test_extract_parquet_import_plan(self):
        """extract_parquet_import_plan should extract import configuration."""
        wizard_data = {
            "has_parquets": True,
            "import_config": [
                {
                    "video": "/path/to/video1.mp4",
                    "action": ImportAction.IMPORT_ZONES.value,
                }
            ],
            "roi_merge_strategy": "merge",
            "parquet_summary": {"total_arena": 1},
        }

        plan = extract_parquet_import_plan(wizard_data)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(len(plan["import_config"]), 1)
        self.assertEqual(plan["roi_merge_strategy"], "merge")
        self.assertEqual(plan["parquet_summary"]["total_arena"], 1)

    def test_extract_parquet_import_plan_no_parquets(self):
        """extract_parquet_import_plan should return None if no parquets."""
        wizard_data = {
            "has_parquets": False,
        }

        plan = extract_parquet_import_plan(wizard_data)

        self.assertIsNone(plan)

    def test_extract_parquet_import_plan_empty_config(self):
        """extract_parquet_import_plan should return None if config is empty."""
        wizard_data = {
            "has_parquets": True,
            "import_config": [],
        }

        plan = extract_parquet_import_plan(wizard_data)

        self.assertIsNone(plan)

    def test_enrich_videos_with_custom_regex_patterns(self):
        """Video enrichment should honour user-specified regex patterns."""
        scanned_videos = [
            {
                "path": "/data/Exp/CBD_10mg/Day5/Animal42.mp4",
                "has_complete_data": True,
            }
        ]

        detected_design = {
            "groups": ["CBD_10mg", "Vehicle"],
            "days": ["Day01", "Day05"],
            "subjects_per_group": {
                "CBD_10mg": ["S01", "S05", "S42"],
                "Vehicle": ["S01"],
            },
            "pattern_used": "custom_regex",
            "confidence": 0.9,
        }

        custom_patterns = {
            "group_pattern": r"Exp/(CBD_10mg|Vehicle)",
            "day_pattern": r"Day(\d+)",
            "subject_pattern": r"Animal(\d+)",
        }

        enriched = enrich_videos_with_design_metadata(
            scanned_videos,
            detected_design,
            custom_patterns,
            {"CBD_10mg": "CBD 10 mg"},
        )

        self.assertEqual(enriched[0]["group"], "CBD_10mg")
        self.assertEqual(enriched[0]["metadata"]["group_display_name"], "CBD 10 mg")
        self.assertEqual(enriched[0]["day"], "Day05")
        self.assertEqual(enriched[0]["metadata"]["day_label"], "05")
        self.assertEqual(enriched[0]["subject"], "S42")

    def test_adapt_raises_on_missing_required_fields(self):
        """Adapter should raise ValueError if required fields are missing."""
        wizard_data = {
            "project_name": "Test",
            # Missing: project_path, video_paths, project_type
        }

        with self.assertRaises(ValueError) as cm:
            adapt_wizard_data_to_controller_format(wizard_data)

        self.assertIn("Missing required wizard fields", str(cm.exception))

    def test_adapt_raises_on_no_videos(self):
        """Adapter should raise ValueError if no scanned videos."""
        wizard_data = {
            "wizard_schema_version": 1,
            "project_type": ProjectType.EXPERIMENTAL.value,
            "project_name": "Test",
            "project_path": "/path/to/Test",
            "video_paths": [],
            "scanned_videos": [],  # Empty!
        }

        with self.assertRaises(ValueError) as cm:
            adapt_wizard_data_to_controller_format(wizard_data)

        self.assertIn("No scanned videos found", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

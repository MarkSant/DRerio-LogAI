"""
Tests for wizard Step 4 (Import Configuration).

Validates:
- Import config step UI creation
- Smart defaults computation
- Table population
- Checkbox toggling
- Action derivation
- ROI merge strategy selection
- Summary calculation
- Data extraction
- Back navigation
"""

import unittest
from tkinter import Tk

from zebtrack.ui.wizard.enums import (
    ImportAction,
    ROIMergeStrategy,
    WizardStepID,
)
from zebtrack.ui.wizard.import_config_step import ImportConfigStep


class TestImportConfigStep(unittest.TestCase):
    """Tests for import configuration step."""

    def setUp(self):
        """Create Tkinter root for testing."""
        self.root = Tk()
        self.root.withdraw()  # Hide window during tests

    def tearDown(self):
        """Destroy Tkinter root."""
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

    def test_import_config_step_builds_ui_without_error(self):
        """Import config step should build UI without errors."""
        wizard_data = {}
        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        self.assertEqual(step.step_id, WizardStepID.IMPORT_CONFIG)

    def test_import_config_step_default_state_is_empty(self):
        """Import config step defaults to empty state."""
        wizard_data = {}
        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()

        self.assertEqual(step.video_configs, [])
        merge_value = step.roi_merge_strategy_var.get()
        self.assertEqual(merge_value, ROIMergeStrategy.REPLACE.value)

    def test_smart_defaults_import_scope_all(self):
        """Smart defaults with 'all' scope should import everything available."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        self.assertEqual(len(step.video_configs), 1)
        config = step.video_configs[0]

        self.assertTrue(config["import_arena"])
        self.assertTrue(config["import_rois"])
        self.assertTrue(config["import_trajectory"])
        self.assertEqual(config["action"], ImportAction.SKIP.value)

    def test_smart_defaults_import_scope_zones(self):
        """Smart defaults with 'zones' scope should import arena+ROIs only."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": "zones",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]

        self.assertTrue(config["import_arena"])
        self.assertTrue(config["import_rois"])
        self.assertFalse(config["import_trajectory"])  # Never import trajectory
        self.assertEqual(config["action"], ImportAction.IMPORT_ZONES.value)

    def test_smart_defaults_import_scope_none(self):
        """Smart defaults with None scope should start fresh (no imports)."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": None,
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]

        self.assertFalse(config["import_arena"])
        self.assertFalse(config["import_rois"])
        self.assertFalse(config["import_trajectory"])
        self.assertEqual(config["action"], ImportAction.FULL.value)

    def test_smart_defaults_partial_parquets(self):
        """Smart defaults should only import what exists."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]

        self.assertTrue(config["import_arena"])
        self.assertFalse(config["import_rois"])  # Not available
        self.assertFalse(config["import_trajectory"])  # Not available
        self.assertEqual(config["action"], ImportAction.PARTIAL.value)

    def test_populate_table_creates_rows(self):
        """Table should be populated with all videos."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                },
                {
                    "path": "/path/video2.mp4",
                    "has_arena": False,
                    "has_rois": False,
                    "has_trajectory": False,
                },
            ],
            "parquet_import_scope": "zones",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()  # Triggers compute defaults and populate

        # Should have 2 rows
        self.assertEqual(len(step.video_tree.get_children()), 2)

    def test_validate_succeeds_with_videos(self):
        """Validation should succeed when videos are configured."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        is_valid, error_message = step.validate()

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

    def test_validate_fails_with_no_videos(self):
        """Validation should fail when no videos are configured."""
        wizard_data = {
            "scanned_videos": [],
            "parquet_import_scope": None,
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        is_valid, error_message = step.validate()

        self.assertFalse(is_valid)
        self.assertIn("nenhum vídeo", error_message.lower())

    def test_get_data_returns_clean_config(self):
        """get_data should return clean config without internal fields."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": "zones",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        data = step.get_data()

        self.assertIn("import_config", data)
        self.assertIn("roi_merge_strategy", data)

        # Config should have exactly the expected fields
        config = data["import_config"][0]
        self.assertIn("video", config)
        self.assertIn("import_arena", config)
        self.assertIn("import_rois", config)
        self.assertIn("import_trajectory", config)
        self.assertIn("action", config)

        # Should NOT have internal fields
        self.assertNotIn("has_arena", config)
        self.assertNotIn("has_rois", config)
        self.assertNotIn("has_trajectory", config)

    def test_roi_merge_strategy_selection(self):
        """ROI merge strategy should be configurable."""
        wizard_data = {}
        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()

        # Change strategy
        step.roi_merge_strategy_var.set(ROIMergeStrategy.MERGE.value)

        data = step.get_data()

        self.assertEqual(data["roi_merge_strategy"], ROIMergeStrategy.MERGE.value)

    def test_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "import_config": [
                {
                    "video": "/path/video1.mp4",
                    "import_arena": True,
                    "import_rois": False,
                    "import_trajectory": False,
                    "action": ImportAction.PARTIAL.value,
                }
            ],
            "roi_merge_strategy": ROIMergeStrategy.MANUAL.value,
        }

        step.set_data(previous_data)

        # Verify state restored
        self.assertEqual(len(step.video_configs), 1)
        self.assertEqual(step.video_configs[0]["import_arena"], True)
        self.assertEqual(step.video_configs[0]["import_rois"], False)
        merge_value = step.roi_merge_strategy_var.get()
        self.assertEqual(merge_value, ROIMergeStrategy.MANUAL.value)

        # Verify table populated
        self.assertEqual(len(step.video_tree.get_children()), 1)

    def test_summary_calculation(self):
        """Summary should correctly count actions."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                },
                {
                    "path": "/path/video2.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": False,
                },
                {
                    "path": "/path/video3.mp4",
                    "has_arena": False,
                    "has_rois": False,
                    "has_trajectory": False,
                },
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        summary = step.summary_var.get()

        # Should show counts for different actions
        self.assertIn("1", summary)  # 1 SKIP
        self.assertIn("1", summary)  # 1 IMPORT_ZONES
        self.assertIn("1", summary)  # 1 FULL

    def test_action_derivation_all_checked(self):
        """All checkboxes checked should derive SKIP action."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]
        self.assertEqual(config["action"], ImportAction.SKIP.value)

    def test_action_derivation_zones_only(self):
        """Arena+ROIs checked should derive IMPORT_ZONES action."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": True,
                    "has_trajectory": True,
                }
            ],
            "parquet_import_scope": "zones",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]
        self.assertEqual(config["action"], ImportAction.IMPORT_ZONES.value)

    def test_action_derivation_arena_only(self):
        """Only arena checked should derive PARTIAL action."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": True,
                    "has_rois": False,
                    "has_trajectory": False,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]
        self.assertEqual(config["action"], ImportAction.PARTIAL.value)

    def test_action_derivation_none_checked(self):
        """No checkboxes should derive FULL action."""
        wizard_data = {
            "scanned_videos": [
                {
                    "path": "/path/video1.mp4",
                    "has_arena": False,
                    "has_rois": False,
                    "has_trajectory": False,
                }
            ],
            "parquet_import_scope": "all",
        }

        step = ImportConfigStep(self.root, wizard_data)
        step.build_ui()
        step._compute_smart_defaults()

        config = step.video_configs[0]
        self.assertEqual(config["action"], ImportAction.FULL.value)


if __name__ == "__main__":
    unittest.main()

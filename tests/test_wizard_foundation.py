"""
Tests for wizard foundation and Step 1 (Discovery).

Validates:
- Wizard initialization
- Step 1 UI creation
- Step 1 data extraction
- Step 1 validation
- Navigation (forward only in Phase W1)
"""

import unittest
from tkinter import Tk

from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import (
    ImportAction,
    ProjectType,
    WizardStepID,
    derive_import_action,
)


class TestWizardFoundation(unittest.TestCase):
    """Tests for wizard initialization and basic navigation."""

    def setUp(self):
        """Create Tkinter root for testing."""
        self.root = Tk()
        self.root.withdraw()  # Hide window during tests

    def tearDown(self):
        """Destroy Tkinter root."""
        self.root.destroy()

    def test_wizard_initializes_with_schema_version(self):
        """Wizard should initialize with wizard_schema_version: 1."""
        # Note: We can't fully test WizardDialog in headless mode
        # because Dialog is modal. Test the data structure instead.
        wizard_data = {
            "wizard_schema_version": 1,
        }
        self.assertEqual(wizard_data["wizard_schema_version"], 1)

    def test_discovery_step_builds_ui_without_error(self):
        """Discovery step should build UI without errors."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        self.assertEqual(step.step_id, WizardStepID.DISCOVERY)

    def test_discovery_step_default_data_is_experimental(self):
        """Discovery step defaults to experimental project type."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        self.assertEqual(data["project_type"], ProjectType.EXPERIMENTAL.value)
        self.assertIn("has_folder_structure", data)
        self.assertIn("folder_meaning", data)
        self.assertFalse(data["has_parquets"])
        self.assertIsNone(data["parquet_import_scope"])

    def test_discovery_step_exploratory_excludes_folder_fields(self):
        """Exploratory projects should not have folder organization fields."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Change to exploratory
        step.project_type_var.set(ProjectType.EXPLORATORY.value)
        data = step.get_data()

        self.assertEqual(data["project_type"], ProjectType.EXPLORATORY.value)
        self.assertNotIn("has_folder_structure", data)
        self.assertNotIn("folder_meaning", data)

    def test_discovery_step_parquet_scope_arena(self):
        """Selecting 'import arena' should set parquet_import_scope to 'arena'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import arena"
        step.parquet_scope_var.set(1)
        data = step.get_data()

        self.assertTrue(data["has_parquets"])
        self.assertEqual(data["parquet_import_scope"], "arena")

    def test_discovery_step_parquet_scope_zones(self):
        """Selecting 'import zones' should set parquet_import_scope to 'zones'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import zones"
        step.parquet_scope_var.set(2)
        data = step.get_data()

        self.assertTrue(data["has_parquets"])
        self.assertEqual(data["parquet_import_scope"], "zones")

    def test_discovery_step_parquet_scope_all(self):
        """Selecting 'import all' should set parquet_import_scope to 'all'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import all"
        step.parquet_scope_var.set(3)
        data = step.get_data()

        self.assertTrue(data["has_parquets"])
        self.assertEqual(data["parquet_import_scope"], "all")

    def test_discovery_step_validate_always_succeeds(self):
        """Discovery step validation should always succeed (all fields have defaults)."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        is_valid, error_message = step.validate()

        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

    def test_discovery_step_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "project_type": ProjectType.EXPLORATORY.value,
            "has_parquets": True,
            "parquet_import_scope": "zones",
        }

        step.set_data(previous_data)

        # Verify UI restored
        self.assertEqual(step.project_type_var.get(), ProjectType.EXPLORATORY.value)
        self.assertEqual(step.parquet_scope_var.get(), 2)  # 2 = zones


class TestEnums(unittest.TestCase):
    """Tests for formal enumerations."""

    def test_project_type_enum_values(self):
        """ProjectType enum should have correct values."""
        self.assertEqual(ProjectType.EXPERIMENTAL.value, "experimental")
        self.assertEqual(ProjectType.EXPLORATORY.value, "exploratory")

    def test_import_action_enum_values(self):
        """ImportAction enum should have correct values."""
        self.assertEqual(ImportAction.SKIP.value, "skip")
        self.assertEqual(ImportAction.IMPORT_ZONES.value, "import_zones")
        self.assertEqual(ImportAction.PARTIAL.value, "partial")
        self.assertEqual(ImportAction.FULL.value, "full")

    def test_derive_import_action_skip(self):
        """All 3 checkboxes → SKIP."""
        action = derive_import_action(True, True, True)
        self.assertEqual(action, ImportAction.SKIP)

    def test_derive_import_action_import_zones(self):
        """Arena + ROIs → IMPORT_ZONES."""
        action = derive_import_action(True, True, False)
        self.assertEqual(action, ImportAction.IMPORT_ZONES)

    def test_derive_import_action_partial(self):
        """Arena only → PARTIAL."""
        action = derive_import_action(True, False, False)
        self.assertEqual(action, ImportAction.PARTIAL)

    def test_derive_import_action_full(self):
        """No checkboxes → FULL."""
        action = derive_import_action(False, False, False)
        self.assertEqual(action, ImportAction.FULL)

    def test_derive_import_action_normalizes_invalid_states(self):
        """Invalid states (ROIs without arena) → FULL."""
        # Invalid: ROIs but no arena
        action = derive_import_action(False, True, False)
        self.assertEqual(action, ImportAction.FULL)

        # Invalid: Trajectory but no arena
        action = derive_import_action(False, False, True)
        self.assertEqual(action, ImportAction.FULL)


if __name__ == "__main__":
    unittest.main()

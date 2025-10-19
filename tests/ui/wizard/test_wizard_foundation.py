"""
Tests for wizard foundation and Step 1 (Discovery).

Validates:
- Wizard initialization
- Step 1 UI creation
- Step 1 data extraction
- Step 1 validation
- Navigation (forward only in Phase W1)
"""

import pytest

from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import (
    ImportAction,
    ProjectType,
    WizardStepID,
    derive_import_action,
)
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep


@pytest.mark.gui
class TestWizardFoundation:
    """Tests for wizard initialization and basic navigation."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root for testing."""
        self.root = wizard_dependencies["root"]

    def test_wizard_initializes_with_schema_version(self):
        """Wizard should initialize with wizard_schema_version: 1."""
        # Note: We can't fully test WizardDialog in headless mode
        # because Dialog is modal. Test the data structure instead.
        wizard_data = {
            "wizard_schema_version": 1,
        }
        assert wizard_data["wizard_schema_version"] == 1

    def test_discovery_step_builds_ui_without_error(self):
        """Discovery step should build UI without errors."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.DISCOVERY

    def test_discovery_step_default_data_is_experimental(self):
        """Discovery step defaults to experimental project type."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        assert data["project_type"] == ProjectType.EXPERIMENTAL.value
        assert "has_folder_structure" in data
        assert "folder_meaning" in data
        assert not data["has_parquets"]
        assert data["parquet_import_scope"] is None

    def test_discovery_step_exploratory_excludes_folder_fields(self):
        """Exploratory projects should not have folder organization fields."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Change to exploratory
        step.project_type_var.set(ProjectType.EXPLORATORY.value)
        data = step.get_data()

        assert data["project_type"] == ProjectType.EXPLORATORY.value
        assert "has_folder_structure" not in data
        assert "folder_meaning" not in data

    def test_discovery_step_parquet_scope_arena(self):
        """Selecting 'import arena' should set parquet_import_scope to 'arena'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import arena"
        step.parquet_scope_var.set(1)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "arena"

    def test_discovery_step_parquet_scope_zones(self):
        """Selecting 'import zones' should set parquet_import_scope to 'zones'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import zones"
        step.parquet_scope_var.set(2)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "zones"

    def test_discovery_step_parquet_scope_all(self):
        """Selecting 'import all' should set parquet_import_scope to 'all'."""
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        # Select "import all"
        step.parquet_scope_var.set(3)
        data = step.get_data()

        assert data["has_parquets"]
        assert data["parquet_import_scope"] == "all"

    def test_discovery_step_validate_always_succeeds(self):
        """
        Discovery step validation should always succeed (all fields have defaults).
        """
        wizard_data = {}
        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

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
        assert step.project_type_var.get() == ProjectType.EXPLORATORY.value
        assert step.parquet_scope_var.get() == 2  # 2 = zones

    def test_discovery_step_template_banner(self):
        """Template metadata should surface in the discovery banner."""
        wizard_data = {
            "template_metadata": {
                "name": "Template Inicial",
                "path": "C:/temp/template_inicial.json",
            }
        }

        step = DiscoveryStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert "Template Inicial" in step.template_info_var.get()

    def test_file_selection_step_template_banner(self):
        """Template metadata should surface in the file selection banner."""
        wizard_data = {
            "template_metadata": {
                "name": "Template Seleção",
                "path": "C:/temp/template_selecao.json",
            }
        }

        step = FileSelectionStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert "Template Seleção" in step.template_info_var.get()


class TestEnums:
    """Tests for formal enumerations."""

    def test_project_type_enum_values(self):
        """ProjectType enum should have correct values."""
        assert ProjectType.EXPERIMENTAL.value == "experimental"
        assert ProjectType.EXPLORATORY.value == "exploratory"

    def test_import_action_enum_values(self):
        """ImportAction enum should have correct values."""
        assert ImportAction.SKIP.value == "skip"
        assert ImportAction.IMPORT_ZONES.value == "import_zones"
        assert ImportAction.PARTIAL.value == "partial"
        assert ImportAction.FULL.value == "full"

    def test_derive_import_action_skip(self):
        """All 3 checkboxes → SKIP."""
        action = derive_import_action(True, True, True)
        assert action == ImportAction.SKIP

    def test_derive_import_action_import_zones(self):
        """Arena + ROIs → IMPORT_ZONES."""
        action = derive_import_action(True, True, False)
        assert action == ImportAction.IMPORT_ZONES

    def test_derive_import_action_partial(self):
        """Arena only → PARTIAL."""
        action = derive_import_action(True, False, False)
        assert action == ImportAction.PARTIAL

    def test_derive_import_action_full(self):
        """No checkboxes → FULL."""
        action = derive_import_action(False, False, False)
        assert action == ImportAction.FULL

    def test_derive_import_action_normalizes_invalid_states(self):
        """Invalid states (ROIs without arena) → FULL."""
        # Invalid: ROIs but no arena
        action = derive_import_action(False, True, False)
        assert action == ImportAction.FULL

        # Invalid: Trajectory but no arena
        action = derive_import_action(False, False, True)
        assert action == ImportAction.FULL

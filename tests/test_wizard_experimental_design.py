"""
Tests for ExperimentalDesignStep (Phase 0 - Critical Fix).

Tests validation, data collection, and UI state management for
experimental design configuration in live projects.
"""

import pytest

from zebtrack.ui.wizard.experimental_design_step import ExperimentalDesignStep

pytestmark = pytest.mark.gui  # All tests in this file are GUI tests


@pytest.fixture
def wizard_data():
    """Create wizard data dict."""
    return {"project_type": "live"}


@pytest.fixture
def step(tkinter_root, wizard_data):
    """Create ExperimentalDesignStep instance."""
    step = ExperimentalDesignStep(tkinter_root, wizard_data)
    step.build_ui()
    return step


def test_experimental_design_step_defaults(step):
    """Test default values are sensible."""
    data = step.get_data()

    assert data["num_groups"] == 2
    assert data["experiment_days"] == 1
    assert data["subjects_per_group"] == 1
    assert len(data["group_names"]) == 2
    assert data["group_names"] == ["Controle", "Tratamento 1"]


def test_experimental_design_validates_empty_group_name(step):
    """Test validation rejects empty group names."""
    # Set first group name to empty
    step.group_name_vars[0].set("")

    valid, msg = step.validate()

    assert not valid
    assert "vazio" in msg.lower()
    # Message says "Nomes de grupos não podem estar vazios" without specifying which one


def test_experimental_design_validates_duplicate_names(step):
    """Test validation rejects duplicate group names."""
    # Set both groups to same name
    step.group_name_vars[0].set("Grupo A")
    step.group_name_vars[1].set("Grupo A")

    valid, msg = step.validate()

    assert not valid
    assert "únicos" in msg.lower() or "duplicado" in msg.lower()


def test_experimental_design_valid_configuration(step):
    """Test validation passes with valid configuration."""
    step.group_name_vars[0].set("Controle")
    step.group_name_vars[1].set("Tratamento")

    valid, msg = step.validate()

    assert valid
    assert msg == ""


def test_experimental_design_get_data_trims_names(step):
    """Test get_data() trims whitespace from group names."""
    step.group_name_vars[0].set("  Controle  ")
    step.group_name_vars[1].set("Tratamento   ")

    data = step.get_data()

    assert data["group_names"] == ["Controle", "Tratamento"]


def test_experimental_design_adjusts_to_group_count(step):
    """Test that changing num_groups rebuilds name entries."""
    # Start with 2 groups
    assert len(step.group_name_vars) == 2

    # Change to 4 groups
    step.num_groups_var.set(4)
    step._on_num_groups_change()

    # Should now have 4 entry fields
    assert len(step.group_name_vars) == 4
    assert len(step.group_name_entries) == 4

    # Get data should return 4 names
    data = step.get_data()
    assert len(data["group_names"]) == 4


def test_experimental_design_set_data_restores_state(step):
    """Test set_data() restores UI state correctly."""
    restore_data = {
        "experiment_days": 7,
        "num_groups": 3,
        "subjects_per_group": 5,
        "group_names": ["Controle", "CBD 10mg", "CBD 20mg"],
    }

    step.set_data(restore_data)

    # Verify variables updated
    assert step.num_days_var.get() == 7
    assert step.num_groups_var.get() == 3
    assert step.subjects_per_group_var.get() == 5

    # Verify group names restored
    assert len(step.group_name_vars) == 3
    assert step.group_name_vars[0].get() == "Controle"
    assert step.group_name_vars[1].get() == "CBD 10mg"
    assert step.group_name_vars[2].get() == "CBD 20mg"


def test_experimental_design_summary_updates(step):
    """Test summary label updates when values change."""
    step.num_groups_var.set(2)
    step.num_days_var.set(5)
    step.subjects_per_group_var.set(3)
    step._update_summary()

    summary = step.summary_var.get()

    # Should calculate: 2 groups × 5 days × 3 subjects = 30 sessions
    assert "30" in summary  # Total sessions
    assert "6" in summary  # Total animals (2 × 3)
    assert "5" in summary  # Days


def test_experimental_design_preserves_existing_names_on_rebuild(step, wizard_data):
    """Test that rebuilding entries preserves existing custom names."""
    # Set custom names
    step.group_name_vars[0].set("My Control")
    step.group_name_vars[1].set("My Treatment")

    # Store in wizard_data as would happen in real wizard
    wizard_data["group_names"] = ["My Control", "My Treatment"]

    # Rebuild (simulating group count change)
    step._rebuild_group_name_entries()

    # Names should be preserved
    assert step.group_name_vars[0].get() == "My Control"
    assert step.group_name_vars[1].get() == "My Treatment"


def test_experimental_design_validation_trims_before_checking(step):
    """Test that validation trims names before checking duplicates."""
    # Set names with whitespace that are the same after trimming
    step.group_name_vars[0].set("  Grupo A  ")
    step.group_name_vars[1].set("Grupo A")

    valid, msg = step.validate()

    # Should detect as duplicates after trimming
    assert not valid
    assert "únicos" in msg.lower()

    # And should have trimmed the values
    assert step.group_name_vars[0].get() == "Grupo A"
    assert step.group_name_vars[1].get() == "Grupo A"


def test_experimental_design_only_validates_active_groups(step):
    """Test that validation only checks active group count."""
    # Set to 2 groups
    step.num_groups_var.set(2)
    step._rebuild_group_name_entries()

    # Set first 2 names to valid
    step.group_name_vars[0].set("Grupo 1")
    step.group_name_vars[1].set("Grupo 2")

    valid, _ = step.validate()

    # Should be valid even though there might be more entries
    assert valid


def test_experimental_design_step_id_set_correctly(step):
    """Test that step_id is set to EXPERIMENTAL_DESIGN."""
    from zebtrack.ui.wizard.enums import WizardStepID

    assert step.step_id == WizardStepID.EXPERIMENTAL_DESIGN

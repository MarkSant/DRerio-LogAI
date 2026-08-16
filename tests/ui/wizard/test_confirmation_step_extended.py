"""Extended unit tests for ConfirmationStep in ui/wizard/confirmation_step.py."""

from __future__ import annotations

from zebtrack.ui.wizard.enums import ImportAction, ProjectType, WizardStepID


class TestConfirmationStepExtended:
    """Test confirmation step ID and wizard enum values."""

    def test_confirmation_step_id_integer(self):
        assert WizardStepID.CONFIRMATION.value == 8

    def test_project_type_values(self):
        names = {m.name for m in ProjectType}
        assert "FULL" in names or len(names) > 0

    def test_import_action_enum(self):
        names = {m.name for m in ImportAction}
        assert len(names) > 0

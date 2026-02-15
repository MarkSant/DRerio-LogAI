from typing import Any, cast

import pytest

from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.wizard_dialog import WizardDialog


class _FakeStep:
    def __init__(self, step_id):
        self.step_id = step_id
        self.pack_called = False

    def pack_forget(self):
        self.pack_called = True

    def pack(self, *a, **k):
        self.pack_called = True

    def on_show(self):
        return None


@pytest.mark.gui
def test_wizard_update_active_steps():
    wizard = WizardDialog.__new__(WizardDialog)
    wizard.wizard_data = {"project_type": ProjectType.EXPERIMENTAL.value}

    wizard.all_steps = cast(
        Any,
        {
            WizardStepID.DISCOVERY: _FakeStep(WizardStepID.DISCOVERY),
            WizardStepID.FILE_SELECTION: _FakeStep(WizardStepID.FILE_SELECTION),
            WizardStepID.CALIBRATION: _FakeStep(WizardStepID.CALIBRATION),
            WizardStepID.DETECTION_VALIDATION: _FakeStep(WizardStepID.DETECTION_VALIDATION),
            WizardStepID.MODEL_SELECTION: _FakeStep(WizardStepID.MODEL_SELECTION),
            WizardStepID.IMPORT_CONFIG: _FakeStep(WizardStepID.IMPORT_CONFIG),
            WizardStepID.CONFIRMATION: _FakeStep(WizardStepID.CONFIRMATION),
            WizardStepID.EXPERIMENTAL_DESIGN: _FakeStep(WizardStepID.EXPERIMENTAL_DESIGN),
            WizardStepID.LIVE_CONFIG: _FakeStep(WizardStepID.LIVE_CONFIG),
        },
    )
    wizard.active_steps = []

    wizard._update_active_steps()
    assert len(wizard.active_steps) == 7

    wizard.wizard_data["project_type"] = ProjectType.LIVE.value
    wizard._update_active_steps()
    assert len(wizard.active_steps) == 6

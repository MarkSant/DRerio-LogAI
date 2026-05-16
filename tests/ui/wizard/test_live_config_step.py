"""Tests for wizard Step 3 (Live Configuration).

Validates that the experimental design metadata fields (group/day/subject/
is_batch_last_session) are no longer collected by the live wizard step --
those values now come from the project batch grid defined in Step 2.
"""

from typing import Any

import pytest

from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.live_config_step import LiveConfigStep


@pytest.mark.gui
class TestLiveConfigStep:
    """Tests for the live recording configuration step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def test_live_config_step_builds_ui_without_error(self):
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()
        assert step.step_id == WizardStepID.LIVE_CONFIG

    def test_get_data_omits_experimental_metadata_fields(self):
        """`get_data()` must not expose the legacy experimental design keys.

        Group/day/subject/is_batch_last_session belong to the project batch
        grid (Step 2) -- exposing them here duplicated state and let the user
        drift the live session metadata away from the slot being recorded.
        """
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        data = step.get_data()

        for legacy_key in (
            "experimental_group",
            "experiment_day",
            "subject_id",
            "is_batch_last_session",
        ):
            assert legacy_key not in data, (
                f"{legacy_key!r} leaked into LiveConfigStep.get_data(); it must "
                "be sourced from the batch grid (Step 2), not the live config step."
            )

    def test_step_does_not_define_experimental_design_vars(self):
        wizard_data: dict[str, Any] = {}
        step = LiveConfigStep(self.root, wizard_data)
        step.build_ui()

        for attr in (
            "experimental_group_var",
            "experiment_day_var",
            "subject_id_var",
            "is_batch_last_session_var",
        ):
            assert not hasattr(step, attr), (
                f"LiveConfigStep should not own {attr!r}; the field was removed "
                "when the redundant experimental design box was dropped."
            )

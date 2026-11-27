"""
Tests for wizard Step 2 (Calibration).

Validates:
- Calibration step UI creation
- Default values and initialization
- Input validation (numeric bounds, required fields)
- Data extraction
- Data restoration (set_data)
- Template banner display
- WizardService integration for validation

==============================================================================
GUI TEST EXECUTION REQUIREMENTS
==============================================================================

CRITICAL: These tests MUST be run with serial execution (-n0).

Why:
  ttkbootstrap.Style maintains global state (singleton) that is NOT thread-safe.
  When pytest-xdist runs tests in parallel workers, simultaneous Style
  instantiation causes TclError "Can't find a usable tk.tcl" failures.

Correct usage:
  ✅ poetry run pytest -m gui -n0                 (all GUI tests, serial)
  ✅ poetry run pytest tests/ui/wizard/ -n0       (specific dir, serial)

Incorrect usage (will fail):
  ❌ poetry run pytest -m gui                     (missing -n0, uses -n=auto)
  ❌ poetry run pytest                            (GUI tests excluded by default)

==============================================================================
"""

from typing import Any

import pytest

from zebtrack.ui.wizard.calibration_step import CalibrationStep
from zebtrack.ui.wizard.enums import WizardStepID


def _need(value):
    """A widget the test just built must exist; narrows ``X | None`` for mypy."""
    assert value is not None
    return value


@pytest.mark.gui
class TestCalibrationStep:
    """Tests for calibration step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root for testing."""
        self.root = wizard_dependencies["root"]

    def test_calibration_step_builds_ui_without_error(self):
        """Calibration step should build UI without errors."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.CALIBRATION

    def test_calibration_step_default_values(self):
        """Calibration step should have sensible default values."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Default values
        assert step.num_aquariums_var.get() == 1
        assert step.animals_per_aquarium_var.get() == 1
        assert step.aquarium_width_var.get() == 10.0
        assert step.aquarium_height_var.get() == 10.0

    def test_calibration_step_get_data(self):
        """get_data should return complete calibration data."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Modify values
        step.num_aquariums_var.set(3)
        step.animals_per_aquarium_var.set(5)
        step.aquarium_width_var.set(25.5)
        step.aquarium_height_var.set(20.0)

        data = step.get_data()

        assert data["num_aquariums"] == 3
        assert data["animals_per_aquarium"] == 5
        assert data["aquarium_width_cm"] == 25.5
        assert data["aquarium_height_cm"] == 20.0

    def test_calibration_step_set_data_restores_ui(self):
        """set_data should restore UI from previously collected data."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Simulate previous data
        previous_data = {
            "num_aquariums": 6,
            "animals_per_aquarium": 2,
            "aquarium_width_cm": 30.0,
            "aquarium_height_cm": 40.0,
        }

        step.set_data(previous_data)

        # Verify state restored
        assert step.num_aquariums_var.get() == 6
        assert step.animals_per_aquarium_var.get() == 2
        assert step.aquarium_width_var.get() == 30.0
        assert step.aquarium_height_var.get() == 40.0

    def test_validation_succeeds_with_valid_data(self):
        """Validation should succeed with valid data."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(5)
        step.animals_per_aquarium_var.set(3)
        step.aquarium_width_var.set(20.0)
        step.aquarium_height_var.set(15.0)

        is_valid, error_message = step.validate()

        assert is_valid
        assert error_message == ""

    def test_validation_fails_with_zero_aquariums(self):
        """Validation should fail when num_aquariums is 0."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(0)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.get()  # Keep default

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "aquariums" in error_message.lower() or "at least 1" in error_message.lower()

    def test_validation_fails_with_zero_animals(self):
        """Validation should fail when animals_per_aquarium is 0."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(0)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.get()  # Keep default

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "animals" in error_message.lower() or "at least 1" in error_message.lower()

    def test_validation_fails_with_negative_dimensions(self):
        """Validation should fail with negative dimensions."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(-5.0)
        step.aquarium_height_var.set(10.0)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "width" in error_message.lower() or "greater than zero" in error_message.lower()

    def test_zero_dimensions_mean_no_calibration_and_are_accepted(self):
        """Zero é a forma de pedir análise em pixels, não um erro.

        ``ProjectLifecycleManager``, que de fato cria o projeto, documenta 0 cm
        como "sem calibração". Este teste esperava reprovação e com isso fixava
        uma divergência: o assistente proibia a única maneira de exprimir um
        projeto não calibrado.
        """
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(0.0)
        step.aquarium_height_var.set(0.0)

        is_valid, error_message = step.validate()

        assert is_valid, error_message

    def test_validation_fails_with_oversized_dimensions(self):
        """Acima de 500 cm o domínio recusa; o assistente precisa recusar antes."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(900.0)
        step.aquarium_height_var.set(10.0)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "500" in error_message

    def test_validation_fails_with_out_of_range_interval(self):
        """O campo de intervalo não era validado em passo nenhum.

        Um valor fora de 1..30 atravessava os cinco passos e só era recusado na
        criação do projeto, por um ``ValueError`` que o event bus engolia — o
        assistente fechava sem criar nada e sem dizer por quê.
        """
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.set(10.0)
        step.analysis_interval_var.set(60)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "30" in error_message

    def test_on_show_restores_from_wizard_data(self):
        """on_show should restore values from wizard_data."""
        wizard_data = {
            "num_aquariums": 8,
            "animals_per_aquarium": 4,
            "aquarium_width_cm": 35.0,
            "aquarium_height_cm": 28.0,
        }

        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        # Verify values loaded from wizard_data
        assert step.num_aquariums_var.get() == 8
        assert step.animals_per_aquarium_var.get() == 4
        assert step.aquarium_width_var.get() == 35.0
        assert step.aquarium_height_var.get() == 28.0

    def test_on_show_auto_detects_video_count(self):
        """on_show should auto-set num_aquariums from video_count if not already set."""
        wizard_data = {
            "video_count": 5,
        }

        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Default is 1 before on_show
        assert step.num_aquariums_var.get() == 1

        step.on_show()

        # Should auto-detect from video_count
        assert step.num_aquariums_var.get() == 5

    def test_on_show_does_not_override_user_modified_aquariums(self):
        """on_show should not override num_aquariums if user already modified it."""
        wizard_data = {
            "video_count": 10,
        }

        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # User already set to different value
        step.num_aquariums_var.set(3)

        step.on_show()

        # Should keep user's value (3), not auto-set to video_count (10)
        # Note: Current implementation only auto-sets if current value is 1
        # and video_count > 1, so this should remain 3
        assert step.num_aquariums_var.get() == 3

    def test_template_banner_display_when_metadata_present(self):
        """Template banner should be displayed when template_metadata is present."""
        wizard_data = {
            "template_metadata": {
                "name": "Template de Teste",
                "path": "/path/to/template.json",
            },
        }

        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Template info should be set
        banner_text = step.template_info_var.get()
        assert "Template loaded" in banner_text

    def test_template_banner_hidden_when_no_metadata(self):
        """Template banner should be hidden when no template_metadata."""
        wizard_data: dict[str, Any] = {}

        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Template info should be empty
        banner_text = step.template_info_var.get()
        assert banner_text == ""

    @pytest.mark.parametrize(
        "num_aquariums,animals,width,height,expected_valid",
        [
            (1, 1, 10.0, 10.0, True),  # Minimum valid
            (100, 50, 100.0, 80.0, True),  # Large valid values
            (1, 1, 0.1, 0.1, True),  # Very small but positive
            (1, 1, 5.5, 7.2, True),  # Decimal dimensions
            (-1, 1, 10.0, 10.0, False),  # Negative aquariums
            (1, -5, 10.0, 10.0, False),  # Negative animals
            (1, 1, 0.0, 10.0, True),  # Zero width = sem calibração (válido)
            (1, 1, 10.0, -1.0, False),  # Negative height
        ],
    )
    def test_validation_boundary_conditions(
        self, num_aquariums, animals, width, height, expected_valid
    ):
        """Test validation with various boundary conditions."""
        wizard_data: dict[str, Any] = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(num_aquariums)
        step.animals_per_aquarium_var.set(animals)
        step.aquarium_width_var.set(width)
        step.aquarium_height_var.set(height)

        is_valid, _ = step.validate()

        assert is_valid == expected_valid

    # ------------------------------------------------------------------
    # Intervals consolidated here (moved out of LiveConfigStep)
    # ------------------------------------------------------------------

    def test_get_data_includes_intervals_for_pre_recorded_project(self):
        """Pre-recorded projects must emit intervals from CalibrationStep."""
        wizard_data: dict[str, Any] = {}  # no project_type → defaults to pre-recorded
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.analysis_interval_var.set(7)
        step.display_interval_var.set(12)

        data = step.get_data()

        assert data["analysis_interval_frames"] == 7
        assert data["display_interval_frames"] == 12

    def test_get_data_includes_intervals_for_live_project(self):
        """Live projects must also emit intervals from CalibrationStep now —
        previously the keys were skipped because the live wizard collected
        them in a different step."""
        from zebtrack.ui.wizard.enums import ProjectType

        wizard_data: dict[str, Any] = {"project_type": ProjectType.LIVE.value}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.analysis_interval_var.set(20)
        step.display_interval_var.set(30)

        data = step.get_data()

        assert data["analysis_interval_frames"] == 20
        assert data["display_interval_frames"] == 30

    def test_on_show_picks_live_default_10_when_no_wizard_value(self):
        """A fresh live wizard run lands on 10/10 (was the LiveConfigStep
        default before consolidation, preserved here)."""
        from zebtrack.ui.wizard.enums import ProjectType

        wizard_data: dict[str, Any] = {"project_type": ProjectType.LIVE.value}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert step.analysis_interval_var.get() == 10
        assert step.display_interval_var.get() == 10

    def test_on_show_keeps_pre_recorded_default_5(self):
        wizard_data: dict[str, Any] = {}  # default project type = pre-recorded
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert step.analysis_interval_var.get() == 5
        assert step.display_interval_var.get() == 5

    def test_on_show_persisted_intervals_override_live_default(self):
        """Back-navigation: if the user already picked 17, on_show must respect
        that even on a live project (it would otherwise reset to 10)."""
        from zebtrack.ui.wizard.enums import ProjectType

        wizard_data: dict[str, Any] = {
            "project_type": ProjectType.LIVE.value,
            "analysis_interval_frames": 17,
            "display_interval_frames": 23,
        }
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()

        assert step.analysis_interval_var.get() == 17
        assert step.display_interval_var.get() == 23


@pytest.mark.gui
class TestCalibrationStepBarnesProfile:
    """ADR-014: with the Barnes protocol one "Table diameter" replaces width and height."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]

    def _step(self, wizard_data: dict[str, Any]) -> CalibrationStep:
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()
        step.on_show()
        self.root.update()
        return step

    @staticmethod
    def _barnes_data(**extra: Any) -> dict[str, Any]:
        return {
            "behavioral_analysis": {"animal_model": "rodent", "protocol": "barnes"},
            **extra,
        }

    def test_a_generic_project_shows_width_and_height_only(self):
        step = self._step({})

        assert _need(step._width_row).winfo_manager()
        assert _need(step._height_row).winfo_manager()
        assert not _need(step._table_row).winfo_manager()
        assert str(_need(step._analysis_entry).cget("state")) == "normal"

    def test_barnes_replaces_width_and_height_by_the_table_diameter(self):
        step = self._step(self._barnes_data())

        assert _need(step._table_row).winfo_manager()
        assert not _need(step._width_row).winfo_manager()
        assert not _need(step._height_row).winfo_manager()

    def test_the_diameter_defaults_to_the_labs_table(self):
        step = self._step(self._barnes_data())

        assert step.table_diameter_var.get() == 184.0

    def test_the_diameter_writes_both_persisted_keys_and_the_protocol_parameter(self):
        step = self._step(self._barnes_data())
        step.table_diameter_var.set(150.0)

        data = step.get_data()

        assert data["aquarium_width_cm"] == 150.0
        assert data["aquarium_height_cm"] == 150.0
        assert data["behavioral_analysis"]["protocol_params"] == {
            "barnes": {"table_diameter_cm": 150.0}
        }

    def test_a_declared_diameter_comes_back_when_the_step_is_shown_again(self):
        step = self._step(
            {
                "behavioral_analysis": {
                    "protocol": "barnes",
                    "protocol_params": {"barnes": {"table_diameter_cm": 150.0}},
                }
            }
        )

        assert step.table_diameter_var.get() == 150.0

    def test_the_old_generic_width_does_not_leak_into_the_diameter(self):
        step = self._step(self._barnes_data(aquarium_width_cm=10.0, aquarium_height_cm=10.0))

        assert step.table_diameter_var.get() == 184.0

    def test_the_analysis_interval_is_pinned_to_every_frame(self):
        step = self._step(self._barnes_data(analysis_interval_frames=10))

        assert step.analysis_interval_var.get() == 1
        assert step.get_data()["analysis_interval_frames"] == 1
        assert str(_need(step._analysis_entry).cget("state")) == "disabled"

    def test_the_view_is_locked_to_top_down(self):
        step = self._step(self._barnes_data())

        values = step.get_data()["behavioral_analysis"]
        assert values["aquarium_perspective"] == "top_down"
        assert values["animal_model"] == "rodent"
        assert values["protocol"] == "barnes"

    def test_a_zero_diameter_is_refused(self):
        step = self._step(self._barnes_data())
        step.table_diameter_var.set(0.0)

        valid, message = step.validate()

        assert valid is False
        assert "greater than zero" in message

    def test_a_valid_diameter_passes(self):
        step = self._step(self._barnes_data())

        assert step.validate() == (True, "")

    def test_a_generic_project_still_writes_no_protocol_parameters(self):
        step = self._step({})

        data = step.get_data()

        assert "protocol_params" not in data["behavioral_analysis"]
        assert data["behavioral_analysis"]["protocol"] == "generic"
        assert data["aquarium_width_cm"] == 10.0

    def test_going_back_to_generic_brings_width_and_height_back(self):
        wizard_data = self._barnes_data()
        step = self._step(wizard_data)

        wizard_data["behavioral_analysis"] = {"animal_model": "zebrafish", "protocol": "generic"}
        step.on_show()
        self.root.update()

        assert _need(step._width_row).winfo_manager()
        assert not _need(step._table_row).winfo_manager()
        assert str(_need(step._analysis_entry).cget("state")) == "normal"

    def test_the_widget_does_not_ask_the_profile_again(self):
        step = self._step(self._barnes_data())

        assert _need(step.behavioral_config_widget).animal_model_combo is None
        assert _need(step.behavioral_config_widget).protocol_combo is None

    def test_set_data_restores_the_barnes_layout(self):
        step = self._step({})

        step.set_data(
            {
                "behavioral_analysis": {
                    "protocol": "barnes",
                    "protocol_params": {"barnes": {"table_diameter_cm": 120.0}},
                }
            }
        )

        assert _need(step._table_row).winfo_manager()
        assert step.table_diameter_var.get() == 120.0


@pytest.mark.gui
class TestWizardProfileEndToEnd:
    """Discovery -> Calibration: the persisted thresholds follow the animal model."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        self.root = wizard_dependencies["root"]
        self.wizard_data: dict[str, Any] = {}
        self.calibration = CalibrationStep(self.root, self.wizard_data)
        self.calibration.build_ui()

    def _run(self, animal: str, protocol: str) -> dict[str, Any]:
        """One pass through the wizard: Discovery picks, Calibration shows and is read."""
        from zebtrack.ui.components.behavioral_config_widget import (
            animal_model_choices,
            protocol_choices,
        )
        from zebtrack.ui.wizard.discovery_step import DiscoveryStep

        discovery = DiscoveryStep(self.root, self.wizard_data)
        discovery.build_ui()
        discovery.set_data({"behavioral_analysis": self.wizard_data.get("behavioral_analysis", {})})
        for combo, choices, token in (
            # Protocol first, as in the UI: Barnes keeps the animal combo locked until left.
            (discovery.protocol_combo, protocol_choices(), protocol),
            (discovery.animal_model_combo, animal_model_choices(), animal),
        ):
            _need(combo).set(next(label for label, value in choices if value == token))
            _need(combo).event_generate("<<ComboboxSelected>>")
        self.wizard_data.update(discovery.get_data())

        self.calibration.on_show()
        self.root.update()
        data = self.calibration.get_data()
        self.wizard_data.update(data)
        return data

    def _baseline(self) -> tuple[float, float]:
        widget = _need(self.calibration.behavioral_config_widget)
        return widget._default_thigmotaxis_cm, widget._default_max_speed_cm_s

    def test_a_rodent_chosen_in_discovery_persists_the_rodent_thresholds(self):
        block = self._run("rodent", "generic")["behavioral_analysis"]

        assert block["animal_model"] == "rodent"
        assert block["thigmotaxis_distance_cm"] == 15.0
        assert block["max_plausible_speed_cm_s"] == 100.0

    def test_barnes_chosen_in_discovery_persists_the_rodent_thresholds(self):
        block = self._run("zebrafish", "barnes")["behavioral_analysis"]

        assert block["protocol"] == "barnes"
        assert block["thigmotaxis_distance_cm"] == 15.0
        assert block["max_plausible_speed_cm_s"] == 100.0

    def test_barnes_and_then_back_to_zebrafish_persists_the_zebrafish_thresholds(self):
        self._run("zebrafish", "barnes")

        block = self._run("zebrafish", "generic")["behavioral_analysis"]

        thigmotaxis, speed = self._baseline()
        assert block["animal_model"] == "zebrafish"
        assert block["thigmotaxis_distance_cm"] == thigmotaxis
        assert block["max_plausible_speed_cm_s"] == speed

    def test_numbers_the_user_set_for_the_same_animal_survive_a_second_pass(self):
        self._run("rodent", "generic")
        self.wizard_data["behavioral_analysis"]["max_plausible_speed_cm_s"] = 120.0

        block = self._run("rodent", "generic")["behavioral_analysis"]

        assert block["max_plausible_speed_cm_s"] == 120.0

    def test_leaving_barnes_gives_the_previous_interval_back(self):
        self.wizard_data["analysis_interval_frames"] = 7
        assert self._run("zebrafish", "barnes")["analysis_interval_frames"] == 1

        restored = self._run("zebrafish", "generic")

        assert restored["analysis_interval_frames"] == 7
        assert str(_need(self.calibration._analysis_entry).cget("state")) == "normal"

    def test_staying_in_barnes_across_passes_keeps_the_remembered_interval(self):
        self.wizard_data["analysis_interval_frames"] = 7
        self._run("zebrafish", "barnes")
        self._run("zebrafish", "barnes")

        assert self._run("zebrafish", "generic")["analysis_interval_frames"] == 7

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

import pytest

from zebtrack.ui.wizard.calibration_step import CalibrationStep
from zebtrack.ui.wizard.enums import WizardStepID


@pytest.mark.gui
class TestCalibrationStep:
    """Tests for calibration step."""

    @pytest.fixture(autouse=True)
    def setup(self, wizard_dependencies):
        """Create Tkinter root for testing."""
        self.root = wizard_dependencies["root"]

    def test_calibration_step_builds_ui_without_error(self):
        """Calibration step should build UI without errors."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Should have step_id set
        assert step.step_id == WizardStepID.CALIBRATION

    def test_calibration_step_default_values(self):
        """Calibration step should have sensible default values."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        # Default values
        assert step.num_aquariums_var.get() == 1
        assert step.animals_per_aquarium_var.get() == 1
        assert step.aquarium_width_var.get() == 10.0
        assert step.aquarium_height_var.get() == 10.0

    def test_calibration_step_get_data(self):
        """get_data should return complete calibration data."""
        wizard_data = {}
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
        wizard_data = {}
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
        wizard_data = {}
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
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(0)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.get()  # Keep default

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "aquários" in error_message.lower() or "pelo menos 1" in error_message.lower()

    def test_validation_fails_with_zero_animals(self):
        """Validation should fail when animals_per_aquarium is 0."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(0)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.get()  # Keep default

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "animais" in error_message.lower() or "pelo menos 1" in error_message.lower()

    def test_validation_fails_with_negative_dimensions(self):
        """Validation should fail with negative dimensions."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(-5.0)
        step.aquarium_height_var.set(10.0)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "largura" in error_message.lower() or "positiv" in error_message.lower()

    def test_validation_fails_with_zero_height(self):
        """Validation should fail when height is zero."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(1)
        step.animals_per_aquarium_var.set(1)
        step.aquarium_width_var.set(10.0)
        step.aquarium_height_var.set(0.0)

        is_valid, error_message = step.validate()

        assert not is_valid
        assert "altura" in error_message.lower() or "maior que zero" in error_message.lower()

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
        assert "Template carregado" in banner_text or "Template" in banner_text

    def test_template_banner_hidden_when_no_metadata(self):
        """Template banner should be hidden when no template_metadata."""
        wizard_data = {}

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
            (1, 1, 0.0, 10.0, False),  # Zero width
            (1, 1, 10.0, -1.0, False),  # Negative height
        ],
    )
    def test_validation_boundary_conditions(
        self, num_aquariums, animals, width, height, expected_valid
    ):
        """Test validation with various boundary conditions."""
        wizard_data = {}
        step = CalibrationStep(self.root, wizard_data)
        step.build_ui()

        step.num_aquariums_var.set(num_aquariums)
        step.animals_per_aquarium_var.set(animals)
        step.aquarium_width_var.set(width)
        step.aquarium_height_var.set(height)

        is_valid, _ = step.validate()

        assert is_valid == expected_valid

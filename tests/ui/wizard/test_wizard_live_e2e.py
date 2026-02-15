"""
End-to-end tests for the live project wizard flow - Service Integration.

Tests the critical integration points of the live project wizard:
- WizardService validation methods
- Pydantic models for type-safe data validation
- Cross-field validation logic
- Data flow integrity

This test suite focuses on service layer integration rather than UI implementation details.
Phase 4 wizard improvements (v2.0).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from zebtrack.core.wizard_service import WizardService
from zebtrack.ui.wizard.models import (
    CalibrationData,
    ExperimentalDesignData,
    LiveConfigData,
)


class TestWizardServiceIntegration:
    """Test WizardService validation and Pydantic model integration."""

    def test_live_config_validation_valid_basic(self):
        """Test LiveConfigData validates with minimal required fields."""
        data: dict[str, Any] = {
            "camera_index": 0,
            "use_arduino": False,
            "arduino_port": "",
            "external_trigger_mode": False,
        }

        # Validate through service
        is_valid, error = WizardService.validate_live_config(data)
        assert is_valid, f"Validation failed: {error}"

        # Validate through Pydantic
        validated = LiveConfigData(**data)
        assert validated.camera_index == 0
        assert not validated.use_arduino

    def test_live_config_validation_with_arduino(self):
        """Test LiveConfigData validates correctly with Arduino enabled."""
        data: dict[str, Any] = {
            "camera_index": 0,
            "use_arduino": True,
            "arduino_port": "COM3",
            "external_trigger_mode": False,
        }

        is_valid, _error = WizardService.validate_live_config(data)
        assert is_valid

        validated = LiveConfigData(**data)
        assert validated.use_arduino
        assert validated.arduino_port == "COM3"

    def test_live_config_validation_external_trigger_requires_arduino(self):
        """Test that external trigger mode requires Arduino to be enabled."""
        data: dict[str, Any] = {
            "camera_index": 0,
            "use_arduino": False,
            "arduino_port": "",
            "external_trigger_mode": True,  # Invalid: trigger without Arduino
        }

        # Should fail service validation
        is_valid, error = WizardService.validate_live_config(data)
        assert not is_valid
        assert "Arduino" in error or "trigger" in error.lower()

        # Should fail Pydantic validation
        with pytest.raises(ValidationError) as exc_info:
            LiveConfigData(**data)
        assert "Arduino" in str(exc_info.value) or "trigger" in str(exc_info.value).lower()

    def test_live_config_validation_arduino_requires_port(self):
        """Test that Arduino enabled requires a port to be specified."""
        data: dict[str, Any] = {
            "camera_index": 0,
            "use_arduino": True,
            "arduino_port": "",  # Invalid: Arduino enabled but no port
            "external_trigger_mode": False,
        }

        is_valid, error = WizardService.validate_live_config(data)
        assert not is_valid
        assert "porta" in error.lower() or "port" in error.lower()

    def test_live_config_validation_invalid_camera_index(self):
        """Test that camera index must be within valid range."""
        data: dict[str, Any] = {
            "camera_index": -1,  # Invalid: negative index
            "use_arduino": False,
            "arduino_port": "",
            "external_trigger_mode": False,
        }

        is_valid, _error = WizardService.validate_live_config(data)
        assert not is_valid

    def test_experimental_design_validation_valid(self):
        """Test ExperimentalDesignData validates with correct data."""
        data: dict[str, Any] = {
            "experiment_days": 7,
            "num_groups": 2,
            "subjects_per_group": 5,
            "group_names": ["Control", "Treatment"],
        }

        # Validate through service
        is_valid, error = WizardService.validate_experimental_design(data)
        assert is_valid, f"Validation failed: {error}"

        # Validate through Pydantic
        validated = ExperimentalDesignData(**data)
        assert validated.experiment_days == 7
        assert validated.num_groups == 2
        assert validated.subjects_per_group == 5
        assert len(validated.group_names) == 2

    def test_experimental_design_validation_group_count_mismatch(self):
        """Test that number of group names must match num_groups."""
        data: dict[str, Any] = {
            "experiment_days": 7,
            "num_groups": 3,
            "subjects_per_group": 5,
            "group_names": ["Control", "Treatment"],  # Only 2 names for 3 groups
        }

        # Should fail service validation
        is_valid, _error = WizardService.validate_experimental_design(data)
        assert not is_valid

        # Should fail Pydantic validation
        with pytest.raises(ValidationError):
            ExperimentalDesignData(**data)

    def test_experimental_design_validation_empty_group_name(self):
        """Test that group names cannot be empty."""
        data: dict[str, Any] = {
            "experiment_days": 5,
            "num_groups": 2,
            "subjects_per_group": 4,
            "group_names": ["Control", ""],  # Empty name
        }

        is_valid, _error = WizardService.validate_experimental_design(data)
        assert not is_valid

    def test_experimental_design_validation_duplicate_group_names(self):
        """Test that group names must be unique."""
        data: dict[str, Any] = {
            "experiment_days": 5,
            "num_groups": 2,
            "subjects_per_group": 4,
            "group_names": ["Control", "Control"],  # Duplicate
        }

        is_valid, _error = WizardService.validate_experimental_design(data)
        assert not is_valid

        with pytest.raises(ValidationError):
            ExperimentalDesignData(**data)

    def test_experimental_design_validation_boundaries(self):
        """Test that experimental design values respect boundaries."""
        # Test minimum values
        data_min: dict[str, Any] = {
            "experiment_days": 1,
            "num_groups": 1,
            "subjects_per_group": 1,
            "group_names": ["Group1"],
        }
        is_valid, error = WizardService.validate_experimental_design(data_min)
        assert is_valid

        # Test maximum values
        data_max: dict[str, Any] = {
            "experiment_days": 365,  # Maximum is 365 days
            "num_groups": 6,
            "subjects_per_group": 20,
            "group_names": [f"Group{i}" for i in range(1, 7)],
        }
        is_valid, _error = WizardService.validate_experimental_design(data_max)
        assert is_valid

        # Test out of bounds (days > 365)
        with pytest.raises(ValidationError):
            ExperimentalDesignData(
                experiment_days=366,  # Exceeds maximum
                num_groups=2,
                subjects_per_group=5,
                group_names=["A", "B"],
            )

        # Test out of bounds (groups > 6)
        with pytest.raises(ValidationError):
            ExperimentalDesignData(
                experiment_days=10,
                num_groups=7,  # Exceeds maximum
                subjects_per_group=5,
                group_names=[f"G{i}" for i in range(7)],
            )

        # Test out of bounds (subjects > 20)
        with pytest.raises(ValidationError):
            ExperimentalDesignData(
                experiment_days=10,
                num_groups=2,
                subjects_per_group=21,  # Exceeds maximum
                group_names=["A", "B"],
            )

    def test_calibration_validation_valid(self):
        """Test CalibrationData validates with positive dimensions."""
        data: dict[str, Any] = {
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 30.0,
            "aquarium_height_cm": 20.0,
        }

        # Validate through service
        is_valid, error = WizardService.validate_basic_calibration(data)
        assert is_valid, f"Validation failed: {error}"

        # Validate through Pydantic
        validated = CalibrationData(**data)
        assert validated.num_aquariums == 1
        assert validated.animals_per_aquarium == 1
        assert validated.aquarium_width_cm == 30.0
        assert validated.aquarium_height_cm == 20.0

    def test_calibration_validation_minimal_values(self):
        """Test CalibrationData validates with minimal values."""
        data: dict[str, Any] = {
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 0.1,  # Minimum positive value
            "aquarium_height_cm": 0.1,
        }

        # Should be valid with minimal values
        validated = CalibrationData(**data)
        assert validated.num_aquariums == 1
        assert validated.animals_per_aquarium == 1

    def test_calibration_validation_negative_dimensions(self):
        """Test that negative dimensions are rejected."""
        data: dict[str, Any] = {
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": -10.0,  # Invalid: negative
            "aquarium_height_cm": 20.0,
        }

        is_valid, _error = WizardService.validate_basic_calibration(data)
        assert not is_valid

        with pytest.raises(ValidationError):
            CalibrationData(**data)

    def test_calibration_validation_zero_dimensions(self):
        """Test that zero or negative dimensions are rejected."""
        data: dict[str, Any] = {
            "num_aquariums": 1,
            "animals_per_aquarium": 1,
            "aquarium_width_cm": 0.0,  # Invalid: must be > 0
            "aquarium_height_cm": 20.0,
        }

        is_valid, _error = WizardService.validate_basic_calibration(data)
        assert not is_valid

        with pytest.raises(ValidationError):
            CalibrationData(**data)

    def test_complete_wizard_data_integration(self):
        """Test that all wizard data can be validated together."""
        # Simulate complete wizard data
        live_config_data: dict[str, Any] = {
            "camera_index": 0,
            "use_arduino": True,
            "arduino_port": "COM3",
            "external_trigger_mode": False,
        }

        design_data: dict[str, Any] = {
            "experiment_days": 14,
            "num_groups": 3,
            "subjects_per_group": 8,
            "group_names": ["Control", "Low Dose", "High Dose"],
        }

        calib_data: dict[str, Any] = {
            "num_aquariums": 1,
            "animals_per_aquarium": 8,
            "aquarium_width_cm": 28.5,
            "aquarium_height_cm": 19.2,
        }

        # Validate all parts through service
        is_valid, error = WizardService.validate_live_config(live_config_data)
        assert is_valid, f"LiveConfig validation failed: {error}"

        is_valid, error = WizardService.validate_experimental_design(design_data)
        assert is_valid, f"ExperimentalDesign validation failed: {error}"

        is_valid, error = WizardService.validate_basic_calibration(calib_data)
        assert is_valid, f"Calibration validation failed: {error}"

        # Validate all parts through Pydantic
        validated_live = LiveConfigData(**live_config_data)
        validated_design = ExperimentalDesignData(**design_data)
        validated_calib = CalibrationData(**calib_data)

        # Verify all data is correct
        assert validated_live.camera_index == 0
        assert validated_live.use_arduino
        assert validated_design.experiment_days == 14
        assert len(validated_design.group_names) == 3
        assert validated_calib.aquarium_width_cm == 28.5
        assert validated_calib.num_aquariums == 1
        assert validated_calib.animals_per_aquarium == 8

    def test_wizard_service_calculation_methods(self):
        """Test WizardService helper calculation methods."""
        # Test suggest_analysis_interval
        interval = WizardService.suggest_analysis_interval(camera_fps=30.0)
        assert isinstance(interval, int)
        assert interval > 0

        # Test calculate_experiment_structure
        structure = WizardService.calculate_experiment_structure(groups=2, days=7, subjects=5)
        # Check for actual returned fields
        assert "total_sessions" in structure
        assert "total_animals" in structure
        assert "sessions_per_day" in structure
        assert "estimated_hours" in structure

        # Verify calculations
        assert structure["total_sessions"] == 2 * 7 * 5  # groups * days * subjects
        assert structure["total_animals"] == 2 * 5  # groups * subjects
        assert structure["sessions_per_day"] == 2 * 5  # groups * subjects per day

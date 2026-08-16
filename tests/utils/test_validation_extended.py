"""Unit tests for utils/validation.py calibration validation."""

from __future__ import annotations

import pytest

from zebtrack.utils.validation import validate_calibration


class TestValidateCalibrationExtended:
    """Test validate_calibration for all edge cases."""

    def test_none_passes_without_error(self):
        validate_calibration(None)  # Should not raise

    def test_valid_positive_ratios_pass(self):
        validate_calibration((10.0, 20.0))
        validate_calibration((1, 1))
        validate_calibration((0.5, 0.5))

    def test_zero_x_ratio_raises_value_error(self):
        with pytest.raises(ValueError, match="positive"):
            validate_calibration((0.0, 5.0))

    def test_zero_y_ratio_raises_value_error(self):
        with pytest.raises(ValueError, match="positive"):
            validate_calibration((5.0, 0.0))

    def test_negative_ratio_raises_value_error(self):
        with pytest.raises(ValueError, match="positive"):
            validate_calibration((-1.0, 5.0))

    def test_infinite_ratio_raises_value_error(self):
        with pytest.raises(ValueError, match="finite"):
            validate_calibration((float("inf"), 5.0))

    def test_nan_ratio_raises_value_error(self):
        with pytest.raises(ValueError, match="finite"):
            validate_calibration((float("nan"), 5.0))

    def test_non_tuple_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_calibration([10.0, 20.0])  # type: ignore[arg-type]

    def test_tuple_wrong_length_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_calibration((10.0,))  # type: ignore[arg-type]

    def test_non_numeric_values_raise_type_error(self):
        with pytest.raises(TypeError, match="numeric"):
            validate_calibration(("a", "b"))  # type: ignore[arg-type]

"""Extended unit tests for utils/validation.py."""

from __future__ import annotations

import pytest

from zebtrack.utils.validation import validate_calibration


class TestValidationExtended:
    """Test calibration ratio validation."""

    def test_validate_calibration_none(self):
        # None is optional and should return without raising
        validate_calibration(None)

    def test_validate_calibration_valid_tuple(self):
        validate_calibration((10.5, 10.5))
        validate_calibration((1, 2))

    def test_validate_calibration_invalid_type_not_tuple(self):
        with pytest.raises(TypeError, match="must be a tuple of two floats or None"):
            validate_calibration([10.0, 10.0])  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="must be a tuple of two floats or None"):
            validate_calibration((10.0,))  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="must be a tuple of two floats or None"):
            validate_calibration((10.0, 10.0, 10.0))  # type: ignore[arg-type]

    def test_validate_calibration_non_numeric_elements(self):
        with pytest.raises(TypeError, match="Calibration ratios must be numeric"):
            validate_calibration(("10.0", 10.0))  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="Calibration ratios must be numeric"):
            validate_calibration((10.0, None))  # type: ignore[arg-type]

    def test_validate_calibration_infinite_or_nan(self):
        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((float("nan"), 10.0))

        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((10.0, float("inf")))

        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((float("-inf"), 10.0))

    def test_validate_calibration_non_positive(self):
        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((0.0, 10.0))

        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((-1.5, 10.0))

        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((10.0, -0.01))

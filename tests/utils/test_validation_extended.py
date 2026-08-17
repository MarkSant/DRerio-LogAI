"""Extended unit tests for utils/validation.py."""

from __future__ import annotations

import pytest

from zebtrack.utils.validation import validate_calibration


class TestValidationExtended:
    """Test calibration ratio validation."""

    def test_validate_calibration_none(self):
        # None is optional and allowed
        validate_calibration(None)

    def test_validate_calibration_valid(self):
        validate_calibration((10.0, 10.0))
        validate_calibration((15, 20))

    def test_validate_calibration_not_tuple_or_wrong_len(self):
        with pytest.raises(TypeError, match="must be a tuple of two floats"):
            validate_calibration([10.0, 10.0])  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be a tuple of two floats"):
            validate_calibration((10.0,))  # type: ignore[arg-type]

    def test_validate_calibration_non_numeric(self):
        with pytest.raises(TypeError, match="must be numeric"):
            validate_calibration(("10", 10.0))  # type: ignore[arg-type]

    def test_validate_calibration_non_finite(self):
        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((float("nan"), 10.0))
        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((10.0, float("inf")))

    def test_validate_calibration_non_positive(self):
        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((0.0, 10.0))
        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((-5.0, 10.0))

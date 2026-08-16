"""
Extended unit tests for validation utility functions.
"""

from __future__ import annotations

import pytest

from zebtrack.utils.validation import validate_calibration


class TestValidationExtended:
    """Test validate_calibration parameter constraints."""

    def test_validate_calibration_none_passes(self):
        validate_calibration(None)  # Should not raise

    def test_validate_calibration_non_tuple_raises(self):
        with pytest.raises(TypeError, match="must be a tuple"):
            validate_calibration([10.0, 10.0])  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="must be a tuple of two"):
            validate_calibration((10.0, 10.0, 10.0))  # type: ignore[arg-type]

    def test_validate_calibration_non_numeric_raises(self):
        with pytest.raises(TypeError, match="must be numeric"):
            validate_calibration(("10", 10.0))  # type: ignore[arg-type]

    def test_validate_calibration_non_finite_raises(self):
        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((float("nan"), 10.0))

        with pytest.raises(ValueError, match="must be finite"):
            validate_calibration((10.0, float("inf")))

    def test_validate_calibration_non_positive_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((0.0, 10.0))

        with pytest.raises(ValueError, match="must be positive"):
            validate_calibration((10.0, -5.0))

    def test_validate_calibration_valid_passes(self):
        validate_calibration((10.0, 10.0))  # Should not raise
        validate_calibration((15, 20))  # Should not raise

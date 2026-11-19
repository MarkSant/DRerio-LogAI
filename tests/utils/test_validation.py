"""Extended unit tests for utils/validation.py."""

from __future__ import annotations

from typing import Any, cast

import pytest

from zebtrack.utils.validation import validate_calibration


def test_valid_calibration():
    """Tests that a valid calibration tuple passes without exception."""
    validate_calibration((1.5, 2.0))  # Should pass


def test_none_calibration():
    """Tests that None is accepted, as calibration is optional."""
    validate_calibration(None)  # Should pass


def test_zero_ratio():
    """Tests that a zero value in the ratio raises a ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        validate_calibration((0, 1))
    with pytest.raises(ValueError, match="must be positive"):
        validate_calibration((1, 0))


def test_negative_ratio():
    """Tests that a negative value in the ratio raises a ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        validate_calibration((1.5, -2.0))
    with pytest.raises(ValueError, match="must be positive"):
        validate_calibration((-1.5, 2.0))


def test_nan_ratio():
    """Tests that a NaN value in the ratio raises a ValueError."""
    with pytest.raises(ValueError, match="must be finite"):
        validate_calibration((float("nan"), 1.0))
    with pytest.raises(ValueError, match="must be finite"):
        validate_calibration((1.0, float("nan")))


def test_inf_ratio():
    """Tests that an infinite value in the ratio raises a ValueError."""
    with pytest.raises(ValueError, match="must be finite"):
        validate_calibration((float("inf"), 1.0))
    with pytest.raises(ValueError, match="must be finite"):
        validate_calibration((1.0, float("inf")))


def test_non_numeric_ratio():
    """Tests that a non-numeric value in the ratio raises a TypeError."""
    with pytest.raises(TypeError, match="must be numeric"):
        validate_calibration(cast(Any, ("1.5", 2.0)))
    with pytest.raises(TypeError, match="must be numeric"):
        validate_calibration(cast(Any, (1.5, "2.0")))


def test_invalid_type():
    """Tests that incorrect types for the main argument raise a TypeError."""
    with pytest.raises(TypeError, match="must be a tuple"):
        validate_calibration(cast(Any, [1.5, 2.0]))  # List instead of tuple
    with pytest.raises(TypeError, match="must be a tuple"):
        validate_calibration(cast(Any, (1.5,)))  # Tuple with single element
    with pytest.raises(TypeError, match="must be a tuple"):
        validate_calibration(cast(Any, 1.5))  # Just a float


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

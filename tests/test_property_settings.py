"""Property-based tests for settings module (Pydantic validation).

Tests Pydantic model validators and utility functions using Hypothesis
to discover edge cases in configuration validation.

Marker: @pytest.mark.property
Run with: poetry run pytest -m property tests/test_property_settings.py
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from zebtrack.settings import (
    AngularVelocitySettings,
    CameraSettings,
    TrajectorySmoothingSettings,
    YOLOModelSettings,
    _deep_merge_dicts,
)

# =============================================================================
# STRATEGIES
# =============================================================================

valid_inference_size = st.integers(min_value=320, max_value=1280).filter(lambda x: x % 32 == 0)
invalid_inference_size = st.integers(min_value=1, max_value=1280).filter(lambda x: x % 32 != 0)
odd_integer = st.integers(min_value=3, max_value=99).filter(lambda x: x % 2 == 1)
even_integer = st.integers(min_value=2, max_value=100).filter(lambda x: x % 2 == 0)

# Dict strategies for _deep_merge_dicts
simple_value = st.one_of(st.integers(), st.text(max_size=20), st.booleans(), st.none())
flat_dict = st.dictionaries(st.text(min_size=1, max_size=5), simple_value, max_size=5)


def nested_dict_strategy(max_depth: int = 2) -> st.SearchStrategy:
    """Generate nested dicts suitable for _deep_merge_dicts testing."""
    if max_depth <= 0:
        return flat_dict
    leaf = st.one_of(simple_value, flat_dict)
    return st.dictionaries(st.text(min_size=1, max_size=5), leaf, max_size=4)


# =============================================================================
# YOLO MODEL SETTINGS
# =============================================================================


@pytest.mark.property
class TestYOLOModelSettingsProperties:
    """Property tests for YOLO inference size validation."""

    # Required fields for a valid YOLOModelSettings instance
    _YOLO_DEFAULTS: ClassVar[dict[str, Any]] = {
        "path": "best_oi.pt",
        "confidence_threshold": 0.5,
        "nms_threshold": 0.4,
    }

    @given(size=valid_inference_size)
    @h_settings(max_examples=50, database=None)
    def test_valid_inference_size_passes(self, size: int) -> None:
        """Valid sizes (divisible by 32) should create model successfully."""
        model = YOLOModelSettings(**self._YOLO_DEFAULTS, inference_size=size)
        assert model.inference_size == size
        assert model.inference_size % 32 == 0

    @given(size=invalid_inference_size)
    @h_settings(max_examples=50, database=None)
    def test_invalid_inference_size_rejected(self, size: int) -> None:
        """Sizes not divisible by 32 must raise ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            YOLOModelSettings(**self._YOLO_DEFAULTS, inference_size=size)

    @given(size=valid_inference_size)
    @h_settings(
        max_examples=30,
        database=None,
        suppress_health_check=[HealthCheck.filter_too_much],
    )
    def test_round_trip(self, size: int) -> None:
        """Model should survive dump/load round-trip."""
        model = YOLOModelSettings(**self._YOLO_DEFAULTS, inference_size=size)
        data = model.model_dump()
        restored = YOLOModelSettings(**data)
        assert restored.inference_size == model.inference_size


# =============================================================================
# TRAJECTORY SMOOTHING SETTINGS
# =============================================================================


@pytest.mark.property
class TestTrajectorySmoothingProperties:
    """Property tests for trajectory smoothing validation."""

    @given(window=odd_integer)
    @h_settings(max_examples=50, database=None)
    def test_odd_window_accepted(self, window: int) -> None:
        """Odd window lengths should pass validation."""
        model = TrajectorySmoothingSettings(window_length=window, polyorder=min(2, window - 1))
        assert model.window_length % 2 == 1

    @given(window=even_integer)
    @h_settings(max_examples=50, database=None)
    def test_even_window_rejected(self, window: int) -> None:
        """Even window lengths must be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TrajectorySmoothingSettings(window_length=window, polyorder=1)

    @given(
        window=odd_integer.filter(lambda x: x >= 5),
    )
    @h_settings(max_examples=30, database=None)
    def test_polyorder_less_than_window(self, window: int) -> None:
        """polyorder must always be < window_length after validation."""
        polyorder = min(3, window - 1)
        model = TrajectorySmoothingSettings(window_length=window, polyorder=polyorder)
        assert model.polyorder < model.window_length


# =============================================================================
# ANGULAR VELOCITY SETTINGS
# =============================================================================


@pytest.mark.property
class TestAngularVelocityProperties:
    """Property tests for angular velocity smoothing window."""

    @given(window=odd_integer)
    @h_settings(max_examples=30, database=None)
    def test_odd_smoothing_window_accepted(self, window: int) -> None:
        """Odd smoothing windows should be accepted."""
        model = AngularVelocitySettings(angular_velocity_smoothing_window=window)
        assert model.angular_velocity_smoothing_window % 2 == 1

    @given(window=even_integer.filter(lambda x: x > 1))
    @h_settings(max_examples=30, database=None)
    def test_even_smoothing_window_rejected(self, window: int) -> None:
        """Even smoothing windows (> 1) must be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AngularVelocitySettings(angular_velocity_smoothing_window=window)

    def test_window_of_one_always_accepted(self) -> None:
        """Window of 1 is a special case that should always be accepted."""
        model = AngularVelocitySettings(angular_velocity_smoothing_window=1)
        assert model.angular_velocity_smoothing_window == 1


# =============================================================================
# CAMERA SETTINGS ROUND-TRIP
# =============================================================================


@pytest.mark.property
class TestCameraSettingsProperties:
    """Property tests for camera settings roundtrip."""

    @given(
        index=st.integers(min_value=0, max_value=10),
        width=st.integers(min_value=1, max_value=7680),
        height=st.integers(min_value=1, max_value=4320),
    )
    @h_settings(max_examples=30, database=None)
    def test_camera_round_trip(self, index: int, width: int, height: int) -> None:
        """Camera settings should survive dump/load round-trip."""
        model = CameraSettings(index=index, desired_width=width, desired_height=height)
        data = model.model_dump()
        restored = CameraSettings(**data)
        assert restored.index == model.index
        assert restored.desired_width == model.desired_width
        assert restored.desired_height == model.desired_height


# =============================================================================
# _deep_merge_dicts ALGEBRAIC PROPERTIES
# =============================================================================


@pytest.mark.property
class TestDeepMergeDictsProperties:
    """Property tests for _deep_merge_dicts utility."""

    @given(d=flat_dict)
    @h_settings(max_examples=50, database=None)
    def test_identity_element(self, d: dict) -> None:
        """Merging with empty dict should return equivalent to original."""
        result = _deep_merge_dicts(d, {})
        assert result == d

    @given(d=flat_dict)
    @h_settings(max_examples=50, database=None)
    def test_empty_base_returns_override(self, d: dict) -> None:
        """Merging empty base with override gives the override."""
        result = _deep_merge_dicts({}, d)
        assert result == d

    @given(base=flat_dict, override=flat_dict)
    @h_settings(max_examples=50, database=None)
    def test_override_keys_present(self, base: dict, override: dict) -> None:
        """All override keys must appear in the result."""
        result = _deep_merge_dicts(base, override)
        for key in override:
            assert key in result
            # Non-dict override values should dominate
            if not isinstance(override[key], dict):
                assert result[key] == override[key]

    @given(base=flat_dict, override=flat_dict)
    @h_settings(max_examples=50, database=None)
    def test_base_keys_preserved(self, base: dict, override: dict) -> None:
        """Base keys not in override must be preserved."""
        result = _deep_merge_dicts(base, override)
        for key in base:
            assert key in result

    @given(d=flat_dict)
    @h_settings(max_examples=30, database=None)
    def test_self_merge_idempotent(self, d: dict) -> None:
        """Merging a dict with itself should equal itself (for flat dicts)."""
        result = _deep_merge_dicts(d, d)
        assert result == d

"""Unit tests for coordinators/processing_types.py."""

from __future__ import annotations

import pytest

from zebtrack.coordinators.processing_types import (
    ProcessingCoordinatorError,
    ValidationResult,
)


class TestValidationResult:
    """Test ValidationResult dataclass factory methods and fields."""

    def test_success_is_valid(self):
        result = ValidationResult.success()
        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None
        assert result.context == {}

    def test_failure_stores_fields(self):
        result = ValidationResult.failure(
            error_code="NO_PROJECT",
            error_message="No project loaded",
            context={"current_state": "idle"},
        )
        assert result.is_valid is False
        assert result.error_code == "NO_PROJECT"
        assert result.error_message == "No project loaded"
        assert result.context == {"current_state": "idle"}

    def test_failure_default_context(self):
        result = ValidationResult.failure("ERR", "msg")
        assert result.context == {}

    def test_failure_none_context_defaults_to_empty(self):
        result = ValidationResult.failure("ERR", "msg", context=None)
        assert result.context == {}

    def test_direct_construction(self):
        result = ValidationResult(
            is_valid=True,
            error_code="ignored",
            error_message=None,
            context={"key": "val"},
        )
        assert result.is_valid is True
        assert result.error_code == "ignored"


class TestProcessingCoordinatorError:
    """Test ProcessingCoordinatorError exception class."""

    def test_is_exception(self):
        err = ProcessingCoordinatorError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"

    def test_default_context_is_empty_dict(self):
        err = ProcessingCoordinatorError("fail")
        assert err.context == {}

    def test_context_stored_correctly(self):
        ctx = {"video_path": "/tmp/v.mp4", "frame": 42}
        err = ProcessingCoordinatorError("fail", context=ctx)
        assert err.context == ctx

    def test_can_be_raised_and_caught(self):
        with pytest.raises(ProcessingCoordinatorError, match="kaboom"):
            raise ProcessingCoordinatorError("kaboom", context={"reason": "test"})

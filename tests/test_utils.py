"""Tests for zebtrack.utils module."""

import random

import numpy as np
import pytest

from zebtrack.utils import (
    IntegrityError,
    calculate_sha256,
    set_seed,
)


class TestIntegrityError:
    """Tests for IntegrityError exception."""

    def test_integrity_error_is_exception(self):
        """IntegrityError should be an Exception subclass."""
        assert issubclass(IntegrityError, Exception)

    def test_integrity_error_can_be_raised(self):
        """IntegrityError should be raisable with a message."""
        with pytest.raises(IntegrityError, match="test message"):
            raise IntegrityError("test message")


class TestCalculateSHA256:
    """Tests for calculate_sha256 function."""

    def test_calculate_sha256_returns_correct_hash(self, tmp_path):
        """calculate_sha256 should return correct SHA256 hash."""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        # Expected hash for "Hello, World!"
        expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"

        result = calculate_sha256(test_file)
        assert result == expected_hash

    def test_calculate_sha256_accepts_string_path(self, tmp_path):
        """calculate_sha256 should accept string paths."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = calculate_sha256(str(test_file))
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest length

    def test_calculate_sha256_accepts_path_object(self, tmp_path):
        """calculate_sha256 should accept Path objects."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = calculate_sha256(test_file)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_calculate_sha256_handles_nonexistent_file(self, tmp_path):
        """calculate_sha256 should return empty string for nonexistent files."""
        nonexistent = tmp_path / "does_not_exist.txt"

        result = calculate_sha256(nonexistent)
        assert result == ""

    def test_calculate_sha256_handles_large_file(self, tmp_path):
        """calculate_sha256 should handle files larger than chunk size."""
        test_file = tmp_path / "large.txt"
        # Create file larger than 4096 bytes (chunk size)
        test_file.write_bytes(b"x" * 10000)

        result = calculate_sha256(test_file)
        assert isinstance(result, str)
        assert len(result) == 64


class TestSetSeed:
    """Tests for set_seed function."""

    def test_set_seed_makes_numpy_deterministic(self):
        """set_seed should make NumPy random number generation deterministic."""
        set_seed(42)
        result1 = np.random.rand(10)

        set_seed(42)
        result2 = np.random.rand(10)

        np.testing.assert_array_equal(result1, result2)

    def test_set_seed_makes_python_random_deterministic(self):
        """set_seed should make Python random module deterministic."""
        set_seed(42)
        result1 = [random.random() for _ in range(10)]

        set_seed(42)
        result2 = [random.random() for _ in range(10)]

        assert result1 == result2

    def test_set_seed_with_different_seeds_produces_different_results(self):
        """Different seeds should produce different random sequences."""
        set_seed(42)
        result1 = np.random.rand(10)

        set_seed(123)
        result2 = np.random.rand(10)

        assert not np.array_equal(result1, result2)

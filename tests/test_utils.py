"""Tests for zebtrack.utils module."""

import random

import numpy as np
import pytest

from zebtrack.utils import (
    IntegrityError,
    calculate_sha256,
    polygon_centroid,
    set_seed,
    snap_point_to_axes,
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


class TestPolygonCentroid:
    """Tests for polygon_centroid function."""

    def test_polygon_centroid_triangle(self):
        """polygon_centroid should calculate correct centroid for triangle."""
        triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
        centroid = polygon_centroid(triangle)

        assert centroid is not None
        cx, cy = centroid
        # Centroid of triangle with vertices at (0,0), (10,0), (5,10) is (5, 10/3)
        assert abs(cx - 5.0) < 0.001
        assert abs(cy - 10.0 / 3.0) < 0.001

    def test_polygon_centroid_square(self):
        """polygon_centroid should calculate correct centroid for square."""
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = polygon_centroid(square)

        assert centroid is not None
        cx, cy = centroid
        assert abs(cx - 5.0) < 0.001
        assert abs(cy - 5.0) < 0.001

    def test_polygon_centroid_returns_none_for_less_than_3_points(self):
        """polygon_centroid should return None for < 3 points."""
        assert polygon_centroid([]) is None
        assert polygon_centroid([(0.0, 0.0)]) is None
        assert polygon_centroid([(0.0, 0.0), (1.0, 1.0)]) is None

    def test_polygon_centroid_returns_none_for_degenerate_polygon(self):
        """polygon_centroid should return None for polygon with zero area."""
        # Collinear points (zero area)
        collinear = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        result = polygon_centroid(collinear)
        assert result is None


class TestSnapPointToAxes:
    """Tests for snap_point_to_axes function."""

    def test_snap_point_to_axes_snaps_to_anchor_horizontal(self):
        """snap_point_to_axes should snap to horizontal axis of anchor."""
        point = (50.0, 103.0)  # 3 pixels away from y=100
        anchors = [(10.0, 100.0)]

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        assert snapped == (50.0, 100.0)  # Snapped to anchor's y

    def test_snap_point_to_axes_snaps_to_anchor_vertical(self):
        """snap_point_to_axes should snap to vertical axis of anchor."""
        point = (103.0, 50.0)  # 3 pixels away from x=100
        anchors = [(100.0, 10.0)]

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        assert snapped == (100.0, 50.0)  # Snapped to anchor's x

    def test_snap_point_to_axes_snaps_to_center(self):
        """snap_point_to_axes should snap to center axes."""
        point = (52.0, 48.0)  # Close to (50, 50)
        centers = [(50.0, 50.0)]

        snapped = snap_point_to_axes(point, centers=centers, threshold=5.0)

        assert snapped is not None
        # Snaps to one of the center's axes (horizontal or vertical alignment)
        assert snapped[0] == 50.0 or snapped[1] == 50.0

    def test_snap_point_to_axes_respects_threshold(self):
        """snap_point_to_axes should not snap if distance > threshold."""
        point = (50.0, 50.0)
        anchors = [(100.0, 100.0)]  # Far away

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is None

    def test_snap_point_to_axes_chooses_closest_snap(self):
        """snap_point_to_axes should choose the closest snap point."""
        point = (51.0, 49.0)
        anchors = [(50.0, 0.0), (0.0, 50.0)]  # Both within threshold

        snapped = snap_point_to_axes(point, anchors=anchors, threshold=5.0)

        assert snapped is not None
        # Should snap to closest option (50, 49) - vertical snap from first anchor
        assert snapped == (50.0, 49.0)

    def test_snap_point_to_axes_handles_no_anchors_or_centers(self):
        """snap_point_to_axes should return None if no anchors/centers."""
        point = (50.0, 50.0)

        snapped = snap_point_to_axes(point, anchors=None, centers=None)

        assert snapped is None

    def test_snap_point_to_axes_handles_empty_iterables(self):
        """snap_point_to_axes should return None for empty iterables."""
        point = (50.0, 50.0)

        snapped = snap_point_to_axes(point, anchors=[], centers=[])

        assert snapped is None

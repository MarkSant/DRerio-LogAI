"""Tests for zebtrack.utils module."""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import zebtrack.utils as utils_root
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


class TestRootUtilsExtended:
    """Test root utils functions for hashing, seeding, and geometry."""

    def test_integrity_error(self):
        err = utils_root.IntegrityError("Corrupt file")
        assert str(err) == "Corrupt file"

    def test_calculate_sha256_valid_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = utils_root.calculate_sha256(f)
        assert len(h) == 64
        # Same hash when passed as string
        assert utils_root.calculate_sha256(str(f)) == h

    def test_calculate_sha256_non_existent_file(self, tmp_path):
        f = tmp_path / "non_existent.txt"
        assert utils_root.calculate_sha256(f) == ""

    def test_set_seed(self):
        utils_root.set_seed(1234)

    def test_polygon_centroid_and_snapping_from_root(self):
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        c = utils_root.polygon_centroid(pts)
        assert c is not None
        assert c[0] == pytest.approx(5.0)

        # Under 3 points
        assert utils_root.polygon_centroid([(0.0, 0.0), (1.0, 1.0)]) is None

        # Snap
        snapped = utils_root.snap_point_to_axes((10.2, 50.0), anchors=[(10.0, 20.0)], threshold=1.0)
        assert snapped == (10.0, 50.0)


class TestUtilsRootExtended:
    """Test root utils module functions: hashing, seeding, and geometry."""

    def test_integrity_error_exception(self):
        with pytest.raises(IntegrityError):
            raise IntegrityError("Hash mismatch")

    def test_calculate_sha256_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, DRerio LogAI!")
        h = calculate_sha256(f)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_calculate_sha256_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.bin"
        assert calculate_sha256(missing) == ""

    def test_set_seed_execution(self):
        # Should execute deterministically without errors
        set_seed(42)

    def test_polygon_centroid_and_snap_point(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        centroid = polygon_centroid(square)
        assert centroid == (5.0, 5.0)

        snapped = snap_point_to_axes((10.1, 20.0), anchors=[(10.0, 10.0)], threshold=1.0)
        assert snapped == (10.0, 20.0)


# --- Property-based checks of the helpers defined in utils/__init__.py ---


def test_polygon_centroid_returns_expected_value():
    square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    centroid = polygon_centroid(square)
    assert centroid is not None
    x, y = centroid
    assert math.isclose(x, 1.0)
    assert math.isclose(y, 1.0)


def test_polygon_centroid_returns_none_for_degenerate_polygon():
    line = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    assert polygon_centroid(line) is None


def test_snap_point_to_axes_uses_anchor_alignment():
    point = (10.5, 19.3)
    anchors = [(5.0, 5.0)]
    snapped = snap_point_to_axes(point, anchors=anchors, threshold=6.0)
    assert snapped is not None
    assert math.isclose(snapped[0], 5.0)
    assert math.isclose(snapped[1], 19.3)


def test_snap_point_to_axes_uses_center_alignment_to_crosshair():
    point = (8.4, 12.6)
    centers = [(10.0, 10.0)]
    snapped = snap_point_to_axes(point, centers=centers, threshold=5.0)
    assert snapped is not None
    assert math.isclose(snapped[0], centers[0][0])
    assert math.isclose(snapped[1], centers[0][1]) or math.isclose(snapped[1], point[1])


def test_snap_point_to_axes_returns_none_when_out_of_threshold():
    point = (0.0, 0.0)
    anchors = [(10.0, 10.0)]
    assert snap_point_to_axes(point, anchors=anchors, threshold=1.0) is None


# ---------------------------------------------------------------------------
# polygon_centroid — casos degenerados
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "points",
    [
        [],
        [(0.0, 0.0)],
        [(0.0, 0.0), (1.0, 1.0)],
    ],
)
def test_polygon_centroid_returns_none_for_fewer_than_three_points(points):
    assert polygon_centroid(points) is None


def test_polygon_centroid_handles_negative_and_large_coordinates():
    square = [(-1e6, -1e6), (1e6, -1e6), (1e6, 1e6), (-1e6, 1e6)]
    centroid = polygon_centroid(square)
    assert centroid is not None
    x, y = centroid
    assert math.isclose(x, 0.0, abs_tol=1e-3)
    assert math.isclose(y, 0.0, abs_tol=1e-3)


@pytest.mark.property
@settings(max_examples=50, deadline=None)
@given(
    cx=st.floats(min_value=-1e4, max_value=1e4),
    cy=st.floats(min_value=-1e4, max_value=1e4),
    half=st.floats(min_value=1.0, max_value=1e3),
)
def test_polygon_centroid_invariant_under_winding_order(cx, cy, half):
    """O centróide independe da ordem (horária/anti-horária) dos vértices."""
    square = [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    ]
    forward = polygon_centroid(square)
    backward = polygon_centroid(list(reversed(square)))
    assert forward is not None
    assert backward is not None
    assert math.isclose(forward[0], backward[0], rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(forward[1], backward[1], rel_tol=1e-6, abs_tol=1e-6)
    # E coincide com o centro geométrico do quadrado.
    assert math.isclose(forward[0], cx, rel_tol=1e-6, abs_tol=1e-3)
    assert math.isclose(forward[1], cy, rel_tol=1e-6, abs_tol=1e-3)


# ---------------------------------------------------------------------------
# snap_point_to_axes — bordas
# ---------------------------------------------------------------------------
def test_snap_point_to_axes_returns_none_without_candidates():
    assert snap_point_to_axes((5.0, 5.0)) is None
    assert snap_point_to_axes((5.0, 5.0), anchors=[], centers=[]) is None


def test_snap_point_to_axes_snaps_onto_center_axis():
    """Ponto próximo ao centro alinha a uma das projeções de eixo do centro.

    A interseção exata ``(cx, cy)`` nunca é estritamente mais próxima que as
    projeções de eixo (mover só uma coordenada é sempre <= mover ambas), então
    o snap recai sobre a projeção mais próxima — aqui, o eixo vertical do centro.
    """
    point = (10.2, 10.2)
    centers = [(10.0, 10.0)]
    snapped = snap_point_to_axes(point, centers=centers, threshold=5.0)
    assert snapped is not None
    # Uma das coordenadas passa a coincidir com o centro (alinhamento a um eixo).
    assert math.isclose(snapped[0], 10.0) or math.isclose(snapped[1], 10.0)


def test_snap_point_to_axes_threshold_is_strict():
    """Distância exatamente igual ao threshold não faz snap (comparação estrita)."""
    point = (0.0, 0.0)
    anchors = [(3.0, 4.0)]  # distância = 5.0 exatamente para o ponto-âncora
    # O candidato mais próximo (alinhamento) fica a 3.0 ou 4.0; com threshold
    # estritamente igual a essas distâncias, não deve haver snap.
    assert snap_point_to_axes(point, anchors=anchors, threshold=3.0) is None

"""Extended unit tests for utils.py root module."""

from __future__ import annotations

from pathlib import Path

import pytest

from zebtrack.utils import (
    IntegrityError,
    calculate_sha256,
    polygon_centroid,
    set_seed,
    snap_point_to_axes,
)


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

"""
Extended unit tests for root utils in zebtrack/utils.py.
"""

from __future__ import annotations

import pytest

import zebtrack.utils as utils_root


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

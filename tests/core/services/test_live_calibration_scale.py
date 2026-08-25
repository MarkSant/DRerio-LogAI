"""Unit tests for ``core/services/live_calibration_scale.py``."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.services.live_calibration_scale import resolve_live_pixel_per_cm

SQUARE_400PX = [[100, 100], [500, 100], [500, 500], [100, 500]]


class TestResolveLivePixelPerCm:
    def test_square_arena_returns_px_per_cm_on_both_axes(self):
        scale = resolve_live_pixel_per_cm(SQUARE_400PX, 20.0, 10.0)

        assert scale is not None
        px_per_cm_x, px_per_cm_y = scale
        # 400 px wide over 20 cm; 400 px tall over 10 cm.
        assert px_per_cm_x == pytest.approx(20.0)
        assert px_per_cm_y == pytest.approx(40.0)

    def test_accepts_numpy_polygon(self):
        scale = resolve_live_pixel_per_cm(np.array(SQUARE_400PX), 40.0, 40.0)

        assert scale is not None
        assert scale[0] == pytest.approx(10.0)

    def test_rotated_polygon_uses_axis_aligned_bounding_box(self):
        diamond = [[300, 100], [500, 300], [300, 500], [100, 300]]

        scale = resolve_live_pixel_per_cm(diamond, 20.0, 20.0)

        assert scale is not None
        assert scale[0] == pytest.approx(20.0)

    @pytest.mark.parametrize(
        "polygon",
        [None, [], [[0, 0], [10, 10]]],
        ids=["none", "empty", "two_vertices"],
    )
    def test_unusable_polygon_returns_none(self, polygon):
        assert resolve_live_pixel_per_cm(polygon, 10.0, 10.0) is None

    @pytest.mark.parametrize(
        ("width_cm", "height_cm"),
        [(None, 10.0), (10.0, None), (0, 10.0), (10.0, 0), (-5.0, 10.0), ("abc", 10.0)],
        ids=["w_none", "h_none", "w_zero", "h_zero", "w_negative", "w_not_a_number"],
    )
    def test_unusable_dimensions_return_none(self, width_cm, height_cm):
        assert resolve_live_pixel_per_cm(SQUARE_400PX, width_cm, height_cm) is None

    def test_degenerate_bbox_returns_none(self):
        # Collinear vertices: zero height span, so no vertical scale exists.
        collinear = [[0, 50], [100, 50], [200, 50]]

        assert resolve_live_pixel_per_cm(collinear, 10.0, 10.0) is None

    def test_malformed_vertices_return_none_instead_of_raising(self):
        assert resolve_live_pixel_per_cm([[0], [1], [2]], 10.0, 10.0) is None
        assert resolve_live_pixel_per_cm(["a", "b", "c"], 10.0, 10.0) is None

    def test_never_returns_one_as_a_silent_default(self):
        """A missing scale must be ``None`` — never a 1.0 that reads as calibrated."""
        assert resolve_live_pixel_per_cm(None, None, None) is None

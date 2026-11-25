"""``analysis/protocols/barnes/layout.py`` — the layout rebuilt from ROI names (#633)."""

from __future__ import annotations

import math

import cv2
import numpy as np
import pytest
from shapely.geometry import Point, Polygon
from tests.analysis.protocols.barnes.barnes_builders import BarnesTable

from zebtrack.analysis.protocols.barnes.contract import (
    BarnesEllipse,
    BarnesHole,
    BarnesLayout,
    circular_offset,
)
from zebtrack.analysis.protocols.barnes.layout import points_in_scaled_ellipse, resolve_layout
from zebtrack.analysis.roi import ROI


def _resolve(table: BarnesTable, rois=None):
    return resolve_layout(table.rois() if rois is None else rois, table.arena(), table.n_holes)


def test_full_layout_is_rebuilt_from_names_and_centroids():
    table = BarnesTable()
    resolution = _resolve(table)

    resolved = resolution.layout
    assert resolution.missing == ()
    assert resolved is not None
    layout = resolved.layout
    assert layout.source == "reconstructed"
    assert layout.n_holes == 20
    assert layout.target_abs_index == 0
    assert [h.abs_index for h in layout.holes] == list(range(20))
    assert [h.offset for h in layout.holes] == [circular_offset(i, 0, 20) for i in range(20)]
    for hole in layout.holes:
        expected = table.hole_xy(hole.offset)
        assert hole.center_px == pytest.approx(expected, abs=1e-6)
        # sqrt(area / pi) of a 32-gon of radius 10
        assert hole.radius_px == pytest.approx(9.968, abs=1e-3)
    assert layout.ring.center_px == pytest.approx(table.center, abs=0.01)
    assert layout.ring.semi_axes_px == pytest.approx((150.0, 150.0), abs=0.01)
    assert layout.table.center_px == pytest.approx(table.center, abs=0.01)
    assert layout.table.semi_axes_px == pytest.approx((200.0, 200.0), abs=0.05)
    assert [h.offset for h in resolved.holes] == [h.offset for h in layout.holes]
    assert [h.roi.name for h in resolved.holes][:2] == ["toca", "buraco_+01"]
    assert resolved.holes[0].area_px == pytest.approx(math.pi * 9.968**2, rel=1e-3)
    assert resolved.quadrant is not None
    assert resolved.quadrant.name == "quadrante_alvo"


def test_rebuild_agrees_with_the_assistant_metadata_cache():
    table = BarnesTable()
    """The cache the assistant writes (another origin) describes the same holes."""
    target_abs = 7
    holes = tuple(
        BarnesHole(
            offset=circular_offset(i, target_abs, 20),
            abs_index=i,
            center_px=table.hole_xy(circular_offset(i, target_abs, 20)),
            radius_px=8.0,
            snapped=True,
            residual_px=0.5,
        )
        for i in range(20)
    )
    ring = BarnesEllipse(table.center, (150.0, 150.0), 0.0)
    cached = BarnesLayout.from_metadata(
        BarnesLayout(
            20, target_abs, BarnesEllipse(table.center, (200.0, 200.0), 0.0), ring, holes, "snapped"
        ).to_metadata()
    )
    assert cached is not None

    rebuilt = _resolve(table).layout
    assert rebuilt is not None

    by_offset = {h.offset: h.center_px for h in rebuilt.layout.holes}
    for hole in cached.holes:
        assert by_offset[hole.offset] == pytest.approx(hole.center_px, abs=1e-6)
    assert rebuilt.layout.ring.center_px == pytest.approx(cached.ring.center_px, abs=0.01)


def test_layout_without_a_table_polygon_uses_the_ring():
    table = BarnesTable()
    resolved = resolve_layout(table.rois(), (), 20).layout

    assert resolved is not None
    assert resolved.layout.table == resolved.layout.ring


@pytest.mark.parametrize(
    ("omit", "rename", "missing"),
    [
        (("toca",), None, ("toca",)),
        (("buraco_-04",), None, ("buraco_-04",)),
        (("buraco_oposto", "buraco_+09"), None, ("buraco_+09", "buraco_oposto")),
        ((), {"toca": "Toca"}, ("toca",)),
        ((), {"buraco_+01": "buraco_+1"}, ("buraco_+01",)),
    ],
)
def test_missing_or_misnamed_holes_leave_the_layout_unresolved(omit, rename, missing):
    table = BarnesTable()
    resolution = _resolve(table, table.rois(omit=omit, rename=rename))

    assert resolution.layout is None
    assert resolution.missing == missing


def test_a_hole_roi_without_area_counts_as_missing():
    table = BarnesTable()
    rois = [
        ROI(r.name, Polygon() if r.name == "buraco_+05" else r.geometry, "px") for r in table.rois()
    ]

    resolution = _resolve(table, rois)

    assert resolution.layout is None
    assert resolution.missing == ("buraco_+05",)


def test_the_quadrant_is_optional():
    table = BarnesTable()
    without = _resolve(table, table.rois(quadrant=False)).layout
    empty = _resolve(
        table,
        [
            ROI(r.name, Polygon() if r.name == "quadrante_alvo" else r.geometry, "px")
            for r in table.rois()
        ],
    ).layout

    assert without is not None
    assert without.quadrant is None
    assert empty is not None
    assert empty.quadrant is None


def test_the_first_roi_of_a_name_wins_and_foreign_rois_are_ignored():
    table = BarnesTable()
    decoy_toca = ROI("toca", Point(0.0, 0.0).buffer(10.0), "px")
    foreign = ROI("start_box", Point(*table.center).buffer(30.0), "px")

    resolved = _resolve(table, [*table.rois(), decoy_toca, foreign]).layout

    assert resolved is not None
    target = resolved.layout.target
    assert target.center_px == pytest.approx(table.hole_xy(0), abs=1e-6)
    assert "start_box" not in [h.roi.name for h in resolved.holes]
    assert len(resolved.holes) == 20


def test_degenerate_hole_centres_do_not_form_a_ring():
    names = ["toca", "buraco_+01", "buraco_-01"]
    rois = [ROI(name, Point(50.0, 50.0).buffer(5.0), "px") for name in names]

    resolution = resolve_layout(rois, (), 3)

    assert resolution.layout is None
    assert resolution.missing == ()


@pytest.mark.parametrize("n_holes", [3, 4, 5, 12])
def test_small_tables_rebuild_a_ring_through_their_holes(n_holes):
    table = BarnesTable(n_holes=n_holes)

    resolved = _resolve(table).layout

    assert resolved is not None
    assert resolved.layout.ring.center_px == pytest.approx(table.center, abs=0.01)
    assert resolved.layout.ring.semi_axes_px == pytest.approx((150.0, 150.0), abs=0.01)


def test_center_disk_scales_the_ring():
    table = BarnesTable()
    resolved = _resolve(table).layout
    assert resolved is not None
    cx, cy = table.center
    x = np.array([cx, cx + 70.0, cx + 80.0, cx, cx - 74.0])
    y = np.array([cy, cy, cy, cy + 76.0, cy])

    inside = resolved.in_center_disk(x, y, 0.5)

    assert inside.tolist() == [True, True, False, False, True]


@pytest.mark.parametrize("angle", [0.0, 30.0, 115.0])
def test_scaled_ellipse_test_agrees_with_opencv_drawing(angle):
    ellipse = BarnesEllipse((200.0, 150.0), (120.0, 60.0), angle)
    boundary = np.asarray(
        cv2.ellipse2Poly((200, 150), (120, 60), int(angle), 0, 360, 5),  # type: ignore[attr-defined]
        dtype=np.float64,
    )
    center = np.array(ellipse.center_px)
    inner = center + (boundary - center) * 0.95
    outer = center + (boundary - center) * 1.05

    assert points_in_scaled_ellipse(ellipse, inner[:, 0], inner[:, 1], 1.0).all()
    assert not points_in_scaled_ellipse(ellipse, outer[:, 0], outer[:, 1], 1.0).any()
    half_inner = center + (boundary - center) * 0.45
    half_outer = center + (boundary - center) * 0.55
    assert points_in_scaled_ellipse(ellipse, half_inner[:, 0], half_inner[:, 1], 0.5).all()
    assert not points_in_scaled_ellipse(ellipse, half_outer[:, 0], half_outer[:, 1], 0.5).any()

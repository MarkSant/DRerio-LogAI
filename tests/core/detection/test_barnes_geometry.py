"""Barnes table geometry on synthetic images (core/detection/barnes_geometry.py, #633).

The synthetic table is the affine image of a circle: a light table on a dark floor,
with ``n`` dark disks evenly spaced on a concentric ring. Tests know the true hole
centres, so every assertion is against ground truth, never against the code's own
prediction.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

import cv2
import numpy as np
import pytest
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon
from tests.helpers.barnes_synthetic import HEIGHT, WIDTH, SyntheticTable
from tests.helpers.barnes_synthetic import affine as _affine

from zebtrack.analysis.protocols.barnes.contract import (
    OPPOSITE_HOLE_ROI,
    QUADRANT_ROI,
    TARGET_ROI,
    BarnesEllipse,
    BarnesLayout,
    BarnesParams,
    expected_roi_names,
    hole_roi_name,
    parse_barnes_roi_name,
)
from zebtrack.core.detection import barnes_geometry as g

pytestmark = pytest.mark.unit


def _hole_by_offset(layout: BarnesLayout, offset: int):
    return next(hole for hole in layout.holes if hole.offset == offset)


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------------------
# Ellipses
# ---------------------------------------------------------------------------


def test_ellipse_param_inverts_ellipse_point():
    ellipse = BarnesEllipse(center_px=(300.0, 200.0), semi_axes_px=(150.0, 90.0), angle_deg=25.0)
    for t in (-2.5, -0.4, 0.0, 1.0, 3.0):
        point = g.ellipse_point(ellipse, t)
        back_t, rho = g.ellipse_param(ellipse, point)
        assert rho == pytest.approx(1.0, abs=1e-9)
        assert math.cos(back_t - t) == pytest.approx(1.0, abs=1e-9)
    _t, inner = g.ellipse_param(
        ellipse,
        (300.0 + 75.0 * math.cos(math.radians(25.0)), 200.0 + 75.0 * math.sin(math.radians(25.0))),
    )
    assert inner == pytest.approx(0.5, abs=1e-9)


def test_ellipse_point_matches_opencv_drawing_convention():
    ellipse = BarnesEllipse(center_px=(300.0, 200.0), semi_axes_px=(150.0, 90.0), angle_deg=30.0)
    canvas = np.zeros((420, 620), dtype=np.uint8)
    cv2.ellipse(canvas, ((300.0, 200.0), (300.0, 180.0), 30.0), 255, 1)
    on_curve = np.argwhere(canvas > 0)[:, ::-1].astype(float)
    for t in np.linspace(0.0, 2.0 * math.pi, 16, endpoint=False):
        point = np.array(g.ellipse_point(ellipse, float(t)))
        assert np.min(np.hypot(*(on_curve - point).T)) < 1.5


def test_parametric_angle_grows_clockwise_on_screen():
    ellipse = BarnesEllipse(center_px=(0.0, 0.0), semi_axes_px=(100.0, 60.0), angle_deg=40.0)
    previous = None
    for t in np.linspace(0.0, 1.5, 6):
        x, y = g.ellipse_point(ellipse, float(t))
        screen = math.atan2(y, x)
        if previous is not None:
            assert math.sin(screen - previous) > 0.0  # y down: growing angle = clockwise
        previous = screen


def test_ellipse_from_points_recovers_a_rotated_ellipse():
    truth = BarnesEllipse(center_px=(310.0, 230.0), semi_axes_px=(190.0, 140.0), angle_deg=20.0)
    rim = [g.ellipse_point(truth, t) for t in np.linspace(0.0, 2.0 * math.pi, 7, endpoint=False)]
    fitted = g.ellipse_from_points(rim)
    assert fitted.center_px == pytest.approx(truth.center_px, abs=0.5)
    assert sorted(fitted.semi_axes_px) == pytest.approx(sorted(truth.semi_axes_px), abs=0.5)
    for t in np.linspace(0.0, 6.0, 9):
        assert g.ellipse_param(fitted, g.ellipse_point(truth, float(t)))[1] == pytest.approx(
            1.0, abs=0.01
        )


def test_ellipse_from_points_needs_five_points():
    with pytest.raises(g.BarnesGeometryError):
        g.ellipse_from_points([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)])


def test_ellipse_from_points_rejects_non_finite_points():
    points = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (10.0, 10.0), (math.nan, 5.0)]
    with pytest.raises(g.BarnesGeometryError):
        g.ellipse_from_points(points)


def test_detection_box_gives_the_inscribed_ellipse():
    ellipse = g.ellipse_from_polygon([(103, 3), (582, 3), (582, 422), (103, 422)])
    assert ellipse.center_px == pytest.approx((342.5, 212.5))
    assert sorted(ellipse.semi_axes_px) == pytest.approx([209.5, 239.5])
    # Every box side touches the ellipse: its four mid-points lie on it.
    for mid in ((342.5, 3.0), (342.5, 422.0), (103.0, 212.5), (582.0, 212.5)):
        assert g.ellipse_param(ellipse, mid)[1] == pytest.approx(1.0, abs=1e-6)


def test_segmentation_outline_is_fitted():
    truth = BarnesEllipse(center_px=(300.0, 220.0), semi_axes_px=(180.0, 150.0), angle_deg=0.0)
    ellipse = g.ellipse_from_polygon(g.ellipse_polygon(truth, 24))
    assert ellipse.center_px == pytest.approx(truth.center_px, abs=0.5)


def test_arena_outline_needs_four_vertices():
    with pytest.raises(g.BarnesGeometryError):
        g.ellipse_from_polygon([(0, 0), (10, 0), (5, 9)])


def test_degenerate_box_is_refused():
    with pytest.raises(g.BarnesGeometryError):
        g.ellipse_from_polygon([(0, 0), (10, 0), (20, 0), (30, 0)])


def test_ellipse_polygon_has_the_requested_vertices_on_the_curve():
    ellipse = BarnesEllipse(center_px=(100.0, 80.0), semi_axes_px=(50.0, 30.0), angle_deg=10.0)
    polygon = g.ellipse_polygon(ellipse)
    assert len(polygon) == g.ARENA_VERTICES == 64
    assert all(g.ellipse_param(ellipse, p)[1] == pytest.approx(1.0) for p in polygon)
    with pytest.raises(g.BarnesGeometryError):
        g.ellipse_polygon(ellipse, 2)


# ---------------------------------------------------------------------------
# Ring and snapping
# ---------------------------------------------------------------------------


def test_click_outside_the_table_is_refused():
    table = SyntheticTable().table_ellipse()
    with pytest.raises(g.BarnesGeometryError):
        g.ring_from_click(table, (5.0, 5.0), 20)


def test_click_on_the_table_centre_is_refused():
    table = SyntheticTable().table_ellipse()
    with pytest.raises(g.BarnesGeometryError):
        g.ring_from_click(table, table.center_px, 20)


def test_ring_needs_three_holes():
    table = SyntheticTable().table_ellipse()
    with pytest.raises(g.BarnesGeometryError):
        g.ring_from_click(table, (400.0, 240.0), 2)


def test_unsnapped_placement_goes_through_the_click_with_even_steps():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    click = synth.hole_center(0)
    layout, model = g.layout_from_click(table, click, 20)
    assert layout.source == "click"
    assert not any(hole.snapped for hole in layout.holes)
    assert _distance(layout.target.center_px, click) < 0.05
    # The ring is the table scaled about its centre.
    assert model.ring.center_px == pytest.approx(table.center_px)
    ratio = model.ring.semi_axes_px[0] / table.semi_axes_px[0]
    assert model.ring.semi_axes_px[1] / table.semi_axes_px[1] == pytest.approx(ratio)
    assert model.step == pytest.approx(math.radians(18.0))


@pytest.mark.parametrize(
    "matrix",
    [
        _affine(0.0, 1.0, 0.85),
        _affine(30.0, 1.0, 0.8),
        _affine(-15.0, 0.95, 0.85, shear=0.08),
    ],
    ids=["axis-aligned", "rotated", "sheared"],
)
def test_snapped_centres_match_the_true_holes(matrix):
    synth = SyntheticTable(matrix=matrix, phase_deg=11.0)
    table = synth.table_ellipse()
    # A sloppy click, 4 px off the escape hole.
    click = (synth.hole_center(0)[0] + 3.0, synth.hole_center(0)[1] - 2.5)
    layout, _model = g.layout_from_click(table, click, 20, synth.image())
    assert layout.source == "snapped"
    assert all(hole.snapped for hole in layout.holes)
    for k in range(20):
        offset = k if k <= 10 else k - 20
        hole = _hole_by_offset(layout, offset)
        assert _distance(hole.center_px, synth.hole_center(k)) < 1.0, (k, hole)
        assert hole.residual_px is not None and hole.residual_px < 3.0
        assert hole.radius_px == pytest.approx(9.0, abs=2.0)


def test_offsets_grow_clockwise_from_the_escape_hole():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    layout, _model = g.layout_from_click(table, synth.hole_center(4), 20, synth.image())
    target = layout.target
    assert _distance(target.center_px, synth.hole_center(4)) < 1.0
    assert _distance(_hole_by_offset(layout, 1).center_px, synth.hole_center(5)) < 1.0
    assert _distance(_hole_by_offset(layout, -1).center_px, synth.hole_center(3)) < 1.0
    assert _distance(_hole_by_offset(layout, 10).center_px, synth.hole_center(14)) < 1.0


def test_abs_index_origin_is_the_hole_nearest_pointing_right():
    synth = SyntheticTable(phase_deg=-5.0)
    table = synth.table_ellipse()
    first, _ = g.layout_from_click(table, synth.hole_center(6), 20, synth.image())
    second, _ = g.layout_from_click(table, synth.hole_center(13), 20, synth.image())
    # Hole 1 of the synthetic table sits at +13 deg: the smallest clockwise angle.
    assert _distance(first.holes[0].center_px, synth.hole_center(1)) < 1.0
    # The same physical hole keeps its abs_index when the escape hole moves.
    for a, b in zip(first.holes, second.holes, strict=True):
        assert _distance(a.center_px, b.center_px) < 0.5
    assert second.target_abs_index - first.target_abs_index == 7


def test_missing_hole_keeps_its_prediction_and_is_flagged():
    synth = SyntheticTable(matrix=_affine(20.0, 1.0, 0.8), missing=(3,))
    table = synth.table_ellipse()
    layout, _model = g.layout_from_click(table, synth.hole_center(0), 20, synth.image())
    missing = _hole_by_offset(layout, 3)
    assert missing.snapped is False
    assert missing.residual_px is None
    assert _distance(missing.center_px, synth.hole_center(3)) < 2.0
    assert sum(hole.snapped for hole in layout.holes) == 19
    quality = g.layout_quality(layout)
    assert quality.snapped == 19
    assert quality.suspicious is True


def test_clean_layout_is_not_suspicious():
    synth = SyntheticTable()
    layout, _model = g.layout_from_click(
        synth.table_ellipse(), synth.hole_center(0), 20, synth.image()
    )
    quality = g.layout_quality(layout)
    assert quality.snapped == quality.n_holes == 20
    assert quality.mean_residual_px is not None and quality.mean_residual_px < 1.0
    assert quality.max_residual_px is not None
    assert quality.suspicious is False


def test_large_residuals_are_suspicious():
    quality = g.LayoutQuality(
        snapped=20, n_holes=20, mean_residual_px=12.0, max_residual_px=20.0, mean_spacing_px=60.0
    )
    assert quality.suspicious is True
    ok = g.LayoutQuality(
        snapped=20, n_holes=20, mean_residual_px=8.0, max_residual_px=9.0, mean_spacing_px=60.0
    )
    assert ok.suspicious is False


def test_unsnapped_layout_quality_has_no_residuals():
    synth = SyntheticTable()
    layout, _ = g.layout_from_click(synth.table_ellipse(), synth.hole_center(0), 20)
    quality = g.layout_quality(layout)
    assert quality.snapped == 0
    assert quality.mean_residual_px is None and quality.max_residual_px is None


def test_wrong_hole_count_never_shares_a_blob():
    synth = SyntheticTable(n_holes=18)
    layout, _model = g.layout_from_click(
        synth.table_ellipse(), synth.hole_center(0), 20, synth.image()
    )
    snapped = [hole.center_px for hole in layout.holes if hole.snapped]
    for i, a in enumerate(snapped):
        for b in snapped[i + 1 :]:
            assert _distance(a, b) > 5.0
    assert g.layout_quality(layout).suspicious is True


def test_snap_ignores_a_low_contrast_window():
    flat = np.full((200, 200), 120, dtype=np.uint8)
    assert g.snap_hole(flat, (100.0, 100.0), 60.0) is None


def test_snap_ignores_the_dark_floor_outside_the_table():
    img = np.full((200, 200), 40, dtype=np.uint8)
    table = BarnesEllipse(center_px=(60.0, 100.0), semi_axes_px=(80.0, 80.0), angle_deg=0.0)
    cv2.circle(img, (60, 100), 80, 200, -1)
    cv2.circle(img, (132, 100), 4, 25, -1)  # a real hole near the rim
    snap = g.snap_hole(img, (130.0, 100.0), 40.0, table)
    assert snap is not None
    assert _distance(snap.center_px, (132.0, 100.0)) < 1.0


def test_snap_rejects_a_thin_dark_seam():
    img = np.full((200, 200), 200, dtype=np.uint8)
    img[95:98, 60:140] = 20  # a seam, not a hole
    assert g.snap_hole(img, (100.0, 100.0), 60.0) is None


def test_snap_window_too_small_finds_nothing():
    img = np.full((50, 50), 200, dtype=np.uint8)
    assert g.snap_hole(img, (25.0, 25.0), 4.0) is None
    assert g.snap_hole(img, (-30.0, -30.0), 40.0) is None


def test_snap_accepts_colour_frames():
    img = np.full((200, 200, 3), 200, dtype=np.uint8)
    cv2.circle(img, (104, 98), 9, (20, 20, 20), -1)
    snap = g.snap_hole(img, (100.0, 100.0), 60.0)
    assert snap is not None
    assert _distance(snap.center_px, (104.0, 98.0)) < 0.6
    assert snap.radius_px == pytest.approx(9.0, abs=1.0)


def test_rotating_the_ring_moves_the_escape_hole_one_hole_clockwise():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    image = synth.image()
    layout, model = g.layout_from_click(table, synth.hole_center(0), 20, image)
    rotated = g.relayout(table, model.rotated(model.step), image)
    assert _distance(rotated.target.center_px, synth.hole_center(1)) < 1.0
    assert rotated.source == "snapped"
    assert _distance(_hole_by_offset(rotated, -1).center_px, layout.target.center_px) < 1.0


def test_relayout_without_background_places_predictions():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    _layout, model = g.layout_from_click(table, synth.hole_center(0), 20)
    layout = g.relayout(table, model, None)
    assert layout.source == "click"
    assert _distance(layout.target.center_px, synth.hole_center(0)) < 0.05


def test_dragged_hole_wins_over_the_snap():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    image = synth.image()
    _layout, model = g.layout_from_click(table, synth.hole_center(0), 20, image)
    moved = (synth.hole_center(2)[0] + 4.0, synth.hole_center(2)[1] + 1.0)
    layout = g.relayout(table, model, image, manual={2: moved})
    hole = _hole_by_offset(layout, 2)
    assert hole.center_px == pytest.approx(moved, abs=0.01)
    assert hole.snapped is False and hole.residual_px is None
    assert hole.radius_px == pytest.approx(9.0, abs=2.0)


def test_cached_layout_rebuilds_its_ring_model():
    synth = SyntheticTable(matrix=_affine(25.0, 1.0, 0.8))
    table = synth.table_ellipse()
    image = synth.image()
    layout, _model = g.layout_from_click(table, synth.hole_center(7), 20, image)
    restored = BarnesLayout.from_metadata(layout.to_metadata())
    assert restored == layout
    again = g.relayout(table, g.ring_model_of_layout(restored), image)
    for a, b in zip(again.holes, layout.holes, strict=True):
        assert _distance(a.center_px, b.center_px) < 0.5
    assert again.target_abs_index == layout.target_abs_index


def test_assemble_layout_checks_the_snap_count():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    model = g.ring_from_click(table, synth.hole_center(0), 20)
    with pytest.raises(g.BarnesGeometryError):
        g.assemble_layout(table, model, [None] * 19)


def test_assemble_layout_honours_an_explicit_source():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    model = g.ring_from_click(table, synth.hole_center(0), 20)
    assert g.assemble_layout(table, model, source="auto").source == "auto"


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------


def _write_video(path: Path, frames: list[np.ndarray]) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"MJPG"), 10.0, (WIDTH, HEIGHT))
    for frame in frames:
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    writer.release()


def test_background_median_removes_the_moving_rat(tmp_path):
    synth = SyntheticTable()
    base = synth.image()
    frames = []
    for i in range(40):
        frame = base.copy()
        cv2.circle(frame, (150 + 8 * i, 240), 18, 15, -1)  # the rat walks across
        frames.append(frame)
    video = tmp_path / "trial.avi"
    _write_video(video, frames)
    background = g.read_background(video, n_samples=30)
    assert background is not None and background.shape == (HEIGHT, WIDTH)
    assert int(background[240, 300]) > 150  # the rat is gone from the table
    layout, _ = g.layout_from_click(synth.table_ellipse(), synth.hole_center(0), 20, background)
    assert all(hole.snapped for hole in layout.holes)


def test_background_of_a_snapshot_is_the_image_itself(tmp_path):
    synth = SyntheticTable()
    image = synth.image()
    snapshot = tmp_path / "reference_frame.png"
    cv2.imwrite(str(snapshot), image)
    background = g.read_background(snapshot)
    assert background is not None
    assert np.array_equal(background, image)


def test_background_of_a_missing_or_broken_file_is_none(tmp_path):
    assert g.read_background(tmp_path / "nope.mp4") is None
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    assert g.read_background(broken) is None
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert g.read_background(empty) is None
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(b"\x00" * 64)
    assert g.read_background(garbage) is None


# ---------------------------------------------------------------------------
# ROIs
# ---------------------------------------------------------------------------


@pytest.fixture
def snapped_layout() -> tuple[SyntheticTable, BarnesLayout]:
    synth = SyntheticTable(matrix=_affine(15.0, 1.0, 0.82))
    layout, _ = g.layout_from_click(synth.table_ellipse(), synth.hole_center(5), 20, synth.image())
    return synth, layout


def test_rois_follow_the_contract_names_and_order(snapped_layout):
    _synth, layout = snapped_layout
    arena, rois = g.build_barnes_rois(layout, BarnesParams(n_holes=20))
    assert [name for name, _ in rois] == list(expected_roi_names(20))
    assert rois[0][0] == QUADRANT_ROI and rois[1][0] == TARGET_ROI
    assert rois[-1][0] == OPPOSITE_HOLE_ROI
    assert all(parse_barnes_roi_name(name, 20) is not None for name, _ in rois)
    assert len(arena) == 64
    assert all(g.ellipse_param(layout.table, p)[1] == pytest.approx(1.0, abs=1e-3) for p in arena)


def test_hole_rois_are_centred_circles_that_never_overlap(snapped_layout):
    _synth, layout = snapped_layout
    _arena, rois = g.build_barnes_rois(layout, BarnesParams(n_holes=20, hole_roi_dilation=3.0))
    holes = {name: Polygon(poly) for name, poly in rois if name != QUADRANT_ROI}
    assert all(len(poly.exterior.coords) - 1 == 32 for poly in holes.values())
    for hole in layout.holes:
        poly = holes[hole_roi_name(hole.offset, 20)]
        assert poly.centroid.distance(ShapelyPoint(hole.center_px)) < 0.1
    names = list(holes)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert not holes[a].intersects(holes[b]), (a, b)


def test_hole_roi_radius_is_the_dilated_hole_below_the_spacing_cap(snapped_layout):
    _synth, layout = snapped_layout
    radii = g.hole_roi_radii(layout, BarnesParams(n_holes=20, hole_roi_dilation=1.25))
    for hole in layout.holes:
        assert radii[hole.abs_index] == pytest.approx(hole.radius_px * 1.25)
    capped = g.hole_roi_radii(layout, BarnesParams(n_holes=20, hole_roi_dilation=3.0))
    spacing = min(
        _distance(layout.holes[i].center_px, layout.holes[(i + 1) % 20].center_px)
        for i in range(20)
    )
    assert max(capped.values()) <= 0.45 * max(
        _distance(layout.holes[i].center_px, layout.holes[(i + 1) % 20].center_px)
        for i in range(20)
    )
    assert min(capped.values()) <= 0.45 * spacing + 1e-9


def test_quadrant_spans_exactly_the_target_and_two_holes_each_side(snapped_layout):
    _synth, layout = snapped_layout
    _arena, rois = g.build_barnes_rois(layout, BarnesParams(n_holes=20))
    quadrant = Polygon(dict(rois)[QUADRANT_ROI])
    assert quadrant.is_valid
    inside = sorted(
        hole.offset for hole in layout.holes if quadrant.contains(ShapelyPoint(hole.center_px))
    )
    assert inside == [-2, -1, 0, 1, 2]
    # Its rim arc has a vertex at least every 3 degrees around the ring centre.
    origin = layout.ring.center_px
    arc = list(quadrant.exterior.coords)[1:-1]
    angles = [math.atan2(y - origin[1], x - origin[0]) for x, y in arc]
    steps = [
        abs(math.atan2(math.sin(b - a), math.cos(b - a))) for a, b in itertools.pairwise(angles)
    ]
    assert max(steps) <= math.radians(3.0) + 1e-9
    assert len(arc) >= 30  # ~90 degrees at <= 3 degrees per step


def test_quadrant_width_follows_quadrant_half_holes(snapped_layout):
    _synth, layout = snapped_layout
    _arena, rois = g.build_barnes_rois(layout, BarnesParams(n_holes=20, quadrant_half_holes=1))
    quadrant = Polygon(dict(rois)[QUADRANT_ROI])
    inside = sorted(
        hole.offset for hole in layout.holes if quadrant.contains(ShapelyPoint(hole.center_px))
    )
    assert inside == [-1, 0, 1]


def test_odd_hole_count_has_no_opposite_hole():
    synth = SyntheticTable(n_holes=15)
    layout, _ = g.layout_from_click(synth.table_ellipse(), synth.hole_center(0), 15, synth.image())
    _arena, rois = g.build_barnes_rois(layout, BarnesParams(n_holes=15))
    names = [name for name, _ in rois]
    assert names == list(expected_roi_names(15))
    assert OPPOSITE_HOLE_ROI not in names


def test_rois_refuse_a_hole_count_mismatch(snapped_layout):
    _synth, layout = snapped_layout
    with pytest.raises(g.BarnesGeometryError):
        g.build_barnes_rois(layout, BarnesParams(n_holes=18))


def test_rois_refuse_collapsed_holes():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    model = g.ring_from_click(table, synth.hole_center(0), 20)
    layout = g.assemble_layout(table, model, manual={1: synth.hole_center(0)})
    with pytest.raises(g.BarnesGeometryError, match="overlap"):
        g.build_barnes_rois(layout, BarnesParams(n_holes=20))


def test_quadrant_needs_the_ring_centre_inside_the_table(snapped_layout):
    _synth, layout = snapped_layout
    far_ring = BarnesEllipse(
        center_px=(5000.0, 5000.0),
        semi_axes_px=layout.ring.semi_axes_px,
        angle_deg=layout.ring.angle_deg,
    )
    moved = BarnesLayout(
        n_holes=layout.n_holes,
        target_abs_index=layout.target_abs_index,
        table=layout.table,
        ring=far_ring,
        holes=layout.holes,
        source=layout.source,
    )
    with pytest.raises(g.BarnesGeometryError, match="outside the table"):
        g.build_barnes_rois(moved, BarnesParams(n_holes=20))


def test_the_ring_is_refitted_when_the_holes_are_not_concentric_with_the_table():
    # The holes sit 8 px off the outline's centre and one of them is missing:
    # only a ring refitted through the snapped holes predicts it.
    synth = SyntheticTable(ring_offset=(8.0, -5.0), missing=(10,))
    table = synth.table_ellipse()
    layout, model = g.layout_from_click(table, synth.hole_center(0), 20, synth.image())
    unfitted, _ = g.layout_from_click(table, synth.hole_center(0), 20)

    missing = _hole_by_offset(layout, 10)
    assert missing.snapped is False
    assert _distance(missing.center_px, synth.hole_center(10)) < 4.0
    assert _distance(_hole_by_offset(unfitted, 10).center_px, synth.hole_center(10)) > 6.0
    assert _distance(model.ring.center_px, table.center_px) > 5.0


def test_an_implausible_refit_keeps_the_concentric_ring():
    synth = SyntheticTable()
    table = synth.table_ellipse()
    model = g.ring_from_click(table, synth.hole_center(0), 20)
    # Five "holes" bunched on one side would fit a tiny ring far from the table's.
    fake = [g.HoleSnap(center_px=(100.0 + i, 100.0 + i * i), radius_px=9.0) for i in range(5)]
    refined, _snaps = g.snap_layout(np.zeros((HEIGHT, WIDTH), dtype=np.uint8), model, table)
    assert refined == model  # nothing snapped on a black frame: no refit
    assert g._refit_ring(model, fake + [None] * 15, table) is None


def test_collinear_rim_points_are_not_an_ellipse():
    with pytest.raises(g.BarnesGeometryError, match="do not lie on an ellipse"):
        g.ellipse_from_points([(10.0 * x, 10.0) for x in range(6)])


@pytest.mark.parametrize("table_holes", [18, 20])
def test_the_hole_count_is_detected_on_the_background(table_holes):
    synth = SyntheticTable(n_holes=table_holes, matrix=_affine(10.0, 1.0, 0.85))
    best, placed = g.detect_hole_count(
        synth.table_ellipse(), synth.hole_center(0), synth.image(), (18, 20)
    )
    assert best == table_holes
    assert set(placed) == {18, 20}
    layout, model = placed[best]
    assert model.n_holes == table_holes
    assert all(hole.snapped for hole in layout.holes)
    wrong = placed[38 - table_holes][0]
    assert g.layout_quality(wrong).suspicious is True


def test_a_count_that_cannot_be_placed_is_skipped():
    synth = SyntheticTable(n_holes=18)
    best, placed = g.detect_hole_count(
        synth.table_ellipse(), synth.hole_center(0), synth.image(), (2, 18)
    )
    assert best == 18 and set(placed) == {18}


def test_hole_count_detection_needs_a_valid_click():
    synth = SyntheticTable()
    with pytest.raises(g.BarnesGeometryError):
        g.detect_hole_count(synth.table_ellipse(), (1.0, 1.0), synth.image())


def test_the_candidate_counts_are_the_labs_tables():
    assert g.HOLE_COUNT_CANDIDATES == (18, 20)


@pytest.mark.parametrize(
    ("center", "fits"),
    [
        ((320.0, 240.0), True),
        ((320.0, 205.0), True),  # touches the top edge, within the 5 % margin
        ((320.0, 150.0), False),
        ((560.0, 240.0), False),
        ((80.0, 240.0), False),
        ((320.0, 330.0), False),
    ],
)
def test_a_table_must_sit_inside_the_frame(center, fits):
    table = BarnesEllipse(center_px=center, semi_axes_px=(200.0, 220.0), angle_deg=0.0)
    assert g.table_fits_frame(table, (480, 640)) is fits

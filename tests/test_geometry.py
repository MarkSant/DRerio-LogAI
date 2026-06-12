import math

import pytest

from zebtrack.utils import polygon_centroid, snap_point_to_axes

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


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

"""
Extended unit tests for GeometryService.
"""

from __future__ import annotations

import pytest

from zebtrack.utils.geometry_service import GeometryService


def test_apply_snapping_to_vertex():
    """Testa snapping para vértice próximo."""
    polygons = [
        [(0, 0), (100, 0), (100, 100), (0, 100)]  # Quadrado
    ]

    # Com axis snapping, (-2, -2) deve snapar para o eixo X ou Y de (0,0).
    # Dist para (0,0) é 2.82. Dist para eixos é 2.
    # Portanto, espera-se (0, -2) ou (-2, 0).
    result = GeometryService.apply_snapping(-2, -2, polygons, threshold=10)
    assert result in [(0, -2), (-2, 0)]

    # Testa sem snap quando longe
    result = GeometryService.apply_snapping(-50, -50, polygons, threshold=10)
    assert result is None


def test_apply_snapping_to_edge():
    """Testa snapping para aresta."""
    polygons = [[(0, 0), (100, 0), (100, 100), (0, 100)]]

    # Ponto (60, 5).
    # Distância para aresta y=0 é 5. Ponto projetado (60, 0).
    # Distância para eixos do centroide (50, 50):
    #   - Eixo X=50: dist |60-50| = 10.
    #   - Eixo Y=50: dist |5-50| = 45.
    # Distância para eixos dos vértices (0 e 100):
    #   - X=0: 60. X=100: 40.
    #   - Y=0: 5. (Align with y=0 axis).
    #
    # O snap_point_to_axes para (60, 5) vai encontrar alinhamento com Y=0
    # (dos vértices 0,0 e 100,0).
    # Isso resulta em (60, 0). Distância 5.
    #
    # Edge snap dá (60, 0), distância 5.
    # Axis snap (com Y=0) dá (60, 0), distância 5.
    #
    # Como as distâncias são iguais, o resultado deve ser (60, 0).

    result = GeometryService.apply_snapping(60, 5, polygons, threshold=10)
    assert result is not None
    assert result[0] == 60
    assert result[1] == 0


def test_clamp_point_to_polygon():
    """Testa clamping de ponto para borda de polígono."""
    polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]

    # Ponto dentro - sem mudança
    result = GeometryService.clamp_point_to_polygon((50, 50), polygon)
    assert result == (50, 50)

    # Ponto fora - clamp para borda mais próxima (borda direita x=100)
    result = GeometryService.clamp_point_to_polygon((150, 50), polygon)
    assert result == (100, 50)


def test_point_to_segment_distance():
    """Testa cálculo de distância ponto-para-segmento."""
    result = GeometryService._point_to_segment_distance(
        50,
        50,  # Ponto
        0,
        0,  # P1 do segmento
        100,
        0,  # P2 do segmento
    )

    assert result is not None
    assert result["x"] == 50
    assert result["y"] == 0
    assert result["distance"] == 50


def test_apply_snapping_exclude_polygon():
    """Testa exclusão de polígono durante snapping."""
    polygons = [
        [(0, 0), (10, 0), (10, 10)],  # Index 0
        [(100, 100), (110, 100), (110, 110)],  # Index 1
    ]

    # Tenta snap para polygon 0, mas excluindo ele
    # (-2, -2) está a 2 de dist dos eixos de polygon 0.
    # Se excluído, não deve snapar.
    result = GeometryService.apply_snapping(-2, -2, polygons, threshold=10, exclude_polygon_index=0)
    assert result is None

    # Tenta snap para polygon 1
    result = GeometryService.apply_snapping(
        105, 105, polygons, threshold=10, exclude_polygon_index=0
    )
    assert result is not None


def test_apply_snapping_to_axis():
    """Testa snapping para alinhamento de eixo (horizontal/vertical)."""
    polygons = [[(0, 0), (100, 0), (100, 100), (0, 100)]]

    # Ponto (200, 5). Deve snapar para (200, 0) alinhando horizontalmente com (0,0) e (100,0).
    result = GeometryService.apply_snapping(200, 5, polygons, threshold=10)
    assert result == (200, 0)

    # Ponto (5, 200). Deve snapar para (0, 200) alinhando verticalmente com (0,0) e (0,100).
    result = GeometryService.apply_snapping(5, 200, polygons, threshold=10)
    assert result == (0, 200)


class TestGeometryServiceExtended:
    def test_apply_snapping_axis_alignment(self):
        # Square: (0,0), (100,0), (100,100), (0,100)
        polygons = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]
        # Point near (100, 0) snaps to horizontal axis y=0
        snapped = GeometryService.apply_snapping(98.0, 2.0, polygons, threshold=5.0)
        assert snapped == (98.0, 0.0)

    def test_apply_snapping_exclude_index(self):
        poly0 = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        poly1 = [(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)]

        # Near poly0, but exclude_polygon_index=0
        snapped = GeometryService.apply_snapping(
            1.0, 1.0, [poly0, poly1], threshold=5.0, exclude_polygon_index=0
        )
        assert snapped is None

    def test_clamp_point_to_polygon_inside(self):
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        point = (50.0, 50.0)
        # Inside -> point returned unchanged
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped == (50.0, 50.0)

    def test_clamp_point_to_polygon_outside(self):
        poly = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        point = (120.0, 50.0)  # Outside on right
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped[0] == pytest.approx(100.0)
        assert clamped[1] == pytest.approx(50.0)

    def test_apply_snapping_vertex_and_edge(self):
        poly = [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]]

        # Near vertex (0, 0) - axis snap to horizontal axis through anchor
        snapped_vertex = GeometryService.apply_snapping(1.0, 1.0, poly, threshold=3.0)
        assert snapped_vertex == (1.0, 0.0)

        # Near edge y=0 between x=20 and x=80 (away from center x=50)
        snapped_edge = GeometryService.apply_snapping(60.0, 2.0, poly, threshold=3.0)
        assert snapped_edge is not None
        assert snapped_edge[0] == pytest.approx(60.0)
        assert snapped_edge[1] == pytest.approx(0.0)

    def test_point_to_segment_distance_degenerate_segment(self):
        res = GeometryService._point_to_segment_distance(10.0, 10.0, 0.0, 0.0, 0.0, 0.0)
        assert res is not None
        assert res["x"] == 0.0
        assert res["y"] == 0.0
        assert res["distance"] == pytest.approx(14.142, 0.01)


class TestGeometryServiceExtended2:
    def test_apply_snapping_empty_polygons(self):
        res = GeometryService.apply_snapping(10.0, 20.0, existing_polygons=[])
        assert res is None

    def test_apply_snapping_to_edge(self):
        poly = [[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]]
        # Point near edge x=100 (99.0, 40.0) -> projects to edge (100.0, 40.0)
        snapped = GeometryService.apply_snapping(99.0, 40.0, poly, threshold=5.0)
        assert snapped is not None
        assert snapped[0] == pytest.approx(100.0)
        assert snapped[1] == pytest.approx(40.0)

    def test_apply_snapping_with_exclusion(self):
        poly1 = [[[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]]
        poly2 = [[[200.0, 200.0], [300.0, 200.0], [300.0, 300.0], [200.0, 300.0]]]
        # Exclude poly1 (index 0), should not snap to (100, 40)
        snapped = GeometryService.apply_snapping(
            99.0, 40.0, [poly1[0], poly2[0]], threshold=5.0, exclude_polygon_index=0
        )
        assert snapped is None

    def test_clamp_point_inside_polygon(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        point = (50.0, 50.0)
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped == point

    def test_clamp_point_outside_polygon(self):
        poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        point = (150.0, 50.0)
        clamped = GeometryService.clamp_point_to_polygon(point, poly)
        assert clamped[0] == pytest.approx(100.0)
        assert clamped[1] == pytest.approx(50.0)

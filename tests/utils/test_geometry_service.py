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
    # O snap_point_to_axes para (60, 5) vai encontrar alinhamento com Y=0 (dos vértices 0,0 e 100,0).
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

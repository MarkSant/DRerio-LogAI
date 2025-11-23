from unittest.mock import MagicMock

from zebtrack.ui.components.polygon_drawing_service import (
    ArenaCompletionStrategy,
    PolygonDrawingService,
    ROICompletionStrategy,
)


def test_arena_completion_strategy():
    """Testa strategy de conclusão de arena."""
    strategy = ArenaCompletionStrategy()
    points = [(0, 0), (100, 0), (100, 100), (0, 100)]

    can_complete, error = strategy.can_complete(points)
    assert can_complete
    assert error is None

def test_arena_completion_strategy_too_few_points():
    """Testa falha com poucos pontos."""
    strategy = ArenaCompletionStrategy()
    points = [(0, 0), (100, 0)]
    can_complete, error = strategy.can_complete(points)
    assert not can_complete
    assert error is not None

def test_roi_completion_strategy():
    """Testa strategy de conclusão de ROI."""
    strategy = ROICompletionStrategy()
    points = [(0, 0), (100, 0), (100, 100)]

    can_complete, error = strategy.can_complete(points)
    assert can_complete

def test_polygon_service_completion_arena():
    """Testa conclusão de polígono de arena via serviço."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    # Mock controller
    mock_gui.controller.set_main_arena_polygon.return_value = True

    result = service.complete_polygon(
        "arena",
        [(0, 0), (100, 0), (100, 100)],
        mock_gui
    )

    assert result is True
    mock_gui.controller.set_main_arena_polygon.assert_called_once()
    mock_gui.canvas_manager.redraw_zones_from_project_data.assert_called_once()
    # mock_gui.update_zone_listbox.assert_called_once() # Replaced by event

def test_polygon_service_completion_roi_cancel_name():
    """Testa cancelamento de ROI se nome não fornecido."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()
    mock_gui.ask_string.return_value = None  # Cancel

    result = service.complete_polygon(
        "roi",
        [(0, 0), (100, 0), (100, 100)],
        mock_gui
    )

    assert result is False
    mock_gui.controller.add_roi_polygon.assert_not_called()

def test_polygon_service_invalid_type():
    """Testa tipo de desenho inválido."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    result = service.complete_polygon(
        "invalid",
        [],
        mock_gui
    )

    assert result is False

def test_polygon_service_validation_fail():
    """Testa falha de validação (pontos insuficientes)."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    result = service.complete_polygon(
        "arena",
        [(0,0)], # Só 1 ponto
        mock_gui
    )

    assert result is False
    mock_gui.show_warning.assert_called_once()

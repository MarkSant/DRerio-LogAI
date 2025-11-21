import pytest
from zebtrack.ui.components.drawing_state_manager import DrawingStateManager

def test_start_polygon_drawing():
    """Testa inicialização de modo de desenho de polígono."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    assert manager.mode == "polygon"
    assert len(manager.current_points) == 0
    assert len(manager._history) == 0

def test_add_point():
    """Testa adição de ponto ao polígono."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    manager.add_point((10, 10), (10, 10), (10, 10))

    assert manager.point_count() == 1
    assert len(manager._history) == 1

def test_undo_redo_stack():
    """Testa funcionalidade undo/redo."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    # Adiciona pontos
    manager.add_point((10, 10), (10, 10), (10, 10))
    manager.add_point((20, 20), (20, 20), (20, 20))

    assert len(manager.current_points) == 2

    # Undo
    success = manager.undo()
    assert success
    assert len(manager.current_points) == 1

    # Redo
    success = manager.redo()
    assert success
    assert len(manager.current_points) == 2

def test_undo_when_empty():
    """Testa undo quando pilha está vazia."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()

    success = manager.undo()
    assert not success

def test_clear_points():
    """Testa limpeza de pontos."""
    manager = DrawingStateManager()
    manager.start_polygon_drawing()
    manager.add_point((10, 10), (10, 10), (10, 10))

    manager.clear_points()
    assert not manager.has_points()
    assert manager.point_count() == 0

def test_has_points():
    """Testa verificação de existência de pontos."""
    manager = DrawingStateManager()
    assert not manager.has_points()

    manager.start_polygon_drawing()
    manager.add_point((10, 10), (10, 10), (10, 10))
    assert manager.has_points()

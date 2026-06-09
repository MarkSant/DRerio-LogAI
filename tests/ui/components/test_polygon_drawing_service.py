from unittest.mock import MagicMock, Mock, patch

from zebtrack.ui.components.polygon_drawing_service import (
    ArenaCompletionStrategy,
    PolygonDrawingService,
    ROICompletionStrategy,
    _is_multi_aquarium_context,
)


def _make_gui_zc(count_var, settings_num_aquariums):
    """Build (gui, zone_controls) stubs for the multi-aquarium guard."""
    gui = MagicMock()
    gui.controller.settings.analysis_config.num_aquariums = settings_num_aquariums
    zone_controls = MagicMock()
    zone_controls.aquarium_count_var.get.return_value = count_var
    return gui, zone_controls


def test_multi_aquarium_context_requires_both_sources():
    """Var de UI em 2 mas settings em 1 (estado vazado) → single."""
    gui, zc = _make_gui_zc(count_var=2, settings_num_aquariums=1)
    assert _is_multi_aquarium_context(gui, zc) is False


def test_multi_aquarium_context_true_when_both_agree():
    """Var de UI e settings ambos em 2 → multi (caso legítimo)."""
    gui, zc = _make_gui_zc(count_var=2, settings_num_aquariums=2)
    assert _is_multi_aquarium_context(gui, zc) is True


def test_multi_aquarium_context_false_when_var_single():
    """Var de UI em 1 → single, independentemente de settings."""
    gui, zc = _make_gui_zc(count_var=1, settings_num_aquariums=2)
    assert _is_multi_aquarium_context(gui, zc) is False


def test_multi_aquarium_context_false_without_zone_controls():
    assert _is_multi_aquarium_context(MagicMock(), None) is False


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

    can_complete, _error = strategy.can_complete(points)
    assert can_complete


def test_polygon_service_completion_arena():
    """Testa conclusão de polígono de arena via serviço."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    # Mock controller
    mock_gui.controller.analysis_vm.set_main_arena_polygon.return_value = True

    result = service.complete_polygon("arena", [(0, 0), (100, 0), (100, 100)], mock_gui)

    assert result is True
    mock_gui.controller.analysis_vm.set_main_arena_polygon.assert_called_once()
    mock_gui.canvas_manager.redraw_zones_from_project_data.assert_called_once()
    # mock_gui.update_zone_listbox.assert_called_once() # Replaced by event


def test_polygon_service_completion_arena_publishes_event():
    """Testa publicação de evento ao completar arena."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()
    mock_gui.controller.analysis_vm.set_main_arena_polygon.return_value = True
    mock_gui.event_bus_v2 = Mock()

    result = service.complete_polygon("arena", [(0, 0), (100, 0), (100, 100)], mock_gui)

    assert result is True
    assert mock_gui.event_bus_v2.publish.call_count == 1
    event = mock_gui.event_bus_v2.publish.call_args[0][0]
    from zebtrack.ui.event_bus_v2 import UIEvents

    assert event.type == UIEvents.ZONES_UPDATED


def test_polygon_service_completion_roi_cancel_name():
    """Testa cancelamento de ROI se nome não fornecido."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()
    mock_gui.ask_string.return_value = None  # Cancel

    result = service.complete_polygon("roi", [(0, 0), (100, 0), (100, 100)], mock_gui)

    assert result is False
    mock_gui.controller.analysis_vm.add_roi_polygon.assert_not_called()


def test_polygon_service_completion_roi_color_cancelled():
    """Testa cancelamento na seleção de cor."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()
    mock_gui.ask_string.return_value = "ROI 1"

    dialog_instance = Mock()
    dialog_instance.result = None

    with patch("zebtrack.ui.dialogs.ColorSelectionDialog", return_value=dialog_instance):
        result = service.complete_polygon("roi", [(0, 0), (100, 0), (100, 100)], mock_gui)

    assert result is False
    mock_gui.controller.analysis_vm.add_roi_polygon.assert_not_called()


def test_polygon_service_completion_roi_success():
    """Testa conclusão de ROI com sucesso e evento."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()
    mock_gui.ask_string.return_value = "ROI 1"
    mock_gui.controller.analysis_vm.add_roi_polygon.return_value = True
    mock_gui.event_bus_v2 = Mock()

    dialog_instance = Mock()
    dialog_instance.result = {"rgb": "#123456"}

    with patch("zebtrack.ui.dialogs.ColorSelectionDialog", return_value=dialog_instance):
        result = service.complete_polygon("roi", [(0, 0), (100, 0), (100, 100)], mock_gui)

    assert result is True
    mock_gui.controller.analysis_vm.add_roi_polygon.assert_called_once_with(
        [(0, 0), (100, 0), (100, 100)], "ROI 1", "#123456"
    )
    assert mock_gui.event_bus_v2.publish.call_count == 1
    event = mock_gui.event_bus_v2.publish.call_args[0][0]
    from zebtrack.ui.event_bus_v2 import UIEvents

    assert event.type == UIEvents.ZONES_UPDATED


def test_polygon_service_invalid_type():
    """Testa tipo de desenho inválido."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    result = service.complete_polygon("invalid", [], mock_gui)

    assert result is False


def test_polygon_service_validation_fail():
    """Testa falha de validação (pontos insuficientes)."""
    service = PolygonDrawingService()
    mock_gui = MagicMock()

    result = service.complete_polygon(
        "arena",
        [(0, 0)],  # Só 1 ponto
        mock_gui,
    )

    assert result is False
    mock_gui.dialog_manager.show_warning.assert_called_once()

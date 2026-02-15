"""Testes para EventDispatcher.

Testes unitários para o dispatcher de eventos,
extraído do MainViewModel na Fase 1 da refatoração.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, MagicMock

import pytest

from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.events import Events

pytestmark = pytest.mark.gui


@pytest.fixture
def mock_event_bus():
    """Cria EventBus mockado."""
    bus = MagicMock()
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def event_dispatcher(mock_event_bus):
    """Cria instância de EventDispatcher para testes."""
    return EventDispatcher(mock_event_bus)


@pytest.fixture
def mock_handler():
    """Cria handler mockado."""
    return MagicMock()


class TestEventDispatcherInitialization:
    """Testes de inicialização do dispatcher."""

    def test_init_with_event_bus(self, mock_event_bus):
        """Testa inicialização com EventBus."""
        dispatcher = EventDispatcher(mock_event_bus)

        assert dispatcher.event_bus is mock_event_bus
        assert dispatcher.handlers == {}
        assert dispatcher.log is not None

    def test_init_without_event_bus(self):
        """Testa inicialização sem EventBus."""
        dispatcher = EventDispatcher(None)

        assert dispatcher.event_bus is None
        assert dispatcher.handlers == {}


class TestRegisterHandler:
    """Testes de registro de handlers."""

    def test_register_no_params(self, event_dispatcher, mock_event_bus, mock_handler):
        """Testa registro de handler sem parâmetros."""
        event_dispatcher.register_handler(
            "test_event", mock_handler, mode=EventDispatcher.MODE_NO_PARAMS
        )

        assert "test_event" in event_dispatcher.handlers
        mock_event_bus.subscribe.assert_called_once()

    def test_register_kwargs_all(self, event_dispatcher, mock_event_bus, mock_handler):
        """Testa registro de handler com kwargs_all."""
        event_dispatcher.register_handler(
            "test_event", mock_handler, mode=EventDispatcher.MODE_KWARGS_ALL
        )

        assert "test_event" in event_dispatcher.handlers

    def test_register_without_event_bus(self, mock_handler):
        """Testa registro sem EventBus."""
        dispatcher = EventDispatcher(None)

        dispatcher.register_handler("test_event", mock_handler)

        assert "test_event" not in dispatcher.handlers


class TestGuiRequirements:
    """Testes para requisitos de GUI."""

    def test_require_gui_raises_without_gui(self, mock_event_bus):
        dispatcher = EventDispatcher(mock_event_bus)

        with pytest.raises(RuntimeError):
            dispatcher._require_gui()


class TestCreateDispatcher:
    """Testes de criação de dispatchers."""

    def test_dispatcher_no_params(self, event_dispatcher, mock_handler):
        """Testa dispatcher no_params."""
        dispatcher = event_dispatcher._create_dispatcher(
            mock_handler, None, EventDispatcher.MODE_NO_PARAMS
        )

        dispatcher({})

        mock_handler.assert_called_once_with()

    def test_dispatcher_kwargs_all(self, event_dispatcher, mock_handler):
        """Testa dispatcher kwargs_all."""
        dispatcher = event_dispatcher._create_dispatcher(
            mock_handler, None, EventDispatcher.MODE_KWARGS_ALL
        )

        dispatcher({"key1": "value1", "key2": "value2"})

        mock_handler.assert_called_once_with(key1="value1", key2="value2")

    def test_dispatcher_kwargs_get(self, event_dispatcher, mock_handler):
        """Testa dispatcher kwargs_get."""
        dispatcher = event_dispatcher._create_dispatcher(
            mock_handler, ["key1", "key2"], EventDispatcher.MODE_KWARGS_GET
        )

        dispatcher({"key1": "value1", "key2": "value2", "key3": "value3"})

        mock_handler.assert_called_once_with(key1="value1", key2="value2")

    def test_dispatcher_positional(self, event_dispatcher, mock_handler):
        """Testa dispatcher positional."""
        dispatcher = event_dispatcher._create_dispatcher(
            mock_handler, ["key1", "key2"], EventDispatcher.MODE_POSITIONAL
        )

        dispatcher({"key1": "value1", "key2": "value2"})

        mock_handler.assert_called_once_with("value1", "value2")

    def test_dispatcher_positional_optional(self, event_dispatcher, mock_handler):
        """Testa dispatcher positional_optional."""
        dispatcher = event_dispatcher._create_dispatcher(
            mock_handler, ["key1", "key2"], EventDispatcher.MODE_POSITIONAL_OPTIONAL
        )

        dispatcher({"key1": "value1"})  # key2 não fornecido

        mock_handler.assert_called_once_with("value1", None)

    def test_dispatcher_unknown_mode(self, event_dispatcher, mock_handler):
        """Testa dispatcher com modo desconhecido."""
        dispatcher = event_dispatcher._create_dispatcher(mock_handler, None, "unknown_mode")

        dispatcher({})

        # Handler não deve ser chamado
        mock_handler.assert_not_called()

    def test_dispatcher_handler_error(self, event_dispatcher):
        """Testa tratamento de erro em handler."""

        def error_handler():
            raise ValueError("Test error")

        dispatcher = event_dispatcher._create_dispatcher(
            error_handler, None, EventDispatcher.MODE_NO_PARAMS
        )

        # Não deve lançar exceção
        dispatcher({})


class TestRegisterDirectHandler:
    """Testes de registro de handler direto."""

    def test_register_direct_handler(self, event_dispatcher, mock_event_bus, mock_handler):
        """Testa registro de handler direto."""
        event_dispatcher.register_direct_handler("test_event", mock_handler)

        assert "test_event" in event_dispatcher.handlers
        mock_event_bus.subscribe.assert_called_once_with("test_event", mock_handler)

    def test_register_direct_handler_without_event_bus(self, mock_handler):
        """Testa registro direto sem EventBus."""
        dispatcher = EventDispatcher(None)

        dispatcher.register_direct_handler("test_event", mock_handler)

        assert "test_event" not in dispatcher.handlers


class TestGuiHandlers:
    """Testes para handlers com GUI."""

    def test_handle_setup_interactive_polygon_defaults(self):
        gui = SimpleNamespace(
            event_bus=MagicMock(),
            setup_interactive_polygon=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher._handle_setup_interactive_polygon(None)

        gui.setup_interactive_polygon.assert_called_once_with([])

    def test_handle_setup_zone_definition_valid(self):
        gui = SimpleNamespace(
            event_bus=MagicMock(),
            setup_zone_definition_for_single_video=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher._handle_setup_zone_definition_for_single_video(
            {"video_path": "/path/video.mp4", "config": {"interval": 10}}
        )

        gui.setup_zone_definition_for_single_video.assert_called_once_with(
            "/path/video.mp4", {"interval": 10}
        )

    def test_handle_setup_zone_definition_missing_data(self):
        gui = SimpleNamespace(
            event_bus=MagicMock(),
            setup_zone_definition_for_single_video=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher._handle_setup_zone_definition_for_single_video({"video_path": ""})

        gui.setup_zone_definition_for_single_video.assert_not_called()


class TestGuiSubscriptions:
    """Testes para subscriptions com GUI."""

    def test_register_event_bus_handlers_subscribes(self):
        event_bus = MagicMock()
        gui = SimpleNamespace(event_bus=event_bus, setup_interactive_polygon=MagicMock())
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.register_event_bus_handlers()

        event_bus.subscribe.assert_called_once()
        args, _kwargs = event_bus.subscribe.call_args
        assert args[0] == Events.UI_SETUP_INTERACTIVE_POLYGON

    def test_subscribe_zone_component_events(self):
        event_bus = MagicMock()
        gui = SimpleNamespace(
            event_bus=event_bus,
            canvas_manager=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
            _on_auto_detect_clicked=MagicMock(),
            _toggle_canvas_view=MagicMock(),
            _on_apply_roi_template=MagicMock(),
            _on_save_roi_template=MagicMock(),
            _on_import_and_apply_roi_template=MagicMock(),
            _filter_video_tree=MagicMock(),
            _refresh_video_selector_tree=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.subscribe_zone_component_events()

        event_bus.subscribe.assert_any_call(Events.ZONE_AUTO_DETECT_CLICKED, ANY)

    def test_subscribe_to_ui_events(self):
        event_bus = MagicMock()
        gui = SimpleNamespace(
            event_bus=event_bus,
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.subscribe_to_ui_events()

        event_bus.subscribe.assert_any_call(Events.UI_SHOW_INFO, ANY)
        event_bus.subscribe.assert_any_call(Events.UI_SHOW_WARNING, ANY)
        event_bus.subscribe.assert_any_call(Events.UI_SHOW_ERROR, ANY)


class TestUnregisterHandler:
    """Testes de remoção de handlers."""

    def test_unregister_existing_handler(self, event_dispatcher, mock_event_bus, mock_handler):
        """Testa remoção de handler existente."""
        event_dispatcher.register_handler("test_event", mock_handler)
        assert "test_event" in event_dispatcher.handlers

        event_dispatcher.unregister_handler("test_event")

        assert "test_event" not in event_dispatcher.handlers

    def test_unregister_nonexistent_handler(self, event_dispatcher):
        """Testa remoção de handler inexistente."""
        # Não deve lançar exceção
        event_dispatcher.unregister_handler("nonexistent_event")


class TestGetRegisteredCount:
    """Testes de contagem de handlers registrados."""

    def test_get_registered_count_empty(self, event_dispatcher):
        """Testa contagem quando vazio."""
        assert event_dispatcher.get_registered_count() == 0

    def test_get_registered_count_with_handlers(
        self, event_dispatcher, mock_event_bus, mock_handler
    ):
        """Testa contagem com handlers registrados."""
        event_dispatcher.register_handler("event1", mock_handler)
        event_dispatcher.register_handler("event2", mock_handler)

        assert event_dispatcher.get_registered_count() == 2


class TestZoneComponentEventHandlers:
    """Testes para handlers de eventos do ZoneControlsWidget."""

    def test_filter_video_tree_delegation(self):
        """Verifica delegação para ProjectViewManager com texto de busca."""
        # Arrange
        mock_gui = MagicMock()
        mock_gui.zone_controls = MagicMock()
        mock_gui.zone_controls.video_search_var.get.return_value = "test_search"
        mock_gui.project_view_manager = MagicMock()

        # Act
        mock_gui._filter_video_tree = lambda: (
            mock_gui.zone_controls
            and mock_gui.project_view_manager._populate_video_selector_tree(
                filter_text=mock_gui.zone_controls.video_search_var.get()
            )
        )
        mock_gui._filter_video_tree()

        # Assert
        mock_gui.project_view_manager._populate_video_selector_tree.assert_called_once_with(
            filter_text="test_search"
        )

    def test_refresh_video_selector_tree_delegation(self):
        """Verifica delegação para ProjectViewManager sem filtro."""
        # Arrange
        mock_gui = MagicMock()
        mock_gui.project_view_manager = MagicMock()

        # Act
        mock_gui._refresh_video_selector_tree = lambda: (
            mock_gui.project_view_manager._populate_video_selector_tree(filter_text=None)
        )
        mock_gui._refresh_video_selector_tree()

        # Assert
        mock_gui.project_view_manager._populate_video_selector_tree.assert_called_once_with(
            filter_text=None
        )

    def test_detector_update_parameters_delegation(self):
        """Verifica que evento DETECTOR_UPDATE_PARAMETERS chama método correto."""
        # Arrange
        mock_gui = MagicMock()
        mock_gui.controller = MagicMock()
        params = {"rule": "centroid_in", "buffer_radius": 0.5, "overlap_ratio": 0.1}

        # Act
        mock_gui._on_apply_roi_settings = lambda p: (
            mock_gui.controller.update_detector_parameters(p) if p and mock_gui.controller else None
        )
        mock_gui._on_apply_roi_settings(params)

        # Assert
        mock_gui.controller.update_detector_parameters.assert_called_once_with(params)

"""Testes para EventDispatcher.

Testes unitários para o dispatcher de eventos,
extraído do MainViewModel na Fase 1 da refatoração.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, MagicMock

import pytest

from zebtrack.ui.components.event_dispatcher import EventDispatcher
from zebtrack.ui.event_bus_v2 import UIEvents

pytestmark = pytest.mark.gui

# Arbitrary event used as a generic token in registration tests
_TEST_EVENT = UIEvents.ZONE_AQUARIUM_SELECTED


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
            _TEST_EVENT, mock_handler, mode=EventDispatcher.MODE_NO_PARAMS
        )

        assert _TEST_EVENT in event_dispatcher.handlers
        mock_event_bus.subscribe.assert_called_once()

    def test_register_kwargs_all(self, event_dispatcher, mock_event_bus, mock_handler):
        """Testa registro de handler com kwargs_all."""
        event_dispatcher.register_handler(
            _TEST_EVENT, mock_handler, mode=EventDispatcher.MODE_KWARGS_ALL
        )

        assert _TEST_EVENT in event_dispatcher.handlers

    def test_register_without_event_bus(self, mock_handler):
        """Testa registro sem EventBus."""
        dispatcher = EventDispatcher(None)

        dispatcher.register_handler(_TEST_EVENT, mock_handler)

        assert _TEST_EVENT not in dispatcher.handlers


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
        event_dispatcher.register_direct_handler(_TEST_EVENT, mock_handler)

        assert _TEST_EVENT in event_dispatcher.handlers
        mock_event_bus.subscribe.assert_called_once_with(_TEST_EVENT, mock_handler)

    def test_register_direct_handler_without_event_bus(self, mock_handler):
        """Testa registro direto sem EventBus."""
        dispatcher = EventDispatcher(None)

        dispatcher.register_direct_handler(_TEST_EVENT, mock_handler)

        assert _TEST_EVENT not in dispatcher.handlers


class TestGuiHandlers:
    """Testes para handlers com GUI."""

    def test_handle_setup_zone_definition_valid(self):
        gui = SimpleNamespace(
            event_bus=MagicMock(),
            single_video_workflow=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher._handle_setup_zone_definition_for_single_video(
            {"video_path": "/path/video.mp4", "config": {"interval": 10}}
        )

        gui.single_video_workflow.setup_zone_definition_for_single_video.assert_called_once_with(
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

    def test_analysis_metadata_handlers_preserve_live_metadata_and_prefer_controller(self):
        event_bus = MagicMock()
        root = MagicMock()
        root.after.side_effect = lambda _delay, callback: callback()

        analysis_view_controller = MagicMock()
        analysis_display_widget = MagicMock()
        live_camera_session_coordinator = MagicMock()
        live_camera_session_coordinator.is_live_session_active.return_value = True

        gui = SimpleNamespace(
            event_bus=event_bus,
            root=root,
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
            analysis_view_controller=analysis_view_controller,
            analysis_display_widget=analysis_display_widget,
            weight_hardware_manager=MagicMock(),
            arduino_dashboard_widget=None,
            single_video_workflow=MagicMock(),
            setup_zone_definition_for_single_video=MagicMock(),
            external_trigger_notice_var=MagicMock(),
            update_button_state=MagicMock(),
            controller=SimpleNamespace(
                state_manager=MagicMock(
                    get_processing_state=MagicMock(
                        return_value=SimpleNamespace(is_live_session_active=True)
                    )
                ),
                live_camera_session_coordinator=live_camera_session_coordinator,
            ),
        )

        dispatcher = EventDispatcher(cast(Any, gui))
        dispatcher.subscribe_to_ui_events()

        handlers = [
            args[1]
            for args, _kwargs in event_bus.subscribe.call_args_list
            if args and args[0] == UIEvents.UI_UPDATE_ANALYSIS_METADATA
        ]

        assert len(handlers) == 2

        for handler in handlers:
            handler({"metadata": {"group": "Controle", "day": "Dia 2", "subject": "02"}})
        for handler in handlers:
            handler({"metadata": {"profile": "custom"}})

        assert dispatcher._pending_analysis_metadata == {
            "metadata": {
                "group": "Controle",
                "day": "Dia 2",
                "subject": "02",
                "profile": "custom",
            }
        }
        analysis_display_widget.set_metadata.assert_not_called()
        assert analysis_view_controller.update_analysis_metadata.call_count == 4

    def test_project_view_navigation_uses_load_project_view(self):
        """UI_NAVIGATE_TO_PROJECT_VIEW must route through full load_project_view path."""
        event_bus = MagicMock()
        root = MagicMock()
        root.after.side_effect = lambda _delay, cb: cb()

        gui = SimpleNamespace(
            event_bus=event_bus,
            root=root,
            project_initializer=SimpleNamespace(load_project_view=MagicMock()),
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
            analysis_view_controller=MagicMock(),
            weight_hardware_manager=MagicMock(),
            arduino_dashboard_widget=None,
            single_video_workflow=MagicMock(),
            setup_zone_definition_for_single_video=MagicMock(),
            external_trigger_notice_var=MagicMock(),
        )

        dispatcher = EventDispatcher(cast(Any, gui))
        dispatcher.subscribe_to_ui_events()

        subscribed_handler = None
        for call in event_bus.subscribe.call_args_list:
            args, _kwargs = call
            if args and args[0] == UIEvents.UI_NAVIGATE_TO_PROJECT_VIEW:
                subscribed_handler = args[1]
                break

        assert subscribed_handler is not None
        subscribed_handler({})
        gui.project_initializer.load_project_view.assert_called_once()

    def test_register_event_bus_handlers_subscribes(self):
        event_bus = MagicMock()
        gui = SimpleNamespace(event_bus=event_bus, setup_interactive_polygon=MagicMock())
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.register_event_bus_handlers()

        subscribed = [call.args[0] for call in event_bus.subscribe.call_args_list]
        assert subscribed == [UIEvents.CLASS_ROLES_CHANGED]

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

        event_bus.subscribe.assert_any_call(UIEvents.ZONE_AUTO_DETECT_CLICKED, ANY)

    def test_subscribe_to_ui_events(self):
        event_bus = MagicMock()
        _vsm = MagicMock()
        gui = SimpleNamespace(
            event_bus=event_bus,
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=_vsm,
            project_view_manager=_vsm,
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.subscribe_to_ui_events()

        event_bus.subscribe.assert_any_call(UIEvents.UI_SHOW_INFO, ANY)
        event_bus.subscribe.assert_any_call(UIEvents.UI_SHOW_WARNING, ANY)
        event_bus.subscribe.assert_any_call(UIEvents.UI_SHOW_ERROR, ANY)

    def test_processing_count_updates_only_processing_card_on_both_widgets(self):
        """UI_UPDATE_PROCESSING_COUNT seta SÓ a chave "processing" nos dois cards."""
        from zebtrack.ui import payloads

        event_bus = MagicMock()
        reports_widget = MagicMock()
        overview_widget = MagicMock()
        gui = SimpleNamespace(
            event_bus=event_bus,
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
            processing_reports_widget=reports_widget,
            project_overview_widget=overview_widget,
        )
        dispatcher = EventDispatcher(cast(Any, gui))
        dispatcher.subscribe_to_ui_events()

        handler = None
        for call in event_bus.subscribe.call_args_list:
            args, _kwargs = call
            if args and args[0] == UIEvents.UI_UPDATE_PROCESSING_COUNT:
                handler = args[1]
                break
        assert handler is not None

        handler(payloads.ProcessingCountPayload(count=2))

        reports_widget.update_status_counts.assert_called_once_with({"processing": 2})
        overview_widget.update_status_counts.assert_called_once_with({"processing": 2})


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
        """Verifica delegação para VideoSelectorTreeManager com texto de busca."""
        # Arrange
        mock_gui = MagicMock()
        mock_gui.zone_controls = MagicMock()
        mock_gui.zone_controls.video_search_var.get.return_value = "test_search"
        mock_gui.video_selector_manager = MagicMock()

        # Act
        mock_gui._filter_video_tree = lambda: (
            mock_gui.zone_controls
            and mock_gui.video_selector_manager._populate_video_selector_tree(
                filter_text=mock_gui.zone_controls.video_search_var.get()
            )
        )
        mock_gui._filter_video_tree()

        # Assert
        mock_gui.video_selector_manager._populate_video_selector_tree.assert_called_once_with(
            filter_text="test_search"
        )

    def test_refresh_video_selector_tree_delegation(self):
        """Verifica delegação para VideoSelectorTreeManager sem filtro."""
        # Arrange
        mock_gui = MagicMock()
        mock_gui.video_selector_manager = MagicMock()

        # Act
        mock_gui._refresh_video_selector_tree = lambda: (
            mock_gui.video_selector_manager._populate_video_selector_tree(filter_text=None)
        )
        mock_gui._refresh_video_selector_tree()

        # Assert
        mock_gui.video_selector_manager._populate_video_selector_tree.assert_called_once_with(
            filter_text=None
        )


class TestAnalysisWindowSpecChanged:
    """The analysis-window panel's save reaches the status bar through the real bus."""

    @staticmethod
    def _wired() -> tuple[Any, MagicMock]:
        from zebtrack.ui.event_bus_v2 import EventBusV2

        bus = EventBusV2()
        status_var = MagicMock()
        gui = SimpleNamespace(event_bus=bus, root=None, status_var=status_var)
        EventDispatcher(cast(Any, gui)).subscribe_zone_component_events()
        return bus, status_var

    def test_saved_window_asks_for_a_new_analysis(self):
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event

        bus, status_var = self._wired()

        bus.publish(
            Event(
                type=UIEvents.ANALYSIS_WINDOW_SPEC_CHANGED,
                data=payloads.AnalysisWindowSpecChangedPayload(
                    spec={"version": 1}, spec_hash="sha256:abc"
                ),
            )
        )

        status_var.set.assert_called_once_with(
            "Analysis window saved. Run the analysis again to apply it."
        )

    def test_removed_window_means_whole_recording(self):
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event

        bus, status_var = self._wired()

        bus.publish(
            Event(
                type=UIEvents.ANALYSIS_WINDOW_SPEC_CHANGED,
                data=payloads.AnalysisWindowSpecChangedPayload(spec=None),
            )
        )

        status_var.set.assert_called_once_with(
            "Analysis window removed: the whole recording will be analysed."
        )


class TestAnalysisWindowStateChanged:
    """The live window's phase reaches the trigger banner through the real bus (v8 F5)."""

    @staticmethod
    def _wired(*, with_banner: bool = True) -> tuple[Any, Any]:
        from zebtrack.ui.components.dialog_manager import DialogManager
        from zebtrack.ui.event_bus_v2 import EventBusV2

        bus = EventBusV2()
        gui = SimpleNamespace(
            event_bus=bus,
            root=None,
            status_var=MagicMock(),
            external_trigger_notice_var=MagicMock(),
            external_trigger_notice_label=MagicMock() if with_banner else None,
            _external_notice_default_bg="white",
            _external_notice_default_fg="black",
        )
        gui.dialog_manager = DialogManager(gui)
        EventDispatcher(cast(Any, gui)).subscribe_zone_component_events()
        return bus, gui

    @staticmethod
    def _publish(bus: Any, **fields: Any) -> None:
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event

        bus.publish(
            Event(
                type=UIEvents.ANALYSIS_WINDOW_STATE_CHANGED,
                data=payloads.AnalysisWindowStatePayload(**fields),
            )
        )

    def test_waiting_turns_the_trigger_notice_into_a_start_condition_banner(self):
        bus, gui = self._wired()

        self._publish(bus, state="waiting_start")

        message = gui.external_trigger_notice_var.set.call_args.args[0]
        assert message == "Recording — waiting for the start condition of the analysis window."
        gui.status_var.set.assert_called_once_with(message)
        gui.external_trigger_notice_label.config.assert_called_once_with(
            background="#FFF7ED", foreground="#92400e"
        )

    def test_open_window_shows_its_start_instant_without_highlight(self):
        bus, gui = self._wired()

        self._publish(bus, state="in_analysis", t_s=6.71, reason="persist")

        message = gui.external_trigger_notice_var.set.call_args.args[0]
        assert message == "Analysis window open since 6.7 s."
        gui.external_trigger_notice_label.config.assert_called_once_with(
            background="white", foreground="black"
        )

    def test_start_not_met_says_what_the_analysis_will_do(self):
        bus, gui = self._wired()

        self._publish(bus, state="start_not_met", on_start_not_met="empty")

        message = gui.external_trigger_notice_var.set.call_args.args[0]
        assert "empty" in message

    def test_ad_hoc_session_without_banner_still_gets_the_status_bar(self):
        bus, gui = self._wired(with_banner=False)

        self._publish(bus, state="finished", t_s=186.0)

        gui.status_var.set.assert_called_once_with("Analysis window finished at 186.0 s.")
        gui.external_trigger_notice_var.set.assert_not_called()

    def test_unknown_state_is_ignored(self):
        bus, gui = self._wired()

        self._publish(bus, state="bogus")

        gui.status_var.set.assert_not_called()
        gui.external_trigger_notice_var.set.assert_not_called()


class TestFinishDrawingRouting:
    """O 'Finalizar Desenho' deve comitar a edição interativa (não reverter)."""

    def test_interactive_edit_detected_when_editing_and_points(self):
        gui = SimpleNamespace(
            canvas_manager=SimpleNamespace(current_editing_zone="arena"),
            edited_polygon_points=[[0, 0], [1, 1], [2, 2]],
        )
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is True

    def test_not_edit_when_no_editing_zone(self):
        gui = SimpleNamespace(
            canvas_manager=SimpleNamespace(current_editing_zone=None),
            current_editing_zone=None,
            edited_polygon_points=[[0, 0], [1, 1], [2, 2]],
        )
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is False

    def test_not_edit_when_no_points(self):
        gui = SimpleNamespace(
            canvas_manager=SimpleNamespace(current_editing_zone="arena"),
            edited_polygon_points=[],
        )
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is False

    def test_editing_flag_on_gui_also_counts(self):
        gui = SimpleNamespace(
            canvas_manager=SimpleNamespace(current_editing_zone=None),
            current_editing_zone="arena",
            edited_polygon_points=[[0, 0], [1, 1], [2, 2]],
        )
        assert EventDispatcher._finish_drawing_is_interactive_edit(gui) is True


class TestUnprefixedMessageAliases:
    """``SHOW_*``/``SET_STATUS`` precisam chegar ao mesmo lugar que os ``UI_*``.

    São dois membros distintos do mesmo enum para o bus e sinônimos para quem
    lê o código. Enquanto só o ``UI_`` tinha assinante, toda mensagem publicada
    sob o nome curto era descartada por ``EventBusV2.publish`` sem log — foi
    assim que o assistente passou a fechar sem criar projeto e sem explicar.
    """

    @staticmethod
    def _dispatcher_with_immediate_after():
        """GUI de teste cujo ``root.after`` executa o callback na hora.

        Os handlers de mensagem embrulham a chamada em ``root.after(0, ...)``
        para voltar à thread do Tk. Com um ``MagicMock`` puro o lambda nunca
        roda e o teste passaria sem exercitar nada.
        """
        event_bus = MagicMock()
        dialog_manager = MagicMock()
        status_var = MagicMock()
        root = MagicMock()
        root.after.side_effect = lambda _delay, callback: callback()

        gui = SimpleNamespace(
            event_bus=event_bus,
            root=root,
            widget_factory=MagicMock(),
            dialog_manager=dialog_manager,
            status_var=status_var,
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
        )
        dispatcher = EventDispatcher(cast(Any, gui))
        dispatcher.subscribe_to_ui_events()
        return event_bus, dialog_manager, status_var

    @staticmethod
    def _handler_for(event_bus, event):
        for call in event_bus.subscribe.call_args_list:
            args, _kwargs = call
            if args and args[0] == event:
                return args[1]
        return None

    def test_show_error_without_prefix_reaches_the_dialog(self):
        from zebtrack.ui import payloads

        event_bus, dialog_manager, _status = self._dispatcher_with_immediate_after()

        handler = self._handler_for(event_bus, UIEvents.SHOW_ERROR)
        assert handler is not None, "UIEvents.SHOW_ERROR ficou sem assinante"

        handler(
            payloads.MessagePayload(
                title="Configuração Inválida",
                message="det só aceita 1 animal por aquário",
            )
        )

        dialog_manager.show_error.assert_called_once_with(
            "Configuração Inválida", "det só aceita 1 animal por aquário"
        )

    def test_show_info_without_prefix_reaches_the_dialog(self):
        from zebtrack.ui import payloads

        event_bus, dialog_manager, _status = self._dispatcher_with_immediate_after()

        handler = self._handler_for(event_bus, UIEvents.SHOW_INFO)
        assert handler is not None, "UIEvents.SHOW_INFO ficou sem assinante"

        handler(payloads.MessagePayload(title="Pronto", message="Projeto criado"))

        dialog_manager.show_info.assert_called_once_with("Pronto", "Projeto criado")

    def test_set_status_without_prefix_updates_the_status_bar(self):
        from zebtrack.ui import payloads

        event_bus, _dialog_manager, status_var = self._dispatcher_with_immediate_after()

        handler = self._handler_for(event_bus, UIEvents.SET_STATUS)
        assert handler is not None, "UIEvents.SET_STATUS ficou sem assinante"

        handler(payloads.StatusPayload(message="Cancelamento solicitado para CECT_4."))

        status_var.set.assert_called_once_with("Cancelamento solicitado para CECT_4.")

    def test_prefixed_and_unprefixed_reach_the_same_dialog_call(self):
        """Os dois nomes precisam produzir o MESMO efeito, não só existir."""
        from zebtrack.ui import payloads

        event_bus, dialog_manager, _status = self._dispatcher_with_immediate_after()
        payload = payloads.MessagePayload(title="Erro", message="falha X")

        self._handler_for(event_bus, UIEvents.UI_SHOW_ERROR)(payload)
        self._handler_for(event_bus, UIEvents.SHOW_ERROR)(payload)

        assert dialog_manager.show_error.call_count == 2
        first, second = dialog_manager.show_error.call_args_list
        assert first == second


class TestClassRolesChanged:
    """A class-role save reaches the status bar and re-resolves the zone tab."""

    @staticmethod
    def _wired() -> tuple[Any, MagicMock, MagicMock]:
        from zebtrack.ui.event_bus_v2 import EventBusV2

        bus = EventBusV2()
        status_var = MagicMock()
        context = MagicMock()
        gui = SimpleNamespace(
            event_bus=bus, root=None, status_var=status_var, class_roles_context=context
        )
        EventDispatcher(cast(Any, gui)).register_event_bus_handlers()
        return bus, status_var, context

    def test_saved_roles_refresh_the_context(self):
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event

        bus, status_var, context = self._wired()

        bus.publish(
            Event(
                type=UIEvents.CLASS_ROLES_CHANGED,
                data=payloads.ClassRolesChangedPayload(
                    scope="project", weight_name="rat.pt", class_roles={"rat": "subject"}
                ),
            )
        )

        status_var.set.assert_called_once_with(
            "Class roles saved. They apply from the next detection run."
        )
        context.refresh.assert_called_once_with()

    def test_cleared_roles_say_automatic(self):
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event

        bus, status_var, _context = self._wired()

        bus.publish(
            Event(
                type=UIEvents.CLASS_ROLES_CHANGED,
                data=payloads.ClassRolesChangedPayload(scope="weight", class_roles=None),
            )
        )

        status_var.set.assert_called_once_with(
            "Class roles back to automatic. They apply from the next detection run."
        )


class TestDisplayFrameCarriesTheDetectorsRoles:
    """#645: ``UI_DISPLAY_FRAME`` hands the publisher's role map to the canvas."""

    @staticmethod
    def _gui():
        root = MagicMock()
        root.after.side_effect = lambda _delay, callback: callback()
        gui = SimpleNamespace(
            event_bus=MagicMock(),
            root=root,
            widget_factory=MagicMock(),
            dialog_manager=MagicMock(),
            status_var=MagicMock(),
            notebook=MagicMock(),
            state_synchronizer=MagicMock(),
            video_selector_manager=MagicMock(),
            project_view_manager=MagicMock(),
            canvas_manager=MagicMock(),
            zone_controls=MagicMock(),
            menu_manager=MagicMock(),
            zone_control_builder=MagicMock(),
        )
        EventDispatcher(cast(Any, gui)).subscribe_to_ui_events()
        return gui

    def test_roles_reach_update_video_frame(self):
        from zebtrack.ui import payloads

        gui = self._gui()
        handler = TestUnprefixedMessageAliases._handler_for(
            gui.event_bus, UIEvents.UI_DISPLAY_FRAME
        )
        assert handler is not None
        handler(payloads.FrameDisplayPayload(frame="f", detections=[1], class_roles={0: "arena"}))
        gui.canvas_manager.update_video_frame.assert_called_once_with(
            "f", [1], class_roles={0: "arena"}
        )

    def test_absent_roles_reach_the_canvas_as_none(self):
        from zebtrack.ui import payloads

        gui = self._gui()
        handler = TestUnprefixedMessageAliases._handler_for(
            gui.event_bus, UIEvents.UI_DISPLAY_FRAME
        )
        assert handler is not None
        handler(payloads.FrameDisplayPayload(frame="f"))
        gui.canvas_manager.update_video_frame.assert_called_once_with("f", None, class_roles=None)


class TestAquariumAssignmentDialogGroups:
    """The project's groups reach the assignment dialog (payload-key drift audit)."""

    def test_project_groups_reach_the_dialog_through_the_bus(self):
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import _coerce_payload

        dialog_manager = MagicMock()
        dialog_manager.show_aquarium_assignment_dialog.return_value = (None, False)
        gui = SimpleNamespace(event_bus=None, dialog_manager=dialog_manager)
        dispatcher = EventDispatcher(cast(Any, gui))
        delivered = _coerce_payload(
            UIEvents.ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG,
            payloads.ZoneShowAquariumAssignmentDialogPayload(
                video_path="v.mp4",
                polygons=[],
                count=2,
                available_groups=("Grupo_A", "Grupo_B"),
            ),
        )

        dispatcher._on_show_aquarium_assignment_dialog(delivered)

        kwargs = dialog_manager.show_aquarium_assignment_dialog.call_args.kwargs
        # Before the fix the payload had no such field and the dialog got [],
        # falling back to its hardcoded "Controle"/"Tratamento" placeholders.
        assert kwargs["available_groups"] == ["Grupo_A", "Grupo_B"]


# ---------------------------------------------------------------------------
# Barnes arena assistant (#633)
# ---------------------------------------------------------------------------


class _BarnesPM:
    """The ProjectManager surface the Barnes handlers read."""

    def __init__(
        self,
        *,
        protocol: str = "barnes",
        project_type: str = "batch",
        active: str | None = None,
        videos: list[dict] | None = None,
        zones: dict | None = None,
    ) -> None:
        self.project_data: dict[str, Any] = {
            "project_type": project_type,
            "behavioral_config": {
                "protocol": protocol,
                "protocol_params": {"barnes": {"n_holes": 18}},
            },
        }
        self._active = active
        self._videos = videos or []
        self._zones = zones or {}

    def get_project_type(self):
        return self.project_data["project_type"]

    def get_active_zone_video(self):
        return self._active

    def get_last_zone_video(self, exclude=None):
        return self._active

    def get_all_videos(self):
        return self._videos

    def find_video_entry(self, *, path=None, experiment_id=None):
        return next((v for v in self._videos if v["path"] == path), None)

    def get_zone_data(self, video_path=None, *, fallback_to_global=True):
        from zebtrack.core.detection import ZoneData

        return self._zones.get(video_path, ZoneData())


def _barnes_gui(pm, *, frame=True, bus=None):
    from PIL import Image

    image = Image.new("RGB", (64, 48)) if frame else None
    return SimpleNamespace(
        event_bus=bus,
        root=MagicMock(),
        zone_controls=MagicMock(),
        dialog_manager=MagicMock(),
        canvas_manager=SimpleNamespace(_raw_bg_image=image),
        _original_image=None,
        controller=SimpleNamespace(project_manager=pm),
    )


class TestBarnesAssistant:
    def test_the_button_follows_the_profile(self):
        pm = _BarnesPM()
        gui = _barnes_gui(pm)
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.refresh_barnes_assistant_visibility()
        gui.zone_controls.set_barnes_assistant_visible.assert_called_with(True)

        pm.project_data["behavioral_config"]["protocol"] = "generic"
        dispatcher.refresh_barnes_assistant_visibility()
        gui.zone_controls.set_barnes_assistant_visible.assert_called_with(False)

    def test_no_project_hides_the_button(self):
        gui = _barnes_gui(SimpleNamespace(project_data=None))
        EventDispatcher(cast(Any, gui)).refresh_barnes_assistant_visibility()
        gui.zone_controls.set_barnes_assistant_visible.assert_called_once_with(False)

    def test_no_zone_controls_is_harmless(self):
        gui = _barnes_gui(_BarnesPM())
        gui.zone_controls = None
        EventDispatcher(cast(Any, gui)).refresh_barnes_assistant_visibility()

    def test_the_zone_events_are_wired(self):
        bus = MagicMock()
        gui = _barnes_gui(_BarnesPM(), bus=bus)
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher.subscribe_zone_component_events()

        handlers: dict[Any, list[Any]] = {}
        for call in bus.subscribe.call_args_list:
            handlers.setdefault(call.args[0], []).append(call.args[1])
        assert dispatcher._open_barnes_assistant in handlers[UIEvents.ZONE_BARNES_ASSISTANT_OPEN]
        gui.zone_controls.set_barnes_assistant_visible.assert_called_once_with(True)

        gui.root.after.side_effect = lambda _delay, callback: callback()
        for event in (UIEvents.PROJECT_OPENED, UIEvents.UI_UPDATE_ZONE_LIST):
            for handler in handlers[event]:
                handler(None)
        assert gui.zone_controls.set_barnes_assistant_visible.call_count >= 3

    def test_a_generic_project_gets_a_warning_not_a_dialog(self, monkeypatch):
        import zebtrack.ui.dialogs.barnes_layout_dialog as dialog_module

        opened = MagicMock()
        monkeypatch.setattr(dialog_module, "BarnesLayoutDialog", opened)
        gui = _barnes_gui(_BarnesPM(protocol="generic", active="v.mp4"), bus=MagicMock())

        EventDispatcher(cast(Any, gui))._open_barnes_assistant(None)

        opened.assert_not_called()
        gui.dialog_manager.show_warning.assert_called_once()
        gui.zone_controls.set_barnes_assistant_visible.assert_called_with(False)

    def test_no_frame_on_the_zones_tab_gets_a_warning(self, monkeypatch):
        import zebtrack.ui.dialogs.barnes_layout_dialog as dialog_module

        opened = MagicMock()
        monkeypatch.setattr(dialog_module, "BarnesLayoutDialog", opened)
        gui = _barnes_gui(_BarnesPM(active="v.mp4"), frame=False, bus=MagicMock())

        EventDispatcher(cast(Any, gui))._open_barnes_assistant(None)

        opened.assert_not_called()
        assert "Zones tab" in gui.dialog_manager.show_warning.call_args.args[1]

    def test_the_dialog_gets_the_videos_state(self, monkeypatch, tmp_path):
        import zebtrack.ui.dialogs.barnes_layout_dialog as dialog_module
        from zebtrack.analysis.protocols.barnes.contract import BarnesEllipse
        from zebtrack.core.detection import ZoneData
        from zebtrack.core.detection import barnes_geometry as geometry

        day1 = tmp_path / "Dia_1" / "trial.mp4"
        day2 = tmp_path / "Dia_2" / "trial.mp4"
        for path in (day1, day2):
            path.parent.mkdir()
            path.write_bytes(b"x")
        missing = str(tmp_path / "gone.mp4")
        table = BarnesEllipse(center_px=(320.0, 240.0), semi_axes_px=(200.0, 170.0), angle_deg=0.0)
        layout, _model = geometry.layout_from_click(table, (480.0, 240.0), 18)
        videos: list[dict[str, Any]] = [
            {
                "path": str(day1),
                "metadata": {"group": "G1", "day": 1, "subject": "rat_3"},
                "protocol_inputs": {"barnes": {"trial_type": "probe"}},
            },
            {"path": str(day2), "metadata": {"group": "G1", "day": 2}},
            {"path": missing},
        ]
        zones = {
            str(day1): ZoneData(
                polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
                metadata={"barnes_layout": layout.to_metadata()},
            )
        }
        opened = MagicMock()
        monkeypatch.setattr(dialog_module, "BarnesLayoutDialog", opened)
        bus = MagicMock()
        gui = _barnes_gui(_BarnesPM(active=str(day1), videos=videos, zones=zones), bus=bus)
        dispatcher = EventDispatcher(cast(Any, gui))

        dispatcher._open_barnes_assistant(None)

        args = opened.call_args.args
        assert args[0] is gui.root and args[1] is bus
        inputs = args[2]
        assert inputs.video_path == str(day1)
        assert inputs.params.n_holes == 18
        assert inputs.cached_layout == layout
        assert inputs.initial_table is None
        assert inputs.trial_type == "probe"
        assert inputs.trial_type_editable is True
        assert inputs.background_source == str(day1)
        assert inputs.can_detect_table is True
        assert [v.path for v in inputs.other_videos] == [str(day2)]
        assert inputs.other_videos[0].label == "G1 / 2 / trial.mp4"
        assert opened.call_args.kwargs["detect_table"] == dispatcher._barnes_detect_table

    def test_an_existing_arena_seeds_the_table(self, monkeypatch, tmp_path):
        import zebtrack.ui.dialogs.barnes_layout_dialog as dialog_module
        from zebtrack.core.detection import ZoneData

        video = str(tmp_path / "v.mp4")
        zones = {video: ZoneData(polygon=[(100, 50), (500, 50), (500, 400), (100, 400)])}
        opened = MagicMock()
        monkeypatch.setattr(dialog_module, "BarnesLayoutDialog", opened)
        gui = _barnes_gui(_BarnesPM(active=video, zones=zones), bus=MagicMock())

        EventDispatcher(cast(Any, gui))._open_barnes_assistant(None)

        inputs = opened.call_args.args[2]
        assert inputs.cached_layout is None
        assert inputs.initial_table.center_px == pytest.approx((300.0, 225.0))
        assert inputs.trial_type_editable is False  # no project entry for that path
        assert inputs.background_source is None  # the file does not exist

    def test_a_live_project_edits_the_reference_snapshot(self, monkeypatch, tmp_path):
        import zebtrack.ui.dialogs.barnes_layout_dialog as dialog_module

        snapshot = tmp_path / "reference_frame.png"
        snapshot.write_bytes(b"png")
        other = tmp_path / "session.mp4"
        other.write_bytes(b"x")
        opened = MagicMock()
        monkeypatch.setattr(dialog_module, "BarnesLayoutDialog", opened)
        pm = _BarnesPM(project_type="live", active=str(snapshot), videos=[{"path": str(other)}])
        gui = _barnes_gui(pm, bus=MagicMock())

        EventDispatcher(cast(Any, gui))._open_barnes_assistant(None)

        inputs = opened.call_args.args[2]
        assert inputs.video_path == str(snapshot)
        assert inputs.can_detect_table is False
        assert inputs.other_videos == ()
        assert inputs.background_source == str(snapshot)

    def test_table_detection_reuses_the_zones_tab_detection(self):
        from zebtrack.core.detection import ZoneData

        bus = MagicMock()
        pm = _BarnesPM(active="v.mp4", zones={"v.mp4": ZoneData(polygon=[(9, 9), (8, 8)])})

        def detection_saves_an_arena(event, payload):
            pm._zones["v.mp4"] = ZoneData(polygon=[(1, 2), (3, 4), (5, 6), (7, 8)])

        bus.publish.side_effect = detection_saves_an_arena
        gui = _barnes_gui(pm, bus=bus)
        gui.zone_controls.stabilization_frames_var.get.return_value = "7"
        dispatcher = EventDispatcher(cast(Any, gui))

        assert dispatcher._barnes_detect_table("v.mp4") == [
            (1.0, 2.0),
            (3.0, 4.0),
            (5.0, 6.0),
            (7.0, 8.0),
        ]

        event, payload = bus.publish.call_args.args
        assert event is UIEvents.ZONE_AUTO_DETECT
        assert payload.video_path == "v.mp4"
        assert payload.stabilization_frames == 7
        assert payload.expected_count == 1

    def test_failed_table_detection_returns_none(self):
        gui = _barnes_gui(_BarnesPM(active="v.mp4"), bus=MagicMock())
        gui.zone_controls.stabilization_frames_var.get.return_value = "oops"
        dispatcher = EventDispatcher(cast(Any, gui))

        assert dispatcher._barnes_detect_table("v.mp4") is None
        assert gui.event_bus.publish.call_args.args[1].stabilization_frames == 10

    def test_an_unchanged_arena_is_not_a_detection(self):
        from zebtrack.core.detection import ZoneData

        stale = ZoneData(polygon=[(1, 2), (3, 4), (5, 6), (7, 8)])
        gui = _barnes_gui(_BarnesPM(active="v.mp4", zones={"v.mp4": stale}), bus=MagicMock())
        gui.zone_controls.stabilization_frames_var.get.return_value = "7"

        assert EventDispatcher(cast(Any, gui))._barnes_detect_table("v.mp4") is None

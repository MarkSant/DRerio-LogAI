"""A aba Configurações Avançadas precisa mostrar a falha, não engoli-la.

``ConfigEditorWidget`` publica ``CONFIG_VALIDATION_ERROR`` quando um campo não
converte. Enquanto ninguém assinava esse evento, ``EventBusV2.publish``
descartava em silêncio (``if not handlers: return``) e o botão "Salvar
Configurações" era literalmente inerte com um campo vazio — o pesquisador
concluía que tinha salvo.

Este arquivo cobre o lado do ASSINANTE. O lado do widget (publicar em vez de
levantar) está em ``tests/ui/components/test_config_editor.py``; os dois juntos
fecham o circuito, e nenhum sozinho prova que a mensagem chega à tela.
"""

from tkinter import ttk
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.ui import payloads
from zebtrack.ui.builders.analysis_widgets import AnalysisWidgetsBuilder
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

pytestmark = pytest.mark.gui


@pytest.fixture
def wired(tkinter_root):
    """Constrói a aba de configuração com um bus real e um dialog_manager falso.

    O bus é real de propósito: um ``MagicMock`` aceitaria qualquer publicação e
    o teste passaria mesmo com o assinante ausente — que é exatamente o bug.
    """
    event_bus = EventBusV2()
    dialog_manager = MagicMock()

    # Notebook REAL: ttkbootstrap inspeciona a classe do pai ao criar o widget,
    # e um MagicMock quebra em ``re.search`` antes de o teste começar.
    notebook = ttk.Notebook(tkinter_root)

    gui = SimpleNamespace(
        notebook=notebook,
        event_bus=event_bus,
        root=tkinter_root,
        dialog_manager=dialog_manager,
        config_editor_widget=None,
        _event_bus_handlers={},
        controller=SimpleNamespace(
            project_manager=SimpleNamespace(project_path=None, project_data={})
        ),
        _extract_setting=lambda _settings, _path, default: default,
        _open_global_model_configuration_window=MagicMock(),
    )

    builder = AnalysisWidgetsBuilder(
        cast(Any, gui),
        common_builder=MagicMock(),
        settings_obj=None,
        dialog_manager=dialog_manager,
    )
    builder.create_configuration_tab_widget()
    # ``settings_obj=None`` faz ``reload_config_editor_values_widget`` avisar
    # que não há settings; esse aviso não é o assunto aqui.
    dialog_manager.reset_mock()
    return gui, event_bus, dialog_manager


def test_validation_error_reaches_the_user(wired):
    _gui, event_bus, dialog_manager = wired

    event_bus.publish(
        UIEvents.CONFIG_VALIDATION_ERROR,
        payloads.ConfigValidationErrorPayload(error="invalid literal for int() with base 10: ''"),
    )

    dialog_manager.show_error.assert_called_once()
    _title, message = dialog_manager.show_error.call_args[0]
    assert "invalid literal" in message, "a causa precisa chegar ao texto do diálogo"


def test_saving_an_unreadable_field_end_to_end_shows_a_dialog(wired):
    """Do clique no botão até o diálogo, sem simular o meio do caminho."""
    gui, _event_bus, dialog_manager = wired

    gui.config_editor_widget.fps_var.set("")
    gui.config_editor_widget._on_save_clicked()

    dialog_manager.show_error.assert_called_once()


def test_the_three_config_events_are_all_subscribed(wired):
    """Salvar, recarregar e falhar: os três precisam de assinante."""
    _gui, event_bus, _dialog_manager = wired

    # ``EventBusV2`` não expõe contagem de assinantes; ler ``_subscribers`` é a
    # única forma de distinguir "ninguém assina" de "assina e não faz nada", que
    # é exatamente a distinção que este arquivo existe para fazer.
    for event in (
        UIEvents.CONFIG_SAVE_REQUESTED,
        UIEvents.CONFIG_RESET_REQUESTED,
        UIEvents.CONFIG_VALIDATION_ERROR,
    ):
        handlers = event_bus._subscribers.get(event, [])
        assert handlers, f"UIEvents.{event.name} sem assinante: o bus descarta em silêncio."

"""O botão "Aplicar" da aba de Zonas precisa PERSISTIR a regra de ROI.

O caminho antigo (``DETECTOR_UPDATE_PARAMETERS`` →
``update_detector_parameters``) descartava ``rule``/``buffer_radius``/
``overlap_ratio`` em silêncio, retornava ``True`` e logava sucesso — nada era
gravado. Aqui só se testa roteamento, com mocks: nenhum Tk real é instanciado.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.settings import load_settings
from zebtrack.ui import payloads
from zebtrack.ui.components.event_dispatcher import EventDispatcher

pytestmark = pytest.mark.gui


def _dispatcher(project_path, project_data, settings) -> Any:
    """Dispatcher com uma GUI de mentira — nenhum widget Tk é criado."""
    project_manager = MagicMock()
    project_manager.project_path = project_path
    project_manager.project_data = project_data

    gui: Any = SimpleNamespace(
        event_bus=MagicMock(),
        show_info=MagicMock(),
        settings=settings,
        controller=SimpleNamespace(
            project_manager=project_manager,
            settings=settings,
            hardware_vm=MagicMock(),
        ),
    )
    dispatcher: Any = EventDispatcher(gui.event_bus)
    dispatcher.gui = gui
    return dispatcher


PAYLOAD = payloads.RoiSettingsApplyPayload(
    rule="centroid_in", buffer_radius=2.5, overlap_ratio=0.35
)


def test_apply_persists_into_project_roi_settings():
    project_data: dict = {}
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, load_settings())

    dispatcher._on_persist_roi_settings(PAYLOAD)

    assert project_data["roi_settings"] == {
        "roi_inclusion_rule": "centroid_in",
        "roi_buffer_radius_value": 2.5,
        "roi_min_bbox_overlap_ratio": 0.35,
    }
    dispatcher.gui.controller.project_manager.save_project.assert_called_once()
    dispatcher.gui.show_info.assert_called_once()


def test_persisted_settings_are_read_back_by_the_resolver():
    """O que o botão grava é exatamente o que ``resolve_roi_rule`` lê."""
    from zebtrack.core.services.roi_rule_resolver import resolve_roi_rule

    project_data: dict = {}
    settings = load_settings()
    settings.roi_inclusion_rule = "bbox_intersects"
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, settings)

    dispatcher._on_persist_roi_settings(PAYLOAD)

    config = resolve_roi_rule(project_data, settings)
    assert config.rule == "centroid_in"
    assert config.buffer_radius_value == 2.5
    assert config.min_bbox_overlap_ratio == 0.35


def test_apply_preserves_other_project_keys():
    project_data = {"roi_settings": {"chave_legada": 1}, "calibration": {"pixelcm_x": 10}}
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, load_settings())

    dispatcher._on_persist_roi_settings(PAYLOAD)

    assert project_data["roi_settings"]["chave_legada"] == 1
    assert project_data["calibration"] == {"pixelcm_x": 10}


def test_apply_without_project_falls_back_to_session_settings():
    """Sem ``project_path``, ``save_project()`` levantaria — e o bus engoliria."""
    settings = load_settings()
    dispatcher = _dispatcher(None, {}, settings)

    dispatcher._on_persist_roi_settings(PAYLOAD)

    assert settings.roi_inclusion_rule == "centroid_in"
    assert settings.roi_buffer_radius_value == 2.5
    assert settings.roi_min_bbox_overlap_ratio == 0.35
    dispatcher.gui.controller.project_manager.save_project.assert_not_called()


def test_apply_does_not_route_to_detector_parameters():
    """A regra de ROI não é parâmetro de detector — não pode voltar para lá."""
    dispatcher = _dispatcher("C:/proj/proj.json", {}, load_settings())

    dispatcher._on_persist_roi_settings(PAYLOAD)

    dispatcher.gui.controller.hardware_vm.update_detector_parameters.assert_not_called()


def test_invalid_text_does_not_crash_and_falls_back():
    """Campo digitado errado não pode derrubar o clique nem gravar lixo."""
    project_data: dict = {}
    settings = load_settings()
    settings.roi_buffer_radius_value = 1.0
    settings.roi_min_bbox_overlap_ratio = 0.20
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, settings)

    dispatcher._on_persist_roi_settings(
        payloads.RoiSettingsApplyPayload(
            rule="centroid_in", buffer_radius="abc", overlap_ratio="1,5"
        )
    )

    assert project_data["roi_settings"] == {
        "roi_inclusion_rule": "centroid_in",
        "roi_buffer_radius_value": 1.0,  # caiu no valor global
        "roi_min_bbox_overlap_ratio": 0.20,
    }


def test_text_values_from_tk_stringvars_are_converted():
    """A UI manda ``str`` (StringVar); quem converte é o resolvedor."""
    project_data: dict = {}
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, load_settings())

    dispatcher._on_persist_roi_settings(
        payloads.RoiSettingsApplyPayload(
            rule="centroid_in_on_buffered_roi", buffer_radius="2.5", overlap_ratio="0.35"
        )
    )

    assert project_data["roi_settings"]["roi_buffer_radius_value"] == 2.5
    assert project_data["roi_settings"]["roi_min_bbox_overlap_ratio"] == 0.35


def test_blank_fields_are_ignored_not_invalid():
    project_data: dict = {}
    settings = load_settings()
    settings.roi_buffer_radius_value = 1.0
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, settings)

    dispatcher._on_persist_roi_settings(
        payloads.RoiSettingsApplyPayload(rule="centroid_in", buffer_radius="", overlap_ratio="  ")
    )

    assert project_data["roi_settings"]["roi_inclusion_rule"] == "centroid_in"
    assert project_data["roi_settings"]["roi_buffer_radius_value"] == 1.0


def test_dialog_shows_effective_parameter():
    """O diálogo mostra o valor APLICADO — é assim que um descarte fica visível."""
    settings = load_settings()
    settings.roi_min_bbox_overlap_ratio = 0.20
    dispatcher = _dispatcher("C:/proj/proj.json", {}, settings)

    dispatcher._on_persist_roi_settings(
        payloads.RoiSettingsApplyPayload(rule="bbox_intersects", overlap_ratio="abc")
    )

    message = dispatcher.gui.show_info.call_args.args[1]
    assert "bbox_intersects" in message
    assert "0.2" in message


@pytest.mark.parametrize("corrupted", [["lista"], "texto", 42])
def test_corrupted_roi_settings_is_replaced_not_crashed(corrupted):
    """``roi_settings`` com tipo errado levantaria TypeError — engolido pelo bus."""
    project_data: dict = {"roi_settings": corrupted}
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, load_settings())

    dispatcher._on_persist_roi_settings(PAYLOAD)

    assert project_data["roi_settings"] == {
        "roi_inclusion_rule": "centroid_in",
        "roi_buffer_radius_value": 2.5,
        "roi_min_bbox_overlap_ratio": 0.35,
    }
    dispatcher.gui.controller.project_manager.save_project.assert_called_once()


@pytest.mark.parametrize("broken", [None, "não é dict", ["lista"]])
def test_project_data_not_a_dict_applies_to_session_instead_of_raising(broken):
    """Projeto carregado pela metade não pode matar o handler no bus."""
    settings = load_settings()
    dispatcher = _dispatcher("C:/proj/proj.json", broken, settings)

    dispatcher._on_persist_roi_settings(PAYLOAD)

    assert settings.roi_inclusion_rule == "centroid_in"
    dispatcher.gui.controller.project_manager.save_project.assert_not_called()


def test_empty_payload_is_a_noop():
    project_data: dict = {}
    dispatcher = _dispatcher("C:/proj/proj.json", project_data, load_settings())

    dispatcher._on_persist_roi_settings(payloads.RoiSettingsApplyPayload(rule=None))

    assert project_data == {}
    dispatcher.gui.controller.project_manager.save_project.assert_not_called()

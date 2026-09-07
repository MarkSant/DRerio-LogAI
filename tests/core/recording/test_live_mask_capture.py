"""``seg_overlap` ao vivo degradava SEMPRE, e a culpa nao era do dado.

O defeito
---------
``core.services.mask_capture.should_capture_masks`` e a regra unica que decide se
uma sessao grava mascaras -- ``recorder.persist_masks`` E modelo de animal ``seg``
E regra de ROI efetiva ``seg_overlap``, as tres juntas.

Ela tinha UM chamador: o worker pre-gravado. O pipeline ao vivo nunca a chamava,
nunca chamava ``set_mask_capture`` e nunca escrevia o sidecar
``3b_Mascaras_*``. Consequencia: uma sessao ao vivo configurada com
``seg_overlap`` caia sempre em ``bbox_intersects`` e o relatorio trazia o aviso de
degradacao -- que o pesquisador leria como limitacao do dado, quando era do
pipeline.

Diferenca proposital em relacao ao worker
-----------------------------------------
Aqui o ``project_data`` E passado ao resolvedor. O ao vivo roda no mesmo processo
e tem o projeto em maos, entao um projeto com ``seg_overlap`` sobre um global
``bbox_intersects`` conta na decisao. O worker recebe so o snapshot de settings,
que ja chega com a regra do projeto aplicada.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin
from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


def _settings(*, persist: bool, animal_method: str, roi_rule: str) -> SimpleNamespace:
    return SimpleNamespace(
        recorder=SimpleNamespace(persist_masks=persist),
        model_selection=SimpleNamespace(animal_method=animal_method),
        roi_inclusion_rule=roi_rule,
    )


def _manager(settings, project_data: dict | None = None):
    manager = object.__new__(LiveSessionManagerMixin)
    manager.settings = settings
    manager.detector_service = MagicMock()
    manager.project_manager = MagicMock()
    manager.project_manager.project_data = project_data or {}
    return manager


def test_masks_are_enabled_when_the_three_conditions_hold() -> None:
    """O caso que nao funcionava: tudo configurado e nada era gravado."""
    manager = _manager(_settings(persist=True, animal_method="seg", roi_rule="seg_overlap"))

    assert manager._configure_mask_capture() is True
    manager.detector_service.detector.set_mask_capture.assert_called_once_with(True)


@pytest.mark.parametrize(
    ("persist", "animal_method", "roi_rule"),
    [
        (False, "seg", "seg_overlap"),  # o operador nao pediu
        (True, "det", "seg_overlap"),  # modelo de caixa nao tem mascara
        (True, "seg", "bbox_intersects"),  # a regra nao usa mascara
    ],
)
def test_any_missing_condition_leaves_masks_off(
    persist: bool, animal_method: str, roi_rule: str
) -> None:
    """As tres condicoes sao conjuncao, e a decisao mora no resolvedor."""
    manager = _manager(_settings(persist=persist, animal_method=animal_method, roi_rule=roi_rule))

    assert manager._configure_mask_capture() is False


def test_the_detector_is_told_to_turn_masks_off_too() -> None:
    """Desligar explicitamente, e nao so "nao ligar".

    O detector e COMPARTILHADO entre sessoes. Sem o desligamento, uma sessao que
    nao precisa de mascaras herdaria a captura ligada pela anterior e pagaria a
    decodificacao a toa.
    """
    manager = _manager(_settings(persist=True, animal_method="det", roi_rule="seg_overlap"))

    manager._configure_mask_capture()

    manager.detector_service.detector.set_mask_capture.assert_called_once_with(False)


def test_a_project_rule_counts_in_the_decision() -> None:
    """``project_data`` participa -- e a diferenca em relacao ao worker.

    Um projeto com ``seg_overlap`` sobre um global ``bbox_intersects`` precisa
    gravar mascaras, senao o relatorio degrada por uma decisao que o projeto
    nunca tomou.
    """
    manager = _manager(
        _settings(persist=True, animal_method="seg", roi_rule="bbox_intersects"),
        project_data={"roi_settings": {"roi_inclusion_rule": "seg_overlap"}},
    )

    assert manager._configure_mask_capture() is True


def test_a_detector_without_the_hook_is_tolerated() -> None:
    """Um plugin sem ``set_mask_capture`` nao pode derrubar o inicio da sessao."""
    manager = _manager(_settings(persist=True, animal_method="seg", roi_rule="seg_overlap"))
    manager.detector_service.detector = SimpleNamespace()  # sem o metodo

    assert manager._configure_mask_capture() is False


# ---------------------------------------------------------------------------
# A escrita, no laco de processamento
# ---------------------------------------------------------------------------


def _pipeline(masks: dict | Exception):
    pipeline = object.__new__(FrameProcessingMixin)
    pipeline.recorder = MagicMock()
    detector = MagicMock()
    if isinstance(masks, Exception):
        detector.pop_track_masks.side_effect = masks
    else:
        detector.pop_track_masks.return_value = masks
    # ``cast`` mantem a anotacao de producao honesta: fora do teste o atributo
    # e um ``DetectorService`` de verdade.
    pipeline.detector_service = cast("Any", SimpleNamespace(detector=detector))
    return pipeline


def test_masks_reach_the_recorder() -> None:
    """O sidecar so existe se alguem escrever nele."""
    pipeline = _pipeline({1: "mascara"})

    pipeline._write_track_masks(42, [("det",)])

    pipeline.recorder.write_mask_data.assert_called_once_with(42, {1: "mascara"})


def test_no_masks_means_no_write() -> None:
    """Captura desligada nao pode custar I/O no caminho normal."""
    pipeline = _pipeline({})

    pipeline._write_track_masks(42, [("det",)])

    pipeline.recorder.write_mask_data.assert_not_called()


def test_a_mask_failure_does_not_abort_the_session() -> None:
    """Degrada, nunca interrompe.

    Uma mascara perdida custa uma linha a menos no sidecar e faz o ROI cair no
    ``bbox_intersects`` com aviso. Uma excecao aqui derrubaria a thread de
    processamento e levaria junto a GRAVACAO, que e o dado que nao volta.
    """
    pipeline = _pipeline(RuntimeError("decodificacao falhou"))

    pipeline._write_track_masks(42, [("det",)])

    pipeline.recorder.write_mask_data.assert_not_called()


def test_a_detector_without_the_hook_is_tolerated_on_write() -> None:
    pipeline = object.__new__(FrameProcessingMixin)
    pipeline.recorder = MagicMock()
    pipeline.detector_service = cast("Any", SimpleNamespace(detector=SimpleNamespace()))

    pipeline._write_track_masks(42, [("det",)])

    pipeline.recorder.write_mask_data.assert_not_called()

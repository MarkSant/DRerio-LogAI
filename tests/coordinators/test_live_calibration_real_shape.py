"""A forma da arena escolhida no diálogo tem de chegar à política de detecção.

O que faltava
-------------
O checkbox "preservar a forma real do aquário" existia só no
``SingleVideoConfigDialog``. No fluxo ao vivo avulso a única maneira de pedir a
máscara era editar ``config.local.yaml`` à mão — e o default de
``detection_zones.preserve_real_aquarium_shape`` é ``false``, então a
auto-detecção entregava um retângulo de 4 cantos mesmo com um modelo de
segmentação carregado e funcionando.

Por que isso não é cosmético
----------------------------
Medido no quadro real de uma sessão com labirinto em cruz visto de cima
(2026-09-06): a bounding box cobria **61%** do quadro e a máscara real, **37%**.
Os ~39% de diferença são os cantos vazios entre os braços do labirinto — área
FORA do aparato que a arena passava a considerar dentro. É onde um artefato
parado vira "objeto dentro da arena", o defeito que o #528 mediu em 22,7% da
trajetória de um peixe.

Por argumento, não pelo ``Settings``
------------------------------------
O valor viaja como argumento até ``resolve_arena_detection``, com a mesma
precedência que a perspectiva. Escrevê-lo no ``Settings`` compartilhado
resolveria o sintoma criando a 13ª escrita global — exatamente o que
``tests/quality/test_shared_settings_mutations.py`` existe para impedir.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator
from zebtrack.core.services.arena_detection_policy import resolve_arena_detection

if TYPE_CHECKING:
    from zebtrack.settings import Settings


def _settings(*, preserve: bool | None) -> Settings:
    """Stand-in com os poucos campos que o coordinator le.

    O cast mantem a assinatura de producao honesta: quem chama de verdade tem
    de passar um ``Settings``.
    """
    return cast(
        "Settings",
        SimpleNamespace(
            camera=SimpleNamespace(index=0),
            yolo_model=SimpleNamespace(confidence_threshold=0.05),
            model_selection=SimpleNamespace(aquarium_method="seg"),
            behavioral_analysis=SimpleNamespace(aquarium_perspective="top_down"),
            detection_zones=SimpleNamespace(preserve_real_aquarium_shape=preserve),
        ),
    )


def _coordinator(*, settings_preserve: bool | None, project_data: dict | None = None):
    project_manager = MagicMock()
    project_manager.project_data = project_data if project_data is not None else {}
    project_manager.project_path = None

    weight_manager = MagicMock()
    weight_manager.get_weight_path_by_method.return_value = "fake_weights.pt"

    return LiveCalibrationCoordinator(
        state_manager=MagicMock(),
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=weight_manager,
        settings_obj=_settings(preserve=settings_preserve),
        event_bus=MagicMock(),
        root=MagicMock(),
        view=None,
    )


def _run(coordinator, *, preserve_real_shape: bool | None) -> bool:
    """Roda a calibração e devolve o ``preserve_real_shape`` que o burst recebeu."""
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    fake_camera = MagicMock()
    fake_camera.is_open = True
    fake_camera.get_frame.return_value = (True, fake_frame)

    polygon = [[100, 100], [200, 100], [200, 200], [100, 200]]
    dialog = MagicMock()
    dialog.show.return_value = {"approved": True, "polygon": polygon, "frame": None}

    with (
        patch.object(
            LiveCalibrationCoordinator, "_detect_polygon_on_burst", return_value=[polygon]
        ) as burst,
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.AquariumDetector"
        ) as detector_cls,
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.Camera",
            return_value=fake_camera,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.cv2.imwrite",
            return_value=True,
        ),
        patch(
            "zebtrack.ui.dialogs.preview_polygon_dialog.PreviewPolygonDialog",
            return_value=dialog,
        ),
        patch(
            "zebtrack.coordinators.live_calibration_coordinator.time.sleep",
            return_value=None,
        ),
    ):
        detector_cls.return_value = MagicMock()
        coordinator.run_live_calibration(
            stabilization_frames=4,
            show_preview=True,
            preserve_real_shape=preserve_real_shape,
        )

    assert burst.call_args is not None, "a calibração nunca chegou a detectar"
    return burst.call_args.kwargs["preserve_real_shape"]


def test_checkbox_on_reaches_the_detection_even_with_the_global_off() -> None:
    """O caso reportado: global ``false``, usuário marcou o checkbox."""
    coordinator = _coordinator(settings_preserve=False)

    assert _run(coordinator, preserve_real_shape=True) is True


def test_checkbox_off_wins_over_a_global_true() -> None:
    """Desmarcar é uma escolha, não ausência de escolha.

    Uma checagem por truthiness trataria ``False`` como "não opinou" e devolveria
    a máscara a quem pediu explicitamente o retângulo.
    """
    coordinator = _coordinator(settings_preserve=True)

    assert _run(coordinator, preserve_real_shape=False) is False


def test_settings_still_decide_when_the_dialog_says_nothing() -> None:
    """O botão da aba de Zonas e o fluxo pré-gravado não passam o argumento."""
    assert _run(_coordinator(settings_preserve=True), preserve_real_shape=None) is True
    assert _run(_coordinator(settings_preserve=False), preserve_real_shape=None) is False


def test_choice_is_remembered_for_the_zone_tab_auto_detect_button() -> None:
    """Reexecutar pela aba de Zonas mantém a escolha do diálogo.

    Sem memorizar, a primeira detecção preservaria a máscara e a segunda voltaria
    ao retângulo — o mesmo defeito, agora intermitente.
    """
    coordinator = _coordinator(settings_preserve=False)

    assert _run(coordinator, preserve_real_shape=True) is True
    assert _run(coordinator, preserve_real_shape=None) is True


def test_project_value_wins_over_the_dialog_argument() -> None:
    """Num projeto, o valor persistido continua mandando.

    O argumento existe para o fluxo SEM projeto. Se passasse à frente,
    uma sessão ao vivo dentro de projeto herdaria a escolha do último diálogo
    avulso.
    """
    coordinator = _coordinator(
        settings_preserve=False,
        project_data={"preserve_real_aquarium_shape": False},
    )

    assert _run(coordinator, preserve_real_shape=True) is False


# ---------------------------------------------------------------------------
# O resolvedor, diretamente
# ---------------------------------------------------------------------------


def test_resolver_precedence_is_request_then_project_then_settings() -> None:
    settings = _settings(preserve=False)
    project = {"preserve_real_aquarium_shape": False}

    assert (
        resolve_arena_detection(
            project, settings, requested_preserve_real_shape=True
        ).preserve_real_shape
        is True
    )
    assert resolve_arena_detection(project, settings).preserve_real_shape is False
    assert resolve_arena_detection({}, _settings(preserve=True)).preserve_real_shape is True
    assert resolve_arena_detection({}, _settings(preserve=None)).preserve_real_shape is False


def test_resolver_treats_an_explicit_false_as_a_decision() -> None:
    """``False`` pedido vence um ``True`` do projeto — é o teste que separa
    "pediu o retângulo" de "não pediu nada"."""
    project = {"preserve_real_aquarium_shape": True}

    policy = resolve_arena_detection(project, None, requested_preserve_real_shape=False)

    assert policy.preserve_real_shape is False


def test_resolver_ignores_the_flag_for_a_box_model() -> None:
    """``uses_masks`` só é verdadeiro com 'seg' — um ``True`` parado é inerte.

    É o que permite ao diálogo guardar a escolha ao alternar para 'det' sem
    perdê-la, em vez de zerar a variável.
    """
    policy = resolve_arena_detection(
        {}, None, requested_method="det", requested_preserve_real_shape=True
    )

    assert policy.preserve_real_shape is True
    assert policy.uses_masks is False

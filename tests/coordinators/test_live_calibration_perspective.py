"""A perspectiva escolhida no diálogo tem de chegar à escolha do PESO.

O defeito
---------
Sessão real de 2026-09-05, fluxo ao vivo avulso, labirinto filmado de cima. O
usuário escolheu ``top_down`` no ``LiveAnalysisDialog`` e a auto-detecção
respondeu que não conseguia achar o aquário.

O log mostra ``perspective_resolved perspective=lateral has_project=False``: a
escolha nunca chegou. A cadeia de precedência terminava em
``settings.behavioral_analysis.aquarium_perspective``, sob o comentário de que
"LiveAnalysisDialog / SingleVideoConfigDialog escrevem" ali — mas só o SEGUNDO
escreve. O ``LiveAnalysisDialog`` devolve a perspectiva dentro de
``result["behavioral_analysis"]``, que só é lido mais tarde, ao montar o
``analysis_config`` da pós-análise — depois desta calibração já ter rodado. O
relatório saía com a perspectiva certa e o detector de arena com a errada.

Por que isso apagava a detecção inteira
---------------------------------------
Não é uma degradação sutil. Medido contra o quadro real da sessão:

* ``best_seg_lateral.pt`` numa cena top-down devolve UMA caixa de **altura
  zero** na borda inferior — ``(177, 720, 1134, 720)``, confiança 0,347. O
  portão de área de ``arena_candidate_selection`` (10% a 98% do quadro) a rejeita,
  corretamente, porque área zero não é um tanque. Sobram zero polígonos, em 30
  quadros, tanto a 0,05 quanto a 0,01.
* ``best_seg_topdown.pt`` acha o tanque no MESMO quadro: ``(236, 45, 1198,
  629)``, 61% da área, aprovado.

Ou seja: o portão estava certo, o modelo estava errado, e a mensagem final
("não foi possível detectar") descrevia o sintoma três camadas acima da causa.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from zebtrack.coordinators.live_calibration_coordinator import LiveCalibrationCoordinator


def _coordinator(*, settings_perspective: str | None, project_data: dict | None = None):
    """Coordinator cujo ``weight_manager`` registra a perspectiva pedida."""
    project_manager = MagicMock()
    project_manager.project_data = project_data if project_data is not None else {}
    # Sem projeto: é o fluxo ad-hoc, onde o defeito vive.
    project_manager.project_path = None

    weight_manager = MagicMock()
    weight_manager.get_weight_path_by_method.return_value = "fake_weights.pt"

    settings_obj = MagicMock()
    settings_obj.camera = SimpleNamespace(index=0)
    settings_obj.yolo_model = SimpleNamespace(confidence_threshold=0.05)
    settings_obj.model_selection = SimpleNamespace(aquarium_method="seg")
    settings_obj.behavioral_analysis = SimpleNamespace(aquarium_perspective=settings_perspective)

    return LiveCalibrationCoordinator(
        state_manager=MagicMock(),
        project_manager=project_manager,
        detector_service=MagicMock(),
        weight_manager=weight_manager,
        settings_obj=settings_obj,
        event_bus=MagicMock(),
        root=MagicMock(),
        view=None,
    )


def _run(coordinator, *, perspective: str | None) -> str | None:
    """Roda a calibração até a escolha do peso e devolve a perspectiva pedida.

    Tudo depois da seleção do peso é substituído: o alvo aqui é exclusivamente
    QUAL perspectiva chega ao ``weight_manager``.
    """
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
        ),
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
            stabilization_frames=4, show_preview=True, perspective=perspective
        )

    calls = coordinator.weight_manager.get_weight_path_by_method.call_args_list
    assert calls, "a calibração nunca chegou a pedir um peso"
    return calls[-1].kwargs.get("perspective")


def test_dialog_perspective_reaches_the_weight_manager() -> None:
    """O caso reportado: top_down escolhido, ``lateral`` nas settings."""
    coordinator = _coordinator(settings_perspective="lateral")

    assert _run(coordinator, perspective="top_down") == "top_down"


def test_settings_still_serve_when_the_dialog_says_nothing() -> None:
    """O ``SingleVideoConfigDialog`` escreve nas settings — esse caminho fica.

    Sem esta garantia, "consertar" o fluxo ao vivo teria quebrado a
    auto-detecção do vídeo único pré-gravado, que não passa perspectiva alguma
    por argumento.
    """
    coordinator = _coordinator(settings_perspective="top_down")

    assert _run(coordinator, perspective=None) == "top_down"


def test_project_data_wins_over_the_dialog_argument() -> None:
    """Num projeto, o valor persistido continua mandando.

    O argumento existe para o fluxo SEM projeto, exatamente como
    ``camera_index``. Se ele passasse à frente do ``project_data``, uma sessão
    ao vivo dentro de projeto passaria a detectar com a perspectiva do último
    diálogo avulso.
    """
    coordinator = _coordinator(
        settings_perspective="lateral",
        project_data={"behavioral_config": {"aquarium_perspective": "lateral"}},
    )

    assert _run(coordinator, perspective="top_down") == "lateral"


def test_perspective_is_remembered_for_the_zone_tab_auto_detect_button() -> None:
    """O botão "auto-detectar" da aba de Zonas reexecuta a calibração sozinho.

    Ele chama ``run_live_calibration`` direto (``single_video_workflow.
    _route_live_auto_detect``) e não tem o config do diálogo em mãos. Sem
    memorizar, a primeira detecção usaria top_down e a segunda voltaria a
    lateral — o mesmo defeito, agora intermitente, que é pior.
    """
    coordinator = _coordinator(settings_perspective="lateral")

    assert _run(coordinator, perspective="top_down") == "top_down"
    # Segunda passada, como a do botão: sem argumento nenhum.
    assert _run(coordinator, perspective=None) == "top_down"


def test_no_perspective_anywhere_leaves_the_choice_to_the_weight_manager() -> None:
    """Nada configurado devolve ``None``, não um palpite.

    Inventar ``lateral`` aqui é o que produziu o defeito original. ``None`` deixa
    o ``WeightManager`` aplicar o próprio fallback, que é onde essa decisão mora.
    """
    coordinator = _coordinator(settings_perspective=None)

    assert _run(coordinator, perspective=None) is None

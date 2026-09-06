"""A caixa que o TRACKER infla também tem de ser barrada.

O defeito
---------
Sessão real ao vivo de 2026-09-06, um peixe, aquário único. O animal aparece com
bbox de ~1.000 px²; quando some de vista ou fica muito tempo parado, o
``3_CoordMovimento`` passa a receber caixas de até **310.800 px²**, várias com
``x1`` NEGATIVO — começando fora do quadro. Variação de 3.000x no mesmo
``track_id``, 36 de 228 linhas acima de 50.000 px².

Elas não são detecções. São predições do filtro de Kalman do ByteTrack::

    bytetrack.no_matching_detection  track_bbox=[140,216,326,611]  best_iou=0.068

73 quadros da sessão foram pura predição, sem detecção casada.

Por que os portões existentes não pegavam
-----------------------------------------
* ``BboxAreaGate`` (o primeiro, ``label="single"``) filtra as DETECÇÕES **antes**
  do ``track()``. Nunca vê o que o tracker produz. Prova: replicando aquele
  portão, com as settings de produção, sobre as 228 linhas gravadas, ele rejeita
  49 (21,5%) — que estão no arquivo, logo não passaram por portão nenhum.
* O filtro de polígono no fim de ``track()`` existe pela MESMA causa — o próprio
  log dele diz ``tracks_moved_outside_polygon_by_kalman_filter`` — mas só pega a
  caixa que sai da arena. A que incha DENTRO dela passava.

Subir o limiar de confiança não era alternativa: mesmo a 0,50 sobravam caixas
gigantes e 58% das linhas boas seriam descartadas.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from zebtrack.core.detection.bbox_area_gate import BboxAreaGate

#: Um peixe típico da sessão medida: ~30x33 px.
FISH_AREA_BOX = (100, 100, 130, 133)

#: A predição inflada, com as proporções reais do log da sessão.
RUNAWAY_BOX = (140, 216, 326, 611)

#: O caso extremo gravado: 777x400, começando fora do quadro.
OFF_FRAME_BOX = (-169, 228, 608, 628)


def _det(box: tuple[int, int, int, int], track_id: int = 1) -> tuple:
    """Uma detecção rastreada no formato que ``track()`` devolve."""
    x1, y1, x2, y2 = box
    return (x1, y1, x2, y2, 0.9, track_id, 0)


def _warm(gate: BboxAreaGate, samples: int = 12) -> None:
    """Alimenta o portão com caixas de peixe até passar do warmup."""
    for _ in range(samples):
        gate.filter([_det(FISH_AREA_BOX)])


def test_runaway_prediction_is_rejected_after_warmup() -> None:
    """O caso reportado: caixa inflada DENTRO da arena."""
    gate = BboxAreaGate(enabled=True, ratio_max=3.0, window=30, warmup=10, label="t")
    _warm(gate)

    assert gate.filter([_det(RUNAWAY_BOX)]) == []


def test_the_off_frame_box_is_rejected() -> None:
    """A caixa que começa fora do quadro (``x1`` negativo) também cai."""
    gate = BboxAreaGate(enabled=True, ratio_max=3.0, window=30, warmup=10, label="t")
    _warm(gate)

    assert gate.filter([_det(OFF_FRAME_BOX)]) == []


def test_a_normal_position_still_passes() -> None:
    """O portão não pode custar as posições boas.

    Sem esta garantia o conserto trocaria caixas infladas por trajetória
    faltando, o que é igualmente ruim para a métrica.
    """
    gate = BboxAreaGate(enabled=True, ratio_max=3.0, window=30, warmup=10, label="t")
    _warm(gate)

    assert gate.filter([_det((200, 200, 232, 234))]) != []


def test_a_rejected_box_never_enters_the_baseline() -> None:
    """Uma rajada de caixas infladas não pode inflar o próprio limiar.

    É o que tornaria o portão inerte justamente na sessão em que ele é preciso:
    73 quadros seguidos de predição pura elevariam a mediana até tudo passar.
    """
    gate = BboxAreaGate(enabled=True, ratio_max=3.0, window=30, warmup=10, label="t")
    _warm(gate)

    for _ in range(50):
        gate.filter([_det(RUNAWAY_BOX)])

    # Depois da rajada, a caixa inflada continua sendo rejeitada.
    assert gate.filter([_det(RUNAWAY_BOX)]) == []
    assert gate.rejections == 51


def test_nothing_is_rejected_during_warmup() -> None:
    """Estatística fria não descarta dado real."""
    gate = BboxAreaGate(enabled=True, ratio_max=3.0, window=30, warmup=10, label="t")

    assert gate.filter([_det(RUNAWAY_BOX)]) != []


# ---------------------------------------------------------------------------
# O FIO: o portão precisa estar ligado dentro de ``track()``
# ---------------------------------------------------------------------------
#
# Os testes acima exercitam o portão isolado e continuam verdes se alguém
# remover a chamada de ``track()`` — foi o que aconteceu ao injetar o defeito de
# propósito. Estes dois dirigem o ``track()`` de verdade.


def _detector_ready_to_track():
    """Um ``SingleDetector`` com o mínimo para ``track()`` rodar.

    Construir um completo exigiria plugin e zonas reais; aqui o alvo é o trecho
    entre a saída do rastreador e o retorno.
    """
    import numpy as np

    from zebtrack.core.detection.single_detector import SingleDetector

    detector = object.__new__(SingleDetector)
    detector.settings = None
    detector._context = "tracking"
    detector._last_height = 720
    detector._last_width = 1280
    detector.base_height = 720
    detector.base_width = 1280
    detector._single_subject_mode = False
    detector._bbox_area_gate = BboxAreaGate.from_settings(None, label="single")
    detector._tracked_area_gate = BboxAreaGate.from_settings(None, label="single_tracked")
    # Polígono vazio desliga o filtro de polígono, isolando o de ÁREA: sem isso
    # um teste verde não distinguiria qual dos dois barrou a caixa.
    # ``cast`` mantem a anotacao de producao honesta: o atributo e um
    # ``ZoneScaler`` de verdade fora do teste.
    detector.zone_scaler = cast("Any", SimpleNamespace(scaled_polygon=np.array([])))
    return detector


def _track_one(detector, box: tuple[int, int, int, int]) -> list[tuple]:
    """Roda ``SingleDetector.track`` com o rastreador devolvendo ``box``."""
    from unittest.mock import patch

    from zebtrack.core.detection.single_detector import SingleDetector

    with (
        patch.object(SingleDetector, "_apply_byte_tracking", return_value=[_det(box)]),
        patch.object(SingleDetector, "_apply_simple_tracking", return_value=[_det(box)]),
    ):
        results, _err = SingleDetector.track(detector, [_det(box)], "live")
    return results


def test_track_drops_a_runaway_tracked_box() -> None:
    """A regressão que importa: o defeito reportado, pelo caminho real."""
    detector = _detector_ready_to_track()
    for _ in range(12):
        _track_one(detector, FISH_AREA_BOX)

    assert _track_one(detector, RUNAWAY_BOX) == []


def test_track_keeps_a_normal_tracked_box() -> None:
    """Controle: o fio não pode engolir as posições boas."""
    detector = _detector_ready_to_track()
    for _ in range(12):
        _track_one(detector, FISH_AREA_BOX)

    assert _track_one(detector, (200, 200, 232, 234)) != []


def test_reset_lets_the_next_video_relearn_its_own_scale() -> None:
    """Trocar de vídeo tem de zerar o baseline do portão do tracker.

    Sem isso, a escala do vídeo anterior decidiria sobre o novo exatamente na
    janela em que o portão ainda não tem dados próprios — e um aquário filmado
    mais de perto teria posições válidas descartadas.

    Comportamental de propósito: o histórico é construído RODANDO ``track()``, e
    o efeito do reset é verificado pelo que o portão passa a aceitar, não
    espiando atributos que o próprio teste tenha criado.
    """
    from zebtrack.core.detection.single_detector import SingleDetector

    detector = _detector_ready_to_track()
    for _ in range(12):
        _track_one(detector, FISH_AREA_BOX)

    # Com o baseline do peixe pequeno, a caixa grande cai.
    assert _track_one(detector, RUNAWAY_BOX) == []

    SingleDetector._reset_bbox_area_history(detector)

    # Depois do reset o portão está em warmup de novo e nada é descartado.
    assert _track_one(detector, RUNAWAY_BOX) != []

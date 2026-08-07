"""Captura de máscaras: gate de custo e alinhamento com o ``track_id``.

O ponto central é a REGRESSÃO DE PERFORMANCE: decodificar máscara custa tempo
de inferência a cada frame, e a esmagadora maioria das sessões não usa
``seg_overlap``. Um teste que só verificasse "com a flag ligada funciona"
deixaria passar o caso caro — a flag desligada continuar decodificando.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.detection.single_detector import SingleDetector
from zebtrack.core.services.mask_capture import should_capture_masks
from zebtrack.plugins.base import DetectorPlugin


class _SpyPlugin(DetectorPlugin):
    """Plugin que CONTA quantas vezes o decode de máscara foi pedido."""

    def __init__(self, contours: list[Any] | None = None) -> None:
        self.decode_calls = 0
        self.detect_calls = 0
        self._contours = contours or []
        self.class_names = {0: "aquarium", 1: "zebrafish"}

    def detect(self, frame, conf_threshold=None):
        self.detect_calls += 1
        if self._capture_masks:
            # Só o caminho de captura toca o decode — é exatamente esta
            # condição que os plugins reais implementam.
            self.decode_calls += 1
            self._frame_masks = list(self._contours)
        else:
            self._frame_masks = []
        return [(10, 10, 30, 30, 0.9, None, 1)]

    def pop_frame_masks(self):
        masks = self._frame_masks
        self._frame_masks = []
        return masks

    @staticmethod
    def get_name() -> str:
        return "spy"

    @property
    def model_input_shape(self) -> tuple[int, int]:
        return (640, 640)


def _detector(plugin: _SpyPlugin) -> SingleDetector:
    detector = SingleDetector(plugin=plugin, base_width=640, base_height=480)
    detector.set_zones(
        ZoneData(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]]),
        640,
        480,
    )
    return detector


def test_capture_disabled_never_decodes_masks() -> None:
    """REGRESSÃO DE PERFORMANCE: sem captura, zero decodificações.

    Este é o teste que protege o custo zero prometido por
    ``recorder.persist_masks=False``.
    """
    plugin = _SpyPlugin(contours=[np.array([[0, 0], [5, 0], [5, 5]])])
    plugin.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    plugin.detect(np.zeros((480, 640, 3), dtype=np.uint8))

    assert plugin.detect_calls == 2
    assert plugin.decode_calls == 0
    assert plugin.pop_frame_masks() == []


def test_capture_enabled_decodes_once_per_frame() -> None:
    plugin = _SpyPlugin(contours=[np.array([[0, 0], [5, 0], [5, 5]])])
    plugin.set_mask_capture(True)

    plugin.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert plugin.decode_calls == 1
    assert len(plugin.pop_frame_masks()) == 1


def test_pop_frame_masks_consumes_the_buffer() -> None:
    """Segunda chamada sem novo ``detect()`` devolve vazio.

    Devolver de novo o frame anterior gravaria uma máscara velha com o
    ``track_id`` de outro frame — pior que máscara nenhuma.
    """
    plugin = _SpyPlugin(contours=[np.array([[0, 0], [5, 0], [5, 5]])])
    plugin.set_mask_capture(True)
    plugin.detect(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(plugin.pop_frame_masks()) == 1
    assert plugin.pop_frame_masks() == []


def test_detector_delegates_capture_to_the_plugin() -> None:
    plugin = _SpyPlugin()
    detector = _detector(plugin)

    detector.set_mask_capture(True)
    assert plugin._capture_masks is True

    detector.set_mask_capture(False)
    assert plugin._capture_masks is False


def test_masks_are_keyed_by_track_id_after_tracking() -> None:
    """A máscara chega ao recorder com o ``track_id`` da linha da trajetória.

    Sem a indexação por bbox, a máscara do peixe 1 poderia ser gravada com o
    ``track_id`` do peixe 2 — o join no consumo ficaria correto no formato e
    errado no conteúdo.
    """
    contour = np.array([[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [10.0, 30.0]])
    plugin = _SpyPlugin(contours=[contour])
    detector = _detector(plugin)
    detector.set_mask_capture(True)

    detections, _ = detector.detect(
        np.zeros((480, 640, 3), dtype=np.uint8), project_type="pre-recorded"
    )
    assert detections, "a detecção precisa sobreviver ao filtro de polígono"

    by_track = detector.pop_track_masks(detections)
    track_ids = {int(det[5]) for det in detections if det[5] is not None}
    assert set(by_track) == track_ids
    for points in by_track.values():
        assert points.shape == (4, 2)


def test_pop_track_masks_consumes_the_index() -> None:
    contour = np.array([[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [10.0, 30.0]])
    detector = _detector(_SpyPlugin(contours=[contour]))
    detector.set_mask_capture(True)

    detections, _ = detector.detect(
        np.zeros((480, 640, 3), dtype=np.uint8), project_type="pre-recorded"
    )
    assert detector.pop_track_masks(detections)
    assert detector.pop_track_masks(detections) == {}


def test_degenerate_contour_is_not_indexed() -> None:
    """Menos de 3 pontos não vira polígono e não entra no índice."""
    detector = _detector(_SpyPlugin(contours=[np.array([[10.0, 10.0], [30.0, 30.0]])]))
    detector.set_mask_capture(True)

    detections, _ = detector.detect(
        np.zeros((480, 640, 3), dtype=np.uint8), project_type="pre-recorded"
    )
    assert detector.pop_track_masks(detections) == {}


# ---------------------------------------------------------------------------
# O gate de três condições
# ---------------------------------------------------------------------------


def _settings(persist: bool, animal_method: str, rule: str) -> Any:
    settings = MagicMock()
    settings.recorder.persist_masks = persist
    settings.model_selection.animal_method = animal_method
    settings.roi_inclusion_rule = rule
    # ``resolve_roi_rule`` lê os demais campos por ``getattr``; um MagicMock
    # devolveria objetos truthy que não são números, e o resolvedor cairia no
    # default COM log. Fixar aqui mantém o teste sobre a decisão, não sobre a
    # normalização.
    settings.roi_min_bbox_overlap_ratio = 0.5
    settings.roi_min_seg_overlap_ratio = 0.3
    settings.roi_buffer_radius_value = 0.5
    settings.roi_bbox_overlap_basis = "bbox"
    settings.roi_flutter_enter_frames = 2
    settings.roi_flutter_exit_frames = 3
    settings.roi_min_visit_s = 0.2
    settings.roi_min_gap_s = 0.0
    settings.roi_max_gap_s = None
    return settings


@pytest.mark.parametrize(
    ("persist", "method", "rule", "expected"),
    [
        (True, "seg", "seg_overlap", True),
        (False, "seg", "seg_overlap", False),
        (True, "det", "seg_overlap", False),
        (True, "seg", "bbox_intersects", False),
        (True, "seg", "centroid_in", False),
    ],
    ids=[
        "tres_condicoes_valem",
        "flag_desligada",
        "modelo_det_nao_produz_mascara",
        "regra_nao_usa_mascara",
        "regra_de_centroide",
    ],
)
def test_capture_requires_all_three_conditions(persist, method, rule, expected) -> None:
    """Nenhuma das três condições sozinha basta.

    Espalhar essa conjunção pelos pipelines de gravação garantiria que eles
    divergissem; ela mora num lugar só.
    """
    assert should_capture_masks(_settings(persist, method, rule)) is expected


def test_project_override_of_the_rule_counts() -> None:
    """Um projeto com ``seg_overlap`` sobre um global ``bbox_intersects`` grava.

    É a mesma precedência (projeto > global) que o relatório vai aplicar
    depois. Sem isso a sessão gravaria sem máscaras e degradaria no relatório.
    """
    settings = _settings(True, "seg", "bbox_intersects")
    assert should_capture_masks(settings) is False
    assert (
        should_capture_masks(settings, {"roi_settings": {"roi_inclusion_rule": "seg_overlap"}})
        is True
    )


def test_no_settings_means_no_capture() -> None:
    assert should_capture_masks(None) is False

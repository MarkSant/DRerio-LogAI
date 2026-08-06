"""Ocupação de ROI por frame para o loop de comandos Arduino ao vivo.

Geometria pura: dados os polígonos de ROI já escalados (espaço de pixels, como
produzidos por ``ZoneScaler``) e as detecções do frame atual, devolve o conjunto
de ROIs ocupadas por ao menos um animal (escopo "any-track").

A regra de inclusão vem da mesma fonte canônica que o relatório
(:mod:`zebtrack.core.services.roi_rule_resolver`) e é avaliada com **shapely**,
os mesmos predicados usados pelo ``ROIAnalyzer`` — sem isso o Arduino disparava
sempre por centroide (``cv2.pointPolygonTest``) e o ``log_eventos`` do relatório
podia contar entradas que o LED nunca acendeu.

Os polígonos preparados (e dilatados, quando a regra pede) são construídos uma
única vez no construtor: nada de geometria nova por frame.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import shapely
import structlog
from shapely import prepare
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from zebtrack.core.services.roi_rule_resolver import RoiRuleConfig

log = structlog.get_logger()

# A cada N chamadas o custo médio do avaliador vai para o log de debug. O loop
# roda 1 vez a cada ``analysis_interval_frames`` frames (default 10), então o
# custo por frame capturado é uma fração disto.
_TIMING_LOG_EVERY = 100

# Mesmo predicado DE-9IM do ``ROIAnalyzer`` para o limiar 0 ("interiores se
# tocam" = sobreposição de área não-nula, tangência excluída).
_INTERIORS_INTERSECT = "T********"


class ArduinoRoiEvaluator:
    """Mapeia detecções para o conjunto de ROIs ocupadas.

    Args:
        roi_names: nomes das ROIs, alinhados por índice com ``roi_polygons``.
        roi_polygons: polígonos escalados em pixels do frame (ex.:
            ``ZoneScaler.scaled_roi_polygons``). Cada um é um array ``(N, 2)``.
            Polígonos vazios/degenerados e nomes sem polígono são ignorados.
        rule_config: regra de inclusão resolvida. ``None`` usa o default de
            :class:`RoiRuleConfig` (o mesmo default de ``Settings``).
        px_per_cm: fator para converter ``buffer_radius_value`` (em cm, quando
            há calibração) para pixels. O ``ROIAnalyzer`` usa
            ``sqrt(pixelcm_x * pixelcm_y)``; passe o mesmo valor para que as
            duas geometrias coincidam. Sem calibração, ``1.0`` mantém o raio em
            pixels.
    """

    def __init__(
        self,
        roi_names: Sequence[str],
        roi_polygons: Sequence[np.ndarray | Sequence[Sequence[float]]],
        rule_config: RoiRuleConfig | None = None,
        px_per_cm: float = 1.0,
    ) -> None:
        self._config = rule_config or RoiRuleConfig()
        self._rule = self._effective_rule(self._config.rule)
        self._px_per_cm = float(px_per_cm) if px_per_cm and px_per_cm > 0 else 1.0

        # A área da ROI é o denominador alternativo da fração de sobreposição
        # (``bbox_overlap_basis``) — pré-calculada aqui, nunca por frame.
        self._rois: list[tuple[str, BaseGeometry, float]] = []
        for name, polygon in zip(roi_names, roi_polygons, strict=False):
            geometry = self._build_geometry(polygon)
            if geometry is None:
                continue
            self._rois.append((str(name), geometry, float(shapely.area(geometry))))

        self._calls = 0
        self._elapsed_s = 0.0
        self._warned_missing_bbox = False

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    @staticmethod
    def _effective_rule(rule: str) -> str:
        """Regra realmente aplicável ao vivo.

        ``seg_overlap`` exige máscaras de segmentação que a sessão ao vivo não
        persiste (o ``ROIAnalyzer`` levanta ``ValueError``). Aqui o loop não
        pode quebrar: cai para ``centroid_in`` e registra o fallback.
        """
        if rule == "seg_overlap":
            log.warning(
                "arduino_roi_evaluator.seg_overlap_unsupported_fallback",
                fallback="centroid_in",
            )
            return "centroid_in"
        return rule

    def _build_geometry(
        self, polygon: np.ndarray | Sequence[Sequence[float]]
    ) -> BaseGeometry | None:
        """Constrói (e dilata, se a regra pedir) o polígono preparado da ROI."""
        poly = np.asarray(polygon, dtype=np.float64)
        if poly.size == 0 or poly.ndim != 2 or poly.shape[0] < 3:
            return None

        geometry: BaseGeometry = Polygon(poly)
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if geometry.is_empty:
            return None

        if self._rule == "centroid_in_on_buffered_roi":
            # Dilatação feita UMA vez, aqui: nunca por frame.
            geometry = geometry.buffer(self._config.buffer_radius_value * self._px_per_cm)
            if geometry.is_empty:
                return None

        prepare(geometry)
        return geometry

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @property
    def roi_names(self) -> list[str]:
        """Nomes das ROIs com polígono utilizável."""
        return [name for name, _, _ in self._rois]

    @property
    def rule(self) -> str:
        """Regra de inclusão efetivamente aplicada (após fallbacks)."""
        return self._rule

    def has_rois(self) -> bool:
        """True quando há ao menos um polígono de ROI utilizável."""
        return bool(self._rois)

    def occupied_rois(self, detections: Iterable[Sequence[float]]) -> set[str]:
        """Conjunto de ROIs ocupadas por ao menos uma detecção.

        Args:
            detections: itens ``(x1, y1, x2, y2)`` (bbox, espaço de pixels do
                frame) ou ``(cx, cy)`` (apenas o centroide — caminho
                compatível com chamadores antigos). Para ``bbox_intersects``,
                uma caixa sem área (centroide, ou um dos lados zerado) não
                permite calcular fração de área: a avaliação cai para
                contenção do ponto e o fallback é logado uma vez.
        """
        if not self._rois:
            return set()

        started = time.perf_counter()
        occupied: set[str] = set()
        for detection in detections:
            box = self._as_bbox(detection)
            if box is None:
                continue
            if self._occupy(box, occupied):
                break  # todas as ROIs já ocupadas — não há o que testar
        self._record_timing(started)
        return occupied

    @staticmethod
    def centroid_of_bbox(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
        """Centroide (ponto central) de uma bounding box."""
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    @staticmethod
    def _as_bbox(detection: Sequence[float]) -> tuple[float, float, float, float] | None:
        """Normaliza a detecção para ``(x1, y1, x2, y2)``.

        Um centroide vira uma caixa degenerada (área zero) — o que é suficiente
        para as regras de centroide e sinalizado para as de bbox.
        """
        try:
            values = [float(v) for v in detection]
        except (TypeError, ValueError):
            return None
        if len(values) >= 4:
            x1, y1, x2, y2 = values[0], values[1], values[2], values[3]
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if len(values) == 2:
            cx, cy = values
            return (cx, cy, cx, cy)
        return None

    def _occupy(self, box: tuple[float, float, float, float], occupied: set[str]) -> bool:
        """Testa uma detecção contra as ROIs pendentes. True se todas ocuparam."""
        x1, y1, x2, y2 = box
        centroid = shapely.points((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        # A fração de sobreposição divide pela ÁREA da caixa: exige as duas
        # dimensões positivas. Uma caixa degenerada (um lado zerado) tem área
        # zero e não é avaliável por essa regra — cai no centroide, mas com o
        # aviso, para não mascarar detecção inválida.
        has_area = x2 > x1 and y2 > y1
        use_bbox = self._rule == "bbox_intersects" and has_area
        if self._rule == "bbox_intersects" and not has_area:
            self._warn_missing_bbox()

        bbox_geom = shapely.box(x1, y1, x2, y2) if use_bbox else None
        bbox_area = shapely.area(bbox_geom) if bbox_geom is not None else 0.0

        for name, geometry, roi_area in self._rois:
            if name in occupied:
                continue
            if bbox_geom is not None and bbox_area > 0:
                inside = self._bbox_inside(geometry, bbox_geom, bbox_area, roi_area)
            else:
                inside = bool(shapely.contains(geometry, centroid))
            if inside:
                occupied.add(name)
        return len(occupied) == len(self._rois)

    def _bbox_inside(
        self,
        geometry: BaseGeometry,
        bbox_geom: BaseGeometry,
        bbox_area: float,
        roi_area: float,
    ) -> bool:
        """Aplica a regra de área com o mesmo cálculo do ``ROIAnalyzer``.

        Divergir aqui é o bug que o resolvedor canônico existe para impedir: o
        relatório contaria uma entrada que o LED nunca acendeu.
        """
        if self._config.overlap_any:
            # Limiar 0: sobreposição de área não-nula, sem fração mínima.
            return bool(shapely.relate_pattern(geometry, bbox_geom, _INTERIORS_INTERSECT))

        intersection_area = float(shapely.area(shapely.intersection(geometry, bbox_geom)))
        basis = self._config.bbox_overlap_basis
        by_bbox = intersection_area / bbox_area
        by_roi = (intersection_area / roi_area) if roi_area > 0 else 0.0
        if basis == "roi":
            ratio = by_roi
        elif basis == "max":
            ratio = max(by_bbox, by_roi)
        else:
            ratio = by_bbox
        return bool(ratio >= self._config.min_bbox_overlap_ratio)

    def _warn_missing_bbox(self) -> None:
        """Avisa uma única vez que a regra de bbox recebeu caixa sem área."""
        if self._warned_missing_bbox:
            return
        self._warned_missing_bbox = True
        log.warning(
            "arduino_roi_evaluator.bbox_rule_without_bbox_fallback",
            rule=self._rule,
            fallback="centroid_in",
        )

    def _record_timing(self, started: float) -> None:
        """Acumula o custo do avaliador e o reporta a cada ``_TIMING_LOG_EVERY``."""
        self._elapsed_s += time.perf_counter() - started
        self._calls += 1
        if self._calls % _TIMING_LOG_EVERY:
            return
        log.debug(
            "arduino_roi_evaluator.timing",
            calls=self._calls,
            rois=len(self._rois),
            rule=self._rule,
            avg_ms=round(self._elapsed_s / self._calls * 1000.0, 4),
        )

    def stats(self) -> dict[str, Any]:
        """Contadores de custo acumulados (usado por testes e diagnóstico)."""
        return {
            "calls": self._calls,
            "avg_ms": (self._elapsed_s / self._calls * 1000.0) if self._calls else 0.0,
            "rule": self._rule,
            "rois": len(self._rois),
        }

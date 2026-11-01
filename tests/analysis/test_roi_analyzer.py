"""
Tests for the ROI analyzer with configurable inclusion rules.
"""

import unittest
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import (
    ROI,
    ROIAnalyzer,
    _entry_counts,
    _latency_to_first_entry,
    _roi_latencies,
)


class TestROIAnalyzerInclusionRules(unittest.TestCase):
    """Test the configurable ROI inclusion rules."""

    def setUp(self):
        """Set up test fixtures with synthetic trajectory data."""
        # Create synthetic trajectory data
        timestamps = pd.date_range(start="2023-01-01", periods=10, freq="100ms")

        # Create trajectory that moves from left to right, crossing ROI boundary
        self.trajectory_df = pd.DataFrame(
            {
                "x_cm_smoothed": np.linspace(5, 25, 10),  # moves from 5cm to 25cm
                "y_cm_smoothed": np.full(10, 15),  # stays at y=15cm
                "x_center_px": np.linspace(50, 250, 10),  # px equivalent
                "y_center_px": np.full(10, 150),
                "x1": np.linspace(45, 245, 10),  # bbox coordinates
                "y1": np.full(10, 145),
                "x2": np.linspace(55, 255, 10),
                "y2": np.full(10, 155),
            },
            index=timestamps,
        )

        # Mock behavioral analyzer
        self.mock_b_analyzer = MagicMock()
        self.mock_b_analyzer.trajectory_data = self.trajectory_df.copy()
        self.mock_b_analyzer.pixelcm_x = 10.0  # 10 pixels per cm
        self.mock_b_analyzer._pixelcm_x = 10.0  # For internal access
        self.mock_b_analyzer.pixelcm_y = 10.0
        self.mock_b_analyzer._pixelcm_y = 10.0  # For internal access
        self.mock_b_analyzer._video_height_px = 300  # Video height in pixels

        # Create a simple rectangular ROI from x=10-20cm, y=10-20cm
        self.roi_polygon = Polygon([(10, 10), (20, 10), (20, 20), (10, 20)])
        self.test_roi = ROI(name="TestROI", geometry=self.roi_polygon, coordinate_space="cm")

    def test_centroid_in_rule(self):
        """Test the centroid_in rule (behaves like the original implementation)."""
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="centroid_in",
        )

        # Check which frames have centroid inside ROI
        # The trajectory moves from 5->25cm, so it should be inside from roughly
        # frame 2-7
        stable_col = analyzer._trajectory["in_TestROI_stable"]

        # First few frames should be outside (x < 10)
        self.assertFalse(stable_col.iloc[0])
        self.assertFalse(stable_col.iloc[1])

        # Middle frames should be inside (10 <= x <= 20)
        self.assertTrue(stable_col.iloc[4])  # x ≈ 15

        # Last frames should be outside (x > 20)
        self.assertFalse(stable_col.iloc[8])
        self.assertFalse(stable_col.iloc[9])

    def test_centroid_in_on_buffered_roi_rule(self):
        """Test the centroid_in_on_buffered_roi rule."""
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="centroid_in_on_buffered_roi",
            buffer_radius_value=2.0,  # 2cm buffer
        )

        stable_col = analyzer._trajectory["in_TestROI_stable"]

        # With 2cm buffer, effective ROI is 8-22cm in x direction
        # Should detect entry earlier than centroid_in
        self.assertTrue(stable_col.iloc[2])  # x ≈ 9.4, should be inside buffered ROI
        self.assertTrue(stable_col.iloc[7])  # x ≈ 20.5, should be inside buffered ROI

    def test_bbox_intersects_rule(self):
        """Test the bbox_intersects rule."""
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="bbox_intersects",
            min_bbox_overlap_ratio=0.1,  # 10% overlap required
        )

        stable_col = analyzer._trajectory["in_TestROI_stable"]

        # bbox_intersects should detect presence when bbox overlaps with ROI
        # Since our bboxes are 10x10 units and ROI is 10x10 cm, expect generous overlap
        entry_frames = stable_col.sum()
        self.assertGreater(entry_frames, 0)  # Should detect some frames as inside

    def test_bbox_intersects_missing_columns_error(self):
        """Test that bbox_intersects raises clear error when bbox columns are
        missing."""
        # Remove bbox columns
        trajectory_without_bbox = self.trajectory_df.drop(columns=["x1", "y1", "x2", "y2"])
        self.mock_b_analyzer.trajectory_data = trajectory_without_bbox

        with self.assertRaises(ValueError) as context:
            ROIAnalyzer(
                behavior_analyzer=self.mock_b_analyzer,
                rois=[self.test_roi],
                flutter_n_frames=1,
                inclusion_rule="bbox_intersects",
            )

        self.assertIn("bbox_intersects rule requires the bbox columns", str(context.exception))

    def test_seg_overlap_without_masks_degrades_instead_of_raising(self):
        """Sem sidecar, ``seg_overlap`` cai para ``bbox_intersects`` COM aviso.

        Era uma exceção incondicional: escolher a regra na UI matava a análise
        inteira. A degradação declarada é o contrato novo — o relatório sai, e
        diz no apêndice de validação que saiu com outra regra.
        """
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="seg_overlap",
        )

        warnings = analyzer.degradation_warnings
        self.assertEqual(len(warnings), 1)
        self.assertIn("seg_overlap", warnings[0])
        self.assertIn("bbox_intersects", warnings[0])

        # E o resultado é o MESMO que a regra de fallback produziria.
        fallback = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="bbox_intersects",
        )
        pd.testing.assert_series_equal(
            analyzer._trajectory["in_TestROI_stable"],
            fallback._trajectory["in_TestROI_stable"],
        )

    def test_coordinate_space_fallback_to_px(self):
        """Test that analyzer falls back to pixel coordinates when cm coords are
        unavailable."""
        # Remove cm coordinates
        trajectory_px_only = self.trajectory_df.drop(columns=["x_cm_smoothed", "y_cm_smoothed"])
        self.mock_b_analyzer.trajectory_data = trajectory_px_only

        # ROI in px coordinates (scaled up by 10x from cm)
        roi_polygon_px = Polygon([(100, 100), (200, 100), (200, 200), (100, 200)])
        roi_px = ROI(name="TestROI", geometry=roi_polygon_px, coordinate_space="px")

        # Should work with px coordinates
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[roi_px],
            flutter_n_frames=1,
            inclusion_rule="centroid_in",
        )

        # Should have calculated some presence
        stable_col = analyzer._trajectory["in_TestROI_stable"]
        self.assertIsInstance(stable_col.iloc[0], (bool, np.bool_))

    def test_coordinate_space_fallback_to_derived_bbox_center(self):
        """Test fallback to bbox-derived center coordinates."""
        # Remove both cm and center_px coordinates, keep only bbox
        trajectory_bbox_only = self.trajectory_df.drop(
            columns=["x_cm_smoothed", "y_cm_smoothed", "x_center_px", "y_center_px"]
        )
        self.mock_b_analyzer.trajectory_data = trajectory_bbox_only

        # ROI in px coordinates
        roi_polygon_px = Polygon([(200, 100), (300, 100), (300, 200), (200, 200)])
        roi_px = ROI(name="TestROI", geometry=roi_polygon_px, coordinate_space="px")

        # Should work by deriving center from bbox
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[roi_px],
            flutter_n_frames=1,
            inclusion_rule="centroid_in",
        )

        # Should have calculated some presence
        stable_col = analyzer._trajectory["in_TestROI_stable"]
        self.assertIsInstance(stable_col.iloc[0], (bool, np.bool_))

    def test_invalid_inclusion_rule(self):
        """Test error handling for invalid inclusion rule."""
        with self.assertRaises(ValueError) as context:
            ROIAnalyzer(
                behavior_analyzer=self.mock_b_analyzer,
                rois=[self.test_roi],
                flutter_n_frames=1,
                inclusion_rule="invalid_rule",
            )

        self.assertIn("Unknown inclusion rule: invalid_rule", str(context.exception))


def _px_analyzer(bboxes, roi_polygon, **kwargs):
    """ROIAnalyzer sobre geometria FABRICADA em pixels.

    ``coordinate_space="px"`` evita a transformação cm→px: o que se escreve no
    teste é exatamente o que a regra vê, então os valores esperados podem ser
    calculados à mão.

    Args:
        bboxes: sequência de ``(x1, y1, x2, y2)``, uma por frame.
        roi_polygon: polígono da ROI, já em pixels.
        **kwargs: repassados ao ``ROIAnalyzer`` (regra, limiar, base…).
    """
    frames = list(bboxes)
    timestamps = pd.date_range(start="2023-01-01", periods=len(frames), freq="100ms")
    trajectory = pd.DataFrame(
        {
            "x1": [b[0] for b in frames],
            "y1": [b[1] for b in frames],
            "x2": [b[2] for b in frames],
            "y2": [b[3] for b in frames],
            "x_center_px": [(b[0] + b[2]) / 2 for b in frames],
            "y_center_px": [(b[1] + b[3]) / 2 for b in frames],
        },
        index=timestamps,
    )

    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 0

    kwargs.setdefault("inclusion_rule", "bbox_intersects")
    # Harness de GEOMETRIA: o que se mede aqui é a regra de inclusão frame a
    # frame. Debounce e filtro de duração ficam neutros de propósito — as
    # séries têm 1 ou 2 frames, e o limiar de visita (0.2 s por padrão)
    # descartaria a visita inteira antes de a geometria dizer qualquer coisa.
    kwargs.setdefault("flutter_n_frames", 1)
    kwargs.setdefault("min_visit_s", 0.0)
    kwargs.setdefault("min_gap_s", 0.0)
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name="R", geometry=roi_polygon, coordinate_space="px")],
        **kwargs,
    )


class TestBboxOverlapBasis(unittest.TestCase):
    """Numéricos da fração de sobreposição: geometria fabricada, valor à mão.

    Uma bbox 20x20 px (área 400) contém inteiramente uma ROI 10x10 px
    (área 100). A interseção é a própria ROI: 100 px².

        base "bbox" -> 100/400 = 0.25
        base "roi"  -> 100/100 = 1.00
        base "max"  -> max(0.25, 1.00) = 1.00

    É o regime que motiva a opção: com a base histórica, cobrir 100% de uma
    zona pequena ainda marca 0.25 e reprova em qualquer limiar >= 0.3.
    """

    BBOX = (0.0, 0.0, 20.0, 20.0)
    ROI_POLY = Polygon([(5, 5), (15, 5), (15, 15), (5, 15)])

    def _presence(self, **kwargs):
        analyzer = _px_analyzer([self.BBOX], self.ROI_POLY, **kwargs)
        return bool(analyzer._trajectory["in_R_stable"].iloc[0])

    def test_basis_bbox_is_quarter(self):
        self.assertTrue(self._presence(min_bbox_overlap_ratio=0.25, bbox_overlap_basis="bbox"))
        self.assertFalse(self._presence(min_bbox_overlap_ratio=0.26, bbox_overlap_basis="bbox"))

    def test_basis_roi_is_full_coverage(self):
        self.assertTrue(self._presence(min_bbox_overlap_ratio=1.0, bbox_overlap_basis="roi"))

    def test_basis_max_takes_the_larger(self):
        self.assertTrue(self._presence(min_bbox_overlap_ratio=1.0, bbox_overlap_basis="max"))

    def test_default_basis_reproduces_the_historical_numbers(self):
        """Regressão: sem configurar a base, o resultado é o de antes do campo.

        Se alguém trocar o default de ``bbox_overlap_basis``, este teste cai —
        é o que impede a mudança silenciosa de medida.
        """
        for threshold in (0.05, 0.10, 0.25, 0.26, 0.5):
            explicit = self._presence(min_bbox_overlap_ratio=threshold, bbox_overlap_basis="bbox")
            implicit = self._presence(min_bbox_overlap_ratio=threshold)
            self.assertEqual(explicit, implicit, f"limiar {threshold}")
            self.assertEqual(implicit, threshold <= 0.25, f"limiar {threshold}")

    def test_zero_ratio_is_not_silently_replaced_by_the_default(self):
        """``x or default`` trocaria o 0.0 explícito por 0.10 — regressão coberta."""
        analyzer = _px_analyzer([self.BBOX], self.ROI_POLY, min_bbox_overlap_ratio=0.0)
        self.assertEqual(analyzer._min_bbox_overlap_ratio, 0.0)
        self.assertTrue(analyzer._overlap_any)

    def test_out_of_range_ratio_falls_back_to_the_default(self):
        """Limiar inválido não vira "qualquer sobreposição" nem passa reto.

        Um negativo é o caso perigoso nas duas direções: tratado como o caso
        especial do 0, mascara entrada inválida; deixado passar para a razão,
        `ratio >= negativo` vale até para caixas que não tocam a ROI.
        """
        for bad in (-0.5, 1.5, float("nan")):
            with self.subTest(bad=bad):
                analyzer = _px_analyzer([self.BBOX], self.ROI_POLY, min_bbox_overlap_ratio=bad)
                self.assertEqual(analyzer._min_bbox_overlap_ratio, 0.10)
                self.assertFalse(analyzer._overlap_any)

    def test_negative_ratio_does_not_include_a_disjoint_bbox(self):
        """Fecha o buraco concreto: caixa fora da ROI segue fora com limiar negativo."""
        disjoint = (500.0, 500.0, 520.0, 520.0)
        analyzer = _px_analyzer([disjoint], self.ROI_POLY, min_bbox_overlap_ratio=-0.5)
        self.assertFalse(bool(analyzer._trajectory["in_R_stable"].iloc[0]))

    def test_unknown_rule_still_raises_after_sanitization(self):
        """A REGRA segue crua: normalizar os parâmetros não pode calar o erro."""
        with self.assertRaises(ValueError) as ctx:
            _px_analyzer([self.BBOX], self.ROI_POLY, inclusion_rule="regra_inexistente")
        self.assertIn("Unknown inclusion rule", str(ctx.exception))


class TestZeroThresholdIsPureIntersection(unittest.TestCase):
    """Limiar 0: sobreposição de área não-nula conta, tangência não.

    ROI 10x10 px na origem. Frame 0 encosta na borda direita (interseção de
    área ZERO); frame 1 invade 1 px². ``shapely.intersects`` devolveria True
    para os dois — por isso a regra usa o predicado de interiores.
    """

    ROI_POLY = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    TANGENT = (10.0, 0.0, 20.0, 10.0)  # encosta em x=10: interseção de área 0
    # Invade 1x1 px = 1 px² de interseção numa caixa de 20x1 px: fração 0.05,
    # abaixo do limiar default (0.10) e acima de zero.
    ONE_PIXEL = (9.0, 0.0, 29.0, 1.0)

    def test_tangency_is_not_overlap_and_one_pixel_is(self):
        analyzer = _px_analyzer(
            [self.TANGENT, self.ONE_PIXEL], self.ROI_POLY, min_bbox_overlap_ratio=0.0
        )
        presence = analyzer._trajectory["in_R_stable"]
        self.assertFalse(bool(presence.iloc[0]), "tangência não é sobreposição")
        self.assertTrue(bool(presence.iloc[1]), "1 px² de interseção é sobreposição")

    def test_one_pixel_fails_the_default_threshold(self):
        """O mesmo 1 px² reprova no limiar default — o 0 não é redundante."""
        analyzer = _px_analyzer([self.TANGENT, self.ONE_PIXEL], self.ROI_POLY)
        presence = analyzer._trajectory["in_R_stable"]
        self.assertFalse(bool(presence.iloc[0]))
        self.assertFalse(bool(presence.iloc[1]))


# ---------------------------------------------------------------------------
# Latency to first entry: rising edge, explicit t0, present at start, censoring
# ---------------------------------------------------------------------------

_INSIDE_BOX = (40.0, 40.0, 60.0, 60.0)
_OUTSIDE_BOX = (400.0, 400.0, 420.0, 420.0)
_SQUARE = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])


def _pattern_analyzer(pattern, start_s=0.0, step_s=0.1, **kwargs):
    """ROIAnalyzer whose RAW presence in ROI ``R`` is exactly ``pattern``.

    The index is a ``TimedeltaIndex`` starting at ``start_s`` -- the shape the
    behavioural analyser produces from the recorded PTS -- so explicit ``t0``
    values are seconds on that same clock.
    """
    boxes = [_INSIDE_BOX if flag else _OUTSIDE_BOX for flag in pattern]
    index = pd.to_timedelta(start_s + np.arange(len(boxes)) * step_s, unit="s")
    trajectory = pd.DataFrame(
        {
            "x1": [b[0] for b in boxes],
            "y1": [b[1] for b in boxes],
            "x2": [b[2] for b in boxes],
            "y2": [b[3] for b in boxes],
            "x_center_px": [(b[0] + b[2]) / 2 for b in boxes],
            "y_center_px": [(b[1] + b[3]) / 2 for b in boxes],
            "x_cm_smoothed": [(b[0] + b[2]) / 2 for b in boxes],
            "y_cm_smoothed": [(b[1] + b[3]) / 2 for b in boxes],
        },
        index=index,
    )
    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 0
    kwargs.setdefault("inclusion_rule", "centroid_in")
    if "flutter_enter_frames" not in kwargs:
        kwargs.setdefault("flutter_n_frames", 1)
    kwargs.setdefault("min_visit_s", 0.0)
    kwargs.setdefault("min_gap_s", 0.0)
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name="R", geometry=_SQUARE, coordinate_space="px")],
        **kwargs,
    )


class TestLatencyRisingEdge:
    """The first ENTRY, never the first change of state."""

    def test_entry_from_outside_is_measured_from_the_first_row(self):
        analyzer = _pattern_analyzer([False, False, False, True, True], start_s=5.0)

        detail = analyzer.get_latency_details()["R"]

        assert detail.latency_s == pytest.approx(0.3)
        assert detail.present_at_start is False
        assert detail.censored is False
        assert analyzer.get_latency_to_first_entry() == {"R": pytest.approx(0.3)}

    def test_starting_inside_is_latency_zero_not_none(self):
        """The golden case: born inside, leaves, comes back.

        The XOR (``bool.diff()``) took the EXIT at 0.2 s as the first change,
        found the subject outside there, and reported ``None`` beside an entry
        count of 1.
        """
        analyzer = _pattern_analyzer([True, True, False, False, True, True])

        detail = analyzer.get_latency_details()["R"]

        assert detail.latency_s == 0.0
        assert detail.present_at_start is True
        assert detail.censored is False
        assert analyzer.get_entry_counts() == {"R": 1}

    def test_exit_after_t0_is_not_an_entry(self):
        # Inside until 0.2, out at 0.3, back in at 0.6. From t0 = 0.3 (outside)
        # the first change is the re-entry, not the exit that preceded it.
        analyzer = _pattern_analyzer([True, True, True, False, False, False, True, True])

        detail = analyzer.get_latency_details(t0=0.3)["R"]

        assert detail.present_at_start is False
        assert detail.latency_s == pytest.approx(0.3)

    def test_inter_visit_latencies_list_entries_only(self):
        # Exits (last inside row) at 0.1 and 0.5; entries at 0.4 and 0.7. The
        # XOR also listed the exits at 0.2 and 0.6 as "entries".
        analyzer = _pattern_analyzer([True, True, False, False, True, True, False, True])

        latencies = analyzer.get_inter_visit_latencies()["R"]

        assert [lat.total_seconds() for lat in latencies] == [
            pytest.approx(0.3),
            pytest.approx(0.2),
        ]

    def test_never_entering_is_censored_and_none_without_a_window(self):
        analyzer = _pattern_analyzer([False] * 6)

        detail = analyzer.get_latency_details()["R"]

        assert detail.latency_s is None
        assert detail.censored is True
        assert detail.present_at_start is False

    def test_censored_with_t_end_takes_the_ceiling(self):
        analyzer = _pattern_analyzer([False] * 10, start_s=2.0)

        detail = analyzer.get_latency_details(t0=2.0, t_end=2.5)["R"]

        assert detail.latency_s == pytest.approx(0.5)
        assert detail.censored is True

    def test_entry_after_t_end_is_censored(self):
        analyzer = _pattern_analyzer([False] * 8 + [True] * 2)

        detail = analyzer.get_latency_details(t0=0.0, t_end=0.5)["R"]

        assert detail.censored is True
        assert detail.latency_s == pytest.approx(0.5)

    def test_entry_at_t_end_is_not_censored(self):
        analyzer = _pattern_analyzer([False] * 5 + [True] * 2)

        detail = analyzer.get_latency_details(t0=0.0, t_end=0.5)["R"]

        assert detail.censored is False
        assert detail.latency_s == pytest.approx(0.5)


class TestExplicitT0:
    """``t0`` is the instant latency is measured from, not the first row."""

    def test_latency_is_measured_from_t0(self):
        analyzer = _pattern_analyzer([False] * 6 + [True] * 2)

        assert analyzer.get_latency_details(t0=0.2)["R"].latency_s == pytest.approx(0.4)
        assert analyzer.get_latency_to_first_entry(t0=0.2)["R"] == pytest.approx(0.4)

    def test_t0_before_the_first_detection(self):
        """START before the subject is first seen: the gap counts as latency."""
        analyzer = _pattern_analyzer([True, True], start_s=3.0)

        detail = analyzer.get_latency_details(t0=1.0)["R"]

        assert detail.present_at_start is False
        assert detail.latency_s == pytest.approx(2.0)

    def test_inside_at_t0_counts_from_the_as_of_row(self):
        # Entered at 0.2 and still inside at t0=0.45 (as-of row 0.4).
        analyzer = _pattern_analyzer([False, False, True, True, True, True, True])

        detail = analyzer.get_latency_details(t0=0.45)["R"]

        assert detail.present_at_start is True
        assert detail.latency_s == 0.0

    def test_entries_count_only_transitions_after_t0(self):
        pattern = [False, True, False, True, False, True, False]
        analyzer = _pattern_analyzer(pattern)

        assert analyzer.get_entry_counts() == {"R": 3}
        assert analyzer.get_entry_counts(t0=0.25) == {"R": 2}
        assert analyzer.get_entry_counts(t0=0.25, t_end=0.35) == {"R": 1}

    def test_present_at_t0_is_not_an_entry(self):
        analyzer = _pattern_analyzer([False, True, True, True, False, True])

        assert analyzer.get_entry_counts(t0=0.2) == {"R": 1}

    def test_time_in_roi_counts_from_t0(self):
        analyzer = _pattern_analyzer([True] * 6)

        whole = analyzer.get_time_spent_in_rois()["R"]["seconds"]
        from_t0 = analyzer.get_time_spent_in_rois(t0=0.2)["R"]["seconds"]
        bounded = analyzer.get_time_spent_in_rois(t0=0.2, t_end=0.4)["R"]["seconds"]

        assert whole == pytest.approx(0.5)
        assert from_t0 == pytest.approx(0.3)
        assert bounded == pytest.approx(0.2)

    def test_t0_accepts_a_timedelta(self):
        analyzer = _pattern_analyzer([False] * 4 + [True])

        detail = analyzer.get_latency_details(t0=pd.Timedelta(seconds=0.1))["R"]

        assert detail.latency_s == pytest.approx(0.3)


class TestLatencyWithDebounce:
    """Backdating keeps "already inside" true at the start."""

    def test_backdated_entry_at_the_first_frame_is_present_at_start(self):
        analyzer = _pattern_analyzer(
            [True] * 4 + [False] * 4, flutter_enter_frames=3, flutter_exit_frames=1
        )

        detail = analyzer.get_latency_details()["R"]

        assert detail.present_at_start is True
        assert detail.latency_s == 0.0

    def test_unconfirmed_start_is_not_present(self):
        # Two inside frames never confirm with enter=3: outside at the start.
        analyzer = _pattern_analyzer(
            [True, True, False, False, True, True, True],
            flutter_enter_frames=3,
            flutter_exit_frames=1,
        )

        detail = analyzer.get_latency_details()["R"]

        assert detail.present_at_start is False
        assert detail.latency_s == pytest.approx(0.4)


class TestLatencyPerAnimal:
    def test_per_animal_metrics_carry_the_flags(self):
        analyzer = _pattern_analyzer([True, False, True])

        (metrics,) = analyzer.get_metrics_by_track().values()

        assert metrics["latencia_primeira_entrada"] == {"R": 0.0}
        assert metrics["latency_present_at_start"] == {"R": True}
        assert metrics["latency_censored"] == {"R": False}
        assert metrics["contagem_entradas"] == {"R": 1}

    def test_free_function_on_a_datetime_index(self):
        frame = pd.DataFrame(
            {"in_A_stable": [True, False, True]},
            index=pd.to_datetime(
                ["2026-01-01 00:00:00", "2026-01-01 00:00:01", "2026-01-01 00:00:02"]
            ),
        )

        assert _latency_to_first_entry(frame, ["A"]) == {"A": 0.0}
        assert _roi_latencies(frame, ["A"])["A"].present_at_start is True

    def test_free_function_on_a_numeric_index(self):
        frame = pd.DataFrame({"in_A_stable": [False, False, True]}, index=[10.0, 10.5, 11.0])

        assert _latency_to_first_entry(frame, ["A"]) == {"A": pytest.approx(1.0)}
        assert _latency_to_first_entry(frame, ["A"], t0=10.25) == {"A": pytest.approx(0.75)}

    def test_empty_frame_is_censored(self):
        frame = pd.DataFrame({"in_A_stable": pd.Series([], dtype=bool)})

        detail = _roi_latencies(frame, ["A"])["A"]

        assert detail.latency_s is None
        assert detail.censored is True

    def test_entry_counts_without_t0_match_the_legacy_diff(self):
        frame = pd.DataFrame({"in_A_stable": [True, False, True, True, False, True]})

        assert _entry_counts(frame, ["A"]) == {"A": 2}


class TestRestrictToWindow:
    """ADR-011 hybrid cut: presence on the whole recording, metrics on the window."""

    def test_latency_counts_from_start_and_reads_the_state_before_it(self):
        # Inside 0.0-0.2, outside 0.3-0.5, back in at 0.6.
        analyzer = _pattern_analyzer([True] * 3 + [False] * 3 + [True] * 3)

        analyzer.restrict_to_window(0.4, 0.8)

        detail = analyzer.get_latency_details()["R"]
        assert detail.present_at_start is False
        assert detail.latency_s == pytest.approx(0.2)
        assert analyzer.get_latency_to_first_entry() == {"R": pytest.approx(0.2)}
        assert analyzer.get_entry_counts() == {"R": 1}

    def test_inside_at_start_is_latency_zero_and_not_an_entry(self):
        analyzer = _pattern_analyzer([False, False, True, True, True, True, False, False])

        analyzer.restrict_to_window(0.3, 0.7)

        detail = analyzer.get_latency_details()["R"]
        assert detail.present_at_start is True
        assert detail.latency_s == 0.0
        assert analyzer.get_entry_counts() == {"R": 0}
        assert analyzer.get_exit_counts() == {"R": 1}

    def test_censored_latency_is_the_window_length(self):
        analyzer = _pattern_analyzer([False] * 10)

        analyzer.restrict_to_window(0.2, 0.6)

        detail = analyzer.get_latency_details()["R"]
        assert detail.censored is True
        assert detail.latency_s == pytest.approx(0.4)

    def test_entry_after_stop_is_censored(self):
        analyzer = _pattern_analyzer([False] * 8 + [True] * 2)

        analyzer.restrict_to_window(0.1, 0.5)

        assert analyzer.get_latency_details()["R"].censored is True
        assert analyzer.get_entry_counts() == {"R": 0}

    def test_debounce_runs_on_the_whole_recording(self):
        """A visit confirmed before START stays confirmed at START.

        Cut first, the 0.2 s row would be the only inside sample of its run and
        ``flutter_enter_frames=3`` would never confirm it.
        """
        analyzer = _pattern_analyzer(
            [True, True, True, False, False, False],
            flutter_enter_frames=3,
            flutter_exit_frames=1,
        )

        analyzer.restrict_to_window(0.2, 0.5)

        assert analyzer.get_latency_details()["R"].present_at_start is True

    def test_time_in_roi_counts_only_the_window(self):
        analyzer = _pattern_analyzer([True] * 10)

        analyzer.restrict_to_window(0.3, 0.7)

        time = analyzer.get_time_spent_in_rois()["R"]
        assert time["seconds"] == pytest.approx(0.4)
        assert time["percentage"] == pytest.approx(100.0)

    def test_first_row_after_a_start_between_rows_is_clipped_to_start(self):
        analyzer = _pattern_analyzer([True] * 10)

        analyzer.restrict_to_window(0.25, 0.7)

        # 0.30 contributes 0.05 s (not its whole 0.1 s), then 0.4 s more.
        assert analyzer.get_time_spent_in_rois()["R"]["seconds"] == pytest.approx(0.45)

    def test_percentage_denominator_is_the_window(self):
        analyzer = _pattern_analyzer([True] * 5 + [False] * 5)

        analyzer.restrict_to_window(0.2, 0.8)

        # Inside credited 0.3-0.4 (0.2 s) of a 0.6 s window.
        time = analyzer.get_time_spent_in_rois()["R"]
        assert time["seconds"] == pytest.approx(0.2)
        assert time["percentage"] == pytest.approx(0.2 / 0.6 * 100)

    def test_exits_count_only_inside_the_window(self):
        analyzer = _pattern_analyzer([True, False, True, False, True, False])
        assert analyzer.get_exit_counts() == {"R": 3}

        analyzer.restrict_to_window(0.15, 0.45)

        assert analyzer.get_exit_counts() == {"R": 1}

    def test_event_log_and_transitions_see_only_the_window(self):
        analyzer = _pattern_analyzer([True, False, False, True, True, False, False])

        analyzer.restrict_to_window(0.2, 0.6)

        log = analyzer.get_event_log()
        assert log["timestamp"].min() >= pd.Timedelta(seconds=0.2)
        assert list(log["event"]) == ["enter", "exit"]
        # One row per window sample (0.2 .. 0.6), the last one going to NaN.
        transitions = analyzer.get_roi_transitions()
        assert int(transitions.to_numpy().sum()) == 5

    def test_distance_in_roi_excludes_the_segment_crossing_start(self):
        analyzer = _pattern_analyzer([True] * 6)
        analyzer._trajectory["x_cm_smoothed"] = np.arange(6, dtype=float)

        analyzer.restrict_to_window(0.2, 0.5)

        assert analyzer.get_distance_in_rois() == {"R": pytest.approx(3.0)}

    def test_unobserved_time_counts_only_gaps_inside_the_window(self):
        # Rows every 0.1 s with a 1.0 s hole before 1.4 and another before 3.0.
        times = [0.0, 0.1, 0.2, 0.3, 0.4, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 3.0, 3.1]
        analyzer = _times_analyzer(times, max_gap_s=0.2)
        assert analyzer.unobserved_time_s == pytest.approx(0.8 + 0.9)

        analyzer.restrict_to_window(1.0, 2.0)

        # Only the part of the first hole after START: 1.0 -> 1.4 minus the cap.
        assert analyzer.unobserved_time_s == pytest.approx(0.2)
        assert analyzer.get_time_spent_in_rois()["R"]["seconds"] == pytest.approx(0.2 + 0.5)

    def test_state_at_a_start_between_rows_is_the_row_before_it(self):
        # Inside up to 0.3, START at 0.35, outside at 0.4: inside AT START.
        analyzer = _pattern_analyzer([True] * 4 + [False] * 2 + [True] * 2)

        analyzer.restrict_to_window(0.35, 0.7)

        detail = analyzer.get_latency_details()["R"]
        assert detail.present_at_start is True
        assert detail.latency_s == 0.0
        assert analyzer.get_exit_counts() == {"R": 1}

    def test_per_animal_metrics_follow_the_window(self):
        # START at 0.25 falls between an inside row (0.2) and an outside one.
        analyzer = _pattern_analyzer([True] * 3 + [False] * 3 + [True] * 3)

        analyzer.restrict_to_window(0.25, 0.8)

        (metrics,) = analyzer.get_metrics_by_track().values()
        assert metrics["latencia_primeira_entrada"] == {"R": 0.0}
        assert metrics["latency_present_at_start"] == {"R": True}
        assert metrics["contagem_entradas"] == {"R": 1}
        assert metrics["contagem_saidas"] == {"R": 1}
        assert metrics["tempo_gasto_por_roi"]["R"]["seconds"] == pytest.approx(0.3)
        assert metrics["tempo_gasto_por_roi"]["R"]["percentage"] == pytest.approx(0.3 / 0.55 * 100)

    def test_empty_window(self):
        analyzer = _pattern_analyzer([True] * 5)

        analyzer.restrict_to_window(None, None, empty=True)

        detail = analyzer.get_latency_details()["R"]
        assert detail.latency_s is None
        assert detail.censored is True
        assert analyzer.get_time_spent_in_rois() == {"R": {"seconds": 0.0, "percentage": 0.0}}
        assert analyzer.get_entry_counts() == {"R": 0}
        assert analyzer.get_exit_counts() == {"R": 0}
        assert analyzer.get_event_log().empty
        assert analyzer.get_metrics_by_track() == {}
        assert analyzer.unobserved_time_s == 0.0

    def test_whole_window_equals_no_window(self):
        pattern = [False, True, True, False, True, False, False, True]
        plain = _pattern_analyzer(pattern)
        windowed = _pattern_analyzer(pattern)

        windowed.restrict_to_window(0.0, 0.7)

        assert windowed.get_time_spent_in_rois()["R"] == pytest.approx(
            plain.get_time_spent_in_rois()["R"]
        )
        assert windowed.get_entry_counts() == plain.get_entry_counts()
        assert windowed.get_exit_counts() == plain.get_exit_counts()
        assert windowed.get_latency_to_first_entry() == plain.get_latency_to_first_entry()
        assert windowed.unobserved_time_s == plain.unobserved_time_s

    def test_restricting_twice_is_rejected(self):
        analyzer = _pattern_analyzer([True] * 4)
        analyzer.restrict_to_window(0.0, 0.2)

        with pytest.raises(RuntimeError, match="once"):
            analyzer.restrict_to_window(0.0, 0.2)

    def test_reversed_or_missing_bounds_are_rejected(self):
        with pytest.raises(ValueError, match="before"):
            _pattern_analyzer([True] * 4).restrict_to_window(0.3, 0.1)
        with pytest.raises(ValueError, match="bounds"):
            _pattern_analyzer([True] * 4).restrict_to_window(0.1, None)

    def test_window_bounds_property(self):
        analyzer = _pattern_analyzer([True] * 4)
        assert analyzer.window_bounds is None

        analyzer.restrict_to_window(0.1, 0.3)

        assert analyzer.window_bounds == (0.1, 0.3)


def _times_analyzer(times, **kwargs):
    """Always-inside analyzer on an arbitrary clock (gaps included)."""
    index = pd.to_timedelta(np.asarray(times, dtype=float), unit="s")
    n = len(times)
    trajectory = pd.DataFrame(
        {
            "x1": [_INSIDE_BOX[0]] * n,
            "y1": [_INSIDE_BOX[1]] * n,
            "x2": [_INSIDE_BOX[2]] * n,
            "y2": [_INSIDE_BOX[3]] * n,
            "x_center_px": [50.0] * n,
            "y_center_px": [50.0] * n,
            "x_cm_smoothed": [50.0] * n,
            "y_cm_smoothed": [50.0] * n,
        },
        index=index,
    )
    b_analyzer = MagicMock()
    b_analyzer.trajectory_data = trajectory
    b_analyzer._pixelcm_x = 1.0
    b_analyzer._pixelcm_y = 1.0
    b_analyzer._video_height_px = 0
    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name="R", geometry=_SQUARE, coordinate_space="px")],
        inclusion_rule="centroid_in",
        flutter_n_frames=1,
        min_visit_s=0.0,
        min_gap_s=0.0,
        **kwargs,
    )


class TestRestrictToWindowMultiTrack:
    def test_group_and_per_animal_views_are_both_cut(self):
        b_analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=_two_animal_trajectory(),
            pixelcm_x=1.0,
            pixelcm_y=1.0,
            video_height_px=0,
            arena_polygon_px=[(0, 0), (500, 0), (500, 500), (0, 500)],
            fps=10.0,
            window_length=1,
            polyorder=0,
        )
        analyzer = ROIAnalyzer(
            behavior_analyzer=b_analyzer,
            rois=[ROI(name="R", geometry=_SQUARE, coordinate_space="px")],
            inclusion_rule="centroid_in",
            flutter_n_frames=1,
            min_visit_s=0.0,
            min_gap_s=0.0,
        )

        analyzer.restrict_to_window(0.3, 0.6)

        # Animal 1 inside throughout, animal 2 enters at 0.5.
        per_animal = analyzer.get_metrics_by_track()
        assert per_animal["1"]["latency_present_at_start"] == {"R": True}
        assert per_animal["2"]["latencia_primeira_entrada"] == {"R": pytest.approx(0.2)}
        assert per_animal["2"]["tempo_gasto_por_roi"]["R"]["seconds"] == pytest.approx(0.2)
        assert analyzer.get_time_spent_in_rois()["R"]["seconds"] == pytest.approx(0.3)


def _two_animal_trajectory() -> pd.DataFrame:
    rows = []
    for i in range(8):
        t = round(i * 0.1, 9)
        rows.append({"timestamp": t, "track_id": 1, "x_center_px": 50.0, "y_center_px": 50.0})
        inside = i >= 5
        x = 50.0 if inside else 300.0
        rows.append({"timestamp": t, "track_id": 2, "x_center_px": x, "y_center_px": 50.0})
    df = pd.DataFrame(rows)
    df["x1"] = df["x_center_px"] - 5
    df["x2"] = df["x_center_px"] + 5
    df["y1"] = df["y_center_px"] - 5
    df["y2"] = df["y_center_px"] + 5
    return df


if __name__ == "__main__":
    unittest.main()

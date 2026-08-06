"""
Tests for the ROI analyzer with configurable inclusion rules.
"""

import unittest
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from zebtrack.analysis.roi import ROI, ROIAnalyzer


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

        self.assertIn("bbox_intersects requer colunas de bbox", str(context.exception))

    def test_seg_overlap_rule_error(self):
        """Test that seg_overlap rule raises appropriate error."""
        with self.assertRaises(ValueError) as context:
            ROIAnalyzer(
                behavior_analyzer=self.mock_b_analyzer,
                rois=[self.test_roi],
                flutter_n_frames=1,
                inclusion_rule="seg_overlap",
            )

        self.assertIn("seg_overlap requer dados de segmentação", str(context.exception))

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

    return ROIAnalyzer(
        behavior_analyzer=b_analyzer,
        rois=[ROI(name="R", geometry=roi_polygon, coordinate_space="px")],
        flutter_n_frames=1,
        inclusion_rule="bbox_intersects",
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


if __name__ == "__main__":
    unittest.main()

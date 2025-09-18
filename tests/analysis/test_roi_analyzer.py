# -*- coding: utf-8 -*-
"""
Tests for the ROI analyzer with configurable inclusion rules.
"""

import unittest
import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from unittest.mock import MagicMock

from zebtrack.analysis.roi import ROI, ROIAnalyzer


class TestROIAnalyzerInclusionRules(unittest.TestCase):
    """Test the configurable ROI inclusion rules."""

    def setUp(self):
        """Set up test fixtures with synthetic trajectory data."""
        # Create synthetic trajectory data 
        timestamps = pd.date_range(start='2023-01-01', periods=10, freq='100ms')
        
        # Create trajectory that moves from left to right, crossing ROI boundary
        self.trajectory_df = pd.DataFrame({
            'x_cm_smoothed': np.linspace(5, 25, 10),  # moves from 5cm to 25cm
            'y_cm_smoothed': np.full(10, 15),  # stays at y=15cm
            'x_center_px': np.linspace(50, 250, 10),  # px equivalent 
            'y_center_px': np.full(10, 150),
            'x1': np.linspace(45, 245, 10),  # bbox coordinates
            'y1': np.full(10, 145),
            'x2': np.linspace(55, 255, 10),
            'y2': np.full(10, 155),
        }, index=timestamps)
        
        # Mock behavioral analyzer
        self.mock_b_analyzer = MagicMock()
        self.mock_b_analyzer.trajectory_data = self.trajectory_df.copy()
        self.mock_b_analyzer.pixelcm_x = 10.0  # 10 pixels per cm
        self.mock_b_analyzer.pixelcm_y = 10.0
        
        # Create a simple rectangular ROI from x=10-20cm, y=10-20cm
        self.roi_polygon = Polygon([(10, 10), (20, 10), (20, 20), (10, 20)])
        self.test_roi = ROI(name="TestROI", geometry=self.roi_polygon)

    def test_centroid_in_rule(self):
        """Test the centroid_in rule (should behave like the original implementation)."""
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="centroid_in"
        )
        
        # Check which frames have centroid inside ROI
        # The trajectory moves from 5->25cm, so it should be inside from roughly frame 2-7
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
            buffer_radius_value=2.0  # 2cm buffer
        )
        
        stable_col = analyzer._trajectory["in_TestROI_stable"]
        
        # With 2cm buffer, effective ROI is 8-22cm in x direction
        # Should detect entry earlier than centroid_in
        self.assertTrue(stable_col.iloc[1])  # x ≈ 8.3, should be inside buffered ROI
        self.assertTrue(stable_col.iloc[7])  # x ≈ 21.7, should be inside buffered ROI

    def test_bbox_intersects_rule(self):
        """Test the bbox_intersects rule."""
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[self.test_roi],
            flutter_n_frames=1,
            inclusion_rule="bbox_intersects",
            min_bbox_overlap_ratio=0.1  # 10% overlap required
        )
        
        stable_col = analyzer._trajectory["in_TestROI_stable"]
        
        # bbox_intersects should detect presence when bbox overlaps with ROI
        # Since our bboxes are 10x10 units and ROI is 10x10 cm, expect generous overlap
        entry_frames = stable_col.sum()
        self.assertGreater(entry_frames, 0)  # Should detect some frames as inside

    def test_bbox_intersects_missing_columns_error(self):
        """Test that bbox_intersects raises clear error when bbox columns are missing."""
        # Remove bbox columns
        trajectory_without_bbox = self.trajectory_df.drop(columns=['x1', 'y1', 'x2', 'y2'])
        self.mock_b_analyzer.trajectory_data = trajectory_without_bbox
        
        with self.assertRaises(ValueError) as context:
            ROIAnalyzer(
                behavior_analyzer=self.mock_b_analyzer,
                rois=[self.test_roi],
                flutter_n_frames=1,
                inclusion_rule="bbox_intersects"
            )
        
        self.assertIn("bbox_intersects requer colunas de bbox", str(context.exception))

    def test_seg_overlap_rule_error(self):
        """Test that seg_overlap rule raises appropriate error."""
        with self.assertRaises(ValueError) as context:
            ROIAnalyzer(
                behavior_analyzer=self.mock_b_analyzer,
                rois=[self.test_roi],
                flutter_n_frames=1,
                inclusion_rule="seg_overlap"
            )
        
        self.assertIn("seg_overlap requer dados de segmentação", str(context.exception))

    def test_coordinate_space_fallback_to_px(self):
        """Test that analyzer falls back to pixel coordinates when cm coords are unavailable."""
        # Remove cm coordinates
        trajectory_px_only = self.trajectory_df.drop(columns=['x_cm_smoothed', 'y_cm_smoothed'])
        self.mock_b_analyzer.trajectory_data = trajectory_px_only
        
        # ROI in px coordinates (scaled up by 10x from cm)
        roi_polygon_px = Polygon([(100, 100), (200, 100), (200, 200), (100, 200)])
        roi_px = ROI(name="TestROI", geometry=roi_polygon_px)
        
        # Should work with px coordinates
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[roi_px],
            flutter_n_frames=1,
            inclusion_rule="centroid_in"
        )
        
        # Should have calculated some presence
        stable_col = analyzer._trajectory["in_TestROI_stable"]
        self.assertIsInstance(stable_col.iloc[0], (bool, np.bool_))

    def test_coordinate_space_fallback_to_derived_bbox_center(self):
        """Test fallback to bbox-derived center coordinates."""
        # Remove both cm and center_px coordinates, keep only bbox
        trajectory_bbox_only = self.trajectory_df.drop(columns=[
            'x_cm_smoothed', 'y_cm_smoothed', 'x_center_px', 'y_center_px'
        ])
        self.mock_b_analyzer.trajectory_data = trajectory_bbox_only
        
        # ROI in px coordinates 
        roi_polygon_px = Polygon([(200, 100), (300, 100), (300, 200), (200, 200)])
        roi_px = ROI(name="TestROI", geometry=roi_polygon_px)
        
        # Should work by deriving center from bbox
        analyzer = ROIAnalyzer(
            behavior_analyzer=self.mock_b_analyzer,
            rois=[roi_px],
            flutter_n_frames=1,
            inclusion_rule="centroid_in"
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
                inclusion_rule="invalid_rule"
            )
        
        self.assertIn("Unknown inclusion rule: invalid_rule", str(context.exception))


if __name__ == "__main__":
    unittest.main()
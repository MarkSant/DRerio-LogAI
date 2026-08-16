"""
Extended unit tests for VisualizationGenerator in analysis/visualization_generator.py.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.visualization_generator import (
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


class TestNormalizeColorExtended:
    """Test color normalization to matplotlib 0-1 RGBA/RGB ranges."""

    def test_255_rgb_tuple(self):
        assert _normalize_color_for_matplotlib((255, 0, 128)) == (
            1.0,
            0.0,
            128 / 255.0,
        )
        assert _normalize_color_for_matplotlib([0, 255, 0]) == (0.0, 1.0, 0.0)

    def test_already_normalized_tuple(self):
        assert _normalize_color_for_matplotlib((0.5, 0.2, 0.8)) == (0.5, 0.2, 0.8)

    def test_string_and_named_colors(self):
        assert _normalize_color_for_matplotlib("red") == "red"
        assert _normalize_color_for_matplotlib("#FF0000") == "#FF0000"


class TestVisualizationGeneratorExtended:
    """Test VisualizationGenerator initialization, comparative boxplot, and plot generation."""

    @pytest.fixture
    def sample_behavior_analyzer(self) -> ConcreteBehavioralAnalyzer:
        n = 20
        timestamps = pd.timedelta_range(start="0s", periods=n, freq="100ms")
        x = np.linspace(10.0, 50.0, n)
        y = np.linspace(20.0, 60.0, n)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x,
                "y_center_px": y,
                "x1": x - 5.0,
                "y1": y - 5.0,
                "x2": x + 5.0,
                "y2": y + 5.0,
            },
            index=timestamps,
        )
        arena = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        return ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
            arena_polygon_px=arena,
            fps=10.0,
        )

    def test_init_minimal(self, sample_behavior_analyzer: ConcreteBehavioralAnalyzer):
        gen = VisualizationGenerator(
            b_analyzer=sample_behavior_analyzer,
            metadata={"experiment_id": "EXP_1"},
        )
        assert gen.b_analyzer == sample_behavior_analyzer
        assert gen.metadata["experiment_id"] == "EXP_1"
        assert gen.r_analyzer is None
        assert gen.roi_colors == {}

    def test_generate_comparative_boxplot(self):
        df = pd.DataFrame(
            {
                "group_id": ["Control", "Control", "Treatment", "Treatment"],
                "total_distance_cm": [100.0, 110.0, 150.0, 160.0],
            }
        )
        fig = VisualizationGenerator.generate_comparative_boxplot(
            df=df,
            metric="total_distance_cm",
            title="Comparison of Total Distance",
        )
        assert fig is not None
        plt.close(fig)

    def test_generate_trajectory_plot(self, sample_behavior_analyzer: ConcreteBehavioralAnalyzer):
        gen = VisualizationGenerator(
            b_analyzer=sample_behavior_analyzer,
            metadata={"experiment_id": "EXP_1"},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
        )
        fig = gen.generate_trajectory_plot()
        assert fig is not None
        plt.close(fig)

    def test_generate_heatmap(self, sample_behavior_analyzer: ConcreteBehavioralAnalyzer):
        gen = VisualizationGenerator(
            b_analyzer=sample_behavior_analyzer,
            metadata={"experiment_id": "EXP_1"},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
        )
        fig = gen.generate_heatmap()
        assert fig is not None
        plt.close(fig)

    def test_generate_angular_velocity_plot(
        self, sample_behavior_analyzer: ConcreteBehavioralAnalyzer
    ):
        gen = VisualizationGenerator(
            b_analyzer=sample_behavior_analyzer,
            metadata={"experiment_id": "EXP_1"},
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=100,
        )
        fig = gen.generate_angular_velocity_plot()
        assert fig is not None
        plt.close(fig)

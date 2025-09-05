# -*- coding: utf-8 -*-
"""
Tests for the BehavioralAnalyzer abstract base class and its concrete methods.
"""

import pytest
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union

from zebtrack.analysis.behavior import BehavioralAnalyzer


# -- Test Data and Fixtures --

@pytest.fixture
def sample_trajectory_data():
    """
    Provides a sample trajectory dataset for testing.
    The data is intentionally non-linear so that smoothing has an effect.
    """
    timestamps = np.linspace(0, 10, 101)
    # Add a quadratic term to make the path non-linear
    px = np.linspace(10, 110, 101) + 2 * (timestamps / 10) ** 2
    py = np.linspace(20, 220, 101) - 5 * (timestamps / 10) ** 2
    return {
        "timestamps": list(timestamps),
        "px": list(px),
        "py": list(py),
        "pixelcm_x": 10.0,
        "pixelcm_y": 10.0,
        "video_height_px": 240,
        "arena_polygon_px": [(0, 0), (120, 0), (120, 240), (0, 240)],
    }


# -- A Concrete Implementation for Testing --

class ConcreteAnalyzer(BehavioralAnalyzer):
    """
    A concrete implementation of BehavioralAnalyzer for testing purposes.
    The abstract methods are implemented with mock logic.
    """

    def calculate_total_distance(self, max_time_gap: Optional[float] = None) -> float:
        return 100.0

    def calculate_velocity_timeseries(self) -> pd.DataFrame:
        v_mag = pd.Series(np.random.rand(101) * 5, index=self._trajectory_data.index)
        return pd.DataFrame({"v_mag": v_mag})

    def detect_freezing_episodes(
        self, vel_threshold: float, min_duration: float
    ) -> List[Dict[str, float]]:
        return [{"start_time": 1.0, "end_time": 2.5, "duration": 1.5}]

    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        return pd.Series(np.random.rand(101) * 10, index=self._trajectory_data.index)

    def get_tortuosity(
        self, window_size: Optional[float] = None, step: Optional[float] = None
    ) -> Union[float, pd.Series]:
        if window_size:
            return pd.Series([1.1, 1.2, 1.3])
        return 1.25

    def get_thigmotaxis_timeseries(self) -> pd.Series:
        # Returns distance from wall, decreasing towards the middle of the trial
        distances = np.abs(np.linspace(-5, 5, 101)) + 1
        return pd.Series(distances, index=self._trajectory_data.index)


# -- Test Cases --

def test_initialization_and_preprocessing(sample_trajectory_data):
    """
    Tests if the analyzer is initialized correctly and if preprocessing
    (unit conversion, smoothing) is applied.
    """
    # Use a lower polyorder to ensure the filter alters the quadratic data
    analyzer = ConcreteAnalyzer(**sample_trajectory_data, polyorder=1)
    df = analyzer._trajectory_data

    assert isinstance(df, pd.DataFrame)
    assert "x_cm" in df.columns and "y_cm" in df.columns
    assert "x_cm_smoothed" in df.columns and "y_cm_smoothed" in df.columns

    # Check Y-axis inversion: py=20, height=240, pixelcm=10 -> y_cm = (240-20)/10 = 22
    assert np.isclose(df["y_cm"].iloc[0], 22.0)
    # Check X-axis conversion: px=10, pixelcm=10 -> x_cm = 10/10 = 1.0
    assert np.isclose(df["x_cm"].iloc[0], 1.0)

    # Check that smoothing was applied (smoothed should be different from raw)
    assert not np.allclose(df["x_cm"], df["x_cm_smoothed"])


def test_get_velocity_stats(sample_trajectory_data):
    """Tests the concrete method `get_velocity_stats`."""
    analyzer = ConcreteAnalyzer(**sample_trajectory_data)

    # Mock the velocity calculation to return predictable values
    velocity_data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    analyzer.calculate_velocity_timeseries = lambda: pd.DataFrame({"v_mag": velocity_data})

    stats = analyzer.get_velocity_stats()

    assert isinstance(stats, dict)
    assert np.isclose(stats["mean"], 3.0)
    assert np.isclose(stats["median"], 3.0)
    assert np.isclose(stats["std_dev"], np.std([1, 2, 3, 4, 5], ddof=1))


def test_calculate_thigmotaxis_index_average_distance(sample_trajectory_data):
    """Tests the 'average_distance' method of `calculate_thigmotaxis_index`."""
    analyzer = ConcreteAnalyzer(**sample_trajectory_data)

    # Mock the thigmotaxis series to return predictable values
    distances = pd.Series([1.0, 2.0, 3.0])
    analyzer.get_thigmotaxis_timeseries = lambda: distances

    index = analyzer.calculate_thigmotaxis_index(method="average_distance")
    assert np.isclose(index, 2.0)


def test_calculate_thigmotaxis_index_time_near_wall(sample_trajectory_data):
    """
    Tests the 'time_near_wall' method of `calculate_thigmotaxis_index`
    with the corrected, more robust logic.
    """
    # Setup a 10-second trial with 1-second intervals
    timestamps = np.linspace(0, 10, 11)
    # Distances: animal is near wall (dist < 3) at t=2, 3, 7, 8
    distances = pd.Series([5, 5, 2, 2, 5, 5, 5, 2, 2, 5, 5], index=timestamps)

    # Re-initialize analyzer with this specific data for accurate time calc
    sample_trajectory_data["timestamps"] = list(timestamps)
    # Ensure px and py have the same length as the new timestamps
    sample_trajectory_data["px"] = [0] * len(timestamps)
    sample_trajectory_data["py"] = [0] * len(timestamps)
    analyzer = ConcreteAnalyzer(**sample_trajectory_data)
    analyzer.get_thigmotaxis_timeseries = lambda: distances

    # threshold = 3. The animal is near the wall at t=2, 3, 7, 8.
    # The intervals ending at these times are (t1,t2), (t2,t3), (t6,t7), (t7,t8).
    # Each interval has a duration of 1s. Total time near wall = 4s.
    # Total trial duration is 10s.
    # Expected index = (4 / 10) * 100 = 40.0
    index = analyzer.calculate_thigmotaxis_index(
        method="time_near_wall", distance_threshold=3.0
    )

    assert np.isclose(index, 40.0)


def test_calculate_thigmotaxis_index_raises_error(sample_trajectory_data):
    """Tests that a ValueError is raised if the threshold is missing."""
    analyzer = ConcreteAnalyzer(**sample_trajectory_data)
    with pytest.raises(ValueError, match="'distance_threshold' is required"):
        analyzer.calculate_thigmotaxis_index(method="time_near_wall")

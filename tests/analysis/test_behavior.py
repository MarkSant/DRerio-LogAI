"""
Tests for the BehavioralAnalyzer abstract base class and its concrete methods.
"""

from typing import Optional, Union

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from zebtrack.analysis.behavior import BehavioralAnalyzer, ConcreteBehavioralAnalyzer


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


def prep_data_for_analyzer(data_dict: dict) -> dict:
    """
    Converts the old dict format into the new DataFrame-based format for the analyzer.
    """
    df = pd.DataFrame(
        {
            "timestamp": data_dict["timestamps"],
            "x_center_px": data_dict["px"],
            "y_center_px": data_dict["py"],
            # Add dummy bbox data as it's expected by the new init docstring
            "x1": [x - 1 for x in data_dict["px"]],
            "y1": [y - 1 for y in data_dict["py"]],
            "x2": [x + 1 for x in data_dict["px"]],
            "y2": [y + 1 for y in data_dict["py"]],
        }
    )

    return {
        "trajectory_df": df,
        "pixelcm_x": data_dict["pixelcm_x"],
        "pixelcm_y": data_dict["pixelcm_y"],
        "video_height_px": data_dict["video_height_px"],
        "arena_polygon_px": data_dict["arena_polygon_px"],
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
        v_mag = pd.Series(
            np.random.rand(len(self.trajectory_data)),
            index=self.trajectory_data.index,
        )
        return pd.DataFrame({"v_mag": v_mag})

    def detect_freezing_episodes(
        self,
        min_duration: float,
        vel_threshold: Optional[float] = None,
        threshold_method: str = "absolute",
        quantile: float = 0.1,
    ) -> list[dict[str, float]]:
        return [{"start_time": 1.0, "end_time": 2.5, "duration": 1.5}]

    def get_angular_velocity(self, unit: str = "degrees") -> pd.Series:
        return pd.Series(
            np.random.rand(len(self.trajectory_data)),
            index=self.trajectory_data.index,
        )

    def get_tortuosity(
        self, window_size: Optional[float] = None, step: Optional[float] = None
    ) -> Union[float, pd.Series]:
        if window_size:
            return pd.Series([1.1, 1.2, 1.3])
        return 1.25

    def get_thigmotaxis_timeseries(self) -> pd.Series:
        # Returns distance from wall, decreasing towards the middle of the trial
        distances = np.abs(np.linspace(-5, 5, len(self.trajectory_data))) + 1
        return pd.Series(distances, index=self.trajectory_data.index)


# -- Test Cases --
def test_initialization_and_preprocessing(sample_trajectory_data):
    """
    Tests if the analyzer is initialized correctly and if preprocessing
    (unit conversion, smoothing) is applied.
    """
    # Use a lower polyorder to ensure the filter alters the quadratic data
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteAnalyzer(**analyzer_args, polyorder=1)
    df = analyzer.trajectory_data

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
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteAnalyzer(**analyzer_args)

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
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteAnalyzer(**analyzer_args)

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
    sample_trajectory_data["timestamps"] = list(timestamps)
    sample_trajectory_data["px"] = [0] * len(timestamps)
    sample_trajectory_data["py"] = [0] * len(timestamps)

    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteAnalyzer(**analyzer_args)

    # Create the mock series with the same TimedeltaIndex as the analyzer's data
    # Distances: animal is near wall (dist < 3) at t=2, 3, 7, 8
    distance_values = [5, 5, 2, 2, 5, 5, 5, 2, 2, 5, 5]
    distances = pd.Series(distance_values, index=analyzer.trajectory_data.index)
    analyzer.get_thigmotaxis_timeseries = lambda: distances

    # threshold = 3. The animal is near the wall at t=2, 3, 7, 8.
    # The intervals ending at these times are (t1,t2), (t2,t3), (t6,t7), (t7,t8).
    # Each interval has a duration of 1s. Total time near wall = 4s.
    # Total trial duration is 10s.
    # Expected index = (4 / 10) * 100 = 40.0
    index = analyzer.calculate_thigmotaxis_index(method="time_near_wall", distance_threshold=3.0)

    assert np.isclose(index, 40.0)


def test_calculate_thigmotaxis_index_raises_error(sample_trajectory_data):
    """Tests that a ValueError is raised if the threshold is missing."""
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteAnalyzer(**analyzer_args)
    with pytest.raises(ValueError, match="'distance_threshold' is required"):
        analyzer.calculate_thigmotaxis_index(method="time_near_wall")


def test_concrete_thigmotaxis_timeseries_matches_boundary_distance(
    sample_trajectory_data,
):
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteBehavioralAnalyzer(**analyzer_args, window_length=5, polyorder=2)

    series = analyzer.get_thigmotaxis_timeseries()

    assert isinstance(series, pd.Series)
    assert len(series) == len(analyzer.trajectory_data)
    assert (series >= 0).all()

    first_point = Point(
        analyzer.trajectory_data["x_cm_smoothed"].iloc[0],
        analyzer.trajectory_data["y_cm_smoothed"].iloc[0],
    )
    expected_distance = first_point.distance(analyzer.arena_polygon_cm.boundary)
    assert np.isclose(series.iloc[0], expected_distance)


def test_thigmotaxis_timeseries_falls_back_to_raw_coordinates(sample_trajectory_data):
    analyzer_args = prep_data_for_analyzer(sample_trajectory_data)
    analyzer = ConcreteBehavioralAnalyzer(**analyzer_args)

    analyzer._trajectory_data["x_cm_smoothed"] = np.nan
    analyzer._trajectory_data["y_cm_smoothed"] = np.nan

    series = analyzer.get_thigmotaxis_timeseries()
    assert not series.isna().all()


def test_preprocess_data_handles_duplicate_timestamps():
    """
    Tests that the preprocessing step correctly handles duplicate timestamps
    by aggregating them, which prevents downstream errors.
    """
    # 1. Create a DataFrame with a duplicate timestamp at t=1.0
    data = {
        "timestamp": [0.0, 1.0, 1.0, 2.0],
        "x_center_px": [10, 20, 30, 40],  # mean should be 25
        "y_center_px": [10, 20, 30, 40],
        "confidence": [0.9, 0.8, 0.95, 0.9],  # max should be 0.95
        "track_id": [1, 1, 2, 1],  # first should be 1
        # Add dummy bbox data
        "x1": [9, 19, 29, 39],
        "y1": [9, 19, 29, 39],
        "x2": [11, 21, 31, 41],
        "y2": [11, 21, 31, 41],
    }
    test_df = pd.DataFrame(data)

    # 2. Setup the analyzer
    analyzer_args = {
        "trajectory_df": test_df,
        "pixelcm_x": 1.0,
        "pixelcm_y": 1.0,
        "video_height_px": 100,
        "arena_polygon_px": [(0, 0), (100, 0), (100, 100), (0, 100)],
    }
    # Use the concrete implementation from this test file
    analyzer = ConcreteAnalyzer(**analyzer_args)
    processed_df = analyzer.trajectory_data

    # 3. Perform assertions
    # The primary assertion: no duplicate timestamps in the index
    assert not processed_df.index.has_duplicates, "Index should be unique after preprocessing."

    # Check that the number of rows is correct (3 unique timestamps)
    assert len(processed_df) == 3

    # Check the aggregated values for the consolidated row (at timestamp 1.0)
    consolidated_row = processed_df.loc[pd.to_timedelta(1.0, unit="s")]
    assert np.isclose(consolidated_row["x_center_px"], 25.0), (
        "x_center_px should be the mean of the duplicates."
    )
    assert np.isclose(consolidated_row["confidence"], 0.95), (
        "confidence should be the max of the duplicates."
    )
    track_value = consolidated_row["track_id"]
    if isinstance(track_value, pd.Series):
        track_value = track_value.iloc[0]
    assert track_value == 1, "track_id should be the first of the duplicates."

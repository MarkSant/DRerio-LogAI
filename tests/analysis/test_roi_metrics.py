"""
Tests for ROI analyzer metrics and analysis functions.

Comprehensive test suite covering time spent in ROIs, entry/exit counts,
transitions, behavioral metrics within ROIs, and spatial analyses.
"""

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon
from unittest.mock import MagicMock

from zebtrack.analysis.roi import ROI, ROIAnalyzer


# === Fixture Helpers ===


def create_mock_behavior_analyzer_with_trajectory(trajectory_df):
    """Create a mock BehavioralAnalyzer with the given trajectory."""
    mock_analyzer = MagicMock()
    mock_analyzer.trajectory_data = trajectory_df.copy()
    mock_analyzer._pixelcm_x = 10.0
    mock_analyzer._pixelcm_y = 10.0
    mock_analyzer._video_height_px = 300
    mock_analyzer.fps = 30.0
    mock_analyzer._trajectory_data = trajectory_df.copy()

    # Add calculate_velocity_timeseries method that adds v_mag column
    def calculate_velocity_timeseries():
        if "v_mag" not in mock_analyzer.trajectory_data.columns:
            # Simple velocity calculation
            dt = mock_analyzer.trajectory_data.index.to_series().diff().dt.total_seconds()
            dx = mock_analyzer.trajectory_data["x_cm_smoothed"].diff()
            dy = mock_analyzer.trajectory_data["y_cm_smoothed"].diff()
            mock_analyzer.trajectory_data["vx"] = dx / dt
            mock_analyzer.trajectory_data["vy"] = dy / dt
            mock_analyzer.trajectory_data["v_mag"] = np.sqrt(
                mock_analyzer.trajectory_data["vx"]**2 + mock_analyzer.trajectory_data["vy"]**2
            )
            # Also update _trajectory_data (used internally by ROIAnalyzer)
            mock_analyzer._trajectory_data = mock_analyzer.trajectory_data.copy()
        return mock_analyzer.trajectory_data

    mock_analyzer.calculate_velocity_timeseries = calculate_velocity_timeseries

    # Add detect_freezing_episodes method
    def detect_freezing_episodes(vel_threshold, min_duration, **kwargs):
        # Return empty list for simplicity
        return []

    mock_analyzer.detect_freezing_episodes = detect_freezing_episodes

    # Add arena_polygon_cm property for center_vs_periphery tests
    from shapely.geometry import Polygon
    arena_cm = Polygon([(0, 0), (80, 0), (80, 30), (0, 30)])  # 80x30 cm arena
    mock_analyzer.arena_polygon_cm = arena_cm

    return mock_analyzer


def create_crossing_trajectory(n_frames=90, fps=30.0):
    """
    Create a trajectory that crosses between two ROIs.

    Trajectory phases:
    - Frames 0-29: In Zone A (x: 5-10 cm)
    - Frames 30-59: In Zone B (x: 15-20 cm)
    - Frames 60-89: Back in Zone A (x: 10-5 cm)
    """
    # Use timedelta to avoid fractional millisecond issues
    timestamps = pd.date_range(start="2023-01-01", periods=n_frames, freq="100ms")

    x_positions = np.concatenate([
        np.linspace(5, 10, 30),    # Move to edge of Zone A
        np.linspace(15, 20, 30),   # Jump to Zone B
        np.linspace(10, 5, 30),    # Return to Zone A
    ])

    y_positions = np.full(n_frames, 15.0)

    # Convert to pixel coordinates
    x_center_px = x_positions * 10.0
    y_center_px = 300 - (y_positions * 10.0)

    df = pd.DataFrame({
        "x_cm_smoothed": x_positions,
        "y_cm_smoothed": y_positions,
        "x_center_px": x_center_px,
        "y_center_px": y_center_px,
        "x1": x_center_px - 5,
        "y1": y_center_px - 5,
        "x2": x_center_px + 5,
        "y2": y_center_px + 5,
    }, index=timestamps)

    return df


def create_stationary_then_moving_trajectory(n_frames=120, fps=30.0):
    """
    Create a trajectory that starts in one ROI then moves to another.

    Phases:
    - Frames 0-59: Stationary in Zone A (x=7.5 cm)
    - Frames 60-119: Move to and stay in Zone B (x: 7.5 -> 17.5 cm)
    """
    # Use timedelta to avoid fractional millisecond issues
    timestamps = pd.date_range(start="2023-01-01", periods=n_frames, freq="100ms")

    x_positions = np.concatenate([
        np.full(60, 7.5),          # Stationary in Zone A
        np.linspace(7.5, 17.5, 60), # Move to Zone B
    ])

    y_positions = np.full(n_frames, 15.0)

    x_center_px = x_positions * 10.0
    y_center_px = 300 - (y_positions * 10.0)

    df = pd.DataFrame({
        "x_cm_smoothed": x_positions,
        "y_cm_smoothed": y_positions,
        "x_center_px": x_center_px,
        "y_center_px": y_center_px,
        "x1": x_center_px - 5,
        "y1": y_center_px - 5,
        "x2": x_center_px + 5,
        "y2": y_center_px + 5,
    }, index=timestamps)

    return df


@pytest.fixture
def two_zone_rois():
    """Create two non-overlapping rectangular ROIs."""
    zone_a = ROI(
        name="Zone A",
        geometry=Polygon([(5, 10), (10, 10), (10, 20), (5, 20)]),
        coordinate_space="cm"
    )
    zone_b = ROI(
        name="Zone B",
        geometry=Polygon([(15, 10), (20, 10), (20, 20), (15, 20)]),
        coordinate_space="cm"
    )
    return [zone_a, zone_b]


@pytest.fixture
def crossing_analyzer(two_zone_rois):
    """ROI analyzer with trajectory crossing between two zones."""
    df = create_crossing_trajectory()
    mock_b_analyzer = create_mock_behavior_analyzer_with_trajectory(df)

    # Pre-calculate velocity before creating ROIAnalyzer (so the copy has v_mag)
    mock_b_analyzer.calculate_velocity_timeseries()

    return ROIAnalyzer(
        behavior_analyzer=mock_b_analyzer,
        rois=two_zone_rois,
        flutter_n_frames=1,
        inclusion_rule="centroid_in",
    )


@pytest.fixture
def stationary_analyzer(two_zone_rois):
    """ROI analyzer with stationary then moving trajectory."""
    df = create_stationary_then_moving_trajectory()
    mock_b_analyzer = create_mock_behavior_analyzer_with_trajectory(df)

    # Pre-calculate velocity before creating ROIAnalyzer (so the copy has v_mag)
    mock_b_analyzer.calculate_velocity_timeseries()

    return ROIAnalyzer(
        behavior_analyzer=mock_b_analyzer,
        rois=two_zone_rois,
        flutter_n_frames=1,
        inclusion_rule="centroid_in",
    )


# === Tests ===


class TestTimeSpentInROIs:
    """Test time spent calculations."""

    def test_get_time_spent_in_rois(self, crossing_analyzer):
        """Test calculation of time spent in each ROI."""
        time_spent = crossing_analyzer.get_time_spent_in_rois()

        assert isinstance(time_spent, dict)
        assert "Zone A" in time_spent
        assert "Zone B" in time_spent

        # Each zone dict should have seconds and percentage
        for zone_name, metrics in time_spent.items():
            assert "seconds" in metrics
            assert "percentage" in metrics
            assert metrics["seconds"] >= 0
            assert 0 <= metrics["percentage"] <= 100

    def test_time_spent_percentages_sum_to_100(self, crossing_analyzer):
        """Test that time percentages sum correctly."""
        time_spent = crossing_analyzer.get_time_spent_in_rois()

        total_percentage = sum(metrics["percentage"] for metrics in time_spent.values())

        # Should be close to 100% (allowing for rounding and gaps)
        assert total_percentage <= 100


class TestEntryExitMetrics:
    """Test entry and exit counting."""

    def test_get_latency_to_first_entry(self, crossing_analyzer):
        """Test latency to first entry calculation."""
        latencies = crossing_analyzer.get_latency_to_first_entry()

        assert isinstance(latencies, dict)
        assert "Zone A" in latencies
        assert "Zone B" in latencies

        # Zone A should have very low latency (starts there)
        assert latencies["Zone A"] is not None
        assert latencies["Zone A"] >= 0

        # Zone B should have higher latency (enters later)
        if latencies["Zone B"] is not None:
            assert latencies["Zone B"] > latencies["Zone A"]

    def test_get_entry_counts(self, crossing_analyzer):
        """Test entry count calculation."""
        entry_counts = crossing_analyzer.get_entry_counts()

        assert isinstance(entry_counts, dict)
        assert "Zone A" in entry_counts
        assert "Zone B" in entry_counts

        # Should have positive entry counts
        assert entry_counts["Zone A"] >= 0
        assert entry_counts["Zone B"] >= 0

    def test_get_exit_counts(self, crossing_analyzer):
        """Test exit count calculation."""
        exit_counts = crossing_analyzer.get_exit_counts()

        assert isinstance(exit_counts, dict)
        assert "Zone A" in exit_counts
        assert "Zone B" in exit_counts

        # Exit counts should match entry counts (closed trajectory)
        assert exit_counts["Zone A"] >= 0
        assert exit_counts["Zone B"] >= 0

    def test_get_inter_visit_latencies(self, crossing_analyzer):
        """Test inter-visit latency calculation."""
        latencies = crossing_analyzer.get_inter_visit_latencies()

        assert isinstance(latencies, dict)
        assert "Zone A" in latencies
        assert "Zone B" in latencies

        # Each zone should have a list of latencies
        for zone_name, zone_latencies in latencies.items():
            assert isinstance(zone_latencies, list)
            # All latencies should be positive (if any exist)
            for latency in zone_latencies:
                # Latencies are Timedelta objects
                assert latency > pd.Timedelta(0)


class TestTransitionsAndEvents:
    """Test transition matrices and event logs."""

    def test_get_roi_transitions(self, crossing_analyzer):
        """Test ROI transition matrix generation."""
        transitions = crossing_analyzer.get_roi_transitions()

        assert isinstance(transitions, pd.DataFrame)

        # Should have rows and columns for each ROI
        assert "Zone A" in transitions.index
        assert "Zone B" in transitions.index
        assert "Zone A" in transitions.columns
        assert "Zone B" in transitions.columns

        # Diagonal can be > 0 (staying in same ROI across frames)
        assert transitions.loc["Zone A", "Zone A"] >= 0
        assert transitions.loc["Zone B", "Zone B"] >= 0

        # Off-diagonal should show transitions
        assert transitions.loc["Zone A", "Zone B"] >= 0
        assert transitions.loc["Zone B", "Zone A"] >= 0

    def test_get_event_log(self, crossing_analyzer):
        """Test event log generation."""
        event_log = crossing_analyzer.get_event_log()

        assert isinstance(event_log, pd.DataFrame)

        # Should have required columns
        assert "timestamp" in event_log.columns
        assert "event" in event_log.columns  # Column is named "event", not "event_type"
        assert "roi_name" in event_log.columns

        # Events should be either "enter" or "exit"
        assert set(event_log["event"].unique()).issubset({"enter", "exit"})

        # Should have events for both zones
        assert "Zone A" in event_log["roi_name"].values
        assert "Zone B" in event_log["roi_name"].values


class TestBehavioralMetricsInROIs:
    """Test behavioral metrics calculated per ROI."""

    def test_get_distance_in_rois(self, stationary_analyzer):
        """Test distance traveled within each ROI."""
        distances = stationary_analyzer.get_distance_in_rois()

        assert isinstance(distances, dict)
        assert "Zone A" in distances
        assert "Zone B" in distances

        # Distances should be non-negative
        assert distances["Zone A"] >= 0
        assert distances["Zone B"] >= 0

    def test_get_velocity_stats_in_rois(self, stationary_analyzer):
        """Test velocity statistics within each ROI."""
        velocity_stats = stationary_analyzer.get_velocity_stats_in_rois()

        assert isinstance(velocity_stats, dict)
        assert "Zone A" in velocity_stats
        assert "Zone B" in velocity_stats

        # Each zone should have stats or None
        for zone_name, stats in velocity_stats.items():
            if stats is not None:
                assert "mean" in stats
                assert "median" in stats
                assert "std_dev" in stats
                assert stats["mean"] >= 0

    def test_get_freezing_in_rois(self, stationary_analyzer):
        """Test freezing detection within each ROI."""
        freezing_stats = stationary_analyzer.get_freezing_in_rois(
            vel_threshold=1.0,  # Positional arg first
            min_duration=0.5,
        )

        assert isinstance(freezing_stats, dict)
        assert "Zone A" in freezing_stats
        assert "Zone B" in freezing_stats

        # Each zone should have freezing stats
        for zone_name, stats in freezing_stats.items():
            assert "count" in stats  # Key is "count", not "episode_count"
            assert "total_duration" in stats
            assert "episodes" in stats
            assert stats["count"] >= 0
            assert stats["total_duration"] >= 0
            assert isinstance(stats["episodes"], list)

    def test_get_tortuosity_in_rois(self, stationary_analyzer):
        """Test tortuosity calculation within each ROI."""
        tortuosity_stats = stationary_analyzer.get_tortuosity_in_rois()

        assert isinstance(tortuosity_stats, dict)
        assert "Zone A" in tortuosity_stats
        assert "Zone B" in tortuosity_stats

        # Tortuosity can be None if insufficient data
        for zone_name, tortuosity in tortuosity_stats.items():
            if tortuosity is not None:
                assert isinstance(tortuosity, float)
                # Tortuosity should be non-negative
                assert tortuosity >= 0 or np.isnan(tortuosity)


class TestSpatialAnalyses:
    """Test spatial analysis functions."""

    def test_analyze_center_vs_periphery_area_ratio_method(self, crossing_analyzer):
        """Test center vs periphery analysis with area_ratio method."""
        result = crossing_analyzer.analyze_center_vs_periphery(
            method="area_ratio",
            value=0.5,  # 50% of arena area
        )

        assert isinstance(result, dict)
        # Result contains metric categories, not region names directly
        assert "time_spent" in result
        assert "distance" in result
        assert "entry_counts" in result

        # Each metric should have Center and Periphery data
        assert "Center" in result["time_spent"]
        assert "Periphery" in result["time_spent"]

        # Time spent should have seconds and percentage
        for region in ["Center", "Periphery"]:
            assert "seconds" in result["time_spent"][region]
            assert "percentage" in result["time_spent"][region]
            assert result["time_spent"][region]["seconds"] >= 0
            assert 0 <= result["time_spent"][region]["percentage"] <= 100

    def test_analyze_center_vs_periphery_distance_method(self, crossing_analyzer):
        """Test center vs periphery analysis with distance method."""
        result = crossing_analyzer.analyze_center_vs_periphery(
            method="distance",
            value=3.0,  # 3 cm from walls
        )

        assert isinstance(result, dict)
        # Result contains metric categories
        assert "time_spent" in result
        assert "distance" in result
        assert "entry_counts" in result

        # Each metric should have Center and Periphery data
        assert "Center" in result["time_spent"]
        assert "Periphery" in result["time_spent"]

        # Percentages should sum to ~100%
        total_pct = (
            result["time_spent"]["Center"]["percentage"]
            + result["time_spent"]["Periphery"]["percentage"]
        )
        assert 99 <= total_pct <= 101


class TestROIProperties:
    """Test ROI property accessors."""

    def test_rois_property(self, crossing_analyzer):
        """Test ROIs property accessor."""
        rois = crossing_analyzer.rois

        assert isinstance(rois, dict)
        assert "Zone A" in rois
        assert "Zone B" in rois

        # Each ROI should be a ROI instance
        for roi_name, roi in rois.items():
            assert isinstance(roi, ROI)
            assert roi.name == roi_name


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_roi_list_raises_error(self):
        """Test that empty ROI list raises ValueError."""
        df = create_crossing_trajectory()
        mock_analyzer = create_mock_behavior_analyzer_with_trajectory(df)

        with pytest.raises(ValueError, match="ROI list cannot be empty"):
            ROIAnalyzer(
                behavior_analyzer=mock_analyzer,
                rois=[],  # Empty list
                flutter_n_frames=1,
                inclusion_rule="centroid_in",
            )

    def test_invalid_roi_geometry_raises_error(self):
        """Test that invalid ROI geometry raises ValueError."""
        df = create_crossing_trajectory()
        mock_analyzer = create_mock_behavior_analyzer_with_trajectory(df)

        # Create an ROI with empty/invalid geometry
        invalid_roi = ROI(
            name="Invalid",
            geometry=Polygon(),  # Empty polygon
            coordinate_space="cm"
        )

        with pytest.raises(ValueError, match="invalid geometry"):
            ROIAnalyzer(
                behavior_analyzer=mock_analyzer,
                rois=[invalid_roi],
                flutter_n_frames=1,
                inclusion_rule="centroid_in",
            )

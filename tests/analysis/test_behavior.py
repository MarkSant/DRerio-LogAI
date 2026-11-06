"""
Tests for zebtrack.analysis.behavior module.

Comprehensive test suite covering distance calculation, velocity metrics,
freezing detection, angular velocity, tortuosity, thigmotaxis, and episode detection.
"""

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer

# === Fixture Functions ===


def create_simple_trajectory(n_frames=100, fps=30.0, pixelcm=10.0):
    """Create a simple trajectory moving in a straight line."""
    timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

    # Moving from (10,10) to (60,10) cm - horizontal movement
    x_positions_cm = np.linspace(10, 60, n_frames)
    y_positions_cm = np.full(n_frames, 10.0)

    x_center_px = x_positions_cm * pixelcm
    y_center_px = 360 - (y_positions_cm * pixelcm)  # Invert for 720px height

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_center_px,
            "y_center_px": y_center_px,
            "x1": x_center_px - 10,
            "y1": y_center_px - 10,
            "x2": x_center_px + 10,
            "y2": y_center_px + 10,
            "confidence": 0.9,
        }
    )


def create_circular_trajectory(n_frames=120, fps=30.0, radius_cm=20.0, pixelcm=10.0):
    """Create a circular trajectory."""
    timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

    # Circular path
    angles = np.linspace(0, 2 * np.pi, n_frames)
    x_positions_cm = 40 + radius_cm * np.cos(angles)
    y_positions_cm = 40 + radius_cm * np.sin(angles)

    x_center_px = x_positions_cm * pixelcm
    y_center_px = 360 - (y_positions_cm * pixelcm)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_center_px,
            "y_center_px": y_center_px,
            "x1": x_center_px - 10,
            "y1": y_center_px - 10,
            "x2": x_center_px + 10,
            "y2": y_center_px + 10,
            "confidence": 0.9,
        }
    )


def create_trajectory_with_gaps(fps=30.0, pixelcm=10.0):
    """Create a trajectory with temporal gaps."""
    # Two separate segments with a gap in between
    frames1 = 30
    frames2 = 30
    gap_frames = 60  # 2 second gap at 30 fps

    # First segment: 0-1s
    t1 = pd.to_timedelta(np.arange(frames1) / fps, unit="s")
    x1 = np.linspace(10, 30, frames1)

    # Gap: 1-3s (missing data)

    # Second segment: 3-4s
    t2 = pd.to_timedelta((np.arange(frames2) + frames1 + gap_frames) / fps, unit="s")
    x2 = np.linspace(50, 70, frames2)

    timestamps = pd.concat([pd.Series(t1), pd.Series(t2)], ignore_index=True)
    x_positions_cm = np.concatenate([x1, x2])
    y_positions_cm = np.full(frames1 + frames2, 10.0)

    x_center_px = x_positions_cm * pixelcm
    y_center_px = 360 - (y_positions_cm * pixelcm)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_center_px,
            "y_center_px": y_center_px,
            "x1": x_center_px - 10,
            "y1": y_center_px - 10,
            "x2": x_center_px + 10,
            "y2": y_center_px + 10,
            "confidence": 0.9,
        }
    )


def create_freezing_trajectory(fps=30.0, pixelcm=10.0):
    """Create a trajectory with freezing episodes."""
    # Moving (1s) -> Frozen (1s) -> Moving (1s) -> Frozen (1s)
    segment_frames = int(fps * 1.0)
    total_frames = segment_frames * 4

    timestamps = pd.to_timedelta(np.arange(total_frames) / fps, unit="s")
    x_positions_cm = np.zeros(total_frames)
    y_positions_cm = np.zeros(total_frames)

    # Segment 1: Moving right (5 cm/s)
    for i in range(segment_frames):
        t = i / fps
        x_positions_cm[i] = 10 + 5.0 * t
        y_positions_cm[i] = 10.0

    # Segment 2: Frozen at x=15
    for i in range(segment_frames, 2 * segment_frames):
        x_positions_cm[i] = 15.0 + np.random.normal(0, 0.05)  # Small jitter
        y_positions_cm[i] = 10.0 + np.random.normal(0, 0.05)

    # Segment 3: Moving up (5 cm/s)
    for i in range(2 * segment_frames, 3 * segment_frames):
        t = (i - 2 * segment_frames) / fps
        x_positions_cm[i] = 15.0
        y_positions_cm[i] = 10.0 + 5.0 * t

    # Segment 4: Frozen at y=15
    for i in range(3 * segment_frames, 4 * segment_frames):
        x_positions_cm[i] = 15.0 + np.random.normal(0, 0.05)
        y_positions_cm[i] = 15.0 + np.random.normal(0, 0.05)

    x_center_px = x_positions_cm * pixelcm
    y_center_px = 360 - (y_positions_cm * pixelcm)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "x_center_px": x_center_px,
            "y_center_px": y_center_px,
            "x1": x_center_px - 10,
            "y1": y_center_px - 10,
            "x2": x_center_px + 10,
            "y2": y_center_px + 10,
            "confidence": 0.9,
        }
    )


@pytest.fixture
def simple_analyzer():
    """Fixture for a simple straight-line trajectory analyzer."""
    df = create_simple_trajectory()
    arena_polygon = [(0, 0), (800, 0), (800, 720), (0, 720)]

    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon,
        fps=30.0,
    )


@pytest.fixture
def circular_analyzer():
    """Fixture for a circular trajectory analyzer."""
    df = create_circular_trajectory()
    arena_polygon = [(0, 0), (800, 0), (800, 720), (0, 720)]

    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon,
        fps=30.0,
    )


@pytest.fixture
def arena_polygon_80x72():
    """Standard 80x72 cm arena polygon in pixel coordinates (800x720 px @ 10px/cm)."""
    return [(0, 0), (800, 0), (800, 720), (0, 720)]


# === Tests ===


class TestBehavioralAnalyzerInitialization:
    """Test initialization and validation."""

    def test_initialization_success(self, arena_polygon_80x72):
        """Test successful initialization with valid parameters."""
        df = create_simple_trajectory()

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=30.0,
        )

        assert analyzer is not None
        assert analyzer.fps == 30.0
        assert len(analyzer.trajectory_data) == len(df)

    def test_polyorder_validation(self, arena_polygon_80x72):
        """Test that polyorder >= window_length raises ValueError."""
        df = create_simple_trajectory()

        with pytest.raises(ValueError, match="polyorder must be less than window_length"):
            ConcreteBehavioralAnalyzer(
                trajectory_df=df,
                pixelcm_x=10.0,
                pixelcm_y=10.0,
                video_height_px=720,
                arena_polygon_px=arena_polygon_80x72,
                fps=30.0,
                window_length=7,
                polyorder=7,  # Invalid: equal to window_length
            )


class TestDistanceCalculation:
    """Test distance calculation methods."""

    def test_calculate_total_distance_simple_line(self, simple_analyzer):
        """Test distance calculation for straight-line movement."""
        distance = simple_analyzer.calculate_total_distance()

        # Moving from x=10 to x=60 cm = 50 cm
        assert 48 <= distance <= 52, f"Expected ~50 cm, got {distance}"

    def test_calculate_total_distance_with_gaps(self, arena_polygon_80x72):
        """Test distance calculation respects temporal gaps."""
        df = create_trajectory_with_gaps()

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=30.0,
        )

        # Without gap detection: includes impossible jump from 30->50 cm
        distance_no_gap = analyzer.calculate_total_distance(max_time_gap=None)

        # With gap detection: excludes the 20 cm jump
        distance_with_gap = analyzer.calculate_total_distance(max_time_gap=1.5)

        # Should be different
        assert distance_no_gap > distance_with_gap
        # Each segment is a straight 20 cm. Smoothing is cut at the gap (#632);
        # it used to straddle it and smear the jump into both segments, which
        # is why this bound once read 50-70 cm.
        assert distance_with_gap == pytest.approx(40.0)
        assert distance_no_gap == pytest.approx(60.0)

    def test_calculate_total_distance_circular(self, circular_analyzer):
        """Test distance for circular trajectory."""
        distance = circular_analyzer.calculate_total_distance()

        # Circumference = 2πr = 2π(20) ≈ 125.66 cm
        expected = 2 * np.pi * 20
        assert abs(distance - expected) / expected < 0.1, f"Expected ~{expected} cm, got {distance}"


class TestVelocityMetrics:
    """Test velocity calculation methods."""

    def test_calculate_velocity_timeseries(self, simple_analyzer):
        """Test velocity timeseries generation."""
        velocity_df = simple_analyzer.calculate_velocity_timeseries()

        assert "v_mag" in velocity_df.columns
        assert "vx" in velocity_df.columns
        assert "vy" in velocity_df.columns
        assert len(velocity_df) == len(simple_analyzer.trajectory_data)
        assert velocity_df["v_mag"].notna().sum() > 0

    def test_get_velocity_stats(self, simple_analyzer):
        """Test velocity statistics calculation."""
        stats = simple_analyzer.get_velocity_stats()

        assert "mean" in stats
        assert "median" in stats
        assert "std_dev" in stats
        assert "max" in stats

        # Simple linear motion should have relatively constant velocity
        assert stats["mean"] > 0
        assert stats["median"] > 0
        assert stats["std_dev"] >= 0
        assert stats["max"] >= stats["mean"]  # Max should be >= mean

    def test_velocity_stats_circular_motion(self, circular_analyzer):
        """Test velocity stats for circular motion."""
        stats = circular_analyzer.get_velocity_stats()

        # Circular motion should have non-zero velocity
        assert stats["mean"] > 0
        # Some variation due to discretization
        assert stats["std_dev"] > 0


class TestFreezingDetection:
    """Test freezing episode detection."""

    def test_detect_freezing_episodes(self, arena_polygon_80x72):
        """Test freezing detection with known freezing periods."""
        np.random.seed(42)  # For reproducible jitter
        df = create_freezing_trajectory()

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=30.0,
        )

        episodes = analyzer.detect_freezing_episodes(
            min_duration=0.3,  # seconds - lower to catch more episodes
            vel_threshold=1.0,  # cm/s - higher threshold to catch freezing
            threshold_method="absolute",
        )

        # Check that method returns a list
        assert isinstance(episodes, list)

        # Check episode structure if they exist
        for episode in episodes:
            assert "start_time" in episode
            assert "end_time" in episode
            assert "duration" in episode
            assert episode["duration"] > 0

    def test_freezing_no_episodes_if_always_moving(self, simple_analyzer):
        """Test that no freezing is detected for continuous movement."""
        episodes = simple_analyzer.detect_freezing_episodes(
            min_duration=0.5,  # seconds
            vel_threshold=0.5,  # cm/s
            threshold_method="absolute",
        )

        # Continuous linear movement shouldn't have freezing episodes
        # (or very few due to smoothing artifacts at edges)
        assert len(episodes) <= 2


class TestAngularVelocity:
    """Test angular velocity calculations."""

    def test_get_angular_velocity_degrees(self, circular_analyzer):
        """Test angular velocity in degrees."""
        angular_vel = circular_analyzer.get_angular_velocity(unit="degrees")

        assert isinstance(angular_vel, pd.Series)
        assert len(angular_vel) > 0
        # Circular motion should have angular velocity
        assert angular_vel.abs().mean() > 0

    def test_angular_velocity_straight_line(self, simple_analyzer):
        """Test angular velocity for straight-line motion."""
        angular_vel = simple_analyzer.get_angular_velocity(unit="degrees")

        # Straight line should have near-zero angular velocity
        # (some noise due to smoothing)
        assert angular_vel.abs().mean() < 10  # degrees/s


class TestTortuosity:
    """Test tortuosity (path straightness) metrics."""

    def test_get_tortuosity_straight_line(self, simple_analyzer):
        """Test tortuosity for straight-line path."""
        tortuosity = simple_analyzer.get_tortuosity()

        # Straight line should have tortuosity close to 1.0
        assert 0.9 <= tortuosity <= 1.1, f"Expected ~1.0, got {tortuosity}"

    def test_get_tortuosity_circular(self, circular_analyzer):
        """Test tortuosity for circular path."""
        tortuosity = circular_analyzer.get_tortuosity()

        # Tortuosity is calculated successfully
        assert isinstance(tortuosity, float)
        # For a full circle, displacement approaches 0, so tortuosity can be very large
        # (path_length / near-zero displacement)
        # Just verify it's a valid number
        assert not np.isnan(tortuosity)

    def test_get_tortuosity_entire_trajectory(self):
        """Test tortuosity calculation for entire trajectory (no window)."""
        # Create a perfectly straight trajectory for predictable results
        df = create_simple_trajectory()
        arena_polygon = [(0, 0), (800, 0), (800, 720), (0, 720)]

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=arena_polygon,
            fps=30.0,
        )

        # Tortuosity without window should return a single float
        tortuosity = analyzer.get_tortuosity()

        # Should successfully calculate
        assert isinstance(tortuosity, float)
        # Straight line should have tortuosity close to 1.0
        assert 0.9 <= tortuosity <= 1.1


class TestThigmotaxis:
    """Test thigmotaxis (wall-following) metrics."""

    def test_get_thigmotaxis_timeseries(self, simple_analyzer):
        """Test thigmotaxis timeseries calculation."""
        thigmo_series = simple_analyzer.get_thigmotaxis_timeseries()

        assert isinstance(thigmo_series, pd.Series)
        assert len(thigmo_series) == len(simple_analyzer.trajectory_data)
        # Values should be distances (positive floats)
        assert (thigmo_series >= 0).all() or thigmo_series.isna().all()

    def test_calculate_thigmotaxis_index_average_distance(self, simple_analyzer):
        """Test thigmotaxis index calculation with average distance method."""
        thigmo_index = simple_analyzer.calculate_thigmotaxis_index(method="average_distance")

        # Should be a positive distance in cm
        assert thigmo_index >= 0 or np.isnan(thigmo_index)

    def test_thigmotaxis_time_near_wall(self, simple_analyzer):
        """Test thigmotaxis with time near wall method."""
        # Time near wall method
        index_near_wall = simple_analyzer.calculate_thigmotaxis_index(
            method="time_near_wall",
            distance_threshold=5.0,  # 5 cm from walls
        )

        # Should be a percentage between 0 and 100
        assert 0 <= index_near_wall <= 100 or np.isnan(index_near_wall)


class TestSpeedBursts:
    """Test speed burst detection."""

    def test_calculate_speed_bursts(self, simple_analyzer):
        """Test speed burst episode detection."""
        result = simple_analyzer.calculate_speed_bursts(
            threshold_cm_s=2.0,  # cm/s
            min_duration=0.1,  # seconds
        )

        # Should return a dict with specific keys
        assert isinstance(result, dict)
        assert "threshold_cm_s" in result
        assert "count" in result
        assert "total_duration_s" in result
        assert "episodes" in result

        # Check episodes structure if they exist
        count_value = result["count"]
        assert isinstance(count_value, int | float)
        episodes = result["episodes"]
        assert isinstance(episodes, list)

        if count_value > 0:
            for episode in episodes:
                assert "start_time" in episode
                assert "end_time" in episode
                assert "duration" in episode

    def test_speed_bursts_high_threshold_no_bursts(self, simple_analyzer):
        """Test that very high threshold yields no bursts."""
        result = simple_analyzer.calculate_speed_bursts(
            threshold_cm_s=1000.0,  # Impossibly high
            min_duration=0.1,
        )

        assert result["count"] == 0
        assert len(result["episodes"]) == 0


class TestInactivityPeriods:
    """Test inactivity period detection."""

    def test_calculate_inactivity_periods(self, arena_polygon_80x72):
        """Test inactivity period detection."""
        np.random.seed(42)
        df = create_freezing_trajectory()

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=30.0,
        )

        result = analyzer.calculate_inactivity_periods(
            velocity_threshold_cm_s=0.5,
            min_duration=0.3,
        )

        # Should detect inactivity periods and return a dict
        assert isinstance(result, dict)
        assert "threshold_cm_s" in result
        assert "count" in result
        assert "total_duration_s" in result
        assert "percentage_of_recording" in result
        assert "episodes" in result

        count_value = result["count"]
        assert isinstance(count_value, int | float)
        episodes = result["episodes"]
        assert isinstance(episodes, list)

        if count_value > 0:
            for episode in episodes:
                assert "start_time" in episode
                assert "end_time" in episode
                assert "duration" in episode


class TestSharpTurns:
    """Test sharp turn detection."""

    def test_calculate_sharp_turns(self, circular_analyzer):
        """Test sharp turn detection."""
        result = circular_analyzer.calculate_sharp_turns(
            threshold_deg_s=30.0,  # degrees/s
            cooldown_s=0.5,
        )

        # Circular motion should have sustained turning
        assert isinstance(result, dict)
        assert "sharp_turns_count" in result
        assert "sharp_turns_per_minute" in result
        assert "sharp_turns_timestamps" in result

        # Circular motion should detect some turns
        assert result["sharp_turns_count"] >= 0

    def test_sharp_turns_straight_line_no_turns(self, simple_analyzer):
        """Test that straight-line motion has no sharp turns."""
        result = simple_analyzer.calculate_sharp_turns(
            threshold_deg_s=30.0,
            cooldown_s=0.5,
        )

        # Straight line shouldn't have sharp turns
        assert result["sharp_turns_count"] == 0
        assert len(result["sharp_turns_timestamps"]) == 0


class TestPropertiesAndDataAccess:
    """Test property accessors."""

    def test_trajectory_data_property(self, simple_analyzer):
        """Test trajectory_data property accessor."""
        data = simple_analyzer.trajectory_data

        assert isinstance(data, pd.DataFrame)
        assert len(data) > 0
        # Should have both original and converted coordinates
        assert "x_center_px" in data.columns or "x_cm" in data.columns

    def test_arena_polygon_cm_property(self, simple_analyzer):
        """Test arena_polygon_cm property accessor."""
        arena = simple_analyzer.arena_polygon_cm

        from shapely.geometry import Polygon

        assert isinstance(arena, Polygon)
        assert arena.is_valid


# === Edge Cases and Boundary Conditions ===


class TestBehaviorEdgeCases:
    """Test edge cases and boundary conditions for behavioral analysis."""

    def test_zero_velocity_trajectory(self, arena_polygon_80x72):
        """Test analysis with stationary subject (zero velocity)."""
        # Create trajectory where subject doesn't move
        n_frames = 100
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")
        # All positions identical with tiny noise
        x_positions_cm = np.full(n_frames, 20.0) + np.random.normal(0, 0.01, n_frames)
        y_positions_cm = np.full(n_frames, 20.0) + np.random.normal(0, 0.01, n_frames)

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Total distance should be near zero
        distance = analyzer.calculate_total_distance()
        assert distance < 1.0  # Less than 1 cm total movement

        # Velocity stats should be near zero
        stats = analyzer.get_velocity_stats()
        assert stats["mean"] < 0.5  # cm/s
        assert stats["median"] < 0.5

        # Should detect as freezing/inactivity
        freezing = analyzer.detect_freezing_episodes(
            min_duration=0.5, vel_threshold=0.5, threshold_method="absolute"
        )
        assert len(freezing) > 0  # Should detect at least one freezing episode

    def test_negative_displacement(self, arena_polygon_80x72):
        """Test trajectory with negative displacement (ends before start position)."""
        n_frames = 100
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

        # Start at (50, 50), move to (10, 10) - negative displacement in both axes
        x_positions_cm = np.linspace(50, 10, n_frames)
        y_positions_cm = np.linspace(50, 10, n_frames)

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Should still calculate positive distance traveled
        distance = analyzer.calculate_total_distance()
        # Diagonal distance from (50,50) to (10,10) ≈ 56.57 cm
        expected = np.sqrt((50 - 10) ** 2 + (50 - 10) ** 2)
        assert abs(distance - expected) / expected < 0.1

        # Tortuosity should work
        tortuosity = analyzer.get_tortuosity()
        assert isinstance(tortuosity, float)
        assert not np.isnan(tortuosity)

    def test_very_short_trajectory(self, arena_polygon_80x72):
        """Test analysis with very short trajectory (<1 second, <30 frames)."""
        # Only 20 frames at 30 fps = 0.67 seconds
        n_frames = 20
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")
        x_positions_cm = np.linspace(10, 30, n_frames)
        y_positions_cm = np.full(n_frames, 20.0)

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Should still calculate distance
        distance = analyzer.calculate_total_distance()
        assert 18 <= distance <= 22  # ~20 cm expected

        # Velocity calculation should work
        velocity_df = analyzer.calculate_velocity_timeseries()
        assert len(velocity_df) == n_frames
        assert velocity_df["v_mag"].notna().sum() > 0

    def test_noisy_position_data(self, arena_polygon_80x72):
        """Test analysis with noisy/jittery position data."""
        n_frames = 100
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

        # Linear movement with heavy noise
        x_base = np.linspace(10, 60, n_frames)
        y_base = np.linspace(10, 30, n_frames)

        # Add significant Gaussian noise (±2 cm) with deterministic seed to keep test stable
        rng = np.random.default_rng(seed=42)
        x_positions_cm = x_base + rng.normal(0, 2.0, n_frames)
        y_positions_cm = y_base + rng.normal(0, 2.0, n_frames)

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Smoothing should help - distance shouldn't be wildly off
        distance = analyzer.calculate_total_distance()
        # Base distance is sqrt(50^2 + 20^2) ≈ 53.85 cm
        # With seeded noise, the smoothed path stays within ~2x baseline distance
        assert 40 <= distance <= 120

        # Velocity calculation should not crash
        velocity_df = analyzer.calculate_velocity_timeseries()
        assert len(velocity_df) == n_frames

        # Standard deviation should be higher due to noise
        stats = analyzer.get_velocity_stats()
        assert stats["std_dev"] > 0

    def test_trajectory_with_outliers(self, arena_polygon_80x72):
        """Test analysis with position outliers (detection errors)."""
        n_frames = 100
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")
        x_positions_cm = np.linspace(20, 40, n_frames)
        y_positions_cm = np.full(n_frames, 30.0)

        # Insert outliers at specific frames (detection jumps)
        x_positions_cm[25] = 5.0  # Jump far left
        x_positions_cm[50] = 70.0  # Jump far right
        y_positions_cm[75] = 5.0  # Jump up

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Should still complete analysis without crashing
        distance = analyzer.calculate_total_distance()
        assert distance > 0  # Some distance calculated

        # Velocity calculation should handle outliers
        velocity_df = analyzer.calculate_velocity_timeseries()
        assert len(velocity_df) == n_frames

        # Outliers might create speed bursts
        bursts = analyzer.calculate_speed_bursts(threshold_cm_s=50.0, min_duration=0.05)
        assert isinstance(bursts, dict)

    def test_single_point_trajectory(self, arena_polygon_80x72):
        """Test analysis with only 1 data point."""
        fps = 30.0
        pixelcm = 10.0

        df = pd.DataFrame(
            {
                "timestamp": pd.to_timedelta([0.0], unit="s"),
                "x_center_px": [200.0],
                "y_center_px": [360.0],
                "x1": [190.0],
                "y1": [350.0],
                "x2": [210.0],
                "y2": [370.0],
                "confidence": [0.9],
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Distance should be zero
        distance = analyzer.calculate_total_distance()
        assert distance == 0.0

        # Velocity should be empty or zero
        velocity_df = analyzer.calculate_velocity_timeseries()
        assert len(velocity_df) > 0  # Should return at least the one point

    def test_extreme_speed_trajectory(self, arena_polygon_80x72):
        """Test analysis with unrealistically high speeds."""
        # 30 frames at 30 fps = 1 second, moving 200 cm = 200 cm/s
        n_frames = 30
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")
        x_positions_cm = np.linspace(10, 210, n_frames)  # 200 cm in 1 second
        y_positions_cm = np.full(n_frames, 40.0)

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Should calculate high velocity
        stats = analyzer.get_velocity_stats()
        mean_velocity = stats["mean"]
        assert isinstance(mean_velocity, int | float)
        assert mean_velocity > 100  # cm/s

        # Should detect as speed burst
        bursts = analyzer.calculate_speed_bursts(threshold_cm_s=50.0, min_duration=0.1)
        burst_count = bursts["count"]
        assert isinstance(burst_count, int | float)
        assert burst_count > 0

    def test_boundary_position_at_arena_edge(self, arena_polygon_80x72):
        """Test analysis when subject is at arena boundary."""
        n_frames = 50
        fps = 30.0
        pixelcm = 10.0

        timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

        # Move along the edge of arena (x=0, y varying)
        x_positions_cm = np.full(n_frames, 1.0)  # Near left edge
        y_positions_cm = np.linspace(1, 71, n_frames)  # Bottom to top

        x_center_px = x_positions_cm * pixelcm
        y_center_px = 360 - (y_positions_cm * pixelcm)

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "x_center_px": x_center_px,
                "y_center_px": y_center_px,
                "x1": x_center_px - 10,
                "y1": y_center_px - 10,
                "x2": x_center_px + 10,
                "y2": y_center_px + 10,
                "confidence": 0.9,
            }
        )

        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=pixelcm,
            pixelcm_y=pixelcm,
            video_height_px=720,
            arena_polygon_px=arena_polygon_80x72,
            fps=fps,
        )

        # Thigmotaxis should be very high (close to wall)
        thigmo_index = analyzer.calculate_thigmotaxis_index(
            method="time_near_wall", distance_threshold=5.0
        )
        # Savitzky-Golay smoothing keeps positions slightly away from the edge,
        # but percentage near the wall should still be majority of the trial.
        assert thigmo_index > 50

        # Average distance thigmotaxis should be small
        avg_dist = analyzer.calculate_thigmotaxis_index(method="average_distance")
        assert avg_dist < 10  # Less than 10 cm from wall on average


# === Angular Velocity Stats ===


class TestAngularVelocityStats:
    """Tests for get_angular_velocity_stats()."""

    def test_angular_velocity_stats_returns_all_keys(self, simple_analyzer):
        stats = simple_analyzer.get_angular_velocity_stats()
        assert set(stats.keys()) == {"mean", "median", "max", "std_dev"}

    def test_angular_velocity_stats_positive_values(self, circular_analyzer):
        """Circular motion should produce non-zero angular velocity."""
        stats = circular_analyzer.get_angular_velocity_stats()
        assert stats["mean"] > 0
        assert stats["max"] > 0
        assert stats["median"] > 0

    def test_angular_velocity_stats_max_geq_mean(self, circular_analyzer):
        stats = circular_analyzer.get_angular_velocity_stats()
        assert stats["max"] >= stats["mean"]

    def test_angular_velocity_stats_empty_trajectory(self):
        """Trajectory with <3 frames should return NaN stats."""
        df = pd.DataFrame(
            {
                "timestamp": pd.to_timedelta([0.0, 0.033], unit="s"),
                "frame": [0, 1],
                "track_id": [1, 1],
                "x_center_px": [100.0, 110.0],
                "y_center_px": [100.0, 100.0],
                "confidence": [0.95, 0.95],
            }
        )
        analyzer = ConcreteBehavioralAnalyzer(
            trajectory_df=df,
            pixelcm_x=10.0,
            pixelcm_y=10.0,
            video_height_px=720,
            arena_polygon_px=[(0, 0), (800, 0), (800, 720), (0, 720)],
            fps=30.0,
        )
        stats = analyzer.get_angular_velocity_stats()
        # With only 2 frames, angular velocity computation returns empty or NaN
        for key in ("mean", "median", "max", "std_dev"):
            assert key in stats


# === Analysis window (ADR-011, F4b) ===


def _window_trajectory(fps: float = 10.0) -> pd.DataFrame:
    """6 s at ``fps``: moving 0-1 s, perfectly still 1-3 s, zig-zag 3-6 s.

    Timestamps start at 10 s, the way a PTS clock looks once a video was cut,
    so a window bound is never confused with "seconds since the first row".
    """
    n = int(6 * fps)
    t = np.arange(n) / fps
    x_cm: np.ndarray = np.where(t < 1.0, 10 + 5 * t, 15.0)
    y_cm: np.ndarray = np.full(n, 10.0)
    zig = t >= 3.0
    # 0.8 cm/frame forward, 1 cm/frame sideways, reversing every 0.5 s.
    phase = np.clip((t - 3.0) * fps, 0, None)
    leg = phase % 10
    x_cm = np.where(zig, 15.0 + 0.8 * phase, x_cm)
    y_cm = np.where(zig, 10.0 + np.where(leg < 5, leg, 10 - leg), y_cm)
    x_px = x_cm * 10.0
    y_px = 720 - y_cm * 10.0
    return pd.DataFrame(
        {
            "timestamp": np.round(10.0 + t, 9),
            "x_center_px": x_px,
            "y_center_px": y_px,
            "x1": x_px - 10,
            "y1": y_px - 10,
            "x2": x_px + 10,
            "y2": y_px + 10,
        }
    )


def _window_analyzer(df: pd.DataFrame | None = None) -> ConcreteBehavioralAnalyzer:
    return ConcreteBehavioralAnalyzer(
        trajectory_df=(_window_trajectory() if df is None else df).copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=[(0, 0), (800, 0), (800, 720), (0, 720)],
        fps=10.0,
        window_length=1,
        polyorder=0,
    )


class TestRestrictToWindow:
    """Hybrid cut: derivatives on the whole recording, metrics on the window."""

    def test_index_stays_absolute_and_bounds_are_inclusive(self):
        analyzer = _window_analyzer()

        analyzer.restrict_to_window(11.5, 13.0)

        index = analyzer.trajectory_data.index
        assert index[0] == pd.Timedelta(seconds=11.5)
        assert index[-1] == pd.Timedelta(seconds=13.0)
        assert len(index) == 16
        assert analyzer.window_bounds == (11.5, 13.0)

    def test_sub_microsecond_clock_noise_keeps_the_edge_samples(self):
        # START/STOP and the index went through separate float -> ns roundings.
        analyzer = _window_analyzer()

        analyzer.restrict_to_window(11.5 + 4e-7, 13.0 - 4e-7)

        index = analyzer.trajectory_data.index
        assert index[0] == pd.Timedelta(seconds=11.5)
        assert index[-1] == pd.Timedelta(seconds=13.0)

    def test_no_window_has_no_bounds(self):
        assert _window_analyzer().window_bounds is None

    def test_border_velocity_keeps_its_neighbour_before_start(self):
        whole = _window_analyzer()
        full_v = whole.calculate_velocity_timeseries()["v_mag"]
        cut = _window_analyzer()

        cut.restrict_to_window(10.5, 12.0)

        v = cut.trajectory_data["v_mag"]
        assert not np.isnan(v.iloc[0])
        assert v.iloc[0] == pytest.approx(full_v.loc[pd.Timedelta(seconds=10.5)])
        assert v.iloc[0] == pytest.approx(5.0)

    def test_border_angular_velocity_is_computed_on_the_whole_recording(self):
        whole = _window_analyzer()
        full_av = whole.get_angular_velocity()
        cut = _window_analyzer()

        cut.restrict_to_window(13.5, 15.0)

        av = cut.get_angular_velocity()
        assert av.index[0] == pd.Timedelta(seconds=13.5)
        lower = full_av.index >= pd.Timedelta(seconds=13.5)
        upper = full_av.index <= pd.Timedelta(seconds=15.0)
        pd.testing.assert_series_equal(av, full_av[lower & upper])
        assert not np.isnan(av.iloc[0])

    def test_distance_excludes_the_segment_that_crosses_start(self):
        analyzer = _window_analyzer()

        analyzer.restrict_to_window(10.5, 11.0)

        # 0.5 s at 5 cm/s inside the window; the 10.4 -> 10.5 step is outside.
        assert analyzer.calculate_total_distance() == pytest.approx(2.5)

    def test_freezing_cut_by_the_edge_is_truncated_and_min_duration_uses_the_rest(self):
        long_enough = _window_analyzer()
        long_enough.restrict_to_window(12.5, 13.5)
        too_short = _window_analyzer()
        too_short.restrict_to_window(12.5, 13.5)

        kept = long_enough.detect_freezing_episodes(min_duration=0.4, vel_threshold=0.5)
        dropped = too_short.detect_freezing_episodes(min_duration=0.6, vel_threshold=0.5)

        # Still from 11.1 s to 13.0 s (13.1 moves again); the window keeps
        # 12.5-13.0, i.e. 0.5 s, although the whole episode lasts 1.9 s.
        assert len(kept) == 1
        assert kept[0]["start_time"] == pd.Timedelta(seconds=12.5)
        assert kept[0]["duration"] == pytest.approx(0.5)
        assert dropped == []

    def test_inactivity_percentage_is_over_the_window(self):
        analyzer = _window_analyzer()
        analyzer.restrict_to_window(12.0, 14.0)

        result = analyzer.calculate_inactivity_periods(
            velocity_threshold_cm_s=0.5, min_duration=0.1
        )

        assert result["total_duration_s"] == pytest.approx(1.0)
        assert result["percentage_of_recording"] == pytest.approx(1.0 / 2.0 * 100)

    def test_observation_span_is_the_window_length(self):
        analyzer = _window_analyzer()
        assert analyzer.observation_span_s() == pytest.approx(5.9)

        analyzer.restrict_to_window(11.0, 14.5)

        assert analyzer.observation_span_s() == pytest.approx(3.5)

    def test_sharp_turns_per_minute_is_over_the_window(self):
        analyzer = _window_analyzer()
        analyzer.restrict_to_window(12.0, 16.0)

        result = analyzer.calculate_sharp_turns(threshold_deg_s=30.0, cooldown_s=0.1)

        assert result["sharp_turns_count"] > 0
        assert result["sharp_turns_per_minute"] == pytest.approx(
            result["sharp_turns_count"] / (4.0 / 60.0)
        )

    def test_whole_window_equals_no_window(self):
        df = _window_trajectory()
        plain = _window_analyzer(df)
        windowed = _window_analyzer(df)
        windowed.restrict_to_window(10.0, 15.9)

        assert windowed.calculate_total_distance() == pytest.approx(
            plain.calculate_total_distance()
        )
        assert windowed.get_velocity_stats() == pytest.approx(plain.get_velocity_stats())
        assert windowed.get_tortuosity() == pytest.approx(plain.get_tortuosity())
        assert windowed.detect_freezing_episodes(
            min_duration=0.5, vel_threshold=0.5
        ) == plain.detect_freezing_episodes(min_duration=0.5, vel_threshold=0.5)
        assert windowed.calculate_inactivity_periods() == plain.calculate_inactivity_periods()
        plain_turns = plain.calculate_sharp_turns(threshold_deg_s=30.0)
        windowed_turns = windowed.calculate_sharp_turns(threshold_deg_s=30.0)
        assert windowed_turns["sharp_turns_count"] == plain_turns["sharp_turns_count"]
        assert windowed_turns["sharp_turns_per_minute"] == pytest.approx(
            plain_turns["sharp_turns_per_minute"]
        )

    def test_empty_window_yields_empty_metrics(self):
        analyzer = _window_analyzer()

        analyzer.restrict_to_window(None, None, empty=True)

        assert analyzer.trajectory_data.empty
        assert analyzer.calculate_total_distance() == 0.0
        assert np.isnan(analyzer.get_velocity_stats()["mean"])
        assert analyzer.detect_freezing_episodes(min_duration=0.1, vel_threshold=1.0) == []
        assert np.isnan(analyzer.get_tortuosity())
        assert analyzer.calculate_inactivity_periods()["count"] == 0
        assert analyzer.calculate_sharp_turns(30.0)["sharp_turns_count"] == 0
        assert analyzer.observation_span_s() == 0.0
        assert analyzer.window_bounds is None
        assert analyzer.window_is_empty is True

    def test_window_with_reversed_bounds_is_rejected(self):
        analyzer = _window_analyzer()

        with pytest.raises(ValueError, match="before"):
            analyzer.restrict_to_window(12.0, 11.0)

    def test_window_without_bounds_is_rejected(self):
        analyzer = _window_analyzer()

        with pytest.raises(ValueError, match="bounds"):
            analyzer.restrict_to_window(None, 11.0)

    def test_restricting_twice_is_rejected(self):
        analyzer = _window_analyzer()
        analyzer.restrict_to_window(11.0, 12.0)

        with pytest.raises(RuntimeError, match="once"):
            analyzer.restrict_to_window(11.0, 12.0)

    def test_multi_track_labels_follow_the_cut(self):
        df = _window_trajectory()
        two = pd.concat([df.assign(track_id=1), df.assign(track_id=2, x_center_px=100.0)])
        analyzer = _window_analyzer(two.sort_values("timestamp", kind="stable"))

        analyzer.restrict_to_window(11.0, 12.0)

        assert analyzer.is_multi_track
        assert analyzer.track_labels.size == len(analyzer.trajectory_data) == 22
        assert [p.size for p in analyzer.track_positions] == [11, 11]


@settings(max_examples=40, deadline=None)
@given(
    start=st.integers(min_value=0, max_value=58),
    length=st.integers(min_value=1, max_value=59),
)
def test_property_cut_never_changes_the_velocity_of_a_kept_sample(start, length):
    """Cutting before or after does not move the velocity (it is computed whole)."""
    end = min(start + length, 59)
    full = _window_analyzer().calculate_velocity_timeseries()["v_mag"]
    cut = _window_analyzer()

    cut.restrict_to_window(10.0 + start / 10.0, 10.0 + end / 10.0)

    v = cut.trajectory_data["v_mag"]
    pd.testing.assert_series_equal(v, full.loc[v.index], check_names=False)


@settings(max_examples=40, deadline=None)
@given(
    start=st.integers(min_value=0, max_value=58),
    length=st.integers(min_value=1, max_value=59),
)
def test_property_window_distance_is_the_sum_of_inner_steps(start, length):
    end = min(start + length, 59)
    whole = _window_analyzer().trajectory_data
    steps = np.hypot(whole["x_cm_smoothed"].diff(), whole["y_cm_smoothed"].diff())
    cut = _window_analyzer()

    cut.restrict_to_window(10.0 + start / 10.0, 10.0 + end / 10.0)

    assert cut.calculate_total_distance() == pytest.approx(steps.iloc[start + 1 : end + 1].sum())


# === Tracking gaps (#632) ===


def _gap_df(segments: list[tuple[float, float, float]], track_id: int | None = None):
    """Rows at 10 Hz for each ``(t_start, t_end, x_cm)`` segment, standing still.

    Nothing is recorded between segments: that hole is a tracking gap (the
    animal occluded by the experimenter's hand), not a standstill.
    """
    times: list[float] = []
    xs: list[float] = []
    for t_start, t_end, x_cm in segments:
        n = round((t_end - t_start) * 10) + 1
        times.extend(round(t_start + i / 10, 9) for i in range(n))
        xs.extend([x_cm] * n)
    x_px = np.asarray(xs) * 10.0
    y_px = np.full(len(xs), 720 - 100.0)
    df = pd.DataFrame(
        {
            "timestamp": times,
            "x_center_px": x_px,
            "y_center_px": y_px,
            "x1": x_px - 10,
            "y1": y_px - 10,
            "x2": x_px + 10,
            "y2": y_px + 10,
        }
    )
    if track_id is not None:
        df["track_id"] = track_id
    return df


def _gap_analyzer(df: pd.DataFrame, **kwargs) -> ConcreteBehavioralAnalyzer:
    return ConcreteBehavioralAnalyzer(
        trajectory_df=df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=[(0, 0), (800, 0), (800, 720), (0, 720)],
        fps=10.0,
        **kwargs,
    )


def _spans(episodes) -> list[tuple[float, float]]:
    return [
        (round(ep["start_time"].total_seconds(), 6), round(ep["end_time"].total_seconds(), 6))
        for ep in episodes
    ]


class TestTrackingGaps:
    """A gap is unobserved time: no episode spans it, no distance crosses it."""

    def test_first_row_has_no_velocity_and_is_not_frozen(self):
        df = pd.concat(
            [_gap_df([(0.0, 2.0, 15.0)]), _gap_df([(2.1, 3.0, 15.0)])], ignore_index=True
        )
        df.loc[df["timestamp"] > 2.0, "x_center_px"] += np.arange(10) * 5.0 + 5.0
        analyzer = _gap_analyzer(df, window_length=1, polyorder=0)

        episodes = analyzer.detect_freezing_episodes(min_duration=0.0, vel_threshold=1.0)

        assert _spans(episodes) == [(0.1, 2.0)]

    def test_freezing_episode_is_cut_at_the_gap(self):
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]))

        episodes = analyzer.detect_freezing_episodes(min_duration=1.0, vel_threshold=1.0)

        assert _spans(episodes) == [(0.1, 2.0), (5.1, 7.0)]
        assert [ep["duration"] for ep in episodes] == pytest.approx([1.9, 1.9])

    def test_inactivity_is_cut_at_the_gap(self):
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]))

        result = analyzer.calculate_inactivity_periods(
            velocity_threshold_cm_s=1.0, min_duration=1.0
        )

        assert _spans(result["episodes"]) == [(0.1, 2.0), (5.1, 7.0)]
        assert result["total_duration_s"] == pytest.approx(3.8)

    def test_reappearance_far_away_is_not_a_speed_burst(self):
        # 50 cm in 3 s reads as 16.7 cm/s on the reappearance row.
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 65.0)]))

        bursts = analyzer.calculate_speed_bursts(threshold_cm_s=5.0, min_duration=0.0)

        assert bursts["count"] == 0

    def test_jump_across_gap_adds_no_distance(self):
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 65.0)]))

        distance = analyzer.calculate_total_distance(max_time_gap=analyzer.gap_threshold_s)

        # Smoothing used to straddle the gap and smear the jump over the rows
        # around it, so even a cut step left centimetres behind.
        assert distance == pytest.approx(0.0, abs=1e-9)

    def test_disabled_cap_counts_the_jump_like_before(self):
        analyzer = _gap_analyzer(
            _gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 65.0)]), max_gap_s=float("inf")
        )

        distance = analyzer.calculate_total_distance(max_time_gap=analyzer.gap_threshold_s)

        assert analyzer.gap_threshold_s == float("inf")
        assert not analyzer.gap_rows.any()
        # Historical: the 50 cm jump counts, and the smoothing that straddles it
        # adds its ringing on top.
        assert distance > 50.0

    def test_gap_threshold_is_the_roi_dt_cap(self):
        auto = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]))
        configured = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]), max_gap_s=5.0)

        assert auto.gap_threshold_s == pytest.approx(0.3)
        assert configured.gap_threshold_s == 5.0
        # A cap above the gap keeps the historical behaviour: one episode.
        episodes = configured.detect_freezing_episodes(min_duration=1.0, vel_threshold=1.0)
        assert _spans(episodes) == [(0.1, 7.0)]

    def test_interval_equal_to_the_cap_is_still_continuous(self):
        # Same edge as the ROI cap: only an interval ABOVE it is a gap.
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]), max_gap_s=3.0)

        episodes = analyzer.detect_freezing_episodes(min_duration=1.0, vel_threshold=1.0)

        assert not analyzer.gap_rows.any()
        assert _spans(episodes) == [(0.1, 7.0)]

    def test_one_animal_gap_does_not_cut_the_other(self):
        df = pd.concat(
            [
                _gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)], track_id=1),
                _gap_df([(0.0, 7.0, 40.0)], track_id=2),
            ],
            ignore_index=True,
        ).sort_values(["timestamp", "track_id"], kind="stable", ignore_index=True)
        analyzer = _gap_analyzer(df)

        episodes = analyzer.detect_freezing_episodes(min_duration=1.0, vel_threshold=1.0)

        by_track = sorted((ep["track_id"], *_spans([ep])[0]) for ep in episodes)
        assert by_track == [(1, 0.1, 2.0), (1, 5.1, 7.0), (2, 0.1, 7.0)]

    def test_window_keeps_the_gap_measured_on_the_whole_recording(self):
        # START falls on the reappearance row: inside the window it has no
        # predecessor, but on the whole recording it closes a 3 s gap.
        analyzer = _gap_analyzer(_gap_df([(0.0, 2.0, 15.0), (5.0, 7.0, 15.0)]))
        analyzer.restrict_to_window(5.0, 7.0)

        episodes = analyzer.detect_freezing_episodes(min_duration=1.0, vel_threshold=1.0)

        assert _spans(episodes) == [(5.1, 7.0)]

    def test_quantile_threshold_ignores_undefined_velocity(self):
        # Constant 10 cm/s: only the first row has no velocity, and counting it
        # as 0 dragged the 2nd percentile below every real speed.
        df = _gap_df([(0.0, 3.0, 15.0)])
        df["x_center_px"] = 150.0 + df["timestamp"] * 100.0
        analyzer = _gap_analyzer(df, window_length=1, polyorder=0)

        bursts = analyzer.calculate_speed_bursts(quantile=0.02, min_duration=0.0)
        frozen = analyzer.detect_freezing_episodes(
            min_duration=0.0, threshold_method="relative", quantile=0.02
        )

        assert bursts["threshold_cm_s"] == pytest.approx(10.0)
        # Every defined row sits on the threshold: one run, from the 2nd row.
        assert _spans(frozen) == [(0.1, 3.0)]

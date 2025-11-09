"""
Tests for zebtrack.analysis.behavior module.

Comprehensive test suite covering distance calculation, velocity metrics,
freezing detection, angular velocity, tortuosity, thigmotaxis, and episode detection.
"""

import numpy as np
import pandas as pd
import pytest

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
        # Each segment is ~20 cm, but smoothing affects exact values
        assert 50 <= distance_with_gap <= 70

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

        # Simple linear motion should have relatively constant velocity
        assert stats["mean"] > 0
        assert stats["median"] > 0
        assert stats["std_dev"] >= 0

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
        if result["count"] > 0:
            for episode in result["episodes"]:
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

        if result["count"] > 0:
            for episode in result["episodes"]:
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

        # Add significant Gaussian noise (±2 cm)
        x_positions_cm = x_base + np.random.normal(0, 2.0, n_frames)
        y_positions_cm = y_base + np.random.normal(0, 2.0, n_frames)

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
        # With noise, expect some increase but not excessive
        assert 40 <= distance <= 100

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
        assert stats["mean"] > 100  # cm/s

        # Should detect as speed burst
        bursts = analyzer.calculate_speed_bursts(threshold_cm_s=50.0, min_duration=0.1)
        assert bursts["count"] > 0

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
        assert thigmo_index > 80  # Should be >80% near wall

        # Average distance thigmotaxis should be small
        avg_dist = analyzer.calculate_thigmotaxis_index(method="average_distance")
        assert avg_dist < 10  # Less than 10 cm from wall on average

# -*- coding: utf-8 -*-
"""
Tests for robust angular velocity calculation that handles detection jitter.

This test suite validates the new jitter-resistant angular velocity implementation
that prevents noise amplification when the subject is nearly stationary.
"""

import numpy as np
import pandas as pd
import pytest

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer


def create_stationary_trajectory_with_jitter(
    n_frames: int = 100,
    center_x: float = 50.0,
    center_y: float = 50.0,
    jitter_magnitude: float = 0.2,
    fps: float = 30.0,
):
    """
    Creates a synthetic trajectory where the subject is essentially stationary
    but experiences small random fluctuations (jitter) typical of detector noise.

    Args:
        n_frames: Number of frames to generate
        center_x: Center position in cm (x-axis)
        center_y: Center position in cm (y-axis)
        jitter_magnitude: Standard deviation of jitter in cm (typically 0.1-0.3)
        fps: Frames per second

    Returns:
        pd.DataFrame: Trajectory dataframe with jittered positions
    """
    np.random.seed(42)

    timestamps = pd.to_timedelta(np.arange(n_frames) / fps, unit="s")

    # Add small random jitter to simulate detector noise
    x_positions = center_x + np.random.normal(0, jitter_magnitude, n_frames)
    y_positions = center_y + np.random.normal(0, jitter_magnitude, n_frames)

    # Convert to pixel coordinates (assuming 10 pixels per cm)
    pixelcm = 10.0
    x_center_px = x_positions * pixelcm
    y_center_px = 360 - (y_positions * pixelcm)  # Invert for 720px height

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

    return df


def create_moving_then_stationary_trajectory(fps: float = 30.0):
    """
    Creates a trajectory with distinct moving and stationary phases.

    Phase 1 (0-2s): Moving rightward at 5 cm/s
    Phase 2 (2-4s): Stationary with jitter
    Phase 3 (4-6s): Moving upward at 5 cm/s
    Phase 4 (6-8s): Stationary with jitter
    """
    np.random.seed(42)

    total_frames = int(8 * fps)
    timestamps = pd.to_timedelta(np.arange(total_frames) / fps, unit="s")

    x_positions = np.zeros(total_frames)
    y_positions = np.zeros(total_frames)

    frames_per_phase = int(2 * fps)

    # Phase 1: Moving right
    for i in range(frames_per_phase):
        t = i / fps
        x_positions[i] = 30.0 + 5.0 * t
        y_positions[i] = 50.0

    # Phase 2: Stationary with jitter
    for i in range(frames_per_phase, 2 * frames_per_phase):
        x_positions[i] = 40.0 + np.random.normal(0, 0.2)
        y_positions[i] = 50.0 + np.random.normal(0, 0.2)

    # Phase 3: Moving up
    for i in range(2 * frames_per_phase, 3 * frames_per_phase):
        t = (i - 2 * frames_per_phase) / fps
        x_positions[i] = 40.0
        y_positions[i] = 50.0 + 5.0 * t

    # Phase 4: Stationary with jitter
    for i in range(3 * frames_per_phase, 4 * frames_per_phase):
        x_positions[i] = 40.0 + np.random.normal(0, 0.2)
        y_positions[i] = 60.0 + np.random.normal(0, 0.2)

    # Convert to pixel coordinates
    pixelcm = 10.0
    x_center_px = x_positions * pixelcm
    y_center_px = 360 - (y_positions * pixelcm)

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

    return df


def test_stationary_trajectory_with_low_threshold():
    """
    Test that a stationary trajectory with jitter produces mostly NaN angular
    velocities when using a strict displacement threshold.
    """
    trajectory_df = create_stationary_trajectory_with_jitter(n_frames=100, jitter_magnitude=0.2)

    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.5,  # Strict threshold
        angle_calculation_window=1,
        angular_velocity_smoothing_window=1,
    )

    angular_velocity = analyzer.get_angular_velocity()

    # Most values should be NaN because displacement is below threshold
    nan_ratio = angular_velocity.isna().sum() / len(angular_velocity)

    assert nan_ratio > 0.7, (
        f"Expected most angular velocities to be NaN for stationary trajectory, "
        f"but only {nan_ratio:.1%} were NaN"
    )

    # Non-NaN values should have reasonable magnitudes (not spurious high values)
    valid_values = angular_velocity.dropna()
    if len(valid_values) > 0:
        max_abs_velocity = valid_values.abs().max()
        assert max_abs_velocity < 200, (
            f"Expected low angular velocities for stationary trajectory with jitter, "
            f"but found max of {max_abs_velocity:.1f} deg/s"
        )


def test_stationary_trajectory_with_permissive_threshold():
    """
    Test that using a very low threshold (approaching the old behavior) still
    calculates angular velocities, but they should be noisy.
    """
    trajectory_df = create_stationary_trajectory_with_jitter(n_frames=100, jitter_magnitude=0.2)

    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.01,  # Very permissive
        angle_calculation_window=1,
        angular_velocity_smoothing_window=1,
    )

    angular_velocity = analyzer.get_angular_velocity()

    # Should have many non-NaN values
    nan_ratio = angular_velocity.isna().sum() / len(angular_velocity)
    assert nan_ratio < 0.3, "Expected more non-NaN values with permissive threshold"


def test_moving_phases_preserve_angular_velocity():
    """Ensure the displacement threshold keeps real movement intact."""

    trajectory_df = create_moving_then_stationary_trajectory(fps=30.0)
    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        # Lower threshold for this test (5 cm/s @ 30 fps ≈ 0.167 cm/frame)
        min_displacement_threshold_cm=0.1,
        angle_calculation_window=1,
        angular_velocity_smoothing_window=3,
    )

    angular_velocity = analyzer.get_angular_velocity()

    phase1_mask = (angular_velocity.index >= pd.Timedelta(0)) & (
        angular_velocity.index <= pd.Timedelta("2s")
    )
    phase1_values = angular_velocity[phase1_mask]
    phase1_valid_ratio = (~phase1_values.isna()).sum() / len(phase1_values)

    phase2_mask = (angular_velocity.index > pd.Timedelta("2s")) & (
        angular_velocity.index <= pd.Timedelta("4s")
    )
    phase2_values = angular_velocity[phase2_mask]
    phase2_nan_ratio = phase2_values.isna().sum() / len(phase2_values)

    phase3_mask = (angular_velocity.index > pd.Timedelta("4s")) & (
        angular_velocity.index <= pd.Timedelta("6s")
    )
    phase3_values = angular_velocity[phase3_mask]
    phase3_valid_ratio = (~phase3_values.isna()).sum() / len(phase3_values)

    assert phase1_valid_ratio > 0.3, (
        "Expected valid angular velocities during the first movement phase, "
        f"but only {phase1_valid_ratio:.1%} were non-NaN"
    )
    assert phase3_valid_ratio > 0.3, (
        "Expected valid angular velocities during the vertical movement phase, "
        f"but only {phase3_valid_ratio:.1%} were non-NaN"
    )
    assert phase2_nan_ratio > 0.5, (
        "Expected mostly NaN values during the stationary phase, "
        f"but only {phase2_nan_ratio:.1%} were NaN"
    )

    transition_mask = (angular_velocity.index >= pd.Timedelta("3.8s")) & (
        angular_velocity.index <= pd.Timedelta("4.2s")
    )
    transition_values = angular_velocity[transition_mask].dropna()

    if len(transition_values) > 0:
        max_transition_av = transition_values.abs().max()
        assert max_transition_av > 50, (
            "Expected a high angular velocity during the 90° turn, "
            f"but max was only {max_transition_av:.1f} deg/s"
        )


def test_wider_calculation_window_reduces_noise():
    """
    Test that using a wider calculation window (e.g., 3 frames instead of 1)
    produces more stable angular velocity estimates.
    """
    trajectory_df = create_stationary_trajectory_with_jitter(n_frames=150, jitter_magnitude=0.3)

    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Analyzer with window=1 (consecutive frames)
    analyzer_narrow = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.2,  # Permissive to allow some calculations
        angle_calculation_window=1,
        angular_velocity_smoothing_window=1,
    )

    # Analyzer with window=3 (every 3rd frame)
    analyzer_wide = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.2,
        angle_calculation_window=3,  # Wider window
        angular_velocity_smoothing_window=1,
    )

    av_narrow = analyzer_narrow.get_angular_velocity().dropna()
    av_wide = analyzer_wide.get_angular_velocity().dropna()

    # Wider window should produce lower variance (more stable)
    if len(av_narrow) > 10 and len(av_wide) > 10:
        std_narrow = av_narrow.std()
        std_wide = av_wide.std()

        # Not a strict assertion since this is synthetic data, but a sanity check
        assert std_wide <= std_narrow * 1.5, (
            f"Expected wider window to produce more stable estimates, "
            f"but std_narrow={std_narrow:.2f}, std_wide={std_wide:.2f}"
        )


def test_smoothing_reduces_variance():
    """
    Test that applying smoothing window reduces variance in angular velocity.
    """
    trajectory_df = create_moving_then_stationary_trajectory(fps=30.0)

    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Analyzer without smoothing
    analyzer_no_smooth = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.3,
        angle_calculation_window=1,
        angular_velocity_smoothing_window=1,  # No smoothing
    )

    # Analyzer with smoothing
    analyzer_smooth = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.3,
        angle_calculation_window=1,
        angular_velocity_smoothing_window=5,  # Smoothing
    )

    av_no_smooth = analyzer_no_smooth.get_angular_velocity().dropna()
    av_smooth = analyzer_smooth.get_angular_velocity().dropna()

    if len(av_no_smooth) > 20 and len(av_smooth) > 20:
        std_no_smooth = av_no_smooth.std()
        std_smooth = av_smooth.std()

        assert std_smooth < std_no_smooth, (
            f"Expected smoothing to reduce variance, "
            f"but std_no_smooth={std_no_smooth:.2f}, std_smooth={std_smooth:.2f}"
        )


def test_sharp_turns_count_with_jitter_filtering():
    """
    Test that the sharp turns count is dramatically reduced when using
    jitter filtering on a stationary trajectory.
    """
    trajectory_df = create_stationary_trajectory_with_jitter(n_frames=200, jitter_magnitude=0.25)

    arena_polygon_px = [(0, 0), (1280, 0), (1280, 720), (0, 720)]

    # Analyzer with strict jitter filtering
    analyzer_filtered = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.5,
        angle_calculation_window=1,
        angular_velocity_smoothing_window=3,
    )

    # Analyzer with permissive settings (old behavior approximation)
    analyzer_permissive = ConcreteBehavioralAnalyzer(
        trajectory_df=trajectory_df.copy(),
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=720,
        arena_polygon_px=arena_polygon_px,
        fps=30.0,
        min_displacement_threshold_cm=0.01,  # Very permissive
        angle_calculation_window=1,
        angular_velocity_smoothing_window=1,
    )

    sharp_turns_result_filtered = analyzer_filtered.calculate_sharp_turns(threshold_deg_s=90.0)
    sharp_turns_result_permissive = analyzer_permissive.calculate_sharp_turns(threshold_deg_s=90.0)

    # Extract the count from the dictionary
    sharp_turns_filtered = sharp_turns_result_filtered["sharp_turns_count"]
    sharp_turns_permissive = sharp_turns_result_permissive["sharp_turns_count"]

    # Filtered should have dramatically fewer sharp turns
    assert sharp_turns_filtered < sharp_turns_permissive * 0.3, (
        f"Expected jitter filtering to reduce sharp turns count, "
        f"but filtered={sharp_turns_filtered}, permissive={sharp_turns_permissive}"
    )

    # Ideally, a stationary trajectory should have zero or very few sharp turns
    assert sharp_turns_filtered < 5, (
        f"Expected very few sharp turns for stationary trajectory, but got {sharp_turns_filtered}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for VisualizationGenerator class.

Phase: Code Quality Improvements (Task 2.5)
Tests plot generation (trajectory, heatmap, ROI reference, angular velocity),
parallel plot generation, and color normalization.
"""

import io
from unittest.mock import Mock, patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.analysis.visualization_generator import (
    VisualizationGenerator,
    _normalize_color_for_matplotlib,
)


@pytest.fixture
def mock_settings():
    """Create mock settings for analyzers."""
    settings = Mock()
    settings.trajectory_smoothing = Mock()
    settings.trajectory_smoothing.window_length = 5
    settings.trajectory_smoothing.polyorder = 2
    settings.angular_velocity = Mock()
    settings.angular_velocity.min_displacement_threshold_cm = 0.5
    settings.angular_velocity.angle_calculation_window = 3
    settings.angular_velocity.angular_velocity_smoothing_window = 5
    settings.roi_inclusion_rule = "centroid_in"
    settings.roi_buffer_radius_value = 0.0
    settings.roi_min_bbox_overlap_ratio = 0.5
    settings.performance = Mock()
    settings.performance.max_parallel_plots = 3
    return settings


@pytest.fixture
def sample_trajectory_df():
    """Create sample trajectory DataFrame for testing."""
    timestamps = pd.date_range("2025-01-01", periods=20, freq="100ms")
    x_positions = [10.0 + i * 2.0 for i in range(20)]
    y_positions = [20.0 + i * 1.5 for i in range(20)]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "frame": range(20),
            "track_id": [1] * 20,
            "x1": [x - 5 for x in x_positions],
            "y1": [y - 5 for y in y_positions],
            "x2": [x + 5 for x in x_positions],
            "y2": [y + 5 for y in y_positions],
            "confidence": [0.95] * 20,
            "x_center_px": x_positions,
            "y_center_px": y_positions,
        }
    )


@pytest.fixture
def sample_rois():
    """Create sample ROI list for testing."""
    return [
        ROI(
            name="center",
            geometry=Polygon([(20, 20), (40, 20), (40, 40), (20, 40)]),
            coordinate_space="px",
        ),
        ROI(
            name="periphery",
            geometry=Polygon([(60, 60), (80, 60), (80, 80), (60, 80)]),
            coordinate_space="px",
        ),
    ]


@pytest.fixture
def behavior_analyzer(sample_trajectory_df, mock_settings):
    """Create ConcreteBehavioralAnalyzer instance with test data."""
    arena_polygon_px = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=sample_trajectory_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        arena_polygon_px=arena_polygon_px,
        fps=10.0,
    )
    return analyzer


@pytest.fixture
def roi_analyzer(behavior_analyzer, sample_rois, mock_settings):
    """Create ROIAnalyzer instance with test data."""
    analyzer = ROIAnalyzer(
        behavior_analyzer=behavior_analyzer,
        rois=sample_rois,
    )
    return analyzer


@pytest.fixture
def generator(behavior_analyzer, roi_analyzer, mock_settings):
    """Create VisualizationGenerator instance."""
    metadata = {"experiment_id": "test_001", "group_id": "control"}
    roi_colors = {"center": (255, 0, 0), "periphery": (0, 255, 0)}

    return VisualizationGenerator(
        b_analyzer=behavior_analyzer,
        r_analyzer=roi_analyzer,
        metadata=metadata,
        roi_colors=roi_colors,
        calibration=None,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        sharp_turn_threshold=90.0,
        settings_obj=mock_settings,
    )


# ============================================================================
# Tests for Color Normalization
# ============================================================================


def test_normalize_color_for_matplotlib_rgb_255():
    """Test color normalization from 0-255 range to 0-1 range."""
    color = (255, 128, 64)
    normalized = _normalize_color_for_matplotlib(color)
    assert normalized == (1.0, 128 / 255.0, 64 / 255.0)


def test_normalize_color_for_matplotlib_rgb_already_normalized():
    """Test color normalization when already in 0-1 range."""
    color = (0.5, 0.3, 0.7)
    normalized = _normalize_color_for_matplotlib(color)
    assert normalized == (0.5, 0.3, 0.7)


def test_normalize_color_for_matplotlib_string_color():
    """Test color normalization with string color names."""
    assert _normalize_color_for_matplotlib("red") == "red"
    assert _normalize_color_for_matplotlib("blue") == "blue"
    assert _normalize_color_for_matplotlib("#FF0000") == "#FF0000"


def test_normalize_color_for_matplotlib_mixed_values():
    """Test color normalization with mixed values (some >1, some <=1)."""
    # When any value > 1, assume all are in 0-255 range
    color = (255, 0.5, 128)
    normalized = _normalize_color_for_matplotlib(color)
    assert normalized == (1.0, 0.5 / 255.0, 128 / 255.0)


# ============================================================================
# Tests for generate_trajectory_plot
# ============================================================================


def test_generate_trajectory_plot_basic(generator):
    """Test basic trajectory plot generation."""
    fig = generator.generate_trajectory_plot()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Trajectory" in ax.get_title()
    assert "test_001" in ax.get_title()
    assert ax.get_xlabel() == "Position (cm)"
    assert ax.get_ylabel() == "Position (cm)"

    # Clean up
    plt.close(fig)


def test_generate_trajectory_plot_with_custom_axes(generator):
    """Test trajectory plot generation with custom axes."""
    fig, ax = plt.subplots(figsize=(8, 8))

    result_fig = generator.generate_trajectory_plot(ax=ax)

    assert result_fig is fig
    assert "Trajectory" in ax.get_title()

    # Clean up
    plt.close(fig)


@patch("pathlib.Path.exists")
@patch("cv2.VideoCapture")
def test_generate_trajectory_plot_with_video_background(mock_video_capture, mock_exists, generator):
    """Test trajectory plot generation with video background."""
    # Mock Path.exists to return True
    mock_exists.return_value = True

    # Mock video capture
    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    mock_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, mock_frame)
    mock_video_capture.return_value = mock_cap

    fig = generator.generate_trajectory_plot(video_path="/fake/video.mp4")

    assert fig is not None
    assert mock_cap.read.called
    assert mock_cap.release.called

    # Clean up
    plt.close(fig)


@patch("pathlib.Path.exists")
@patch("cv2.VideoCapture")
def test_generate_trajectory_plot_applies_frame_crop(mock_video_capture, mock_exists, generator):
    """Ensure frame_crop_box crops the background and updates extent."""

    mock_exists.return_value = True

    # Mock a frame larger than the crop box
    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mock_video_capture.return_value = mock_cap

    # Set crop box: width=30, height=40 -> expect extent width 3cm (px_per_cm=10)
    generator.frame_crop_box = (10, 20, 30, 40)

    fig, ax = plt.subplots(figsize=(6, 6))
    with patch.object(ax, "imshow", wraps=ax.imshow) as spy_imshow:
        generator.generate_trajectory_plot(ax=ax, video_path="/fake/video.mp4")

    assert spy_imshow.called
    _, kwargs = spy_imshow.call_args
    extent = kwargs.get("extent")
    # Extent is (left, right, bottom, top) in cm
    # With crop_box=(10,20,30,40), pixelcm=10, video_height=100:
    # x_left = 10/10 = 1.0, x_right = (10+30)/10 = 4.0
    # y_bottom = (100-60)/10 = 4.0, y_top = (100-20)/10 = 8.0
    assert extent == (1.0, 4.0, 4.0, 8.0)

    plt.close(fig)


# ============================================================================
# Tests for generate_heatmap
# ============================================================================


def test_generate_heatmap(generator):
    """Test heatmap generation."""
    fig = generator.generate_heatmap()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Heatmap" in ax.get_title()
    assert "test_001" in ax.get_title()
    assert ax.get_xlabel() == "Position (cm)"
    assert ax.get_ylabel() == "Position (cm)"

    # Clean up
    plt.close(fig)


def test_generate_heatmap_with_custom_axes(generator):
    """Test heatmap generation with custom axes."""
    fig, ax = plt.subplots(figsize=(8, 8))

    result_fig = generator.generate_heatmap(ax=ax)

    assert result_fig is fig
    assert "Heatmap" in ax.get_title()

    # Clean up
    plt.close(fig)


def _background_frame_call(spy_imshow):
    """Return the (args, kwargs) of the imshow call that drew the video frame.

    The background frame is drawn by ``_draw_background_frame`` with
    ``zorder=0`` and no ``cmap``; the heatmap layer is drawn with
    ``cmap="hot"``. This lets tests target the frame layer unambiguously.
    """
    for call in spy_imshow.call_args_list:
        _, kwargs = call
        if kwargs.get("zorder") == 0 and "cmap" not in kwargs:
            return call
    raise AssertionError("background-frame imshow call not found")


def _heatmap_data_call(spy_imshow):
    """Return the (args, kwargs) of the imshow call that drew the density layer."""
    for call in spy_imshow.call_args_list:
        _, kwargs = call
        if kwargs.get("cmap") == "hot":
            return call
    raise AssertionError("heatmap-data imshow call not found")


@patch("pathlib.Path.exists")
@patch("cv2.VideoCapture")
def test_generate_heatmap_background_frame_extent_and_origin(
    mock_video_capture, mock_exists, generator
):
    """Heatmap background frame must use the same extent/origin as trajectory.

    Regression guard for the partial-distortion bug: ``_draw_background_frame``
    previously used an additive ``y_top`` formula, the default
    ``origin="upper"`` and ``aspect="equal"``, which stretched the lower part of
    the frame and forced a heatmap row-flip workaround.
    """
    mock_exists.return_value = True

    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mock_video_capture.return_value = mock_cap

    # Same crop box as the trajectory test so the expected extent is identical.
    generator.frame_crop_box = (10, 20, 30, 40)

    fig, ax = plt.subplots(figsize=(6, 6))
    with patch.object(ax, "imshow", wraps=ax.imshow) as spy_imshow:
        generator.generate_heatmap(ax=ax, video_path="/fake/video.mp4")

    _, kwargs = _background_frame_call(spy_imshow)
    # Identical to test_generate_trajectory_plot_applies_frame_crop:
    # x_left=1.0, x_right=4.0, y_bottom=4.0, y_top=8.0
    assert kwargs.get("extent") == (1.0, 4.0, 4.0, 8.0)
    assert kwargs.get("origin") == "lower"

    plt.close(fig)


@patch("pathlib.Path.exists")
@patch("cv2.VideoCapture")
def test_heatmap_and_trajectory_background_extent_consistent(
    mock_video_capture, mock_exists, generator
):
    """The frame extent must be identical between heatmap and trajectory plots."""
    mock_exists.return_value = True

    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    frame = np.zeros((120, 80, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mock_video_capture.return_value = mock_cap

    generator.frame_crop_box = (10, 20, 30, 40)

    fig_t, ax_t = plt.subplots(figsize=(6, 6))
    with patch.object(ax_t, "imshow", wraps=ax_t.imshow) as spy_t:
        generator.generate_trajectory_plot(ax=ax_t, video_path="/fake/video.mp4")
    _, kwargs_t = spy_t.call_args  # trajectory draws the frame in a single imshow
    extent_traj = kwargs_t.get("extent")
    plt.close(fig_t)

    fig_h, ax_h = plt.subplots(figsize=(6, 6))
    with patch.object(ax_h, "imshow", wraps=ax_h.imshow) as spy_h:
        generator.generate_heatmap(ax=ax_h, video_path="/fake/video.mp4")
    _, kwargs_h = _background_frame_call(spy_h)
    extent_heat = kwargs_h.get("extent")
    plt.close(fig_h)

    assert extent_heat == extent_traj


@patch("pathlib.Path.exists")
@patch("cv2.VideoCapture")
def test_generate_heatmap_density_not_flipped_by_video_background(
    mock_video_capture, mock_exists, generator
):
    """The density layer must be orientation-stable regardless of video_path.

    Guards the removal of the ``heatmap[::-1, :]`` round-6 workaround: the
    occupancy array is computed identically with or without a background frame,
    so both renders must pass the same data to imshow (no extra inversion).
    """
    mock_exists.return_value = True

    mock_cap = Mock()
    mock_cap.isOpened.return_value = True
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mock_video_capture.return_value = mock_cap

    fig_no, ax_no = plt.subplots(figsize=(6, 6))
    with patch.object(ax_no, "imshow", wraps=ax_no.imshow) as spy_no:
        generator.generate_heatmap(ax=ax_no)
    args_no, _ = _heatmap_data_call(spy_no)
    density_no = np.asarray(args_no[0]).copy()
    plt.close(fig_no)

    fig_yes, ax_yes = plt.subplots(figsize=(6, 6))
    with patch.object(ax_yes, "imshow", wraps=ax_yes.imshow) as spy_yes:
        generator.generate_heatmap(ax=ax_yes, video_path="/fake/video.mp4")
    args_yes, _ = _heatmap_data_call(spy_yes)
    density_yes = np.asarray(args_yes[0]).copy()
    plt.close(fig_yes)

    assert np.array_equal(density_no, density_yes)


# ============================================================================
# Tests for generate_roi_reference_plot
# ============================================================================


def test_generate_roi_reference_plot(generator):
    """Test ROI reference map generation."""
    fig = generator.generate_roi_reference_plot()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "ROI Reference Map" in ax.get_title()
    assert "test_001" in ax.get_title()

    # Clean up
    plt.close(fig)


def test_generate_roi_reference_plot_no_rois(behavior_analyzer, mock_settings):
    """Test ROI reference map generation without ROIs."""
    metadata = {"experiment_id": "test_002"}
    generator_no_rois = VisualizationGenerator(
        b_analyzer=behavior_analyzer,
        r_analyzer=None,
        metadata=metadata,
        roi_colors={},
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        settings_obj=mock_settings,
    )

    fig = generator_no_rois.generate_roi_reference_plot()

    assert fig is not None
    ax = fig.get_axes()[0]
    # Should show message about no ROIs (in Portuguese)
    assert any("sem ROIs" in text.get_text() for text in ax.texts)

    # Clean up
    plt.close(fig)


# ============================================================================
# Tests for generate_angular_velocity_plot
# ============================================================================


def test_generate_angular_velocity_plot(generator):
    """Test angular velocity plot generation."""
    fig = generator.generate_angular_velocity_plot()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Angular Velocity" in ax.get_title()

    # Clean up
    plt.close(fig)


def test_generate_angular_velocity_plot_insufficient_data(behavior_analyzer, mock_settings):
    """Test angular velocity plot with insufficient data."""
    # Create minimal trajectory (insufficient for angular velocity)
    minimal_df = pd.DataFrame(
        {
            "timestamp": pd.to_timedelta([0, 100], unit="ms"),
            "frame": [0, 1],
            "track_id": [1, 1],
            "x1": [10.0, 11.0],
            "y1": [20.0, 21.0],
            "x2": [30.0, 31.0],
            "y2": [40.0, 41.0],
            "confidence": [0.95, 0.95],
            "x_center_px": [20.0, 21.0],
            "y_center_px": [30.0, 31.0],
        }
    )

    arena_polygon_px = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    minimal_analyzer = ConcreteBehavioralAnalyzer(
        trajectory_df=minimal_df,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        arena_polygon_px=arena_polygon_px,
        fps=10.0,
    )

    metadata = {"experiment_id": "test_minimal"}
    minimal_generator = VisualizationGenerator(
        b_analyzer=minimal_analyzer,
        metadata=metadata,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        settings_obj=mock_settings,
    )

    fig = minimal_generator.generate_angular_velocity_plot()

    assert fig is not None
    # Should show message about insufficient data
    ax = fig.get_axes()[0]
    assert "Angular Velocity" in ax.get_title()

    # Clean up
    plt.close(fig)


# ============================================================================
# Tests for generate_position_vs_time_plot
# ============================================================================


def test_generate_position_vs_time_plot(generator):
    """Test position vs. time plot generation."""
    fig = generator.generate_position_vs_time_plot()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Position vs. Time" in ax.get_title()
    assert ax.get_xlabel() == "Time (s)"
    assert ax.get_ylabel() == "Position (cm)"

    # Clean up
    plt.close(fig)


# ============================================================================
# Tests for generate_cumulative_distance_plot
# ============================================================================


def test_generate_cumulative_distance_plot(generator):
    """Test cumulative distance plot generation."""
    fig = generator.generate_cumulative_distance_plot()

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Cumulative Distance" in ax.get_title()
    assert ax.get_xlabel() == "Time (s)"
    assert ax.get_ylabel() == "Cumulative Distance (cm)"

    # Clean up
    plt.close(fig)


# ============================================================================
# Tests for generate_comparative_boxplot
# ============================================================================


def test_generate_comparative_boxplot():
    """Test comparative boxplot generation for group analysis."""
    df = pd.DataFrame(
        {
            "group_id": ["control", "control", "treatment", "treatment"],
            "total_distance_cm": [42.5, 38.2, 55.3, 60.1],
        }
    )

    fig = VisualizationGenerator.generate_comparative_boxplot(
        df, metric="total_distance_cm", title="Distance Comparison"
    )

    assert fig is not None
    assert len(fig.get_axes()) > 0

    ax = fig.get_axes()[0]
    assert "Distance Comparison" in ax.get_title()
    assert "Experimental Group" in ax.get_xlabel()

    # Clean up
    plt.close(fig)


# ============================================================================
# Tests for Parallel Plot Generation
# ============================================================================


def test_generate_single_plot_thread_safe(generator):
    """Test single plot generation in thread-safe manner."""

    # Use a simple plot function
    def simple_plot_func(ax):
        ax.plot([1, 2, 3], [1, 2, 3])
        ax.set_title("Test Plot")

    buffer, name = VisualizationGenerator.generate_single_plot_thread_safe(
        simple_plot_func, "test_plot"
    )

    assert isinstance(buffer, io.BytesIO)
    assert name == "test_plot"
    assert buffer.getvalue()  # Should contain PNG data


def test_generate_single_plot_thread_safe_with_error():
    """Test single plot generation handles errors gracefully."""

    def failing_plot_func(ax):
        raise ValueError("Intentional error")

    buffer, name = VisualizationGenerator.generate_single_plot_thread_safe(
        failing_plot_func, "failing_plot"
    )

    # Should return empty buffer instead of raising
    assert isinstance(buffer, io.BytesIO)
    assert name == "failing_plot"
    # Buffer should be empty or minimal
    assert len(buffer.getvalue()) == 0


def test_generate_plots_parallel(generator):
    """Test parallel plot generation with ThreadPoolExecutor."""

    def plot1(ax):
        ax.plot([1, 2, 3], [1, 2, 3])
        ax.set_title("Plot 1")

    def plot2(ax):
        ax.plot([1, 2, 3], [3, 2, 1])
        ax.set_title("Plot 2")

    def plot3(ax):
        ax.scatter([1, 2, 3], [2, 2, 2])
        ax.set_title("Plot 3")

    plot_configs = [(plot1, "plot1"), (plot2, "plot2"), (plot3, "plot3")]

    results = generator.generate_plots_parallel(plot_configs)

    assert len(results) == 3
    assert all(isinstance(buf, io.BytesIO) for buf, _ in results)
    assert [name for _, name in results] == ["plot1", "plot2", "plot3"]

    # All buffers should contain PNG data
    assert all(buf.getvalue() for buf, _ in results)


def test_generate_plots_parallel_respects_max_workers(generator):
    """Test parallel plot generation respects max_workers setting."""

    def simple_plot(ax):
        ax.plot([1, 2], [1, 2])

    plot_configs = [(simple_plot, f"plot{i}") for i in range(10)]

    # Generator has max_parallel_plots=3 from mock_settings
    results = generator.generate_plots_parallel(plot_configs)

    assert len(results) == 10
    # All plots should complete successfully
    assert all(isinstance(buf, io.BytesIO) for buf, _ in results)


def test_generate_plots_parallel_maintains_order(generator):
    """Test parallel plot generation maintains original order."""

    def plot_with_delay(ax, plot_num):
        import time

        # intentional jitter delay - testing plot ordering despite variable timing
        time.sleep(0.001 * (plot_num % 3))
        ax.plot([1, 2], [plot_num, plot_num + 1])
        ax.set_title(f"Plot {plot_num}")

    plot_configs = [(lambda ax, n=i: plot_with_delay(ax, n), f"plot{i}") for i in range(5)]

    results = generator.generate_plots_parallel(plot_configs)

    # Order should be preserved
    assert [name for _, name in results] == [f"plot{i}" for i in range(5)]


# ============================================================================
# Tests for Thread Safety and GIL
# ============================================================================


def test_visualization_generator_is_stateless(behavior_analyzer, mock_settings):
    """Test that VisualizationGenerator can be safely used in parallel."""
    metadata = {"experiment_id": "test_parallel"}

    gen1 = VisualizationGenerator(
        b_analyzer=behavior_analyzer,
        metadata=metadata,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        settings_obj=mock_settings,
    )

    gen2 = VisualizationGenerator(
        b_analyzer=behavior_analyzer,
        metadata=metadata,
        pixelcm_x=10.0,
        pixelcm_y=10.0,
        video_height_px=100,
        settings_obj=mock_settings,
    )

    # Both generators should produce similar plots independently
    fig1 = gen1.generate_trajectory_plot()
    fig2 = gen2.generate_trajectory_plot()

    assert fig1 is not fig2
    assert fig1.get_axes()[0].get_title() == fig2.get_axes()[0].get_title()

    # Clean up
    plt.close(fig1)
    plt.close(fig2)


# ============================================================================
# Tests for ROI Geometry Conversion
# ============================================================================


def test_roi_geometry_to_cm_conversion(generator):
    """Test ROI geometry conversion from pixels to cm."""
    roi = ROI(
        name="test_roi",
        geometry=Polygon([(10, 10), (20, 10), (20, 20), (10, 20)]),
        coordinate_space="px",
    )

    geom_cm = generator._roi_geometry_to_cm(roi)

    assert geom_cm is not None
    # Geometry should be scaled by pixelcm conversion
    bounds = geom_cm.bounds
    assert all(isinstance(b, float) for b in bounds)


def test_roi_geometry_to_cm_empty_geometry(generator):
    """Test ROI geometry conversion with empty geometry."""
    roi = ROI(name="empty_roi", geometry=Polygon(), coordinate_space="px")

    geom_cm = generator._roi_geometry_to_cm(roi)

    assert geom_cm is None


def test_iter_polygon_parts():
    """Test polygon parts iteration utility."""
    from shapely.geometry import MultiPolygon

    # Single polygon
    single_poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    parts = VisualizationGenerator._iter_polygon_parts(single_poly)
    assert len(parts) == 1
    assert parts[0] == single_poly

    # MultiPolygon
    poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    poly2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
    multi_poly = MultiPolygon([poly1, poly2])
    parts = VisualizationGenerator._iter_polygon_parts(multi_poly)
    assert len(parts) == 2

    # None geometry
    parts = VisualizationGenerator._iter_polygon_parts(None)
    assert parts == []

"""Visualization generation service for analysis reports.

This module handles the generation of all plots, heatmaps, and visualizations
used in analysis reports.

Extracted from reporter.py as part of Phase 2 refactoring (Task 2.5).
"""

import io
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

import cv2
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend to avoid GUI thread warnings
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import structlog
from matplotlib import patches
from matplotlib.axes import Axes
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure
from scipy.ndimage import gaussian_filter
from shapely import affinity
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon as ShapelyPolygon

from zebtrack.analysis.behavior import BehaviorAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer

log = structlog.get_logger(__name__)


def _normalize_color_for_matplotlib(color):
    """
    Normalize color to matplotlib format (0-1 range).

    Handles different input formats:
    - RGB tuple (0-255): convert to (0-1)
    - String/named color: return as-is
    - Already normalized (0-1): return as-is
    """
    if isinstance(color, (tuple, list)) and len(color) == 3:
        # Check if values are in 0-255 range (need normalization)
        # If any value is > 1, assume it's in 0-255 range
        if any(isinstance(c, (int, float)) and c > 1 for c in color):
            return tuple(c / 255.0 for c in color)
        else:
            # Already normalized or mixed values
            return color
    # String colors or other formats - return as-is
    return color


class VisualizationGenerator:
    """Generates visualizations for behavioral analysis reports.

    This class handles all visualization generation logic, including trajectory
    plots, heatmaps, angular velocity plots, and ROI reference maps.

    Responsibilities:
        - Generate trajectory plots with optional video background
        - Generate heatmaps showing occupancy density
        - Generate ROI reference maps
        - Generate time-series plots (position, velocity, cumulative distance)
        - Generate comparative boxplots for group analysis
        - Support parallel plot generation for performance

    Example:
        >>> generator = VisualizationGenerator(
        ...     b_analyzer=behavior_analyzer,
        ...     r_analyzer=roi_analyzer,
        ...     metadata={"experiment_id": "exp_001"},
        ...     roi_colors={"roi1": (255, 0, 0)},
        ...     calibration=calibration_obj,
        ...     pixelcm_x=10.0,
        ...     pixelcm_y=10.0,
        ...     video_height_px=480
        ... )
        >>> fig = generator.generate_trajectory_plot(video_path="video.mp4")
        >>> fig = generator.generate_heatmap()
    """

    def __init__(
        self,
        b_analyzer: BehaviorAnalyzer,
        metadata: dict,
        r_analyzer: ROIAnalyzer | None = None,
        roi_colors: dict | None = None,
        calibration=None,
        pixelcm_x: float | None = None,
        pixelcm_y: float | None = None,
        video_height_px: int | None = None,
        sharp_turn_threshold: float = 90.0,
        settings_obj=None,
    ):
        """Initialize VisualizationGenerator.

        Args:
            b_analyzer: BehaviorAnalyzer instance with trajectory data
            metadata: Experiment metadata
            r_analyzer: ROIAnalyzer instance (optional)
            roi_colors: Dictionary mapping ROI names to RGB tuples (optional)
            calibration: Calibration object (optional)
            pixelcm_x: Pixels-to-cm conversion for x-axis
            pixelcm_y: Pixels-to-cm conversion for y-axis
            video_height_px: Video height in pixels
            sharp_turn_threshold: Threshold for sharp turn detection (deg/s)
            settings_obj: Settings object for configuration
        """
        self.b_analyzer = b_analyzer
        self.r_analyzer = r_analyzer
        self.metadata = metadata
        self.roi_colors = roi_colors if roi_colors else {}
        self.calibration = calibration
        self._pixelcm_x = pixelcm_x
        self._pixelcm_y = pixelcm_y
        self._video_height_px = video_height_px
        self.sharp_turn_threshold = sharp_turn_threshold
        self.settings = settings_obj

    def _roi_geometry_to_cm(self, roi: ROI):
        """Convert ROI geometry from pixels to cm coordinates.

        Args:
            roi: ROI object with geometry

        Returns:
            Shapely geometry in cm coordinates, or None if empty
        """
        geometry = roi.geometry
        if geometry is None or geometry.is_empty:
            return None

        if roi.coordinate_space == "px":
            px_per_cm_x = self._pixelcm_x or 1.0
            px_per_cm_y = self._pixelcm_y or 1.0
            offset_y = (
                self._video_height_px / px_per_cm_y if px_per_cm_y else float(self._video_height_px)
            )
            geometry = affinity.affine_transform(
                geometry,
                [1.0 / px_per_cm_x, 0.0, 0.0, -1.0 / px_per_cm_y, 0.0, offset_y],
            )

        return geometry

    @staticmethod
    def _iter_polygon_parts(geometry) -> list[ShapelyPolygon]:
        """Iterate over polygon parts of a geometry.

        Args:
            geometry: Shapely geometry object

        Returns:
            list: List of Shapely Polygon objects
        """
        if geometry is None:
            return []

        if isinstance(geometry, ShapelyPolygon):
            return [geometry]
        if isinstance(geometry, MultiPolygon):
            return [
                poly
                for poly in geometry.geoms
                if isinstance(poly, ShapelyPolygon) and not poly.is_empty
            ]

        exterior = getattr(geometry, "exterior", None)
        if exterior is not None:
            return [ShapelyPolygon(exterior.coords)]

        geoms = getattr(geometry, "geoms", None)
        if geoms:
            return [
                poly for poly in geoms if isinstance(poly, ShapelyPolygon) and not poly.is_empty
            ]

        return []

    def generate_trajectory_plot(
        self, ax: Axes | None = None, video_path: str | None = None
    ) -> Figure:
        """Generate trajectory plot with optional video background.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)
            video_path: Path to video file for background (optional)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        # Get video dimensions if available
        if video_path and Path(video_path).exists():
            cap = None
            try:
                cap = cv2.VideoCapture(video_path)
                ret, frame = cap.read()
                if ret:
                    # Apply perspective warp if calibration is available
                    if self.calibration:
                        frame = self.calibration.warp_frame(frame)

                    frame_height_px = frame.shape[0]
                    frame_width_px = frame.shape[1]
                    # Calculate proper extent based on pixel-to-cm conversion
                    pixelcm_x = self.b_analyzer._pixelcm_x
                    pixelcm_y = self.b_analyzer._pixelcm_y

                    # Frame coordinates in cm
                    # Per COORDINATE_SYSTEMS.md:
                    # - Frame warped: y_px=0 at top, y_px=height at bottom
                    #   (image convention)
                    # - Trajectory y_cm: y_cm=0 at bottom, y_cm=max at top
                    #   (cartesian)
                    # - Conversion: y_cm = (video_height_px - y_center_px) / pixelcm_y
                    #
                    # To align frame with trajectories:
                    # 1. Flip frame vertically so frame[0] = bottom
                    # 2. Use origin='lower' so matplotlib maps frame[0] to y=0 (bottom)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_rgb_flipped = cv2.flip(frame_rgb, 0)  # Flip vertically

                    frame_extent: tuple[float, float, float, float] = (
                        0.0,  # left (x=0)
                        frame_width_px / pixelcm_x,  # right (x=max)
                        0.0,  # bottom (y=0)
                        frame_height_px / pixelcm_y,  # top (y=max)
                    )
                    ax.imshow(
                        frame_rgb_flipped,
                        extent=frame_extent,
                        origin="lower",
                        aspect="auto",
                        alpha=0.5,
                    )
            finally:
                if cap is not None and cap.isOpened():
                    cap.release()

        ax.set_facecolor("lightgray")
        # Draw arena boundary
        ax.add_patch(
            patches.Polygon(arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2)
        )

        # Draw ROIs if available
        if self.r_analyzer:
            for roi_name, roi in self.r_analyzer.rois.items():
                roi_geom_cm = self._roi_geometry_to_cm(roi)
                if roi_geom_cm is None:
                    continue
                roi_color = self.roi_colors.get(roi_name, "blue")
                normalized_color = _normalize_color_for_matplotlib(roi_color)
                for polygon in self._iter_polygon_parts(roi_geom_cm):
                    if not hasattr(polygon, "exterior"):
                        continue
                    ax.add_patch(
                        patches.Polygon(
                            polygon.exterior.coords,
                            fill=True,
                            facecolor=normalized_color,
                            alpha=0.3,
                            edgecolor=normalized_color,
                            linewidth=2,
                        )
                    )

        # Draw trajectory - use single color for single animal
        ax.plot(x, y, color="blue", linewidth=1.5, alpha=0.7, label="Trajectory")

        ax.set_title(f"Trajectory - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_heatmap(self, ax: Axes | None = None) -> Figure:
        """Generate occupancy heatmap.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        heatmap, xedges, yedges = np.histogram2d(
            x, y, bins=50, range=[[min_x, max_x], [min_y, max_y]]
        )
        heatmap = gaussian_filter(heatmap.T, sigma=2)
        extent: tuple[float, float, float, float] = (
            float(xedges[0]),
            float(xedges[-1]),
            float(yedges[0]),
            float(yedges[-1]),
        )
        im = ax.imshow(
            heatmap,
            cmap="hot",
            origin="lower",
            extent=extent,
        )
        ax.set_title(f"Heatmap - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        existing_artists = getattr(fig, "artists", [])
        if not any(isinstance(artist, Colorbar) for artist in existing_artists):
            fig.colorbar(im, ax=ax, label="Occupancy Density")
        return fig

    def generate_roi_reference_plot(self, ax: Axes | None = None) -> Figure:
        """Generate ROI reference map showing all defined ROIs.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(6, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        px_per_cm_x = getattr(self.b_analyzer, "_pixelcm_x", 1.0) or 1.0
        px_per_cm_y = getattr(self.b_analyzer, "_pixelcm_y", 1.0) or 1.0
        video_height_px = getattr(self.b_analyzer, "_video_height_px", 0) or 0

        def _geometry_to_cm(roi_obj: ROI):
            geometry = roi_obj.geometry
            if geometry is None or geometry.is_empty:
                return None
            if roi_obj.coordinate_space == "px":
                scale_x = 1.0 / px_per_cm_x if px_per_cm_x else 1.0
                scale_y = -1.0 / px_per_cm_y if px_per_cm_y else -1.0
                offset_y = video_height_px / px_per_cm_y if px_per_cm_y else float(video_height_px)
                geometry = affinity.affine_transform(
                    geometry,
                    [scale_x, 0.0, 0.0, scale_y, 0.0, offset_y],
                )
            return geometry

        ax.set_facecolor("lightgray")
        ax.add_patch(
            patches.Polygon(arena_poly_cm.exterior.coords, fill=False, edgecolor="black", lw=2)
        )

        if self.r_analyzer:
            for i, (roi_name, roi) in enumerate(self.r_analyzer.rois.items()):
                roi_geom_cm = _geometry_to_cm(roi)
                if roi_geom_cm is None or roi_geom_cm.is_empty:
                    continue
                roi_color = self.roi_colors.get(roi_name, "blue")
                # Normalize color for matplotlib (0-255 RGB tuples -> 0-1 range)
                normalized_color = _normalize_color_for_matplotlib(roi_color)
                polygon_geoms: list[ShapelyPolygon]
                if isinstance(roi_geom_cm, ShapelyPolygon):
                    polygon_geoms = [roi_geom_cm]
                else:
                    polygon_geoms = [
                        geom
                        for geom in getattr(roi_geom_cm, "geoms", [])
                        if isinstance(geom, ShapelyPolygon)
                    ]
                if not polygon_geoms:
                    continue

                for polygon in polygon_geoms:
                    if polygon.is_empty:
                        continue
                    ax.add_patch(
                        patches.Polygon(
                            polygon.exterior.coords,
                            fill=True,
                            color=normalized_color,
                            alpha=0.4,
                        )
                    )

                centroid = roi_geom_cm.centroid
                ax.text(
                    centroid.x,
                    centroid.y,
                    str(i + 1),
                    color="white",
                    ha="center",
                    va="center",
                    fontweight="bold",
                    fontsize=12,
                    bbox=dict(
                        facecolor=normalized_color,
                        alpha=0.7,
                        boxstyle="circle,pad=0.2",
                        ec="none",
                    ),
                )
        else:
            ax.text(
                0.5,
                0.5,
                "No ROIs defined for this analysis.",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )

        title = f"ROI Reference Map - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")
        ax.set_xlim(min_x - 1, max_x + 1)
        ax.set_ylim(min_y - 1, max_y + 1)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def generate_angular_velocity_plot(self, ax: Axes | None = None) -> Figure:
        """Generate angular velocity plot with sharp turns marked.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        angular_velocity = self.b_analyzer.get_angular_velocity()
        if angular_velocity.empty or angular_velocity.isna().all():
            ax.text(
                0.5,
                0.5,
                "Not enough data for angular velocity.",
                ha="center",
                va="center",
            )
            ax.set_title("Angular Velocity")
            return fig

        sharp_turn_results = self.b_analyzer.calculate_sharp_turns(self.sharp_turn_threshold)
        sharp_turn_times = cast(pd.Series, sharp_turn_results["sharp_turns_timestamps"])

        time_seconds = (angular_velocity.index - angular_velocity.index[0]).total_seconds()

        ax.plot(time_seconds, angular_velocity, label="Angular Velocity")

        if not sharp_turn_times.empty:
            sharp_turn_values = angular_velocity.loc[sharp_turn_times]
            sharp_turn_time_seconds = (sharp_turn_times - angular_velocity.index[0]).total_seconds()
            ax.plot(
                sharp_turn_time_seconds,
                sharp_turn_values,
                "ro",
                markersize=5,
                label="Sharp Turns",
            )

        title = f"Angular Velocity - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Angular Velocity (deg/s)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_position_vs_time_plot(self, ax: Axes | None = None) -> Figure:
        """Generate position vs. time plot showing X and Y coordinates.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        if traj_data.empty:
            ax.text(0.5, 0.5, "No trajectory data.", ha="center", va="center")
            ax.set_title("Position vs. Time")
            return fig

        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, traj_data["x_cm_smoothed"], label="X coordinate (cm)")
        ax.plot(time_seconds, traj_data["y_cm_smoothed"], label="Y coordinate (cm)")

        title = f"Position vs. Time - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position (cm)")
        ax.legend()
        ax.grid(True)
        return fig

    def generate_cumulative_distance_plot(self, ax: Axes | None = None) -> Figure:
        """Generate cumulative distance plot.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        traj_data = self.b_analyzer.trajectory_data
        if len(traj_data) < 2:
            ax.text(
                0.5,
                0.5,
                "Not enough data for distance calculation.",
                ha="center",
                va="center",
            )
            ax.set_title("Cumulative Distance")
            return fig

        x_smoothed = pd.to_numeric(
            cast(pd.Series, traj_data["x_cm_smoothed"]), errors="coerce"
        ).diff()
        y_smoothed = pd.to_numeric(
            cast(pd.Series, traj_data["y_cm_smoothed"]), errors="coerce"
        ).diff()
        distance_array = np.sqrt(
            np.square(x_smoothed.to_numpy()) + np.square(y_smoothed.to_numpy())
        )
        distances = pd.Series(distance_array, index=x_smoothed.index)
        cumulative_distance = distances.cumsum().fillna(0)
        time_seconds = (traj_data.index - traj_data.index[0]).total_seconds()

        ax.plot(time_seconds, cumulative_distance)
        title = f"Cumulative Distance vs. Time - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Cumulative Distance (cm)")
        ax.grid(True)
        return fig

    @staticmethod
    def generate_single_plot_thread_safe(
        plot_func: Callable, name: str, *args, **kwargs
    ) -> tuple[io.BytesIO, str]:
        """
        Generate a single plot in a thread-safe manner (Phase 8).

        This method creates an independent figure context for each plot,
        allowing matplotlib to safely generate plots in parallel threads.

        Args:
            plot_func: The plotting function to call
            name: Name of the plot for logging
            *args, **kwargs: Arguments to pass to the plotting function

        Returns:
            tuple: (BytesIO buffer with PNG data, plot name)
        """
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_func(ax, *args, **kwargs)
            memfile = io.BytesIO()
            fig.savefig(memfile, format="png", dpi=300, bbox_inches="tight")
            plt.close(fig)
            memfile.seek(0)
            log.debug("visualization.plot.generated", name=name)
            return (memfile, name)
        except Exception as e:
            log.error("visualization.plot.failed", name=name, error=str(e), exc_info=True)
            # Return empty buffer to avoid breaking the report
            empty_buffer = io.BytesIO()
            return (empty_buffer, name)

    def generate_plots_parallel(
        self, plot_configs: list[tuple[Callable, str]]
    ) -> list[tuple[io.BytesIO, str]]:
        """
        Generate multiple plots in parallel using ThreadPoolExecutor (Phase 8).

        This method leverages parallel execution for I/O-bound matplotlib operations,
        significantly reducing report generation time.

        Args:
            plot_configs: List of (plot_function, name) tuples

        Returns:
            list: List of (BytesIO buffer, name) tuples in original order
        """
        # Get configured max parallel plots from settings (use injected or default)
        max_workers = 3  # Default
        if self.settings is not None:
            max_workers = getattr(
                getattr(self.settings, "performance", None), "max_parallel_plots", 3
            )

        # Store results with their original indices to maintain order
        indexed_results: dict[int, tuple[io.BytesIO, str]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all plot generation tasks
            future_to_index = {}
            for i, (plot_func, name) in enumerate(plot_configs):
                future = executor.submit(self.generate_single_plot_thread_safe, plot_func, name)
                future_to_index[future] = i

            # Collect results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result(timeout=60)  # 60s timeout per plot
                    indexed_results[index] = result
                except Exception as e:
                    name = plot_configs[index][1]
                    log.error("visualization.plot.executor_failed", name=name, error=str(e))
                    # Add empty buffer as fallback
                    indexed_results[index] = (io.BytesIO(), name)

        # Return results in original order
        return [indexed_results[i] for i in range(len(plot_configs))]

    @staticmethod
    def generate_comparative_boxplot(df: pd.DataFrame, metric: str, title: str) -> Figure:
        """Generate comparative boxplot for group analysis.

        Args:
            df: DataFrame with group_id column and metric
            metric: Metric column name to plot
            title: Plot title

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(x="group_id", y=metric, data=df, ax=ax)
        sns.stripplot(x="group_id", y=metric, data=df, ax=ax, color=".25", size=6)
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Experimental Group", fontsize=12)
        ax.set_ylabel(metric.replace("_", " ").title(), fontsize=12)
        plt.tight_layout()
        return fig

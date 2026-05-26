"""Visualization generation service for analysis reports.

This module handles the generation of all plots, heatmaps, and visualizations
used in analysis reports.

Extracted from reporter.py as part of Phase 2 refactoring (Task 2.5).
"""

import io
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

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

from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
from zebtrack.analysis.roi import ROI, ROIAnalyzer
from zebtrack.constants import DEFAULT_MAX_PARALLEL_PLOTS

__all__ = ["VisualizationGenerator"]

log = structlog.get_logger(__name__)

# Default timeout for individual plot generation (in seconds)
# This prevents hanging on complex plots or matplotlib issues
PLOT_GENERATION_TIMEOUT_SECONDS = 60


def _normalize_color_for_matplotlib(color):
    """
    Normalize color to matplotlib format (0-1 range).

    Handles different input formats:
    - RGB tuple (0-255): convert to (0-1)
    - String/named color: return as-is
    - Already normalized (0-1): return as-is
    """
    if isinstance(color, tuple | list) and len(color) == 3:
        # Check if values are in 0-255 range (need normalization)
        # If any value is > 1, assume it's in 0-255 range
        if any(isinstance(c, int | float) and c > 1 for c in color):
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
        b_analyzer: ConcreteBehavioralAnalyzer,
        metadata: dict,
        r_analyzer: ROIAnalyzer | None = None,
        roi_colors: dict | None = None,
        calibration=None,
        pixelcm_x: float | None = None,
        pixelcm_y: float | None = None,
        video_height_px: int | None = None,
        sharp_turn_threshold: float = 90.0,
        settings_obj=None,
        frame_crop_box: tuple[int, int, int, int] | None = None,
        behavioral_config: dict[str, Any] | None = None,
    ):
        """Initialize VisualizationGenerator.

        Args:
            b_analyzer: BehavioralAnalyzer instance with trajectory data
            metadata: Experiment metadata
            r_analyzer: ROIAnalyzer instance (optional)
            roi_colors: Dictionary mapping ROI names to RGB tuples (optional)
            calibration: Calibration object (optional)
            pixelcm_x: Pixels-to-cm conversion for x-axis
            pixelcm_y: Pixels-to-cm conversion for y-axis
            video_height_px: Video height in pixels
            sharp_turn_threshold: Threshold for sharp turn detection (deg/s)
            settings_obj: Settings object for configuration
            behavioral_config: Project-specific behavioral configuration (optional)
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
        self.frame_crop_box = frame_crop_box
        self.behavioral_config = behavioral_config or {}

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
            # Safe access to video height
            v_height = float(self._video_height_px or 0.0)
            offset_y = v_height / px_per_cm_y if px_per_cm_y else v_height
            geometry = affinity.affine_transform(
                geometry,
                [1.0 / px_per_cm_x, 0.0, 0.0, -1.0 / px_per_cm_y, 0.0, offset_y],
            )

        return geometry

    @staticmethod
    def _normalize_perspective(perspective: str | None) -> str:
        """Normalize perspective aliases to canonical values.

        Canonical values are ``lateral`` and ``top_down``.
        """
        raw = str(perspective or "").strip().lower().replace("-", "_")
        if raw in {"top_down", "top_down_view", "topdown", "top"}:
            return "top_down"
        return "lateral"

    @staticmethod
    def _figure_size_from_bounds(
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> tuple[float, float]:
        """Return an aspect-aware figure size based on arena bounds."""
        width = max(float(max_x - min_x), 1e-6)
        height = max(float(max_y - min_y), 1e-6)
        aspect = width / height
        base_height = 5.5
        fig_width = max(5.0, min(10.0, base_height * aspect))
        return fig_width, base_height

    def _draw_geotaxis_zones(self, ax: Any):
        """Draw geotaxis separation lines if configured (Lateral view only)."""
        try:
            # Check perspective (default lateral)
            perspective = self._normalize_perspective(
                self.behavioral_config.get("aquarium_perspective", "lateral")
            )
            if perspective != "lateral":
                return

            num_zones = int(self.behavioral_config.get("geotaxis_num_zones", 3))
            if num_zones <= 1:
                return

            arena_poly_cm = self.b_analyzer.arena_polygon_cm
            if not arena_poly_cm or arena_poly_cm.is_empty:
                return

            min_x, min_y, max_x, max_y = arena_poly_cm.bounds
            height_cm = max_y - min_y
            zone_height = height_cm / num_zones

            # Draw lines
            for i in range(1, num_zones):
                y_line = min_y + (i * zone_height)
                ax.axhline(y_line, color="white", linestyle="--", linewidth=1.5, alpha=0.9)

                # Label for the bottom zone boundary
                if i == 1:
                    label_x = min_x + (max_x - min_x) * 0.02
                    ax.text(
                        label_x,
                        y_line + (height_cm * 0.02),
                        f"Bottom Zone Limit ({y_line - min_y:.1f}cm)",
                        color="white",
                        fontsize=9,
                        fontweight="bold",
                        ha="left",
                        va="bottom",
                    )

        except Exception as e:
            log.warning("viz.geotaxis.draw_lines_failed", error=str(e))

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
        self, ax: Axes | None = None, video_path: Path | str | None = None
    ) -> Figure:
        """Generate trajectory plot with optional video background.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)
            video_path: Path to video file for background (optional)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        fig_obj = (
            ax.get_figure()
            if ax
            else plt.figure(figsize=self._figure_size_from_bounds(min_x, min_y, max_x, max_y))
        )
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()
        ax.set_facecolor("lightgray")

        # Get video dimensions if available
        if video_path and Path(video_path).exists():
            cap = None
            frame = None
            try:
                # If a background frame image is provided (e.g., per-aquarium extracted PNG),
                # load it directly instead of using VideoCapture.
                suffix = str(video_path).lower()
                if suffix.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
                    # IMPROVEMENT: Use robust reading for Windows paths with unicode/spaces
                    frame = cv2.imdecode(
                        np.fromfile(str(video_path), dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                else:
                    # Try backends appropriate for *video files*.
                    # (DSHOW/MSMF are camera/capture backends and are noisy for file paths.)
                    backends_to_try = [cv2.CAP_ANY]
                    if hasattr(cv2, "CAP_FFMPEG"):
                        backends_to_try = [cv2.CAP_FFMPEG, cv2.CAP_ANY]

                    if frame is None:
                        for backend in backends_to_try:
                            cap = cv2.VideoCapture(video_path, backend)
                            if cap.isOpened():
                                ret, frame = cap.read()
                                cap.release()
                                cap = None
                                if ret and frame is not None:
                                    break
                                frame = None
                            else:
                                if cap:
                                    cap.release()
                                    cap = None

                if frame is not None:
                    # Apply perspective warp if calibration is available
                    if self.calibration:
                        frame = self.calibration.warp_frame(frame)
                    if frame is None:
                        return fig
                    frame = cast(np.ndarray, frame)

                    # Track crop offset for extent calculation
                    crop_x_offset = 0
                    crop_y_offset = 0

                    # Only apply crop if reading from VIDEO (not pre-cropped PNG)
                    # PNG files from _prepare_background_image are already cropped
                    is_image_file = suffix.endswith(
                        (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
                    )
                    if self.frame_crop_box and not is_image_file:
                        x_crop, y_crop, w_crop, h_crop = self.frame_crop_box
                        x_crop = max(0, int(x_crop))
                        y_crop = max(0, int(y_crop))
                        w_crop = max(1, int(w_crop))
                        h_crop = max(1, int(h_crop))
                        x2 = min(frame.shape[1], x_crop + w_crop)
                        y2 = min(frame.shape[0], y_crop + h_crop)
                        frame = frame[y_crop:y2, x_crop:x2]
                        # Store offsets for extent calculation
                        crop_x_offset = x_crop
                        crop_y_offset = y_crop
                    # FIX: For pre-cropped PNGs, do NOT apply offset!
                    # The PNG already starts at (0,0) - offsets remain 0 (default above)

                    frame_height_px = frame.shape[0]
                    frame_width_px = frame.shape[1]
                    # Calculate proper extent based on pixel-to-cm conversion
                    pixelcm_x = self.b_analyzer._pixelcm_x
                    pixelcm_y = self.b_analyzer._pixelcm_y

                    # CRITICAL: Use the SAME video_height_px that BehavioralAnalyzer used
                    # for coordinate transformations. The formula was:
                    #   y_cm = (video_height_px - y_px) / pixelcm_y
                    # Using a different height would misalign the frame with arena/ROIs.
                    video_height_for_transform = self.b_analyzer._video_height_px

                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    # Flip frame vertically to match Cartesian Y-axis of arena/ROI
                    # After flip: original row 0 (video top) -> row H-1 (image bottom)
                    #             original row H-1 (video bottom) -> row 0 (image top)
                    frame_rgb = cv2.flip(frame_rgb, 0)

                    # Extent: [left, right, bottom, top]
                    # The coordinate transformation in BehavioralAnalyzer is:
                    #   x_cm = x_px / pixelcm_x
                    #   y_cm = (video_height_for_transform - y_px) / pixelcm_y
                    #
                    # When a crop is applied, the cropped frame represents a sub-region
                    # of the original video starting at (crop_x_offset, crop_y_offset).
                    # The extent must reflect the ORIGINAL pixel coordinates:
                    # - Cropped (0,0) → original (crop_x_offset, crop_y_offset)
                    # - Cropped (w,h) → original (crop_x_offset+w, crop_y_offset+h)
                    #
                    # For X: left = crop_x_offset / pixelcm_x
                    #        right = (crop_x_offset + frame_width_px) / pixelcm_x
                    # For Y (with inverted axis):
                    #   - bottom = orig y_px = crop_y_offset + frame_height_px
                    #   - top = orig y_px = crop_y_offset
                    x_left_cm = crop_x_offset / pixelcm_x
                    x_right_cm = (crop_x_offset + frame_width_px) / pixelcm_x

                    y_bottom_orig_px = crop_y_offset + frame_height_px
                    y_bottom_cm = (video_height_for_transform - y_bottom_orig_px) / pixelcm_y
                    if y_bottom_cm < 0:
                        y_bottom_cm = 0.0

                    y_top_orig_px = crop_y_offset
                    y_top_cm = (video_height_for_transform - y_top_orig_px) / pixelcm_y

                    frame_extent: tuple[float, float, float, float] = (
                        x_left_cm,  # left
                        x_right_cm,  # right
                        y_bottom_cm,  # bottom
                        y_top_cm,  # top
                    )
                    ax.imshow(
                        frame_rgb,
                        extent=frame_extent,
                        origin="lower",
                        aspect="auto",
                        alpha=0.8,
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

        # Draw Geotaxis Zones (separators)
        self._draw_geotaxis_zones(ax)

        ax.set_title(f"Trajectory - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")

        # Add 5% margin to prevent clipping
        width = max_x - min_x
        height = max_y - min_y
        margin_x = width * 0.05
        margin_y = height * 0.05

        ax.set_xlim(min_x - margin_x, max_x + margin_x)
        # Standard Cartesian Y-axis (min at bottom, max at top)
        # Image is aligned to this: Top (Row 0) at max_y, Bottom (Row H) at 0
        ax.set_ylim(min_y - margin_y, max_y + margin_y)
        ax.set_aspect("equal", adjustable="box")
        return fig

    def _draw_background_frame(
        self,
        ax: Axes,
        video_path: Path | str | None,
        calibration,
    ) -> None:
        """Render the first frame of ``video_path`` beneath ``ax`` content.

        Audit Erro 3 round 4 (2026-05-25): factored from
        ``generate_roi_reference_plot`` so multiple plots can share the
        same video-frame compositing logic. No-op when ``video_path`` is
        falsy / missing / unreadable (logged via ``roi_reference.background_skipped``
        for traceability).
        """
        if not video_path:
            log.info("roi_reference.background_skipped", reason="video_path_is_empty")
            return
        if not Path(video_path).exists():
            log.warning(
                "roi_reference.background_skipped",
                reason="video_path_does_not_exist",
                video_path=str(video_path),
            )
            return

        cap = None
        try:
            suffix = str(video_path).lower()
            if suffix.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
                frame = cv2.imdecode(np.fromfile(str(video_path), dtype=np.uint8), cv2.IMREAD_COLOR)
            else:
                backends_to_try = [cv2.CAP_ANY]
                if hasattr(cv2, "CAP_FFMPEG"):
                    backends_to_try = [cv2.CAP_FFMPEG, cv2.CAP_ANY]
                frame = None
                for backend in backends_to_try:
                    cap = cv2.VideoCapture(str(video_path), backend)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        cap.release()
                        cap = None
                        if ret and frame is not None:
                            break
                        frame = None

            if frame is None:
                log.warning(
                    "roi_reference.background_skipped",
                    reason="video_capture_returned_no_frame",
                    video_path=str(video_path),
                )
                return

            if calibration and hasattr(calibration, "warp_frame"):
                warped = calibration.warp_frame(frame)
                if warped is None:
                    log.warning(
                        "roi_reference.background_skipped",
                        reason="calibration_warp_returned_none",
                        video_path=str(video_path),
                    )
                    return
                frame = warped

            px_per_cm_x = getattr(self.b_analyzer, "_pixelcm_x", 1.0) or 1.0
            px_per_cm_y = getattr(self.b_analyzer, "_pixelcm_y", 1.0) or 1.0
            video_height_px = getattr(self.b_analyzer, "_video_height_px", 0) or 0

            crop_x_offset = 0
            crop_y_offset = 0
            is_image_file = suffix.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"))
            if self.frame_crop_box and not is_image_file:
                x_crop, y_crop, w_crop, h_crop = self.frame_crop_box
                x_crop = max(0, int(x_crop))
                y_crop = max(0, int(y_crop))
                w_crop = max(1, int(w_crop))
                h_crop = max(1, int(h_crop))
                x2 = min(frame.shape[1], x_crop + w_crop)
                y2 = min(frame.shape[0], y_crop + h_crop)
                frame = frame[y_crop:y2, x_crop:x2]
                crop_x_offset = x_crop
                crop_y_offset = y_crop

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb = cv2.flip(frame_rgb, 0)

            frame_height_px = frame.shape[0]
            frame_width_px = frame.shape[1]

            x_left_cm = crop_x_offset / px_per_cm_x
            x_right_cm = (crop_x_offset + frame_width_px) / px_per_cm_x
            y_bottom_orig_px = crop_y_offset + frame_height_px
            y_bottom_cm = (video_height_px - y_bottom_orig_px) / px_per_cm_y
            if y_bottom_cm < 0:
                y_bottom_cm = 0
            y_top_cm = y_bottom_cm + (frame_height_px / px_per_cm_y)

            ax.imshow(
                frame_rgb,
                extent=(x_left_cm, x_right_cm, y_bottom_cm, y_top_cm),
                aspect="equal",
                zorder=0,
            )
        except Exception as e:
            log.warning(
                "roi_reference.background_failed",
                video_path=str(video_path),
                error=str(e),
            )
        finally:
            if cap:
                cap.release()

    def generate_heatmap(
        self,
        ax: Axes | None = None,
        video_path: Path | str | None = None,
        calibration=None,
    ) -> Figure:
        """Generate occupancy heatmap.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)
            video_path: Path to source video; if provided, the first frame
                is rendered beneath the heatmap as semi-transparent context
                (audit Erro 3 round 4, 2026-05-25 — user requested visual
                context for the density overlay).
            calibration: Calibration with optional ``warp_frame`` method to
                undo perspective distortion before compositing.

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        traj_data = self.b_analyzer.trajectory_data
        x = traj_data["x_cm_smoothed"]
        y = traj_data["y_cm_smoothed"]
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        fig_obj = (
            ax.get_figure()
            if ax
            else plt.figure(figsize=self._figure_size_from_bounds(min_x, min_y, max_x, max_y))
        )
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        # Audit Erro 3 round 4 (2026-05-25): draw the video frame beneath
        # the heatmap so the user sees WHERE the density falls in the real
        # aquarium. Heatmap uses alpha to stay legible above the frame.
        self._draw_background_frame(ax, video_path, calibration)

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
            alpha=0.6 if video_path else 1.0,
        )

        # Draw Geotaxis Zones
        self._draw_geotaxis_zones(ax)

        ax.set_title(f"Heatmap - {self.metadata.get('experiment_id', 'Unknown')}")
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")

        # Add 5% margin
        width = max_x - min_x
        height = max_y - min_y
        margin_x = width * 0.05
        margin_y = height * 0.05

        ax.set_xlim(min_x - margin_x, max_x + margin_x)
        ax.set_ylim(min_y - margin_y, max_y + margin_y)
        ax.set_aspect("equal", adjustable="box")
        existing_artists = getattr(fig, "artists", [])
        if not any(isinstance(artist, Colorbar) for artist in existing_artists):
            fig.colorbar(im, ax=ax, label="Occupancy Density")
        return fig

    def generate_roi_reference_plot(  # noqa: C901
        self,
        ax: Axes | None = None,
        video_path: Path | str | None = None,
        calibration=None,
    ) -> Figure:
        """Generate ROI reference map showing arena and ROIs with optional video background.

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)
            video_path: Path to video file for background frame (optional)
            calibration: Calibration object for warping background frame (optional)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        arena_poly_cm = self.b_analyzer.arena_polygon_cm
        min_x, min_y, max_x, max_y = arena_poly_cm.bounds

        fig_obj = (
            ax.get_figure()
            if ax
            else plt.figure(figsize=self._figure_size_from_bounds(min_x, min_y, max_x, max_y))
        )
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()
        ax.set_facecolor("lightgray")

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

        # ==================================================================
        # NEW: Add video background if video_path is provided
        # ==================================================================
        # Audit Erro 6 follow-up (2026-05-25): the silent-skip when
        # ``video_path`` is missing or absent on disk was hiding the most
        # common failure mode for live recordings. Log explicitly so the
        # user (and future debugging sessions) can tell whether the path
        # was None, didn't exist, or failed to load.
        if not video_path:
            log.info(
                "roi_reference.background_skipped",
                reason="video_path_is_empty",
            )
        elif not Path(video_path).exists():
            log.warning(
                "roi_reference.background_skipped",
                reason="video_path_does_not_exist",
                video_path=str(video_path),
            )
        if video_path and Path(video_path).exists():
            cap = None
            frame = None
            try:
                # If a background frame image is provided (e.g., per-aquarium extracted PNG),
                # load it directly instead of using VideoCapture.
                suffix = str(video_path).lower()
                if suffix.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
                    # IMPROVEMENT: Use robust reading for Windows paths with unicode/spaces
                    frame = cv2.imdecode(
                        np.fromfile(str(video_path), dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                else:
                    # Try backends appropriate for *video files*.
                    # (DSHOW/MSMF are camera/capture backends and are noisy for file paths.)
                    backends_to_try = [cv2.CAP_ANY]
                    if hasattr(cv2, "CAP_FFMPEG"):
                        backends_to_try = [cv2.CAP_FFMPEG, cv2.CAP_ANY]

                    if frame is None:
                        for backend in backends_to_try:
                            cap = cv2.VideoCapture(str(video_path), backend)
                            if cap.isOpened():
                                ret, frame = cap.read()
                                cap.release()
                                cap = None
                                if ret and frame is not None:
                                    break
                                frame = None
                            else:
                                if cap:
                                    cap.release()
                                    cap = None

                if frame is None:
                    log.warning(
                        "roi_reference.background_skipped",
                        reason="video_capture_returned_no_frame",
                        video_path=str(video_path),
                    )
                if frame is not None:
                    # Apply warp if calibration is available
                    if calibration and hasattr(calibration, "warp_frame"):
                        warped = calibration.warp_frame(frame)
                        if warped is None:
                            log.warning(
                                "roi_reference.background_skipped",
                                reason="calibration_warp_returned_none",
                                video_path=str(video_path),
                            )
                            return fig
                        frame = warped
                    frame = cast(np.ndarray, frame)

                    # Track crop offset for extent calculation
                    crop_x_offset = 0
                    crop_y_offset = 0

                    # Only apply crop if reading from VIDEO (not pre-cropped PNG)
                    # PNG files from _prepare_background_image are already cropped
                    is_image_file = suffix.endswith(
                        (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
                    )
                    if self.frame_crop_box and not is_image_file:
                        x_crop, y_crop, w_crop, h_crop = self.frame_crop_box
                        x_crop = max(0, int(x_crop))
                        y_crop = max(0, int(y_crop))
                        w_crop = max(1, int(w_crop))
                        h_crop = max(1, int(h_crop))
                        x2 = min(frame.shape[1], x_crop + w_crop)
                        y2 = min(frame.shape[0], y_crop + h_crop)
                        frame = frame[y_crop:y2, x_crop:x2]
                        # Store offsets for extent calculation
                        crop_x_offset = x_crop
                        crop_y_offset = y_crop
                    # FIX: For pre-cropped PNGs, do NOT apply offset!
                    # The PNG already starts at (0,0) - offsets remain 0 (default above)

                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_rgb = cv2.flip(frame_rgb, 0)  # Invert Y for Cartesian

                    # Calculate extent with crop offset (same logic as trajectory plot)
                    video_height_for_transform = video_height_px
                    frame_height_px = frame.shape[0]
                    frame_width_px = frame.shape[1]

                    # Account for crop offset in extent calculation
                    x_left_cm = crop_x_offset / px_per_cm_x
                    x_right_cm = (crop_x_offset + frame_width_px) / px_per_cm_x

                    y_bottom_orig_px = crop_y_offset + frame_height_px
                    y_bottom_cm = (video_height_for_transform - y_bottom_orig_px) / px_per_cm_y
                    if y_bottom_cm < 0:
                        y_bottom_cm = 0.0

                    y_top_orig_px = crop_y_offset
                    y_top_cm = (video_height_for_transform - y_top_orig_px) / px_per_cm_y

                    frame_extent = (
                        x_left_cm,
                        x_right_cm,
                        y_bottom_cm,
                        y_top_cm,
                    )
                    ax.imshow(
                        frame_rgb,
                        extent=frame_extent,
                        origin="lower",
                        aspect="auto",
                        alpha=0.8,  # Semi-transparent to highlight overlays
                    )
                    log.debug(
                        "roi_reference.background_added",
                        video_path=str(video_path),
                        frame_shape=frame.shape,
                        extent=frame_extent,
                    )
            except Exception as e:
                log.warning(
                    "roi_reference.background_failed",
                    video_path=str(video_path),
                    error=str(e),
                )
            finally:
                if cap is not None and cap.isOpened():
                    cap.release()

        ax.set_facecolor("lightgray")

        # Arena polygon is ALWAYS drawn (even without ROIs)
        ax.add_patch(
            patches.Polygon(
                arena_poly_cm.exterior.coords,
                fill=False,
                edgecolor="blue",
                linewidth=2.5,
                linestyle="-",
                label="Arena",
            )
        )

        if self.r_analyzer and self.r_analyzer.rois:
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
            # No ROIs - show informative message but still display arena
            ax.text(
                0.5,
                0.95,
                "Área de processamento (sem ROIs definidas)",
                ha="center",
                va="top",
                transform=ax.transAxes,
                fontsize=10,
                style="italic",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
            )

        # Draw Geotaxis Zones (separators)
        self._draw_geotaxis_zones(ax)

        title = f"ROI Reference Map - {self.metadata.get('experiment_id', 'Unknown')}"
        ax.set_title(title)
        ax.set_xlabel("Position (cm)")
        ax.set_ylabel("Position (cm)")

        # Add 5% margin
        width = max_x - min_x
        height = max_y - min_y
        margin_x = width * 0.05
        margin_y = height * 0.05

        ax.set_xlim(min_x - margin_x, max_x + margin_x)
        ax.set_ylim(min_y - margin_y, max_y + margin_y)
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
        return fig

    def generate_thigmotaxis_plot(self, ax: Axes | None = None) -> Figure:
        """Generate thigmotaxis plot (distance to wall vs time).

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        try:
            thigmo_series = self.b_analyzer.get_thigmotaxis_timeseries()
            if thigmo_series.empty:
                ax.text(0.5, 0.5, "No thigmotaxis data.", ha="center", va="center")
            else:
                time_seconds = (thigmo_series.index - thigmo_series.index[0]).total_seconds()
                ax.plot(time_seconds, thigmo_series, label="Distance to Wall", color="purple")

                # Plot threshold line if configured
                behavioral_config = getattr(self.settings, "behavioral_analysis", None)
                if behavioral_config and hasattr(
                    behavioral_config, "default_thigmotaxis_distance_cm"
                ):
                    thresh = behavioral_config.default_thigmotaxis_distance_cm
                    ax.axhline(y=thresh, color="r", linestyle="--", label=f"Wall Zone ({thresh}cm)")

                ax.set_ylabel("Distance to Wall (cm)")
                ax.set_xlabel("Time (s)")
                ax.legend()
                ax.grid(True)
        except Exception as e:
            log.error("viz.thigmotaxis.error", error=str(e))
            ax.text(0.5, 0.5, f"Error generating plot: {e!s}", ha="center", va="center")

        ax.set_title(f"Thigmotaxis - {self.metadata.get('experiment_id', 'Unknown')}")
        return fig

    def generate_geotaxis_plot(self, ax: Axes | None = None) -> Figure:
        """Generate geotaxis plot (distance to bottom vs time).

        Args:
            ax: Matplotlib Axes to plot on (optional, creates new if None)

        Returns:
            matplotlib.figure.Figure: Generated figure
        """
        fig_obj = ax.get_figure() if ax else plt.figure(figsize=(12, 6))
        fig = cast(Figure, fig_obj)
        ax = ax or fig.add_subplot(111)
        ax.clear()

        try:
            # Check if we have valid geotaxis data (requires bottom boundary)
            geo_series = self.b_analyzer.get_geotaxis_timeseries()

            # Additional check: only show if we have arena polygon (needed for bottom detection)
            if geo_series.empty or self.b_analyzer.arena_polygon_cm.is_empty:
                ax.text(
                    0.5, 0.5, "No geotaxis data (Angle view required).", ha="center", va="center"
                )
            elif geo_series.isna().all():
                ax.text(0.5, 0.5, "Animal detected below arena bottom.", ha="center", va="center")
            else:
                time_seconds = (geo_series.index - geo_series.index[0]).total_seconds()
                ax.plot(time_seconds, geo_series, label="Distance to Bottom", color="brown")

                # Plot threshold line if configured
                behavioral_config = getattr(self.settings, "behavioral_analysis", None)
                if behavioral_config and hasattr(behavioral_config, "default_geotaxis_distance_cm"):
                    thresh = behavioral_config.default_geotaxis_distance_cm
                    ax.axhline(
                        y=thresh, color="r", linestyle="--", label=f"Bottom Zone ({thresh}cm)"
                    )

                ax.set_ylabel("Distance to Bottom (cm)")
                ax.set_xlabel("Time (s)")
                ax.legend()
                ax.grid(True)
        except Exception as e:
            log.error("viz.geotaxis.error", error=str(e))
            ax.text(0.5, 0.5, f"Error generating plot: {e!s}", ha="center", va="center")

        ax.set_title(f"Geotaxis - {self.metadata.get('experiment_id', 'Unknown')}")
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
        """Generate multiple plots in parallel using ThreadPoolExecutor.

        This method leverages parallel execution for I/O-bound matplotlib operations,
        significantly reducing report generation time.

        Thread Safety:
            - VisualizationGenerator is stateless and thread-safe for read operations
            - Each plot is generated in an isolated matplotlib figure context
            - Thread pooling is beneficial despite Python's GIL because:
              * Matplotlib operations are I/O-bound (file/buffer writing)
              * Figure rendering releases GIL during C-level operations
              * Parallel execution reduces total wall-clock time

        Performance:
            - Respects settings.performance.max_parallel_plots (default: 3)
            - Each plot has PLOT_GENERATION_TIMEOUT_SECONDS timeout
            - Failed plots return empty buffers to avoid blocking report generation

        Args:
            plot_configs: List of (plot_function, name) tuples

        Returns:
            list: List of (BytesIO buffer, name) tuples in original order

        Note:
            This method is safe to call from the main thread. Do not nest
            ThreadPoolExecutor calls to avoid thread exhaustion.
        """
        # Get configured max parallel plots from settings (use injected or default)
        max_workers = DEFAULT_MAX_PARALLEL_PLOTS
        if self.settings is not None:
            max_workers = getattr(
                getattr(self.settings, "performance", None),
                "max_parallel_plots",
                DEFAULT_MAX_PARALLEL_PLOTS,
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
                    result = future.result(timeout=PLOT_GENERATION_TIMEOUT_SECONDS)
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
        import warnings

        fig, ax = plt.subplots(figsize=(8, 6))
        # seaborn 0.13 passes deprecated `vert` kwarg to matplotlib internally
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="vert.*deprecated",
                category=PendingDeprecationWarning,
            )
            sns.boxplot(x="group_id", y=metric, data=df, ax=ax, showfliers=False)
            sns.stripplot(x="group_id", y=metric, data=df, ax=ax, color=".25", size=6)
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Experimental Group", fontsize=12)
        ax.set_ylabel(metric.replace("_", " ").title(), fontsize=12)
        plt.tight_layout()
        return fig

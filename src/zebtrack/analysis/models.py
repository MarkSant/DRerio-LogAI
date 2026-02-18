"""
Data Transfer Objects (DTOs) for analysis layer.

Phase: Reporter Refactoring (v2.1+)
Purpose: Separate analysis execution from report generation via dependency inversion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from zebtrack.analysis.behavior import ConcreteBehavioralAnalyzer
    from zebtrack.analysis.roi import ROI, ROIAnalyzer
    from zebtrack.core.detection.calibration import Calibration


@dataclass
class CalibrationParams:
    """Calibration parameters for analysis and reporting.

    Encapsulates pixel-to-cm conversion and video dimensions.
    """

    pixelcm_x: float
    """Pixels per cm in X axis."""

    pixelcm_y: float
    """Pixels per cm in Y axis."""

    video_height_px: int
    """Video height in pixels."""

    arena_polygon_px: Sequence[Sequence[float]]
    """Arena polygon vertices in pixel coordinates."""

    fps: float
    """Video frames per second."""

    calibration: Calibration | None = None
    """Optional Calibration object for perspective correction."""


@dataclass
class AnalysisResult:
    """Complete behavioral analysis result.

    This DTO contains all data needed for report generation, decoupling
    analysis execution from reporting.

    Usage:
        # After running analysis
        analysis_result = AnalysisResult(
            report=report_dict,
            behavioral_analyzer=b_analyzer,
            roi_analyzer=r_analyzer,
            trajectory_df=df,
            metadata={"experiment_id": "exp_001"},
            calibration_params=CalibrationParams(...),
            rois=rois,
            roi_colors=roi_colors,
        )

        # Create reporter
        reporter = Reporter(analysis=analysis_result)
        reporter.export_summary_data("output.parquet")

    Attributes:
        report: Nested dictionary with analysis metrics
        behavioral_analyzer: Analyzer instance with behavioral metrics
        roi_analyzer: Analyzer instance with ROI metrics (None if no ROIs)
        trajectory_df: Raw trajectory DataFrame
        metadata: Experiment metadata
        calibration_params: Calibration and video parameters
        rois: List of ROI objects
        roi_colors: ROI name to RGB color mapping
        video_path: Optional path to source video
        sharp_turn_threshold: Sharp turn detection threshold (deg/s)
        freezing_threshold: Freezing velocity threshold (cm/s)
        freezing_duration: Minimum freezing duration (seconds)
        smoothing_window_length: Trajectory smoothing window
        smoothing_polyorder: Trajectory smoothing polynomial order
    """

    report: dict[str, Any]
    """Analysis report dictionary with metrics."""

    behavioral_analyzer: ConcreteBehavioralAnalyzer
    """Behavioral analyzer instance."""

    roi_analyzer: ROIAnalyzer | None
    """ROI analyzer instance (None if no ROIs defined)."""

    trajectory_df: pd.DataFrame
    """Raw trajectory DataFrame."""

    metadata: dict[str, Any]
    """Experiment metadata (experiment_id, group, subject, etc.)."""

    calibration_params: CalibrationParams
    """Calibration and video parameters."""

    rois: list[ROI]
    """List of ROI objects for analysis."""

    roi_colors: dict[str, tuple[int, int, int]]
    """ROI name to RGB color mapping."""

    # Optional fields
    video_path: str | None = None
    """Optional path to source video file."""

    sharp_turn_threshold: float = 45.0
    """Sharp turn detection threshold in degrees/second."""

    freezing_threshold: float = 1.5
    """Freezing velocity threshold in cm/s."""

    freezing_duration: float = 1.0
    """Minimum freezing duration in seconds."""

    smoothing_window_length: int | None = None
    """Trajectory smoothing window length."""

    smoothing_polyorder: int | None = None
    """Trajectory smoothing polynomial order."""

    validation_warnings: list[str] = field(default_factory=list)
    """List of warnings generated during trajectory validation."""

    validation_stats: dict[str, Any] = field(default_factory=dict)
    """Quality metrics and statistics from trajectory validation."""

    frame_crop_box: tuple[int, int, int, int] | None = None
    """Optional crop box (x, y, w, h) used to generate aquarium-local frames."""

    behavioral_config: dict[str, Any] = field(default_factory=dict)
    """Configuration for behavioral analysis (thigmotaxis, geotaxis)."""

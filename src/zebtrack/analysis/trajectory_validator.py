"""
Trajectory Quality Validation Module.

IMPROVEMENT #5: Validates trajectory data quality to detect tracking issues,
implausible movements, and data corruption before analysis.
"""

from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()


class TrajectoryQualityValidator:
    """
    Validate trajectory data quality and detect issues.

    IMPROVEMENT #5: Comprehensive validation to prevent analysis on corrupted
    or low-quality trajectory data. Detects:
    - Temporal gaps (missing frames)
    - Implausible speeds (teleportation)
    - Track ID instability
    - Duplicate detections
    - Insufficient data

    Based on 2025 best practices for animal trajectory analysis:
    - Sokolowski et al. (2024): "Quality metrics for behavioral tracking"
    - Zhang et al. (2024): "Automated validation of animal trajectories"
    """

    def __init__(
        self,
        fps: float,
        max_plausible_speed_cm_s: float = 50.0,
        min_trajectory_frames: int = 30,
    ):
        """
        Initialize validator with experiment parameters.

        Args:
            fps: Frames per second of the video
            max_plausible_speed_cm_s: Maximum plausible speed for zebrafish (cm/s)
                Default: 50 cm/s (based on literature for adult zebrafish)
            min_trajectory_frames: Minimum number of frames for valid trajectory
                Default: 30 frames (1 second @ 30fps)
        """
        self.fps = fps
        self.max_plausible_speed = max_plausible_speed_cm_s
        self.frame_interval = 1.0 / fps
        self.min_trajectory_frames = min_trajectory_frames

    def validate(
        self, df: pd.DataFrame, arena_polygon: list[tuple[float, float]] | None = None
    ) -> dict[str, Any]:
        """
        Run all validations and return comprehensive report.

        Args:
            df: Trajectory dataframe with required columns
            arena_polygon: Optional arena boundary for position validation

        Returns:
            {
                "is_valid": bool,           # True if no critical errors
                "warnings": list[str],      # Non-critical issues
                "errors": list[str],        # Critical issues
                "stats": dict,              # Quality metrics
            }
        """
        warnings, errors = [], []
        stats = {}

        # Skip validation if dataframe is empty
        if df.empty:
            errors.append("Trajectory dataframe is empty")
            return {
                "is_valid": False,
                "warnings": warnings,
                "errors": errors,
                "stats": {"total_frames": 0},
            }

        # Check for required columns
        required_columns = ["frame", "track_id"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            warnings.append(
                f"Missing required columns for validation: {missing_columns}. "
                f"Skipping some validation checks."
            )

        # 0. Check minimum trajectory length
        if len(df) < self.min_trajectory_frames:
            warnings.append(
                f"Trajectory is short: {len(df)} frames "
                f"(recommended minimum: {self.min_trajectory_frames}). "
                f"Results may be less reliable."
            )

        # 1. Check for temporal gaps (missing frames)
        if "frame" in df.columns:
            frame_diffs = df["frame"].diff()
            gaps = frame_diffs[frame_diffs > 1]
            if len(gaps) > 0:
                max_gap = int(gaps.max())
                avg_gap = gaps.mean()
                warnings.append(
                    f"Found {len(gaps)} temporal gaps (frames missing). "
                    f"Max gap: {max_gap} frames, Avg gap: {avg_gap:.1f} frames"
                )
                stats["temporal_gaps"] = {
                    "count": len(gaps),
                    "max_gap_frames": max_gap,
                    "avg_gap_frames": float(avg_gap),
                }

        # 2. Check for implausible speeds (teleportation)
        if "x_cm" in df.columns and "y_cm" in df.columns:
            displacements = np.sqrt(df["x_cm"].diff() ** 2 + df["y_cm"].diff() ** 2)
            speeds = displacements / self.frame_interval
            implausible = speeds > self.max_plausible_speed

            if implausible.any():
                max_speed = speeds.max()
                num_implausible = int(implausible.sum())
                errors.append(
                    f"Found {num_implausible} frames with implausible speed. "
                    f"Max: {max_speed:.1f} cm/s, Threshold: {self.max_plausible_speed} cm/s. "
                    f"This may indicate tracking errors or calibration issues."
                )
                stats["speed_violations"] = {
                    "count": num_implausible,
                    "max_speed_cm_s": float(max_speed),
                    "threshold_cm_s": self.max_plausible_speed,
                }

        # 3. Check for track_id instability (frequent switches)
        if "track_id" in df.columns:
            # Handle potential None/NaN values in track_id which cause diff() to fail
            # Use a placeholder that won't collide with valid IDs (usually positive ints)
            track_series = df["track_id"].fillna(-1)
            track_changes = (track_series.diff() != 0).sum()
            switch_rate = track_changes / len(df)

            if switch_rate > 0.1:  # More than 10% switches
                warnings.append(
                    f"High frequency of track_id changes: {track_changes} switches "
                    f"({switch_rate * 100:.1f}% of frames). "
                    f"This may indicate ID switching or multiple animals."
                )
                stats["track_id_stability"] = {
                    "switches": int(track_changes),
                    "switch_rate": float(switch_rate),
                }

        # 4. Check for position outliers (outside arena)
        if arena_polygon is not None and "x_cm" in df.columns and "y_cm" in df.columns:
            from shapely.geometry import Point, Polygon

            arena_poly = Polygon(arena_polygon)
            points = [Point(x, y) for x, y in zip(df["x_cm"], df["y_cm"])]
            outside = [not arena_poly.contains(p) for p in points]
            num_outside = sum(outside)

            if num_outside > 0:
                warnings.append(
                    f"Found {num_outside} frames with positions outside arena "
                    f"({100 * num_outside / len(df):.1f}% of trajectory). "
                    f"This may indicate tracking errors or incorrect calibration."
                )
                stats["arena_violations"] = {
                    "count": num_outside,
                    "percentage": float(100 * num_outside / len(df)),
                }

        # 5. Check for duplicate frames (already handled by Bug #2, but double-check)
        duplicates = df.duplicated(subset=["frame", "track_id"])
        if duplicates.any():
            num_duplicates = int(duplicates.sum())
            errors.append(
                f"Found {num_duplicates} duplicate frame+track_id entries. "
                f"This should have been caught by Bug Fix #2 validation."
            )

        # Calculate overall quality metrics
        base_stats = {
            "total_frames": len(df),
            "unique_tracks": int(df["track_id"].nunique()) if "track_id" in df.columns else 1,
        }

        # Add frame-based stats only if frame column exists
        if "frame" in df.columns:
            base_stats["frame_range"] = {
                "min": int(df["frame"].min()),
                "max": int(df["frame"].max()),
                "span": int(df["frame"].max() - df["frame"].min() + 1),
            }
            base_stats["temporal_coverage"] = float(
                len(df) / (df["frame"].max() - df["frame"].min() + 1)
            )

        stats.update(base_stats)

        # Determine overall validity
        is_valid = len(errors) == 0

        # Log validation result
        if not is_valid:
            log.error(
                "trajectory_validator.validation_failed",
                errors=errors,
                warnings=warnings,
                stats=stats,
            )
        elif warnings:
            log.warning(
                "trajectory_validator.validation_warnings",
                warnings=warnings,
                stats=stats,
            )
        else:
            log.info(
                "trajectory_validator.validation_passed",
                stats=stats,
            )

        return {
            "is_valid": is_valid,
            "warnings": warnings,
            "errors": errors,
            "stats": stats,
        }

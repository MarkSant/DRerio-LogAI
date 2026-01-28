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
        warnings: list[str] = []
        errors: list[str] = []
        stats: dict[str, Any] = {}

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

        # Run individual validation checks (refactored for complexity reduction)
        self._check_trajectory_length(df, warnings)
        self._check_temporal_gaps(df, warnings, stats)
        self._check_speed_violations(df, warnings, stats)
        self._check_track_id_stability(df, warnings, stats)
        self._check_arena_violations(df, arena_polygon, warnings, stats)
        self._check_duplicate_frames(df, errors)
        self._check_multi_aquarium_validation(df, errors, warnings, stats)
        self._check_per_aquarium_gaps(df, warnings, stats)

        # Calculate overall quality metrics
        stats.update(self._calculate_base_stats(df))

        # Determine overall validity and log result
        is_valid = len(errors) == 0
        self._log_validation_result(is_valid, errors, warnings, stats)

        return {
            "is_valid": is_valid,
            "warnings": warnings,
            "errors": errors,
            "stats": stats,
        }

    def _check_trajectory_length(self, df: pd.DataFrame, warnings: list[str]) -> None:
        """Check minimum trajectory length."""
        if len(df) < self.min_trajectory_frames:
            warnings.append(
                f"Trajectory is short: {len(df)} frames "
                f"(recommended minimum: {self.min_trajectory_frames}). "
                f"Results may be less reliable."
            )

    def _check_temporal_gaps(
        self, df: pd.DataFrame, warnings: list[str], stats: dict[str, Any]
    ) -> None:
        """Check for temporal gaps (missing frames)."""
        if "frame" not in df.columns:
            return

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

    def _check_speed_violations(
        self, df: pd.DataFrame, warnings: list[str], stats: dict[str, Any]
    ) -> None:
        """Check for implausible speeds (teleportation)."""
        if "x_cm" not in df.columns or "y_cm" not in df.columns or "frame" not in df.columns:
            return

        # Use timestamp if available for most accurate time delta, fallback to frame-based
        if "timestamp" in df.columns:
            time_deltas = df.groupby("track_id")["timestamp"].diff()
        else:
            time_deltas = df.groupby("track_id")["frame"].diff() * self.frame_interval

        # Calculate displacement grouped by track to avoid "jumps" between different IDs
        dx = df.groupby("track_id")["x_cm"].diff()
        dy = df.groupby("track_id")["y_cm"].diff()
        displacements = np.sqrt(dx**2 + dy**2)

        # Speed = distance / time (handle division by zero or NaN)
        speeds = displacements / time_deltas

        # Filter out NaN/Inf resulting from first frame or same-frame entries
        valid_speeds = speeds.replace([np.inf, -np.inf], np.nan).dropna()
        implausible = valid_speeds > self.max_plausible_speed

        if implausible.any():
            max_speed = float(valid_speeds.max())
            num_implausible = int(implausible.sum())
            warnings.append(
                f"Found {num_implausible} frames with implausible speed. "
                f"Max: {max_speed:.1f} cm/s, Threshold: {self.max_plausible_speed} cm/s. "
                f"This may indicate tracking errors or calibration issues."
            )
            stats["speed_violations"] = {
                "count": num_implausible,
                "max_speed_cm_s": max_speed,
                "threshold_cm_s": self.max_plausible_speed,
            }

    def _check_track_id_stability(
        self, df: pd.DataFrame, warnings: list[str], stats: dict[str, Any]
    ) -> None:
        """Check for track_id instability (frequent switches)."""
        if "track_id" not in df.columns:
            return

        # Handle potential None/NaN values in track_id
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

    def _check_arena_violations(
        self,
        df: pd.DataFrame,
        arena_polygon: list[tuple[float, float]] | None,
        warnings: list[str],
        stats: dict[str, Any],
    ) -> None:
        """Check for position outliers (outside arena)."""
        if arena_polygon is None:
            return
        if "x_cm" not in df.columns or "y_cm" not in df.columns:
            return

        from shapely.geometry import Point, Polygon

        arena_poly = Polygon(arena_polygon)
        points = [Point(x, y) for x, y in zip(df["x_cm"], df["y_cm"], strict=False)]
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

    def _check_duplicate_frames(self, df: pd.DataFrame, errors: list[str]) -> None:
        """Check for duplicate frames."""
        if "frame" not in df.columns or "track_id" not in df.columns:
            return

        duplicates = df.duplicated(subset=["frame", "track_id"])
        if duplicates.any():
            num_duplicates = int(duplicates.sum())
            errors.append(
                f"Found {num_duplicates} duplicate frame+track_id entries. "
                f"This should have been caught by Bug Fix #2 validation."
            )

    def _check_multi_aquarium_validation(
        self,
        df: pd.DataFrame,
        errors: list[str],
        warnings: list[str],
        stats: dict[str, Any],
    ) -> None:
        """Check multi-aquarium track ID validation."""
        if "track_id" not in df.columns or "aquarium_id" not in df.columns:
            return

        aquarium_id_issues = self._validate_multi_aquarium_ids(df)
        if aquarium_id_issues["errors"]:
            errors.extend(aquarium_id_issues["errors"])
        if aquarium_id_issues["warnings"]:
            warnings.extend(aquarium_id_issues["warnings"])
        if aquarium_id_issues["stats"]:
            stats["multi_aquarium_validation"] = aquarium_id_issues["stats"]

    def _check_per_aquarium_gaps(
        self, df: pd.DataFrame, warnings: list[str], stats: dict[str, Any]
    ) -> None:
        """Check per-aquarium gap detection."""
        if "frame" not in df.columns or "aquarium_id" not in df.columns:
            return

        per_aquarium_gaps = self._detect_per_aquarium_gaps(df)
        if per_aquarium_gaps["warnings"]:
            warnings.extend(per_aquarium_gaps["warnings"])
        if per_aquarium_gaps["stats"]:
            stats["per_aquarium_gaps"] = per_aquarium_gaps["stats"]

    def _calculate_base_stats(self, df: pd.DataFrame) -> dict[str, Any]:
        """Calculate overall quality metrics."""
        base_stats: dict[str, Any] = {
            "total_frames": len(df),
            "unique_tracks": int(df["track_id"].nunique()) if "track_id" in df.columns else 1,
        }

        if "frame" in df.columns:
            base_stats["frame_range"] = {
                "min": int(df["frame"].min()),
                "max": int(df["frame"].max()),
                "span": int(df["frame"].max() - df["frame"].min() + 1),
            }
            base_stats["temporal_coverage"] = float(
                len(df) / (df["frame"].max() - df["frame"].min() + 1)
            )

        return base_stats

    def _log_validation_result(
        self,
        is_valid: bool,
        errors: list[str],
        warnings: list[str],
        stats: dict[str, Any],
    ) -> None:
        """Log validation result."""
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

    def _validate_multi_aquarium_ids(self, df: pd.DataFrame) -> dict:
        """Validate track IDs stay within their aquarium bounds.

        Track ID convention: aquarium_id * 1000 + local_track_id
        So aquarium 0 should have IDs 0-999, aquarium 1 should have IDs 1000-1999, etc.

        Returns:
            dict with errors, warnings, and stats
        """
        errors: list[str] = []
        warnings: list[str] = []
        stats: dict = {}

        # Group by aquarium and check ID ranges
        id_violations = []
        aquarium_stats = {}

        for aq_id, group in df.groupby("aquarium_id"):
            expected_min = int(aq_id) * 1000
            expected_max = expected_min + 999

            track_ids = group["track_id"].dropna().unique()
            out_of_range = [tid for tid in track_ids if not (expected_min <= tid <= expected_max)]

            aquarium_stats[f"aquarium_{aq_id}"] = {
                "track_ids": list(map(int, track_ids)),
                "expected_range": [expected_min, expected_max],
                "out_of_range": list(map(int, out_of_range)) if out_of_range else [],
            }

            if out_of_range:
                id_violations.append((aq_id, out_of_range))

        if id_violations:
            for aq_id, bad_ids in id_violations:
                warnings.append(
                    f"Aquarium {aq_id}: Track IDs {bad_ids} are outside expected range "
                    f"({int(aq_id) * 1000}-{int(aq_id) * 1000 + 999}). "
                    f"This may indicate cross-aquarium ID assignment."
                )

        # Check for ID jumps (sudden large changes in track ID within same aquarium)
        id_jumps = []
        for aq_id, group in df.groupby("aquarium_id"):
            if len(group) < 2:
                continue

            sorted_group = group.sort_values("frame")
            track_diffs = sorted_group["track_id"].diff().abs()

            # ID jump threshold: more than 100 suggests aquarium boundary crossed
            large_jumps = track_diffs[track_diffs > 100]
            if len(large_jumps) > 0:
                id_jumps.append((aq_id, len(large_jumps), int(large_jumps.max())))

        if id_jumps:
            for aq_id, num_jumps, max_jump in id_jumps:
                warnings.append(
                    f"Aquarium {aq_id}: Detected {num_jumps} large track ID jumps "
                    f"(max jump: {max_jump}). May indicate tracking loss/recovery."
                )

        stats["aquariums"] = aquarium_stats
        stats["id_violations_count"] = sum(len(v[1]) for v in id_violations)
        stats["id_jumps_count"] = sum(j[1] for j in id_jumps)

        return {"errors": errors, "warnings": warnings, "stats": stats}

    def _detect_per_aquarium_gaps(self, df: pd.DataFrame) -> dict:
        """Detect frames with missing detections per aquarium.

        Returns:
            dict with warnings and stats for per-aquarium gap analysis
        """
        warnings: list[str] = []
        stats: dict = {}

        # Get overall frame range
        frame_min = int(df["frame"].min())
        frame_max = int(df["frame"].max())
        all_frames = set(range(frame_min, frame_max + 1))

        per_aquarium_stats = {}

        for aq_id, group in df.groupby("aquarium_id"):
            detected_frames = set(group["frame"].unique())
            missing_frames = all_frames - detected_frames

            # Find continuous gap sequences
            if missing_frames:
                sorted_missing = sorted(missing_frames)
                gaps = []
                gap_start = sorted_missing[0]
                gap_end = sorted_missing[0]

                for frame in sorted_missing[1:]:
                    if frame == gap_end + 1:
                        gap_end = frame
                    else:
                        gaps.append((gap_start, gap_end, gap_end - gap_start + 1))
                        gap_start = frame
                        gap_end = frame
                gaps.append((gap_start, gap_end, gap_end - gap_start + 1))

                # Find longest gap
                longest_gap = max(gaps, key=lambda g: g[2])

                per_aquarium_stats[f"aquarium_{aq_id}"] = {
                    "total_missing_frames": len(missing_frames),
                    "coverage_percent": 100 * len(detected_frames) / len(all_frames),
                    "gap_count": len(gaps),
                    "longest_gap_frames": longest_gap[2],
                    "longest_gap_range": [longest_gap[0], longest_gap[1]],
                }

                # Warn if coverage is low
                coverage = len(detected_frames) / len(all_frames)
                if coverage < 0.9:  # Less than 90% coverage
                    gap_len = longest_gap[2]
                    warnings.append(
                        f"Aquarium {aq_id}: Low detection coverage ({100 * coverage:.1f}%). "
                        f"Missing {len(missing_frames)} frames, longest gap: {gap_len} frames."
                    )
            else:
                per_aquarium_stats[f"aquarium_{aq_id}"] = {
                    "total_missing_frames": 0,
                    "coverage_percent": 100.0,
                    "gap_count": 0,
                    "longest_gap_frames": 0,
                    "longest_gap_range": None,
                }

        stats["per_aquarium"] = per_aquarium_stats

        return {"warnings": warnings, "stats": stats}

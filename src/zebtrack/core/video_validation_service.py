"""Video Validation Service - Sprint 12.

Classifies video entries into processing categories based on available data.

Sprint: 12 of REFACTOR-MASTER-PLAN-2025.md
Purpose: Extract classification logic from MainViewModel to dedicated service
Related: SPRINT_10_PROCESSING_REFACTORING_ANALYSIS.md - Phase 2: Helper Extraction
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.project_manager import ProjectManager

log = structlog.get_logger()


@dataclass
class VideoScanResult:
    """
    Result of video path scanning and validation.

    Sprint 12: Value object for scan results.
    Separates scan logic from UI presentation.

    Attributes:
        info_by_norm: Dictionary mapping normalized paths to video info
        missing_files: List of paths that were not found or could not be scanned
        scanned_videos: List of all successfully scanned video info dicts
        has_missing: Whether any files are missing
    """

    info_by_norm: dict[str, dict] = field(default_factory=dict)
    missing_files: list[str] = field(default_factory=list)
    scanned_videos: list[dict] = field(default_factory=list)

    @property
    def has_missing(self) -> bool:
        """Check if any files are missing."""
        return len(self.missing_files) > 0

    @property
    def scan_count(self) -> int:
        """Get count of successfully scanned videos."""
        return len(self.scanned_videos)


class VideoValidationService:
    """
    Service for validating and scanning video paths.

    Sprint 12: Extracted from MainViewModel._scan_and_validate_candidate_paths().
    Pure scan logic with minimal UI coupling.

    Validates videos by:
    - Scanning paths using ProjectManager.scan_input_paths()
    - Creating normalized path lookup dictionary
    - Identifying missing/invalid files

    Example:
        >>> service = VideoValidationService()
        >>> result = service.scan_and_validate_paths(
        ...     candidate_paths=["/video1.mp4", "/video2.mp4"],
        ...     project_manager=project_manager
        ... )
        >>> print(f"Scanned: {result.scan_count}, Missing: {len(result.missing_files)}")
    """

    def __init__(self):
        """Initialize VideoValidationService."""
        log.info("video_validation_service.initialized")

    def scan_and_validate_paths(
        self,
        candidate_paths: list[str],
        project_manager: ProjectManager,
    ) -> VideoScanResult:
        """
        Scan and validate video paths for available data.

        Sprint 12: Core scan logic extracted from MainViewModel.

        Process:
        1. Scan paths using ProjectManager.scan_input_paths()
        2. Create normalized path lookup dictionary (info_by_norm)
        3. Identify missing files (paths that failed to scan)

        Args:
            candidate_paths: List of video file paths to scan
            project_manager: ProjectManager instance for scanning

        Returns:
            VideoScanResult: Structured scan results with info_by_norm, missing_files

        Example:
            >>> result = service.scan_and_validate_paths(
            ...     candidate_paths=["/videos/test1.mp4", "/videos/test2.mp4"],
            ...     project_manager=project_manager
            ... )
            >>> if result.has_missing:
            ...     print(f"Missing: {result.missing_files}")
            >>> for path, info in result.info_by_norm.items():
            ...     print(f"{path}: has_arena={info.get('has_arena')}")
        """
        log.debug(
            "video_validation_service.scan_and_validate_paths.start",
            path_count=len(candidate_paths),
        )

        # Scan all candidate paths
        scanned_videos = project_manager.scan_input_paths(candidate_paths)

        # Enrich scan results with project-aware paths (Fix for hierarchical project structure)
        if project_manager:
            for info in scanned_videos:
                path = info.get("path")
                if not path:
                    continue

                video_entry = project_manager.find_video_entry(path=path)
                if not video_entry:
                    continue

                # Check registered parquet files in project data (Legacy/Single Video)
                registered_parquets = video_entry.get("parquet_files", {})

                # Check for Multi-Aquarium Data (Via Manager API)
                # This handles data stored in central registry OR video entry transparently
                try:
                    multi_zone_data = project_manager.get_multi_aquarium_zone_data(path)
                    if multi_zone_data and multi_zone_data.aquariums:
                        has_multi_arena = False
                        has_multi_rois = False
                        for aq in multi_zone_data.aquariums:
                            if aq.polygon and len(aq.polygon) >= 3:
                                has_multi_arena = True
                            if aq.roi_polygons:
                                has_multi_rois = True

                        if has_multi_arena:
                            info["has_arena"] = True
                            info["is_multi_aquarium"] = True
                        if has_multi_rois:
                            info["has_rois"] = True
                except Exception as e:
                    # Log but continue (can fail if data structure changes)
                    # Use lower level log to avoid noise
                    pass

                # Trajectory Data (Multi)
                # Check direct output registry
                multi_outputs = video_entry.get("multi_aquarium_outputs", {})
                if multi_outputs:
                    has_multi_traj = False
                    for out in multi_outputs.values():
                        if out.get("parquet_files", {}).get("trajectory"):
                            has_multi_traj = True
                            break

                    if has_multi_traj:
                        info["has_trajectory"] = True
                        info["is_multi_aquarium"] = True

                # Standard/Legacy Parquet Checks (augmenting multi checks)
                if registered_parquets:
                    # Update info if files exist
                    scan_parquets = info.setdefault("parquet_files", {})

                    # Check Arena
                    arena_path = registered_parquets.get("arena")
                    if arena_path and os.path.exists(arena_path):
                        scan_parquets["arena"] = arena_path
                        info["has_arena"] = True

                    # Check ROIs
                    rois_path = registered_parquets.get("rois")
                    if rois_path and os.path.exists(rois_path):
                        scan_parquets["rois"] = rois_path
                        info["has_rois"] = True

                    # Check Trajectory
                    traj_path = registered_parquets.get("trajectory")
                    if traj_path and os.path.exists(traj_path):
                        scan_parquets["trajectory"] = traj_path
                        info["has_trajectory"] = True

                # Fallback: Check cached flags in video entry
                # If we have flags in memory, respect them (they might be from a recent save)
                if not info.get("has_arena") and video_entry.get("has_arena"):
                    info["has_arena"] = True
                if not info.get("has_rois") and video_entry.get("has_rois"):
                    info["has_rois"] = True


        # Create normalized path lookup
        info_by_norm: dict[str, dict] = {}
        for info in scanned_videos:
            path = info.get("path")
            if isinstance(path, str):
                norm_path = os.path.normpath(path)
                info_by_norm[norm_path] = info

        # Identify missing files
        missing_files: list[str] = []
        for path in candidate_paths:
            norm_path = os.path.normpath(path)
            if norm_path not in info_by_norm:
                missing_files.append(path)

        result = VideoScanResult(
            info_by_norm=info_by_norm,
            missing_files=missing_files,
            scanned_videos=scanned_videos,
        )

        log.info(
            "video_validation_service.scan_and_validate_paths.complete",
            scanned=result.scan_count,
            missing=len(missing_files),
            has_missing=result.has_missing,
        )

        return result

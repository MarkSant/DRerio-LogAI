"""Video Validation Service - Sprint 12.

Classifies video entries into processing categories based on available data.

Sprint: 12 of REFACTOR-MASTER-PLAN-2025.md
Purpose: Extract classification logic from MainViewModel to dedicated service
Related: SPRINT_10_PROCESSING_REFACTORING_ANALYSIS.md - Phase 2: Helper Extraction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager

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

    def __init__(self) -> None:
        """Initialize VideoValidationService."""
        log.info("video_validation_service.initialized")

    @staticmethod
    def _normalize_aquarium_key(raw_key: object) -> int | None:
        """Normalize stored aquarium keys to integers when possible."""
        if isinstance(raw_key, int):
            return raw_key

        digits = "".join(ch for ch in str(raw_key) if ch.isdigit())
        if not digits:
            return None

        try:
            return int(digits)
        except ValueError:
            return None

    def scan_and_validate_paths(  # noqa: C901
        self,
        candidate_paths: list[str],
        project_manager: ProjectManager,
    ) -> VideoScanResult:
        """
        Scan and validate video paths for available data.
        """
        from zebtrack.core.project.video_manager import VideoManager

        log.debug(
            "video_validation_service.scan_and_validate_paths.start",
            path_count=len(candidate_paths),
        )

        # Scan all candidate paths
        scanned_videos = project_manager.scan_input_paths(candidate_paths)

        # Enrich scan results with project-aware paths
        if project_manager:
            for info in scanned_videos:
                path = info.get("path")
                if not path:
                    continue

                video_entry = project_manager.find_video_entry(path=path)
                if not video_entry:
                    continue

                aquarium_flags: dict[int, dict[str, bool]] = {}

                # Multi-Aquarium Data Checks
                try:
                    multi_zone_data = project_manager.get_multi_aquarium_zone_data(path)
                    if multi_zone_data and multi_zone_data.aquariums:
                        for aq in multi_zone_data.aquariums:
                            aquarium_flags[int(aq.id)] = project_manager.get_aquarium_asset_flags(
                                path, int(aq.id)
                            )
                        info["is_multi_aquarium"] = True
                # except Exception justified: multi-aquarium zone scan — must not prevent validation
                except Exception:
                    log.warning(
                        "video_validation.multi_aquarium_zone_scan.suppressed",
                        exc_info=True,
                    )

                # Trajectory Data (Multi)
                multi_outputs = video_entry.get("multi_aquarium_outputs", {})
                if multi_outputs:
                    info["is_multi_aquarium"] = True
                    info["multi_aquarium_outputs"] = multi_outputs
                    for raw_key in multi_outputs:
                        aq_id = self._normalize_aquarium_key(raw_key)
                        if aq_id is None or aq_id in aquarium_flags:
                            continue
                        aquarium_flags[aq_id] = project_manager.get_aquarium_asset_flags(
                            path, aq_id
                        )

                if aquarium_flags:
                    info["aquarium_flags"] = aquarium_flags
                    info["has_arena"] = any(flags["has_arena"] for flags in aquarium_flags.values())
                    info["has_rois"] = any(flags["has_rois"] for flags in aquarium_flags.values())
                    info["has_trajectory"] = any(
                        flags["has_trajectory"] for flags in aquarium_flags.values()
                    )
                    info["has_complete_data"] = any(
                        flags["has_complete_data"] for flags in aquarium_flags.values()
                    )

                # Standard Flags Fallback
                if not info.get("has_arena") and video_entry.get("has_arena"):
                    info["has_arena"] = True
                if not info.get("has_rois") and video_entry.get("has_rois"):
                    info["has_rois"] = True
                if not info.get("has_trajectory") and video_entry.get("has_trajectory"):
                    info["has_trajectory"] = True
                if not info.get("has_complete_data") and video_entry.get("has_complete_data"):
                    info["has_complete_data"] = True

        # Create normalized path lookup
        info_by_norm: dict[str, dict] = {}
        for info in scanned_videos:
            path = info.get("path")
            if isinstance(path, str):
                norm_path = VideoManager.normalize_path(path)
                if norm_path:
                    info_by_norm[norm_path] = info

        # Identify missing files
        missing_files: list[str] = []
        for path in candidate_paths:
            norm_path = VideoManager.normalize_path(path)
            if not norm_path or norm_path not in info_by_norm:
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
        )

        return result

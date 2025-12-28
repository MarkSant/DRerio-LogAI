"""Video Selection Service - Sprint 12.

Selects candidate videos for processing based on criteria.

Sprint: 12 of REFACTOR-MASTER-PLAN-2025.md
Purpose: Extract selection logic from MainViewModel to dedicated service
Related: SPRINT_10_PROCESSING_REFACTORING_ANALYSIS.md - Phase 2: Helper Extraction
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


@dataclass
class VideoSelectionResult:
    """
    Result of video selection operation.

    Sprint 12: Value object for selection results.
    Separates selection logic from UI presentation.

    Attributes:
        candidate_entries: List of selected video entry dictionaries
        missing_targets: List of target paths that were not found in project
        has_missing: Whether any target paths are missing
        selection_mode: Either 'targeted' (specific paths) or 'pending' (all pending)
    """

    candidate_entries: list[dict] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)
    selection_mode: str = "pending"  # 'targeted' or 'pending'

    @property
    def has_missing(self) -> bool:
        """Check if any target paths are missing."""
        return len(self.missing_targets) > 0

    @property
    def candidate_count(self) -> int:
        """Get count of selected candidates."""
        return len(self.candidate_entries)


class VideoSelectionService:
    """
    Service for selecting candidate videos for processing.

    Sprint 12: Extracted from MainViewModel._gather_candidate_entries().
    Pure selection logic with minimal UI coupling.

    Selects videos by:
    - Building normalized path lookup from all videos
    - Filtering by specific target paths (if provided)
    - Or selecting all pending videos (if no targets)
    - Identifying missing/invalid target paths

    Example:
        >>> service = VideoSelectionService()
        >>> result = service.select_candidates(
        ...     all_videos=[...],
        ...     target_paths=["/video1.mp4", "/video2.mp4"]
        ... )
        >>> print(f"Selected: {result.candidate_count}, Missing: {len(result.missing_files)}")
    """

    def __init__(self):
        """Initialize VideoSelectionService."""
        log.info("video_selection_service.initialized")

    def select_candidates(
        self,
        all_videos: list[dict],
        target_paths: list[str] | None = None,
    ) -> VideoSelectionResult:
        """
        Select candidate videos for processing.

        Sprint 12: Core selection logic extracted from MainViewModel.

        Selection modes:
        1. Targeted: If target_paths provided, select only those specific videos
        2. Pending: If no target_paths, select all videos with pending status

        Args:
            all_videos: List of all video entries in project
            target_paths: Optional list of specific video paths to select

        Returns:
            VideoSelectionResult: Selected candidates with metadata

        Example:
            >>> # Targeted selection
            >>> result = service.select_candidates(
            ...     all_videos=[...],
            ...     target_paths=["/video1.mp4", "/video2.mp4"]
            ... )

            >>> # Pending selection
            >>> result = service.select_candidates(all_videos=[...])
        """
        log.debug(
            "video_selection_service.select_candidates.start",
            total_videos=len(all_videos),
            has_targets=target_paths is not None,
            target_count=len(target_paths) if target_paths else 0,
        )

        # Build normalized path lookup
        videos_by_norm: dict[str, dict] = {}
        from zebtrack.core.video_manager import VideoManager
        for video in all_videos:
            path_value = video.get("path")
            if isinstance(path_value, str) and path_value:
                norm_path = VideoManager.normalize_path(path_value)
                if norm_path:
                    videos_by_norm[norm_path] = video

        if target_paths:
            # DEBUG: Log all normalized keys in project for comparison
            log.debug(
                "video_selection_service.project_keys",
                keys=list(videos_by_norm.keys())[:5],
                total=len(videos_by_norm)
            )
            # Targeted selection mode
            return self._select_targeted(videos_by_norm, target_paths)
        else:
            # Pending selection mode
            return self._select_pending(all_videos)

    def _select_targeted(
        self,
        videos_by_norm: dict[str, dict],
        target_paths: list[str],
    ) -> VideoSelectionResult:
        """
        Select specific target videos.

        Args:
            videos_by_norm: Normalized path lookup dictionary
            target_paths: List of specific paths to select

        Returns:
            VideoSelectionResult: Targeted selection results
        """
        from zebtrack.core.video_manager import VideoManager
        # Normalize target paths
        normalized_targets: list[str] = []
        raw_lookup: dict[str, str] = {}

        for raw_path in target_paths:
            if not isinstance(raw_path, str) or not raw_path:
                continue
            
            norm_path = VideoManager.normalize_path(raw_path)
            if not norm_path:
                continue
                
            normalized_targets.append(norm_path)
            raw_lookup.setdefault(norm_path, raw_path)
            
            # DIAGNOSTIC: Check why candidate might not be found
            is_in = norm_path in videos_by_norm
            log.debug(
                "video_selection_service.target_check",
                raw=raw_path,
                norm=norm_path,
                found=is_in
            )

        # Select candidates that exist in project
        candidate_entries = [
            videos_by_norm[norm_path]
            for norm_path in normalized_targets
            if norm_path in videos_by_norm
        ]

        # Identify missing targets (excluding internal _sub_ entries which are UI tree IDs)
        missing_targets = [
            raw_lookup[norm_path]
            for norm_path in normalized_targets
            if norm_path not in videos_by_norm
            and "_sub_" not in norm_path  # Filter out multi-subject UI tree IDs
        ]

        result = VideoSelectionResult(
            candidate_entries=candidate_entries,
            missing_targets=missing_targets,
            selection_mode="targeted",
        )

        log.info(
            "video_selection_service.select_targeted.complete",
            candidates=result.candidate_count,
            missing=len(missing_targets),
        )

        return result

    def _select_pending(self, all_videos: list[dict]) -> VideoSelectionResult:
        """
        Select all pending videos (not processed/complete).

        Args:
            all_videos: List of all video entries

        Returns:
            VideoSelectionResult: Pending selection results
        """
        # Select videos that are not yet processed
        candidate_entries = [
            video for video in all_videos if video.get("status") not in {"processed", "complete"}
        ]

        result = VideoSelectionResult(
            candidate_entries=candidate_entries,
            missing_targets=[],
            selection_mode="pending",
        )

        log.info(
            "video_selection_service.select_pending.complete",
            candidates=result.candidate_count,
            total_videos=len(all_videos),
        )

        return result

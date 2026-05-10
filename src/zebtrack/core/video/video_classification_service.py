"""Video Classification Service - Sprint 12.

Classifies video entries into processing categories based on available data.

Sprint: 12 of REFACTOR-MASTER-PLAN-2025.md
Purpose: Extract classification logic from MainViewModel to dedicated service
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
class VideoClassificationResult:
    """
    Result of video classification operation.

    Sprint 12: Value object for classification results.
    Separates classification logic from UI presentation.

    Videos are classified into categories based on available data:
    - ready_with_trajectory: Has arena, ROIs, AND trajectory data (ready for reports)
    - ready_with_zones: Has arena AND ROIs (can be processed)
    - arena_only: Has arena but NO ROIs (needs ROI definition)
    - without_arena: NO arena (needs arena definition)

    Attributes:
        ready_with_trajectory: Videos with complete data (arena + ROIs + trajectory)
        ready_with_zones: Videos with zones defined (arena + ROIs)
        arena_only: Videos with only arena defined
        without_arena: Videos without arena
        data_changed: Whether any video metadata was updated during classification
    """

    ready_with_trajectory: list[dict] = field(default_factory=list)
    ready_with_zones: list[dict] = field(default_factory=list)
    arena_only: list[dict] = field(default_factory=list)
    without_arena: list[dict] = field(default_factory=list)
    data_changed: bool = False


class VideoClassificationService:
    """
    Service for classifying videos into processing categories.

    Sprint 12: Extracted from MainViewModel._classify_candidate_videos().
    Pure business logic with no UI dependencies.

    Classifies videos based on:
    - has_arena: Whether arena polygon is defined
    - has_rois: Whether ROI polygons are defined
    - has_trajectory: Whether trajectory data exists
    - has_complete_data: Whether all data is complete

    Example:
        >>> service = VideoClassificationService()
        >>> result = service.classify_videos(
        ...     candidate_entries=[...],
        ...     info_by_norm={...}
        ... )
        >>> print(f"Ready: {len(result.ready_with_trajectory)}")
    """

    def __init__(self):
        """Initialize VideoClassificationService."""
        log.info("video_classification_service.initialized")

    @staticmethod
    def _resolve_effective_flags(
        info: dict,
        norm_path: Path | str | None,
        aquarium_filter: dict[str, list[int]] | None,
    ) -> dict[str, bool]:
        """Resolve selection-aware flags without mutating persisted video state."""
        flags = {
            "has_arena": bool(info.get("has_arena")),
            "has_rois": bool(info.get("has_rois")),
            "has_trajectory": bool(info.get("has_trajectory")),
            "has_complete_data": bool(info.get("has_complete_data")),
        }

        if not norm_path or not aquarium_filter:
            return flags

        selected_ids: list[int] | None = None
        for raw_path, aquarium_ids in aquarium_filter.items():
            if os.path.normpath(raw_path).lower() == os.path.normpath(norm_path).lower():
                selected_ids = [int(aquarium_id) for aquarium_id in aquarium_ids]
                break

        aquarium_flags = info.get("aquarium_flags") or {}
        if not selected_ids or not aquarium_flags:
            return flags

        selected_flags = [
            aquarium_flags[aq_id] for aq_id in selected_ids if aq_id in aquarium_flags
        ]
        if not selected_flags:
            return {
                "has_arena": False,
                "has_rois": False,
                "has_trajectory": False,
                "has_complete_data": False,
            }

        has_arena = any(bool(flag.get("has_arena")) for flag in selected_flags)
        has_rois = any(bool(flag.get("has_rois")) for flag in selected_flags)
        has_trajectory = any(bool(flag.get("has_trajectory")) for flag in selected_flags)

        return {
            "has_arena": has_arena,
            "has_rois": has_rois,
            "has_trajectory": has_trajectory,
            "has_complete_data": bool(has_arena and has_rois and has_trajectory),
        }

    def classify_videos(
        self,
        candidate_entries: list[dict],
        info_by_norm: dict[str, dict],
        aquarium_filter: dict[str, list[int]] | None = None,
    ) -> VideoClassificationResult:
        """
        Classify candidate video entries into processing categories.

        Sprint 12: Core classification logic extracted from MainViewModel.

        Iterates through candidate entries and classifies each based on:
        1. Available data flags (has_arena, has_rois, has_trajectory)
        2. Updates video entry with latest data flags
        3. Places video into appropriate category

        Args:
            candidate_entries: List of video entry dictionaries to classify
            info_by_norm: Lookup dict mapping normalized paths to video info

        Returns:
            VideoClassificationResult: Classified videos in categorized buckets

        Example:
            >>> result = service.classify_videos(
            ...     candidate_entries=[
            ...         {"path": "/video1.mp4", "status": "pending"},
            ...         {"path": "/video2.mp4", "status": "pending"},
            ...     ],
            ...     info_by_norm={
            ...         "/video1.mp4": {
            ...             "path": "/video1.mp4",
            ...             "has_arena": True,
            ...             "has_rois": True,
            ...             "has_trajectory": True
            ...         },
            ...         "/video2.mp4": {
            ...             "path": "/video2.mp4",
            ...             "has_arena": True,
            ...             "has_rois": False
            ...         }
            ...     }
            ... )
            >>> print(len(result.ready_with_trajectory))  # 1
            >>> print(len(result.arena_only))  # 1
        """
        log.debug(
            "video_classification_service.classify_videos.start",
            candidates=len(candidate_entries),
            info_count=len(info_by_norm),
        )

        result = VideoClassificationResult()

        for video in candidate_entries:
            path = video.get("path")
            if not isinstance(path, str) or not path:
                log.warning(
                    "video_classification_service.classify_videos.invalid_path",
                    video=video,
                )
                continue

            # Get video info from lookup
            from zebtrack.core.project.video_manager import VideoManager

            norm_path = VideoManager.normalize_path(path)

            info = info_by_norm.get(norm_path) if norm_path else None
            if not info:
                log.warning(
                    "video_classification_service.classify_videos.no_info",
                    path=path,
                    norm_path=norm_path,
                )
                continue

            # Update video entry with latest aggregate data flags.
            for key in ("has_arena", "has_rois", "has_trajectory", "has_complete_data"):
                new_value = info.get(key, False)
                if video.get(key) != new_value:
                    video[key] = new_value
                    result.data_changed = True

            # Copy all scan data from info to video (parquet_files, has_data, etc.)
            # This ensures zone loading works correctly
            for key in ("parquet_files", "has_data"):
                if key in info:
                    video[key] = info[key]

            classified_video = dict(video)
            for key in (
                "parquet_files",
                "has_data",
                "multi_aquarium_outputs",
                "aquarium_flags",
                "is_multi_aquarium",
            ):
                if key in info:
                    classified_video[key] = info[key]

            effective_flags = self._resolve_effective_flags(info, norm_path, aquarium_filter)
            classified_video.update(effective_flags)

            # Debug: log parquet_files being copied
            pf = info.get("parquet_files", {})
            log.debug(
                "video_classification_service.classify_videos.parquet_copy",
                path=path,
                has_arena=info.get("has_arena"),
                has_rois=info.get("has_rois"),
                arena_path=pf.get("arena"),
                rois_path=pf.get("rois"),
            )

            # Classify into appropriate bucket for this selection.
            if effective_flags["has_arena"]:
                if effective_flags["has_trajectory"]:
                    result.ready_with_trajectory.append(classified_video)
                elif effective_flags["has_rois"]:
                    result.ready_with_zones.append(classified_video)
                else:
                    result.arena_only.append(classified_video)
            else:
                result.without_arena.append(classified_video)

        log.info(
            "video_classification_service.classify_videos.complete",
            trajectory=len(result.ready_with_trajectory),
            zones=len(result.ready_with_zones),
            arena_only=len(result.arena_only),
            without_arena=len(result.without_arena),
            data_changed=result.data_changed,
        )

        return result

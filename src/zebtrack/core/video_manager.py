"""Video management module for ZebTrack-AI projects.

Handles all video-related operations including:
- Video scanning and discovery
- Video batch management
- Video status tracking
- Video entry retrieval and manipulation
- Asset management per video

This module was extracted from ProjectManager during Phase 2 refactoring
to reduce the God Object pattern and improve maintainability.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import structlog

from zebtrack.utils import calculate_sha256

log = structlog.get_logger()


class VideoManager:
    """Manages video-related operations for ZebTrack-AI projects.

    Responsibilities:
    - Scanning directories for video files
    - Adding and removing videos from projects
    - Tracking video processing status
    - Managing video metadata and assets
    - Caching video scan results for performance

    This class is stateless regarding project data - it operates on
    project_data dictionaries passed to its methods.

    Cache Behavior:
    - Uses class-level cache shared across all VideoManager instances
    - Cache is intentional for performance in multi-project scenarios
    - TTL of 30 seconds prevents stale data
    - Use clear_scan_cache() to manually invalidate cache if needed
    """

    # Cache for video scanning operations (30s TTL)
    # NOTE: Class-level cache is shared across all instances for performance
    _SCAN_CACHE_TTL_SECONDS: ClassVar[float] = 30.0
    _scan_cache: ClassVar[dict[str, dict[str, Any]]] = {}

    @staticmethod
    def scan_input_paths(paths: list[str]) -> list[dict[str, Any]]:
        """
        Scan a list of input paths (files or directories) and identifies video files.

        For each video, it checks if corresponding parquet files exist and identifies
        their types (arena, ROIs, trajectory).

        Args:
            paths: A list of file or directory paths.

        Returns:
            A list of dictionaries, where each dictionary represents a video and
            contains detailed information about existing parquet files.

            Example::

                [{
                    'path': 'path/to/video.mp4',
                    'has_arena': True,
                    'has_rois': True,
                    'has_trajectory': True,
                    'has_complete_data': True,
                    'has_data': True,
                    'parquet_files': {
                        'arena': 'path/to/1_ProcessingArea_video.parquet',
                        'rois': 'path/to/2_AreasOfInterest_video.parquet',
                        'trajectory': 'path/to/3_CoordMovimento_video.parquet'
                    }
                }, ...]
        """
        video_files: set[Path] = set()
        video_extensions = {".mp4", ".avi", ".mov"}

        for p_str in paths:
            p = Path(p_str)
            if not p.exists():
                log.debug(
                    "video_manager.scan_input_paths.missing_path",
                    path=str(p),
                )
                continue

            if p.is_dir():
                video_files.update(VideoManager._scan_directory_for_videos(p, video_extensions))
            elif p.is_file() and p.suffix.lower() in video_extensions:
                video_files.update(VideoManager._scan_file_entry(p, video_extensions))

        results = []
        for video_path in sorted(video_files):
            parent_dir = video_path.parent
            base_name = video_path.stem

            # Check for specific parquet file types
            arena_pattern = f"1_ProcessingArea_{base_name}.parquet"
            rois_pattern = f"2_AreasOfInterest_{base_name}.parquet"
            trajectory_pattern = f"3_CoordMovimento_{base_name}.parquet"

            # Search in parent directory and potential _results subdirectory
            search_dirs = [parent_dir, parent_dir / f"{base_name}_results"]

            arena_path = None
            rois_path = None
            trajectory_path = None

            for search_dir in search_dirs:
                if search_dir.exists():
                    if not arena_path:
                        arena_candidates = list(search_dir.glob(arena_pattern))
                        if arena_candidates:
                            arena_path = str(arena_candidates[0])

                    if not rois_path:
                        rois_candidates = list(search_dir.glob(rois_pattern))
                        if rois_candidates:
                            rois_path = str(rois_candidates[0])

                    if not trajectory_path:
                        trajectory_candidates = list(search_dir.glob(trajectory_pattern))
                        if trajectory_candidates:
                            trajectory_path = str(trajectory_candidates[0])

            has_arena = arena_path is not None
            has_rois = rois_path is not None
            has_trajectory = trajectory_path is not None
            has_complete_data = has_arena and has_rois and has_trajectory

            # Backward compatibility: has_data is True if trajectory exists or complete
            has_data = has_trajectory or has_complete_data

            result = {
                "path": video_path.as_posix(),
                "has_arena": has_arena,
                "has_rois": has_rois,
                "has_trajectory": has_trajectory,
                "has_complete_data": has_complete_data,
                "has_data": has_data,  # Backward compatibility
                "parquet_files": {
                    "arena": arena_path,
                    "rois": rois_path,
                    "trajectory": trajectory_path,
                },
            }

            # Check for recording metadata file
            metadata_file = parent_dir / "_recording_metadata.json"
            if metadata_file.exists():
                try:
                    import json

                    with open(metadata_file, encoding="utf-8") as f:
                        recording_metadata = json.load(f)

                    # Add metadata to result
                    if recording_metadata:
                        result["metadata"] = recording_metadata
                        log.info(
                            "video_manager.scan.metadata_loaded",
                            video=video_path.name,
                            metadata=recording_metadata,
                        )
                except Exception as e:
                    log.warning(
                        "video_manager.scan.metadata_load_failed",
                        video=video_path.name,
                        error=str(e),
                    )

            results.append(result)

        return results

    @classmethod
    def _scan_directory_for_videos(
        cls, directory: Path | str, video_extensions: set[str]
    ) -> list[Path]:
        """Recursively scan a directory for video files with caching.

        Args:
            directory: Directory path to scan
            video_extensions: Set of valid video file extensions

        Returns:
            List of Path objects for found video files
        """
        directory = Path(directory) if isinstance(directory, str) else directory
        cache_key = str(directory.resolve())
        signature = cls._compute_path_signature(directory)
        now = time.time()

        cached = cls._scan_cache.get(cache_key)
        if (
            cached
            and cached["signature"] == signature
            and now - cached["timestamp"] <= cls._SCAN_CACHE_TTL_SECONDS
        ):
            return [Path(item) for item in cached["videos"]]

        videos: list[Path] = []
        try:
            for video_path in directory.rglob("*"):
                if video_path.suffix.lower() in video_extensions:
                    videos.append(video_path)
        except (OSError, PermissionError) as exc:
            log.warning(
                "video_manager.scan_directory.error",
                directory=str(directory),
                error=str(exc),
            )

        cls._scan_cache[cache_key] = {
            "signature": signature,
            "timestamp": now,
            "videos": [str(video) for video in videos],
        }
        return videos

    @classmethod
    def _scan_file_entry(cls, file_path: Path | str, video_extensions: set[str]) -> list[Path]:
        """Check if a single file is a video and cache the result.

        Args:
            file_path: Path to the file to check
            video_extensions: Set of valid video file extensions

        Returns:
            List with the file Path if it's a video, empty list otherwise
        """
        file_path = Path(file_path) if isinstance(file_path, str) else file_path
        if file_path.suffix.lower() not in video_extensions:
            return []

        cache_key = str(file_path.resolve())
        signature = cls._compute_path_signature(file_path)
        now = time.time()

        cached = cls._scan_cache.get(cache_key)
        if (
            cached
            and cached["signature"] == signature
            and now - cached["timestamp"] <= cls._SCAN_CACHE_TTL_SECONDS
        ):
            return [Path(item) for item in cached["videos"]]

        videos = [file_path]

        cls._scan_cache[cache_key] = {
            "signature": signature,
            "timestamp": now,
            "videos": [str(file_path)],
        }
        return videos

    @staticmethod
    def _compute_path_signature(path: Path | str) -> tuple[str, int]:
        """Compute a signature for a path based on mtime and size.

        Args:
            path: Path to compute signature for

        Returns:
            Tuple of (mtime_ns as string, size in bytes)
        """
        path = Path(path) if isinstance(path, str) else path
        try:
            stat_result = path.stat()
        except FileNotFoundError:
            return ("missing", 0)

        return (str(stat_result.st_mtime_ns), stat_result.st_size)

    @classmethod
    def clear_scan_cache(cls, target_path: Path | str | None = None) -> None:
        """Clear the video scan cache.

        Args:
            target_path: If provided, only clear cache for this path.
                        If None, clear all cache entries.
        """
        if target_path is None:
            cls._scan_cache.clear()
            return

        target_path = Path(target_path) if isinstance(target_path, str) else target_path
        resolved = str(target_path.resolve())
        cls._scan_cache.pop(resolved, None)
        cls._scan_cache.pop(str(target_path), None)

    @staticmethod
    def add_video_batch(
        project_data: dict[str, Any],
        video_files: list[dict[str, Any]],
        save_callback: Callable[[], None] | None = None,
    ) -> int:
        """
        Add a new batch of videos to the project data.

        Args:
            project_data: The project data dictionary to modify
            video_files: A list of video dicts from scan_input_paths.
            save_callback: Optional callback to save project after adding

        Returns:
            Number of videos added
        """
        if not video_files:
            return 0

        new_batch: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "videos": [],
        }

        for video_info in video_files:
            # Handle both string paths and dict formats
            if isinstance(video_info, str):
                video_path = video_info
                has_data = False
                metadata = {}
                video_info = {"path": video_path}  # Convert to dict for consistent handling below
            else:
                video_path = video_info["path"]
                has_data = bool(
                    video_info.get(
                        "has_data",
                        video_info.get("has_complete_data", False),
                    )
                )
                metadata = dict(video_info.get("metadata") or {})

            # Ensure video_path is always a string (not Path object) for JSON serialization
            if not isinstance(video_path, str):
                video_path = str(Path(video_path).as_posix())

            video_hash = calculate_sha256(video_path)

            for key in (
                "group",
                "group_display_name",
                "day",
                "subject",
                "is_multi_subject",
                "subject_entries",
            ):
                value = video_info.get(key)
                if value is not None and (
                    value != "" or isinstance(value, (int, float, bool, list))
                ):
                    metadata.setdefault(key, value)

            # Remove empty values to keep JSON compact (but preserve bools and lists)
            metadata = {
                key: value
                for key, value in metadata.items()
                if value is not None
                and (value != "" or isinstance(value, (int, float, bool, list)))
            }

            video_entry: dict[str, Any] = {
                "path": video_path,
                "sha256": video_hash,
                "status": "processed" if has_data else "pending",
                "has_arena": bool(video_info.get("has_arena", False)),
                "has_rois": bool(video_info.get("has_rois", False)),
                "has_trajectory": bool(video_info.get("has_trajectory", False)),
                "has_complete_data": bool(
                    video_info.get(
                        "has_complete_data",
                        has_data,
                    )
                ),
                "zones_finalized": False,
            }

            if metadata:
                video_entry["metadata"] = metadata

            new_batch["videos"].append(video_entry)

        project_data.setdefault("batches", []).append(new_batch)

        metadata_count = sum(1 for v in new_batch["videos"] if "metadata" in v)
        arena_count = sum(1 for v in new_batch["videos"] if v.get("has_arena"))
        trajectory_count = sum(1 for v in new_batch["videos"] if v.get("has_trajectory"))

        log.info(
            "video_manager.batch_added",
            count=len(video_files),
            with_metadata=metadata_count,
            with_arena=arena_count,
            with_trajectory=trajectory_count,
        )

        if save_callback:
            save_callback()

        return len(video_files)

    @staticmethod
    def update_video_status(
        project_data: dict[str, Any],
        video_path: Path | str,
        new_status: str,
        save_callback: Callable[[], None] | None = None,
    ) -> bool:
        """
        Update the status of a specific video across all batches.

        Args:
            project_data: The project data dictionary to modify
            video_path: Path to the video to update
            new_status: New status value
            save_callback: Optional callback to save project after update

        Returns:
            bool: True if video was found and updated, False otherwise.
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        video_path_str = str(video_path)

        for batch in project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video["path"] == video_path_str:
                    video["status"] = new_status
                    log.info(
                        "video_manager.status_updated",
                        video_path=video_path_str,
                        status=new_status,
                    )
                    if save_callback:
                        save_callback()
                    return True
        return False

    @staticmethod
    def reset_all_video_statuses(
        project_data: dict[str, Any],
        to_status: str = "pending",
        save_callback: Callable[[], None] | None = None,
    ) -> bool:
        """Reset every video status to a given value (default 'pending').

        Args:
            project_data: The project data dictionary to modify
            to_status: Status value to set for all videos
            save_callback: Optional callback to save project after reset

        Returns:
            bool: True if any videos were changed, False otherwise
        """
        changed = False
        for batch in project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video.get("status") != to_status:
                    video["status"] = to_status
                    changed = True

        if changed:
            log.info("video_manager.statuses_reset", to_status=to_status)
            if save_callback:
                save_callback()

        return changed

    @staticmethod
    def get_all_videos(project_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a flat list of all videos from all batches.

        Args:
            project_data: The project data dictionary to query

        Returns:
            List of video entry dictionaries
        """
        all_vids = []
        for batch in project_data.get("batches", []):
            all_vids.extend(batch.get("videos", []))
        return all_vids

    @staticmethod
    def iter_project_videos(project_data: dict[str, Any]) -> Any:
        """Yield (batch_dict, video_dict) pairs for every registered video.

        Args:
            project_data: The project data dictionary to iterate

        Yields:
            Tuples of (batch_dict, video_dict)
        """
        for batch in project_data.get("batches", []):
            videos = batch.get("videos", [])
            for video in videos:
                yield batch, video

    @staticmethod
    def refresh_complete_flag(video_entry: dict) -> None:
        """Update the has_complete_data flag based on individual asset flags.

        Args:
            video_entry: Video entry dictionary to update (modified in place)
        """
        video_entry["has_complete_data"] = bool(
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
        )

    @staticmethod
    def normalize_path(path: str | Path | None) -> str | None:
        """Robustly normalize path for cross-platform comparison."""
        if not path:
            return None
        try:
            # Standardize to absolute POSIX lowercase path
            return os.path.abspath(str(path)).replace("\\", "/").lower()
        except Exception:
            return str(path).replace("\\", "/").lower()

    @staticmethod
    def find_video_entry(
        project_data: dict,
        *,
        path: str | None = None,
        experiment_id: str | None = None,
    ) -> dict | None:
        """Return the project entry for a given video path or experiment id.

        Args:
            project_data: The project data dictionary to search
            path: Video file path to search for
            experiment_id: Experiment ID to search for

        Returns:
            Video entry dictionary if found, None otherwise
        """
        if not project_data:
            return None

        normalized_target = VideoManager.normalize_path(path)

        for _batch, video in VideoManager.iter_project_videos(project_data):
            candidate_path = video.get("path")
            if candidate_path and normalized_target:
                if VideoManager.normalize_path(candidate_path) == normalized_target:
                    return video

            if experiment_id:
                candidate_name = os.path.basename(candidate_path or "")
                candidate_id = os.path.splitext(candidate_name)[0]
                if candidate_id == experiment_id:
                    return video

        return None

    @staticmethod
    def get_next_video(project_data: dict) -> str | None:
        """
        Return the path of the next video with 'pending' status from all batches.

        Args:
            project_data: The project data dictionary to search

        Returns:
            Path to next pending video, or None if no pending videos exist
        """
        for video in VideoManager.get_all_videos(project_data):
            if video["status"] == "pending":
                return video["path"]
        return None

    @staticmethod
    def remove_video_entry(
        project_data: dict[str, Any],
        video_path: Path | str,
        video_entry: dict[str, Any],
        clear_zones_callback: Callable[[str], None] | None = None,
    ) -> bool:
        """Remove a video entry from project data.

        Args:
            project_data: The project data dictionary to modify
            video_path: Path to the video to remove
            video_entry: The video entry dictionary (for reference)
            clear_zones_callback: Optional callback to clear zone data for video

        Returns:
            bool: True if video was found and removed, False otherwise
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        changed = False

        # Clear zone data if callback provided
        if clear_zones_callback:
            clear_zones_callback(video_path_str)

        # Remove from all batches
        for batch in project_data.get("batches", []):
            original_count = len(batch.get("videos", []))
            batch["videos"] = [
                item for item in batch.get("videos", []) if item.get("path") != video_path_str
            ]
            if len(batch["videos"]) != original_count:
                changed = True

        return changed

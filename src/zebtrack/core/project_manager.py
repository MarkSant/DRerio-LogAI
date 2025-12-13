"""Project management module for ZebTrack-AI.

Provides the ProjectManager class for handling project lifecycle operations including
creation, loading, configuration management, and asset tracking for zebrafish behavioral analysis.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml

from zebtrack.core.asset_manager import AssetManager
from zebtrack.core.detector import ZoneData
from zebtrack.core.project_service import ProjectService
from zebtrack.core.state_manager import StateManager
from zebtrack.core.types import AssetType
from zebtrack.core.video_manager import VideoManager
from zebtrack.core.zone_manager import ZoneManager
from zebtrack.utils import IntegrityError, calculate_sha256


class ProjectInvalidError(ValueError):
    """Exception raised when project structure or data is invalid.

    Raised when:
    - Project directory cannot be created
    - Project configuration file is missing or not found
    - Project configuration is corrupted or contains invalid JSON
    - Project file save operation fails due to permissions or disk errors

    This exception replaces GUI messagebox calls for thread-safe error handling
    and allows calling code to handle project validation errors appropriately.

    Attributes:
        message: Human-readable error description
        path: Optional Path to the project directory or file involved
        cause: Optional underlying exception that caused this error
    """

    def __init__(
        self,
        message: str,
        path: Path | str | None = None,
        cause: Exception | None = None,
    ):
        """
        Initialize ProjectInvalidError with structured error information.

        Args:
            message: Human-readable error description
            path: Optional path to the project directory or file involved
            cause: Optional underlying exception that caused this error
        """
        self.path = Path(path) if path and not isinstance(path, Path) else path
        self.cause = cause
        super().__init__(message)


CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"
ROI_TEMPLATE_VERSION = 1

log = structlog.get_logger()


# Task 2.2: Thread-safe decorator for ProjectManager methods
def _threadsafe(method):
    """Decorator to make ProjectManager methods thread-safe using instance lock.

    Task 2.2: Prevents race conditions in concurrent load/save operations.
    """
    from functools import wraps

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class ProjectManager:
    """Manages project lifecycle, configuration, and asset tracking.

    Handles project creation, loading, saving, asset management, zone data,
    video metadata, and configuration persistence for zebrafish tracking projects.
    """

    def __init__(self, state_manager: StateManager | None = None, settings_obj=None):
        """Initialize ProjectManager with dependency injection.

        Args:
            state_manager: StateManager for state propagation
            settings_obj: Settings instance (injected dependency, optional for tests)
        """
        # Phase 1, Step 3: Delegate file I/O to ProjectService
        self.project_service = ProjectService()

        # Phase 2, Step 4: Optional StateManager reference for state propagation
        self.state_manager = state_manager

        # Settings dependency (injected)
        self.settings = settings_obj

        # Task 2.2: Thread safety for concurrent load/save operations
        self._lock = threading.RLock()

        # Phase 2 Task 2.3: Specialized managers for different responsibilities
        self.video_manager = VideoManager()
        self.zone_manager = ZoneManager()
        self.asset_manager = AssetManager()

        # In-memory project state
        self.project_path = None
        self.project_data = {}
        self.metadata = None  # Will hold the DataFrame for metadata.csv
        # Compatibility: keep roi_template_manager reference for legacy code
        self.roi_template_manager = self.asset_manager.roi_template_manager

    # ------------------------------------------------------------------
    # Internal helpers for zone management
    # ------------------------------------------------------------------

    def _ensure_zone_structures(self) -> None:
        """Ensure zone-related structures exist in project data. Delegates to ZoneManager."""
        ZoneManager.ensure_zone_structures(self.project_data)

    @staticmethod
    def _normalize_video_path(path: Path | str | None) -> str | None:
        """Delegate to ZoneManager for path normalization."""
        return ZoneManager.normalize_video_path(path)

    def _resolve_zone_entry(self, video_path: Path | str | None) -> tuple[str | None, dict | None]:
        """Locate a stored zone entry matching the provided video path. Delegates to ZoneManager."""
        return self.zone_manager.resolve_zone_entry(self.project_data, video_path)

    def _deduplicate_zone_keys(self, preferred_key: str | None) -> None:
        """
        Remove duplicate zone entries that resolve to the same canonical path.

        Delegates to ZoneManager.
        """
        ZoneManager.deduplicate_zone_keys(self.project_data, preferred_key)

    def list_roi_templates(
        self,
        *,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        """List all ROI templates. Delegates to AssetManager."""
        return self.asset_manager.list_roi_templates(
            self.project_data, include_global=include_global
        )

    def save_roi_template(
        self,
        name: str,
        zone_data: ZoneData,
        *,
        save_arena: bool = True,
        save_rois: bool = True,
        save_location: Literal["project", "global", "custom"] | None = "project",
        custom_path: str | Path | None = None,
        overwrite: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Save an ROI template. Delegates to AssetManager."""
        persist_callback = self.save_project if persist else None
        return self.asset_manager.save_roi_template(
            project_data=self.project_data,
            project_path=self.project_path,
            name=name,
            zone_data=zone_data,
            zone_data_to_dict_fn=self._zone_data_to_dict,
            save_arena=save_arena,
            save_rois=save_rois,
            save_location=save_location,
            custom_path=custom_path,
            overwrite=overwrite,
            persist_callback=persist_callback,
        )

    def import_roi_template(
        self,
        file_path: Path | str,
        *,
        name: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Import an ROI template from file. Delegates to AssetManager."""
        persist_callback = self.save_project if persist and self.project_path else None
        return self.asset_manager.import_roi_template(
            project_data=self.project_data,
            project_path=self.project_path,
            file_path=file_path,
            zone_data_from_dict_fn=self._zone_data_from_dict,
            zone_data_to_dict_fn=self._zone_data_to_dict,
            name=name,
            persist_callback=persist_callback,
        )

    def load_roi_template(
        self,
        name: str,
        *,
        location: Literal["project", "global", "custom"] | None = None,
        file_path: str | Path | None = None,
    ) -> ZoneData:
        """Load an ROI template. Delegates to AssetManager."""
        return self.asset_manager.load_roi_template(
            project_data=self.project_data,
            project_path=self.project_path,
            name=name,
            zone_data_from_dict_fn=self._zone_data_from_dict,
            location=location,
            file_path=file_path,
        )

    def _zone_data_to_dict(self, zone_data: ZoneData) -> dict:
        """Serialize ZoneData into a JSON-friendly dictionary. Delegates to ZoneManager."""
        return ZoneManager.zone_data_to_dict(zone_data)

    def _zone_data_from_dict(self, data: dict | None) -> ZoneData:
        """Deserialize zone data stored in JSON back into ZoneData. Delegates to ZoneManager."""
        return ZoneManager.zone_data_from_dict(data)

    def _update_video_zone_flags(
        self,
        video_path: Path | str,
        zone_data: ZoneData | None,
    ) -> None:
        """Update has_arena/has_rois flags for a given video entry. Delegates to ZoneManager."""
        ZoneManager.update_video_zone_flags(self.project_data, video_path, zone_data)

    def _refresh_last_zone_source(self, removed_path: Path | str | None = None) -> None:
        """Refresh cache for last zone source video when data changes. Delegates to ZoneManager."""
        self.zone_manager.refresh_last_zone_source(self.project_data, removed_path)

    # ------------------------------------------------------------------
    # Public helpers for zone lifecycle
    # ------------------------------------------------------------------

    def set_active_zone_video(self, video_path: Path | str | None) -> None:
        """
        Set the video whose zones should be considered active in memory.
        
        Robustly attempts to load zone data from the project structure if in-memory data
        is incomplete, ensuring the editor reflects the files on disk.
        """
        if video_path:
            video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
            
            # 1. Resolve where the files SHOULD be in the project structure
            video_entry = self.find_video_entry(path=video_path_str)
            metadata = video_entry.get("metadata") if video_entry else None
            experiment_id = Path(video_path_str).stem
            
            try:
                results_dir = self.resolve_results_directory(
                    experiment_id,
                    video_path=video_path_str,
                    metadata=metadata
                )
                
                # 2. Check for parquet files in the project structure
                arena_path = results_dir / f"1_ProcessingArea_{experiment_id}.parquet"
                rois_path = results_dir / f"2_AreasOfInterest_{experiment_id}.parquet"
                
                found_parquets = {}
                if arena_path.exists():
                    found_parquets["arena"] = str(arena_path)
                if rois_path.exists():
                    found_parquets["rois"] = str(rois_path)
                
                # 3. If files found, force load/merge
                if found_parquets:
                    log.info("project.set_active.found_project_parquets", files=list(found_parquets.keys()))
                    
                    # Prepare info dict for loader
                    video_info = {"path": video_path_str, "parquet_files": found_parquets}
                    
                    # Load from disk
                    loaded_zones = self.load_zones_from_parquet(video_info)
                    
                    if loaded_zones:
                        # Check what we have in memory currently
                        current_zones = self.zone_manager.get_zone_data(
                            self.project_data, video_path_str, fallback_to_global=False
                        )
                        
                        # Use loaded data if memory is empty OR if memory lacks ROIs but disk has them
                        should_update = False
                        if not current_zones.polygon and loaded_zones.polygon:
                            should_update = True
                        if not current_zones.roi_polygons and loaded_zones.roi_polygons:
                            should_update = True
                            
                        # If we loaded data and decide to use it, save to memory
                        if should_update or (not current_zones.polygon and not current_zones.roi_polygons):
                            log.info("project.set_active.syncing_memory_from_disk", video=video_path_str)
                            self.save_zone_data(loaded_zones, video_path=video_path_str, persist=False)
                            
                            # Also update video entry registry so future scans work
                            if video_entry:
                                video_entry.setdefault("parquet_files", {}).update(found_parquets)
                                if loaded_zones.polygon:
                                    video_entry["has_arena"] = True
                                if loaded_zones.roi_polygons:
                                    video_entry["has_rois"] = True

            except Exception as e:
                log.warning("project.set_active.load_failed", error=str(e))

        # Delegate to manager to set the active pointer
        self.zone_manager.set_active_zone_video(self.project_data, video_path)

    def get_active_zone_video(self) -> str | None:
        """Return the currently active video for zone operations. Delegates to ZoneManager."""
        return self.zone_manager.get_active_zone_video()

    def get_last_zone_video(self, exclude: str | None = None) -> str | None:
        """
        Return the last video that had zones saved, excluding optional target.

        Delegates to ZoneManager.
        """
        return self.zone_manager.get_last_zone_video(self.project_data, exclude)

    def has_zone_data(self, video_path: Path | str | None) -> bool:
        """
        Check whether the given video currently stores arena or ROI data.

        Delegates to ZoneManager.
        """
        return self.zone_manager.has_zone_data(self.project_data, video_path)

    def has_arena_data(self, video_path: Path | str | None) -> bool:
        """Check if arena data exists for the given video."""
        entry = self.find_video_entry(path=video_path)
        return self._video_has_asset(entry, "arena") if entry else False

    def has_roi_data(self, video_path: Path | str | None) -> bool:
        """Check if ROI data exists for the given video."""
        entry = self.find_video_entry(path=video_path)
        return self._video_has_asset(entry, "rois") if entry else False

    def has_trajectory_data(self, video_path: Path | str | None) -> bool:
        """Check if trajectory data exists for the given video."""
        entry = self.find_video_entry(path=video_path)
        return self._video_has_asset(entry, "trajectory") if entry else False

    def has_summary_data(self, video_path: Path | str | None) -> bool:
        """Check if summary data exists for the given video."""
        entry = self.find_video_entry(path=video_path)
        return self._video_has_asset(entry, "summary") if entry else False

    def save_zone_data(
        self,
        zone_data: ZoneData,
        video_path: Path | str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        """Persist zone data for the active video and project defaults. Delegates to ZoneManager."""
        # Update in-memory state first (no callback)
        self.zone_manager.save_zone_data(
            self.project_data, zone_data, video_path=video_path, persist_callback=None
        )

        # Handle persistence logic here to support single-video workflow (no project path)
        if persist:
            # Generate parquet files if we have a valid video path and project
            target_video = video_path or self.get_active_zone_video()
            if target_video and self.project_path:
                try:
                    exported = self.export_zones_to_parquet(target_video, zone_data)
                    
                    # Update video entry with new parquet files
                    video_entry = self.find_video_entry(path=target_video)
                    if video_entry:
                        parquet_map = video_entry.setdefault("parquet_files", {})
                        parquet_map.update(exported)
                        
                        # Update flags based on export success
                        if "arena" in exported:
                            video_entry["has_arena"] = True
                        if "rois" in exported:
                            video_entry["has_rois"] = True
                            
                except Exception as e:
                    log.error("project.save_zone_data.parquet_export_failed", error=str(e))

            if self.project_path:
                self.save_project()
            else:
                log.info(
                    "project.zone_data.save.in_memory",
                    video_path=str(video_path) if video_path else None,
                    reason="single_video_workflow"
                )

    def clear_zone_data_for_video(
        self,
        video_path: Path | str,
        *,
        persist: bool = True,
    ) -> None:
        """Remove stored zone data for a specific video."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)

        self._ensure_zone_structures()

        key, _ = self._resolve_zone_entry(video_path)
        if key and key in self.project_data["zones_by_video"]:
            del self.project_data["zones_by_video"][key]

        normalized_target = self._normalize_video_path(video_path)
        active_zone_video = self.get_active_zone_video()
        if active_zone_video and normalized_target == active_zone_video:
            self.project_data["detection_zones"] = self._zone_data_to_dict(ZoneData())

        self._update_video_zone_flags(video_path, None)
        self._refresh_last_zone_source(removed_path=video_path)

        if persist:
            self.save_project()

    def clone_zone_data_from_video(self, video_path: Path | str) -> ZoneData:
        """Return a deep copy of zone data stored for another video."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)

        _, stored = self._resolve_zone_entry(video_path)
        return self._zone_data_from_dict(stored)

    def export_zones_to_parquet(
        self,
        video_path: Path | str,
        zone_data: ZoneData,
    ) -> dict[str, str]:
        """Export zone data (arena and ROIs) to parquet files.

        Args:
            video_path: Path to the video file.
            zone_data: ZoneData object to export.

        Returns:
            Dictionary mapping asset type ('arena', 'rois') to generated file path.
        """
        import pandas as pd

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        exported = {}

        if not self.project_path:
            return exported

        # Resolve destination directory
        video_stem = Path(video_path).stem
        video_entry = self.find_video_entry(path=video_path)
        metadata_hint = video_entry.get("metadata") if video_entry else None
        
        results_dir = self.resolve_results_directory(
            video_stem,
            video_path=video_path,
            metadata=metadata_hint,
        )
        results_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export Arena
        if zone_data.polygon:
            arena_df = pd.DataFrame(zone_data.polygon, columns=["x", "y"])
            arena_path = results_dir / f"1_ProcessingArea_{video_stem}.parquet"
            arena_df.to_parquet(arena_path)
            exported["arena"] = str(arena_path)

        # 2. Export ROIs
        if zone_data.roi_polygons and zone_data.roi_names:
            roi_data = []
            for name, poly in zip(zone_data.roi_names, zone_data.roi_polygons):
                for idx, point in enumerate(poly):
                    roi_data.append({
                        "roi_name": name,
                        "point_index": idx,
                        "x": point[0],
                        "y": point[1]
                    })
            
            if roi_data:
                rois_df = pd.DataFrame(roi_data)
                rois_path = results_dir / f"2_AreasOfInterest_{video_stem}.parquet"
                rois_df.to_parquet(rois_path)
                exported["rois"] = str(rois_path)

        return exported

    def copy_zone_parquet_files(
        self,
        source_video_path: Path | str,
        target_video_path: Path | str,
        *,
        persist: bool = True,
    ) -> dict[str, str]:
        """Copy arena/ROI parquet files from one video to another.

        Returns a mapping with the copied parquet types and their new paths.
        """
        # Force sync of source video to ensure files are registered
        # This triggers the "self-healing" logic if files exist on disk but not in memory
        self.set_active_zone_video(source_video_path)

        source_video_path = str(
            Path(source_video_path) if isinstance(source_video_path, str) else source_video_path
        )
        target_video_path = str(
            Path(target_video_path) if isinstance(target_video_path, str) else target_video_path
        )

        copied: dict[str, str] = {}

        if not source_video_path or not target_video_path:
            return copied

        scan_results = self.scan_input_paths([source_video_path])
        if not scan_results:
            log.info(
                "project_manager.zones.copy_missing_source_scan",
                source=source_video_path,
            )
            return copied

        parquet_files: dict[str, str] = scan_results[0].get("parquet_files", {})
        
        # Enrich with registered files if missing (Fix for hierarchical project structure)
        if not parquet_files.get("arena") or not parquet_files.get("rois"):
            source_entry = self.find_video_entry(path=source_video_path)
            if source_entry:
                registered = source_entry.get("parquet_files", {})
                if registered:
                    parquet_files.update(registered)

        if not parquet_files:
            log.info(
                "project_manager.zones.copy_no_parquets",
                source=source_video_path,
            )
            return copied

        target_path = Path(target_video_path)

        target_stem = target_path.stem

        target_parent = target_path.parent
        target_parent.mkdir(parents=True, exist_ok=True)

        filename_map = {
            "arena": f"1_ProcessingArea_{target_stem}.parquet",
            "rois": f"2_AreasOfInterest_{target_stem}.parquet",
        }

        target_video_entry = self.find_video_entry(path=target_video_path)
        metadata_hint: dict | None = None
        if target_video_entry:
            metadata_hint = dict(target_video_entry.get("metadata") or {})
            for key in ("group", "group_display_name", "day", "subject"):
                if (
                    key in target_video_entry
                    and key not in metadata_hint
                    and target_video_entry[key] is not None
                ):
                    metadata_hint[key] = target_video_entry[key]

        hierarchical_results_dir = self.resolve_results_directory(
            target_stem,
            video_path=target_video_path,
            metadata=metadata_hint,
        )

        updated_video_entry = False

        for key, target_filename in filename_map.items():
            source_file = parquet_files.get(key)
            if not source_file:
                continue

            source_file_path = Path(source_file)
            if not source_file_path.exists():
                log.warning(
                    "project_manager.zones.copy_source_missing",
                    file=source_file,
                    key=key,
                )
                continue

            destination_dirs: list[Path] = [target_parent]

            if hierarchical_results_dir:
                destination_dirs.append(Path(hierarchical_results_dir))

            for dest_dir in destination_dirs:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file_path = Path(dest_dir) / target_filename
                try:
                    shutil.copy2(source_file_path, dest_file_path)
                    copied[key] = str(dest_file_path)
                    log.info(
                        "project_manager.zones.copy_success",
                        source=source_file_path,
                        destination=dest_file_path,
                    )
                    updated_video_entry = True
                except (OSError, PermissionError) as exc:  # pragma: no cover - defensive
                    log.error(
                        "project_manager.zones.copy_failed",
                        source=source_file_path,
                        destination=dest_file_path,
                        error=str(exc),
                    )
                    # Non-fatal: continue processing other files

        if updated_video_entry and copied:
            video_entry = target_video_entry or self.find_video_entry(path=target_video_path)
            if video_entry is not None:
                parquet_map = video_entry.setdefault("parquet_files", {})
                parquet_map.update(copied)
                
                # Critical Fix: Update status flags so analysis sees the data
                if "arena" in copied:
                    video_entry["has_arena"] = True
                if "rois" in copied:
                    video_entry["has_rois"] = True
                
                # Reset zones_finalized to force re-evaluation if needed
                video_entry["zones_finalized"] = False

        if persist and updated_video_entry:
            self.save_project()

        return copied

    @staticmethod
    def scan_input_paths(paths: list[str]) -> list[dict]:
        """Scan input paths for videos. Delegates to VideoManager."""
        return VideoManager.scan_input_paths(paths)

    @classmethod
    def clear_scan_cache(cls, target_path: Path | str | None = None) -> None:
        """Clear video scan cache. Delegates to VideoManager."""
        VideoManager.clear_scan_cache(target_path)

    @staticmethod
    def load_zones_from_parquet(video_info: dict) -> ZoneData | None:
        """
        Load zone data (arena and ROIs) from existing parquet files.

        Args:
            video_info: Dictionary returned by scan_input_paths containing
                       'parquet_files' with paths to arena and ROI files.

        Returns:
            ZoneData object with loaded zones, or None if loading failed.
        """
        import pandas as pd  # Lazy import to avoid loading pandas during startup

        parquet_files = video_info.get("parquet_files", {})
        arena_path = parquet_files.get("arena")
        rois_path = parquet_files.get("rois")

        if not arena_path and not rois_path:
            log.warning(
                "project_manager.load_zones.no_files",
                video=video_info.get("path"),
            )
            return None

        zone_data = ZoneData()

        try:
            # Load arena polygon
            if arena_path and os.path.exists(arena_path):
                arena_df = pd.read_parquet(arena_path)
                if not arena_df.empty and "x" in arena_df.columns and "y" in arena_df.columns:
                    polygon_points = arena_df[["x", "y"]].values.tolist()
                    zone_data.polygon = polygon_points
                    log.info(
                        "project_manager.load_zones.arena_loaded",
                        path=arena_path,
                        points=len(polygon_points),
                    )
                else:
                    log.warning(
                        "project_manager.load_zones.arena_empty",
                        path=arena_path,
                    )

            # Load ROIs
            if rois_path and os.path.exists(rois_path):
                rois_df = pd.read_parquet(rois_path)
                if not rois_df.empty:
                    required_cols = {"roi_name", "point_index", "x", "y"}
                    if required_cols.issubset(rois_df.columns):
                        # Group by ROI name and reconstruct polygons
                        roi_polygons = []
                        roi_names = []

                        for roi_name in rois_df["roi_name"].unique():
                            roi_df = rois_df[rois_df["roi_name"] == roi_name].sort_values(
                                "point_index"
                            )
                            roi_points = roi_df[["x", "y"]].values.tolist()
                            roi_polygons.append(roi_points)
                            roi_names.append(roi_name)

                        zone_data.roi_polygons = roi_polygons
                        zone_data.roi_names = roi_names

                        # Generate default colors if not provided
                        # (actual colors are not stored in parquet, using defaults)
                        default_colors = [
                            (0, 128, 0),  # Green
                            (255, 0, 0),  # Blue
                            (0, 0, 255),  # Red
                            (255, 255, 0),  # Cyan
                            (255, 0, 255),  # Magenta
                            (0, 204, 204),  # Darker Yellow (was 0, 255, 255)
                        ]
                        zone_data.roi_colors = [
                            default_colors[i % len(default_colors)] for i in range(len(roi_names))
                        ]

                        log.info(
                            "project_manager.load_zones.rois_loaded",
                            path=rois_path,
                            count=len(roi_names),
                            names=roi_names,
                        )
                    else:
                        log.warning(
                            "project_manager.load_zones.rois_invalid_schema",
                            path=rois_path,
                            columns=list(rois_df.columns),
                        )
                else:
                    log.warning(
                        "project_manager.load_zones.rois_empty",
                        path=rois_path,
                    )

            return zone_data

        except OSError as e:
            log.error(
                "project_manager.load_zones.io_error",
                video=video_info.get("path"),
                error=str(e),
                exc_info=True,
            )
            return None
        except (ValueError, KeyError) as e:
            log.error(
                "project_manager.load_zones.data_error",
                video=video_info.get("path"),
                error=str(e),
                exc_info=True,
            )
            return None
        except Exception as e:
            # Catch pandas parquet errors and other unforeseen issues
            log.error(
                "project_manager.load_zones.unexpected_error",
                video=video_info.get("path"),
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return None

    def import_parquets_from_wizard(
        self,
        import_config: list[dict],
        roi_merge_strategy: str = "replace",
        scanned_videos: list[dict] | None = None,
    ) -> bool:
        """
        Import arena, ROIs, and trajectory data from existing parquet files.

        This method is called after project creation to import data from parquet files
        based on the wizard's import configuration.

        Args:
            import_config: List of per-video import configurations from wizard.

                Example::

                    [
                        {
                            "video": str,
                            "import_arena": bool,
                            "import_rois": bool,
                            "import_trajectory": bool,
                            "action": str,
                        },
                        ...
                    ]

            roi_merge_strategy: How to handle ROI conflicts:

                - "replace": Replace existing ROIs with imported ones
                - "merge": Keep both, rename conflicts with "_imported" suffix
                - "manual": Ask user for each conflict (future implementation)

            scanned_videos: List of scanned video info (from wizard) containing
                parquet file paths. If None, will re-scan paths.

        Returns:
            bool: True if import succeeded, False otherwise
        """
        if not self.project_data:
            log.error("project_manager.import_parquets.no_project")
            return False

        if not import_config:
            log.info("project_manager.import_parquets.no_config")
            return True  # Nothing to import is not an error

        log.info(
            "project_manager.import_parquets.start",
            video_count=len(import_config),
            roi_strategy=roi_merge_strategy,
        )

        # Build lookup from video path to parquet info
        video_parquet_map = {}
        if scanned_videos:
            for video_info in scanned_videos:
                video_parquet_map[video_info["path"]] = video_info.get("parquet_files", {})

        imported_count = {"arena": 0, "rois": 0, "trajectory": 0}

        try:
            for config in import_config:
                # Delegate per-video import processing to a helper to reduce complexity
                per_counts = self._process_single_parquet_import(
                    config, video_parquet_map, roi_merge_strategy
                )
                for k, v in per_counts.items():
                    imported_count[k] += v

            # Save updated zone data to project
            self.save_project()

            log.info(
                "project_manager.import_parquets.success",
                arena_count=imported_count["arena"],
                roi_count=imported_count["rois"],
                trajectory_count=imported_count["trajectory"],
            )
            return True

        except ProjectInvalidError as e:
            log.error(
                "project_manager.import_parquets.save_error",
                error=str(e),
                exc_info=True,
            )
            return False
        except (OSError, ValueError, KeyError) as e:
            log.error(
                "project_manager.import_parquets.data_error",
                error=str(e),
                exc_info=True,
            )
            return False
        except Exception as e:
            # Catch pandas parquet errors and other unforeseen issues
            log.error(
                "project_manager.import_parquets.unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return False

    def _process_single_parquet_import(
        self, config: dict, video_parquet_map: dict, roi_merge_strategy: str
    ) -> dict:
        """Process a single video import configuration and return counts.

        Returns a dict with keys: arena, rois, trajectory (counts)
        """
        import pandas as pd  # Lazy import to avoid loading pandas during startup

        counts = {"arena": 0, "rois": 0, "trajectory": 0}

        video_path = config.get("video")
        import_arena = config.get("import_arena", False)
        import_rois = config.get("import_rois", False)
        import_trajectory = config.get("import_trajectory", False)

        if not video_path:
            log.warning("project_manager.import_parquets.invalid_video_path", config=config)
            return counts

        if not any([import_arena, import_rois, import_trajectory]):
            return counts

        parquet_files = video_parquet_map.get(video_path, {})
        if not parquet_files:
            log.warning("project_manager.import_parquets.no_parquets", video=Path(video_path).name)
            return counts

        zone_data = self.get_zone_data(video_path=video_path, fallback_to_global=False)

        # Arena import
        if import_arena:
            arena_path = parquet_files.get("arena")
            if arena_path and os.path.exists(arena_path):
                arena_df = pd.read_parquet(arena_path)
                if not arena_df.empty and "x" in arena_df.columns and "y" in arena_df.columns:
                    polygon_points = arena_df[["x", "y"]].values.tolist()
                    zone_data.polygon = polygon_points
                    counts["arena"] += 1
                    log.info(
                        "project_manager.import_parquets.arena_imported",
                        video=Path(video_path).name,
                        points=len(polygon_points),
                    )

        # ROIs import
        if import_rois:
            rois_path = parquet_files.get("rois")
            if rois_path and os.path.exists(rois_path):
                rois_df = pd.read_parquet(rois_path)
                if not rois_df.empty:
                    required_cols = {"roi_name", "point_index", "x", "y"}
                    if required_cols.issubset(rois_df.columns):
                        imported_roi_polygons = []
                        imported_roi_names = []

                        for roi_name in rois_df["roi_name"].unique():
                            roi_df = rois_df[rois_df["roi_name"] == roi_name].sort_values(
                                "point_index"
                            )
                            roi_points = roi_df[["x", "y"]].values.tolist()
                            imported_roi_polygons.append(roi_points)
                            imported_roi_names.append(roi_name)

                        if roi_merge_strategy == "replace":
                            zone_data.roi_polygons = imported_roi_polygons
                            zone_data.roi_names = imported_roi_names
                        elif roi_merge_strategy == "merge":
                            existing_names = set(zone_data.roi_names)
                            for roi_poly, roi_name in zip(
                                imported_roi_polygons, imported_roi_names, strict=False
                            ):
                                final_name = roi_name
                                if roi_name in existing_names:
                                    counter = 1
                                    while f"{roi_name}_imported{counter}" in existing_names:
                                        counter += 1
                                    final_name = f"{roi_name}_imported{counter}"
                                    log.info(
                                        "project_manager.import_parquets.roi_renamed",
                                        original=roi_name,
                                        renamed=final_name,
                                    )

                                zone_data.roi_polygons.append(roi_poly)
                                zone_data.roi_names.append(final_name)
                                existing_names.add(final_name)
                        else:
                            log.warning(
                                "project_manager.import_parquets.manual_strategy_not_implemented",
                                fallback="replace",
                            )
                            zone_data.roi_polygons = imported_roi_polygons
                            zone_data.roi_names = imported_roi_names

                        default_colors = [
                            (0, 128, 0),
                            (255, 0, 0),
                            (0, 0, 255),
                            (0, 204, 204),
                            (255, 0, 255),
                            (0, 204, 204),
                        ]
                        zone_data.roi_colors = [
                            default_colors[i % len(default_colors)]
                            for i in range(len(zone_data.roi_names))
                        ]

                        counts["rois"] += len(imported_roi_names)
                        log.info(
                            "project_manager.import_parquets.rois_imported",
                            video=Path(video_path).name,
                            count=len(imported_roi_names),
                            names=imported_roi_names,
                            strategy=roi_merge_strategy,
                        )

        # Persist zone data in memory for this video
        self.save_zone_data(zone_data, video_path, persist=False)

        # Trajectory import
        if import_trajectory := config.get("import_trajectory", False):
            trajectory_path = parquet_files.get("trajectory")
            if trajectory_path and os.path.exists(trajectory_path):
                video_name = Path(video_path).stem
                if not self.project_path:
                    log.warning("project_manager.import_parquets.no_project_path", video=video_name)
                    return counts

                results_dir = self.resolve_results_directory(video_name, video_path=video_path)
                results_dir.mkdir(parents=True, exist_ok=True)
                dest_path = results_dir / f"3_CoordMovimento_{video_name}.parquet"

                import shutil

                shutil.copy2(trajectory_path, dest_path)

                counts["trajectory"] += 1
                log.info(
                    "project_manager.import_parquets.trajectory_imported",
                    video=video_name,
                    source=trajectory_path,
                    dest=str(dest_path),
                )

        return counts

    def _save_settings_snapshot(self):
        """Save a snapshot of the current settings to the project directory."""
        if not self.project_path:
            return False

        snapshot_path = os.path.join(self.project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            # Use model_dump with proper serialization to ensure YAML compatibility
            import json

            # Check if settings is available and is a real settings object (not a mock)
            if self.settings is None:
                log.debug("settings.snapshot.skipped", reason="settings not injected")
                return True  # Return True to not block project creation in tests

            if not hasattr(self.settings, "model_dump_json") or not callable(
                self.settings.model_dump_json
            ):
                log.debug("settings.snapshot.skipped", reason="settings not available or mocked")
                return True  # Return True to not block project creation in tests

            json_str = self.settings.model_dump_json()
            # Verify it's actually a string (not a mock)
            if not isinstance(json_str, str):
                log.debug("settings.snapshot.skipped", reason="model_dump_json returned non-string")
                return True

            settings_dict = json.loads(json_str)
            with open(snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(settings_dict, f, indent=4, sort_keys=False)
            log.info("settings.snapshot.saved", path=snapshot_path)
            return True
        except (OSError, TypeError, ValueError) as e:
            log.error("settings.snapshot.save_error", error=str(e))
            return False

    def _validate_project_parameters(
        self,
        num_aquariums: int,
        animals_per_aquarium: int,
        aquarium_width_cm: float,
        aquarium_height_cm: float,
        analysis_interval_frames: int,
        display_interval_frames: int,
        camera_index: int,
        project_type: str,
        video_files: list | None,
    ) -> None:
        """Validate project creation parameters.

        Phase 3.3: Extracted from create_new_project to reduce complexity (C901).
        Validation bounds match Pydantic models in ui/wizard/models.py.

        Args:
            num_aquariums: Number of aquariums/arenas
            animals_per_aquarium: Number of animals per aquarium
            aquarium_width_cm: Aquarium width in cm (0 = no calibration)
            aquarium_height_cm: Aquarium height in cm (0 = no calibration)
            analysis_interval_frames: Detection interval in frames
            display_interval_frames: Overlay update interval in frames
            camera_index: Camera device index
            project_type: Type of project ("Pre-recorded" or "Live")
            video_files: Optional list of video files

        Raises:
            ValueError: If any parameter is invalid.
        """
        # Validate aquarium count
        if num_aquariums < 1:
            raise ValueError("num_aquariums deve ser >= 1")
        if num_aquariums > 100:
            raise ValueError("num_aquariums deve ser <= 100 (limite prático)")

        # Validate animals per aquarium
        if animals_per_aquarium < 1:
            raise ValueError("animals_per_aquarium deve ser >= 1")
        if animals_per_aquarium > 100:
            raise ValueError("animals_per_aquarium deve ser <= 100 (limite prático)")

        # Phase 1.2: Calibration dimensions - 0 means "no calibration", which is valid
        if aquarium_width_cm < 0:
            raise ValueError("aquarium_width_cm deve ser >= 0 (0 = sem calibração)")
        if aquarium_width_cm > 500:
            raise ValueError("aquarium_width_cm deve ser <= 500 cm (valor irreal)")

        if aquarium_height_cm < 0:
            raise ValueError("aquarium_height_cm deve ser >= 0 (0 = sem calibração)")
        if aquarium_height_cm > 500:
            raise ValueError("aquarium_height_cm deve ser <= 500 cm (valor irreal)")

        # Validate frame intervals
        if analysis_interval_frames < 1:
            raise ValueError("analysis_interval_frames deve ser >= 1")
        if analysis_interval_frames > 30:
            raise ValueError("analysis_interval_frames deve ser <= 30")

        if display_interval_frames < 1:
            raise ValueError("display_interval_frames deve ser >= 1")
        if display_interval_frames > 30:
            raise ValueError("display_interval_frames deve ser <= 30")

        # Validate camera index
        if camera_index < 0:
            raise ValueError("camera_index deve ser >= 0")
        if camera_index > 10:
            raise ValueError("camera_index deve ser <= 10 (limite de dispositivos)")

        # Validate project type (case-insensitive)
        valid_types = ["Pre-recorded", "Live"]
        if not any(project_type.lower() == vt.lower() for vt in valid_types):
            raise ValueError(
                f"project_type deve ser um de: {', '.join(valid_types)}\nRecebido: {project_type}"
            )

    def create_new_project(
        self,
        project_path: Path | str,
        project_type,
        use_openvino=False,
        active_weight=None,
        video_files=None,
        num_aquariums: int = 1,
        animals_per_aquarium: int = 1,
        aquarium_width_cm: float = 0.0,
        aquarium_height_cm: float = 0.0,
        use_timed_recording: bool = False,
        recording_duration_s: int = 0,
        use_countdown: bool = False,
        countdown_duration_s: int = 0,
        use_single_subject_tracker: bool | None = None,
        analysis_interval_frames: int = 10,
        display_interval_frames: int = 10,
        camera_index: int = 0,
        use_arduino: bool = False,
        arduino_port: str = "",
        external_trigger_mode: bool = False,
        # New live project params
        experiment_days: int | None = None,
        subjects_per_group: int | None = None,
        num_groups: int | None = None,
        group_names: list[str] | None = None,
        # Wizard metadata
        _wizard_metadata: dict | None = None,
    ):
        """
        Initialize a new project, creating its directory and config file.

        It no longer handles OpenVINO conversion, just records the settings.
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        self.project_path = project_path
        log_context = log.bind(
            project_path=project_path,
            project_type=project_type,
            use_openvino=use_openvino,
            active_weight=active_weight,
            num_aquariums=num_aquariums,
            animals_per_aquarium=animals_per_aquarium,
        )
        log_context.info("project.create.start")

        # Phase 3: Validate all parameters (extracted to reduce complexity)
        self._validate_project_parameters(
            num_aquariums=num_aquariums,
            animals_per_aquarium=animals_per_aquarium,
            aquarium_width_cm=aquarium_width_cm,
            aquarium_height_cm=aquarium_height_cm,
            analysis_interval_frames=analysis_interval_frames,
            display_interval_frames=display_interval_frames,
            camera_index=camera_index,
            project_type=project_type,
            video_files=video_files,
        )

        # Note: Video file existence is NOT validated during project creation to allow:
        # 1. Projects with placeholder paths (used in tests and workflows)
        # 2. Videos to be added later after project creation
        # 3. Paths to be resolved dynamically
        # File existence is validated when videos are actually processed.

        try:
            os.makedirs(self.project_path, exist_ok=True)
        except OSError as e:
            log.error("project.create.dir_error", error=str(e))
            raise ProjectInvalidError(
                message=f"Não foi possível criar o diretório do projeto: {e}\n\n"
                "Por favor, verifique as permissões da pasta e se o caminho é válido.",
                path=self.project_path,
                cause=e,
            ) from e

        self._save_settings_snapshot()

        safe_camera_index = camera_index if camera_index is not None else 0
        safe_use_arduino = bool(use_arduino)
        safe_arduino_port = arduino_port or ""
        safe_external_trigger = bool(external_trigger_mode) and safe_use_arduino
        if use_single_subject_tracker is None:
            # Use settings if available, otherwise default to False
            default_tracker = False
            if self.settings and hasattr(self.settings, "tracking"):
                default_tracker = bool(self.settings.tracking.use_single_subject_tracker)
            tracker_pref = animals_per_aquarium == 1 or default_tracker
        else:
            tracker_pref = bool(use_single_subject_tracker)

        self.project_data = {
            "project_name": os.path.basename(project_path),
            "project_type": project_type,
            "calibration": {
                "num_aquariums": num_aquariums,
                "animals_per_aquarium": animals_per_aquarium,
                "aquarium_width_cm": aquarium_width_cm,
                "aquarium_height_cm": aquarium_height_cm,
            },
            "use_openvino": use_openvino,
            "active_weight": active_weight,
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
            },
            "use_timed_recording": use_timed_recording,
            "recording_duration_s": recording_duration_s,
            "use_countdown": use_countdown,
            "countdown_duration_s": countdown_duration_s,
            "batches": [],  # Changed from "videos" to "batches"
            "groups": group_names if group_names else [],
            "num_groups": num_groups,
            "experiment_days": experiment_days,
            "subjects_per_group": subjects_per_group,
            "last_selected_day": 1,
            "last_selected_group": group_names[0] if group_names else None,
            "analysis_interval_frames": analysis_interval_frames,
            "display_interval_frames": display_interval_frames,
            "camera_index": safe_camera_index,
            "use_arduino": safe_use_arduino,
            "arduino_port": safe_arduino_port,
            "external_trigger_mode": safe_external_trigger,
            "tracking": {
                "use_single_subject_tracker": tracker_pref,
            },
            "detection_zones": {},
            "zones_by_video": {},
            "analysis_profiles": [self.asset_manager._default_analysis_profile()],
            "roi_templates": [],
        }

        # Add wizard metadata if provided (from wizard v1.5+)
        if _wizard_metadata:
            self.project_data["_wizard_metadata"] = _wizard_metadata

        if video_files:
            # The initial set of videos becomes the first batch
            self.add_video_batch(video_files, save_project=False)

        self.save_project()
        log_context.info("project.create.success")

    def add_video_batch(self, video_files: list[dict], save_project: bool = True):
        """
        Add a new batch of videos to the project.

        Args:
            video_files: A list of video dicts from scan_input_paths.
            save_project: Whether to save the project file after adding.
        """
        if not video_files:
            return

        new_batch = {
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
            else:
                video_path = video_path

            video_hash = calculate_sha256(video_path)

            for key in ("group", "group_display_name", "day", "subject"):
                value = video_info.get(key)
                if value is not None and (value != "" or isinstance(value, (int, float))):
                    metadata.setdefault(key, value)

            # Remove empty values to keep JSON compact
            metadata = {
                key: value
                for key, value in metadata.items()
                if value is not None and (value != "" or isinstance(value, (int, float)))
            }

            video_entry = {
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

        self.project_data.setdefault("batches", []).append(new_batch)

        metadata_count = sum(1 for v in new_batch["videos"] if "metadata" in v)
        arena_count = sum(1 for v in new_batch["videos"] if v.get("has_arena"))
        trajectory_count = sum(1 for v in new_batch["videos"] if v.get("has_trajectory"))

        log.info(
            "project.batch.added",
            count=len(video_files),
            with_metadata=metadata_count,
            with_arena=arena_count,
            with_trajectory=trajectory_count,
        )

        if save_project:
            self.save_project()

    def _apply_project_migrations(
        self, loaded_data: dict, log_context
    ) -> tuple[dict, bool, list[str]]:
        """Apply backward compatibility migrations to loaded project data.

        Returns:
            Tuple of (migrated_data, migration_applied, migrated_fields)
        """
        migration_applied = False
        migrated_fields: list[str] = []

        if (
            "calibration" in loaded_data
            and "animals_per_aquarium" not in loaded_data["calibration"]
        ):
            loaded_data["calibration"]["animals_per_aquarium"] = 1
            migration_applied = True
            migrated_fields.append("calibration.animals_per_aquarium")
            log_context.info(
                "project.load.backward_compatibility",
                message=("Added missing animals_per_aquarium field with default value 1"),
            )

        # Add defaults for legacy projects missing interval/camera/arduino fields
        if "analysis_interval_frames" not in loaded_data:
            loaded_data["analysis_interval_frames"] = 10
            migration_applied = True
            migrated_fields.append("analysis_interval_frames")

        if "display_interval_frames" not in loaded_data:
            loaded_data["display_interval_frames"] = 10
            migration_applied = True
            migrated_fields.append("display_interval_frames")

        if "analysis_profiles" not in loaded_data or not loaded_data.get("analysis_profiles"):
            loaded_data["analysis_profiles"] = [self.asset_manager._default_analysis_profile()]
            migration_applied = True
            migrated_fields.append("analysis_profiles")

        # Use settings if available, otherwise default to False
        tracker_flag = False
        if self.settings and hasattr(self.settings, "tracking"):
            tracker_flag = self.settings.tracking.use_single_subject_tracker
        tracking_defaults = {"use_single_subject_tracker": tracker_flag}
        if "tracking" not in loaded_data or not isinstance(loaded_data.get("tracking"), dict):
            loaded_data["tracking"] = dict(tracking_defaults)
            migration_applied = True
            migrated_fields.append("tracking")
        else:
            existing_tracking = loaded_data["tracking"]
            if (
                "use_single_subject_tracker" not in existing_tracking
                or existing_tracking["use_single_subject_tracker"] is None
            ):
                existing_tracking["use_single_subject_tracker"] = tracking_defaults[
                    "use_single_subject_tracker"
                ]
                migration_applied = True
                migrated_fields.append("tracking.use_single_subject_tracker")

        if "roi_templates" not in loaded_data or not isinstance(
            loaded_data.get("roi_templates"), list
        ):
            loaded_data["roi_templates"] = []
            migration_applied = True
            migrated_fields.append("roi_templates")

        if "camera_index" not in loaded_data or loaded_data["camera_index"] is None:
            loaded_data["camera_index"] = 0
            migration_applied = True
            migrated_fields.append("camera_index")

        if "use_arduino" not in loaded_data or loaded_data["use_arduino"] is None:
            loaded_data["use_arduino"] = False
            migration_applied = True
            migrated_fields.append("use_arduino")

        if "arduino_port" not in loaded_data or loaded_data["arduino_port"] is None:
            loaded_data["arduino_port"] = ""
            migration_applied = True
            migrated_fields.append("arduino_port")

        if (
            "external_trigger_mode" not in loaded_data
            or loaded_data["external_trigger_mode"] is None
        ):
            loaded_data["external_trigger_mode"] = False
            migration_applied = True
            migrated_fields.append("external_trigger_mode")

        overrides = loaded_data.get("model_overrides")
        overrides_updated = False
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None}
            overrides_updated = True
        else:
            if "active_weight" not in overrides:
                overrides["active_weight"] = None
                overrides_updated = True
            if "use_openvino" not in overrides:
                overrides["use_openvino"] = None
                overrides_updated = True

        if overrides_updated:
            loaded_data["model_overrides"] = overrides
            migration_applied = True
            migrated_fields.append("model_overrides")

        # Add file_hash for legacy projects that don't have it
        if "file_hash" not in loaded_data:
            loaded_data["file_hash"] = {}
            migration_applied = True
            migrated_fields.append("file_hash")

        return loaded_data, migration_applied, migrated_fields

    @_threadsafe
    def load_project(self, project_path: Path | str):
        """
        Load project data from a config file in the given directory.

        Phase 1, Step 3: Delegates file I/O to ProjectService.
        Task 2.2: Thread-safe via @_threadsafe decorator.
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        log_context = log.bind(path=config_path)
        log_context.info("project.load.start")

        if not os.path.exists(config_path):
            log_context.error("project.load.not_found")
            raise ProjectInvalidError(
                message=f"Arquivo de configuração do projeto '{CONFIG_FILE_NAME}' não "
                f"encontrado no diretório selecionado: {project_path}\n\n"
                "Por favor, garanta que você selecionou uma pasta de projeto válida.",
                path=project_path,
            )

        try:
            # Phase 1, Step 3: Delegate to ProjectService for file I/O
            loaded_data = self.project_service.load_project_config(project_path)

            # Apply backward compatibility migrations
            loaded_data, migration_applied, migrated_fields = self._apply_project_migrations(
                loaded_data, log_context
            )

            self.project_path = project_path
            self.project_data = loaded_data

            if migration_applied:
                log_context.info(
                    "project.load.migration_applied",
                    fields=migrated_fields,
                )
                self.save_project()
            self.load_metadata()  # Load metadata right after loading the project
            log_context.info(
                "project.load.success",
                project_name=self.project_data.get("project_name"),
            )
        except (OSError, json.JSONDecodeError, IntegrityError) as e:
            log_context.error("project.load.error", exc_info=e)
            raise ProjectInvalidError(
                message=f"Falha ao carregar ou analisar o arquivo de configuração do projeto: "
                f"{config_path}\n\nO arquivo pode estar corrompido ou ilegível.\n\nErro: {e}",
                path=project_path,
                cause=e,
            ) from e

    @_threadsafe
    def save_project(self) -> None:
        """
        Save the current project data to the config file with an integrity hash.

        Phase 1, Step 3: Delegates file I/O to ProjectService.
        Task 2.2: Thread-safe via @_threadsafe decorator.

        Raises:
            ProjectInvalidError: If project path is not set or save operation fails.
        """
        # Critical Fix #5: Add validation before saving
        if not self.project_path:
            log.debug("project.save.no_path", reason="project not yet created")
            raise ProjectInvalidError(
                message="Não é possível salvar o projeto: caminho do projeto não definido.\n\n"
                "O projeto deve ser criado antes de ser salvo.",
            )

        try:
            # Delegate to ProjectService for file I/O
            self.project_service.save_project_config(self.project_path, self.project_data)

            log.info("project.save.success", path=self.project_path)
        except PermissionError as e:
            log.error("project.save.permission_denied", path=self.project_path, exc_info=e)
            raise ProjectInvalidError(
                message=(
                    f"Permissão negada ao salvar o projeto: {self.project_path}\n\n"
                    f"Verifique se você tem permissão de escrita na pasta.\n\nErro: {e}"
                ),
                path=self.project_path,
                cause=e,
            ) from e
        except OSError as e:
            log.error("project.save.io_error", path=self.project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro de I/O ao salvar o projeto: "
                f"{self.project_path}\n\nVerifique o espaço em disco e permissões.\n\nErro: {e}",
                path=self.project_path,
                cause=e,
            ) from e
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.error("project.save.serialization_error", path=self.project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro ao serializar dados do projeto: "
                f"{self.project_path}\n\nDados do projeto podem estar corrompidos.\n\nErro: {e}",
                path=self.project_path,
                cause=e,
            ) from e
        except Exception as e:
            log.error("project.save.unexpected_error", path=self.project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro inesperado ao salvar o projeto: "
                f"{self.project_path}\n\nPor favor, verifique as permissões da pasta.\n\nErro: {e}",
                path=self.project_path,
                cause=e,
            ) from e

    def _default_analysis_profile(self) -> dict:
        """Return the default analysis profile. Delegates to AssetManager."""
        return self.asset_manager._default_analysis_profile()

    def get_analysis_profiles(self) -> list[dict]:
        """Get analysis profiles. Delegates to AssetManager."""
        return self.asset_manager.get_analysis_profiles(self.project_data)

    def resolve_analysis_profile(self, metadata: dict | None) -> dict:
        """Resolve analysis profile for metadata. Delegates to AssetManager."""
        return self.asset_manager.resolve_analysis_profile(self.project_data, metadata)

    def update_video_status(self, video_path: Path | str, new_status) -> bool:
        """
        Update the status of a specific video across all batches and saves the project.

        Returns:
            bool: True if video was found and updated, False otherwise.
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        video_path_str = str(video_path)
        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video["path"] == video_path_str:
                    video["status"] = new_status
                    log.info(
                        "video.status.update",
                        video_path=video_path,
                        status=new_status,
                    )
                    self.save_project()
                    return True
        return False

    def reset_all_video_statuses(self, to_status: str = "pending"):
        """Reset every video status to a given value (default 'pending')."""
        changed = False
        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video.get("status") != to_status:
                    video["status"] = to_status
                    changed = True
        if changed:
            log.info("video.status.reset_all", to_status=to_status)
            self.save_project()
        return changed

    def get_all_videos(self) -> list[dict]:
        """Return a flat list of all videos from all batches. Delegates to VideoManager."""
        return VideoManager.get_all_videos(self.project_data)

    def _iter_project_videos(self):
        """
        Yield (batch_dict, video_dict) pairs for every registered video.

        Delegates to VideoManager.
        """
        return VideoManager.iter_project_videos(self.project_data)

    def _video_has_asset(self, video_entry: dict, asset: AssetType) -> bool:
        """Check if video has asset. Delegates to AssetManager."""
        return AssetManager.video_has_asset(video_entry, asset)

    @staticmethod
    def _refresh_complete_flag(video_entry: dict) -> None:
        """Refresh complete data flag. Delegates to VideoManager."""
        VideoManager.refresh_complete_flag(video_entry)

    def _delete_file_if_exists(self, path: Path | str | None) -> bool:
        """Delete file if exists. Delegates to AssetManager."""
        return AssetManager.delete_file_if_exists(path)

    def can_remove_asset(self, video_path: Path | str, asset: AssetType) -> tuple[bool, str | None]:
        """Check if an asset can be removed from a video entry.

        Validates removal dependencies to ensure integrity of project data.

        Args:
            video_path: Path to the video file.
            asset: Type of asset to remove (arena, rois, trajectory, summary, video).

        Returns:
            Tuple of (can_remove, error_message). If can_remove is True, error_message is None.
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = self.find_video_entry(path=video_path)
        if not video_entry:
            return False, "Vídeo não encontrado no projeto."

        has_summary_outputs = self._video_has_asset(video_entry, "summary")

        if asset in {"arena", "rois", "trajectory"}:
            if has_summary_outputs:
                return (
                    False,
                    ("Remova os relatórios e sumários antes de apagar arena, ROIs ou trajetórias."),
                )
            if not self._video_has_asset(video_entry, asset):
                labels = {
                    "arena": "arena",
                    "rois": "ROIs",
                    "trajectory": "trajetória",
                }
                missing_label = labels.get(asset, asset)
                return False, f"Não há {missing_label} registrada para este vídeo."

        if asset == "summary" and not has_summary_outputs:
            return False, "Não há relatórios ou sumários para remover."

        if asset == "video":
            if has_summary_outputs:
                return False, "Remova relatórios e sumários antes de excluir o vídeo."
            if any(
                self._video_has_asset(video_entry, dependency)
                for dependency in ("trajectory", "rois", "arena")
            ):
                return (
                    False,
                    ("Remova arena, ROIs e trajetórias antes de excluir o vídeo do projeto."),
                )

        return True, None

    def remove_asset(
        self,
        video_path: Path | str,
        asset: AssetType,
        *,
        delete_files: bool = True,
    ) -> bool:
        """Remove an asset from a video entry and optionally delete associated files.

        Args:
            video_path: Path to the video file.
            asset: Type of asset to remove.
            delete_files: If True, delete associated files from disk.

        Returns:
            True if asset was successfully removed, False otherwise.
        """
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = self.find_video_entry(path=video_path)
        if not video_entry:
            log.warning("project_manager.asset.remove_video_missing", path=video_path)
            return False

        if asset == "arena":
            changed = self._remove_arena_asset(video_path, video_entry, delete_files)
        elif asset == "rois":
            changed = self._remove_rois_asset(video_path, video_entry, delete_files)
        elif asset == "trajectory":
            changed = self._remove_trajectory_asset(video_entry, delete_files)
        elif asset == "summary":
            changed = self._remove_summary_asset(video_entry, delete_files)
        elif asset == "video":
            changed = self._remove_video_entry(video_path, video_entry, delete_files)
        else:  # pragma: no cover - guarded by type
            raise ValueError(f"Asset type '{asset}' desconhecido.")

        if changed:
            self.save_project()

        return changed

    def _remove_arena_asset(
        self,
        video_path: Path | str,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        changed = False

        self.clear_zone_data_for_video(video_path, persist=False)
        parquet_files = video_entry.get("parquet_files") or {}

        for key in ("arena", "rois"):
            file_path = parquet_files.pop(key, None)
            if file_path:
                changed = True
                if delete_files:
                    self._delete_file_if_exists(file_path)

        if video_entry.get("has_arena"):
            video_entry["has_arena"] = False
            changed = True
        if video_entry.get("has_rois"):
            video_entry["has_rois"] = False
            changed = True

        self._refresh_complete_flag(video_entry)

        return changed

    def _remove_rois_asset(
        self,
        video_path: Path | str,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        changed = False

        zone_data = self.get_zone_data(video_path, fallback_to_global=False)
        if zone_data and zone_data.roi_polygons:
            zone_data.roi_polygons = []
            zone_data.roi_names = []
            zone_data.roi_colors = []
            self.save_zone_data(zone_data, video_path=video_path, persist=False)
            changed = True

        parquet_files = video_entry.get("parquet_files") or {}
        roi_path = parquet_files.pop("rois", None)
        if roi_path:
            changed = True
            if delete_files:
                self._delete_file_if_exists(roi_path)

        if video_entry.get("has_rois"):
            video_entry["has_rois"] = False
            changed = True

        self._refresh_complete_flag(video_entry)

        return changed

    def _remove_trajectory_asset(
        self,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        changed = False

        parquet_files = video_entry.get("parquet_files") or {}
        trajectory_path = parquet_files.pop("trajectory", None)
        if trajectory_path:
            changed = True
            if delete_files:
                self._delete_file_if_exists(trajectory_path)

        if video_entry.get("has_trajectory"):
            video_entry["has_trajectory"] = False
            changed = True

        self._refresh_complete_flag(video_entry)

        return changed

    def _remove_summary_asset(
        self,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        changed = False
        parquet_files = video_entry.get("parquet_files") or {}

        for key in ("summary", "summary_excel", "report_docx"):
            file_path = parquet_files.pop(key, None)
            if file_path:
                changed = True
                if delete_files:
                    self._delete_file_if_exists(file_path)

        if video_entry.get("has_summary"):
            video_entry["has_summary"] = False
            changed = True

        return changed

    def _remove_video_entry(
        self,
        video_path: Path | str,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        changed = False

        parquet_files = dict(video_entry.get("parquet_files") or {})
        if delete_files:
            for path in parquet_files.values():
                self._delete_file_if_exists(path)

        self.clear_zone_data_for_video(video_path, persist=False)

        for batch in self.project_data.get("batches", []):
            original_count = len(batch.get("videos", []))
            batch["videos"] = [
                item for item in batch.get("videos", []) if item.get("path") != video_path
            ]
            if len(batch["videos"]) != original_count:
                changed = True

        if changed:
            self._refresh_last_zone_source(removed_path=video_path)

        return changed

    def find_video_entry(
        self,
        *,
        path: str | None = None,
        experiment_id: str | None = None,
    ) -> dict | None:
        """
        Return the project entry for a given video path or experiment id.

        Delegates to VideoManager.
        """
        return VideoManager.find_video_entry(
            self.project_data, path=path, experiment_id=experiment_id
        )

    def derive_processing_metadata(
        self,
        experiment_id: str,
        video_path: Path | str | None = None,
    ) -> dict:
        """Construct metadata for processing when metadata.csv has no entry."""
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        metadata: dict = {}

        video_entry = self.find_video_entry(path=video_path, experiment_id=experiment_id)
        if video_entry:
            metadata.update(dict(video_entry.get("metadata") or {}))

            for key in ("group", "group_display_name", "day", "subject"):
                value = video_entry.get(key)
                if (
                    value is not None
                    and (value != "" or isinstance(value, (int, float)))
                    and key not in metadata
                ):
                    metadata[key] = value

        metadata.setdefault("experiment_id", experiment_id)
        metadata.setdefault("video_name", experiment_id)

        if metadata.get("group") and not metadata.get("group_id"):
            metadata["group_id"] = metadata["group"]
        if metadata.get("group_display_name") and not metadata.get("group_label"):
            metadata["group_label"] = metadata["group_display_name"]

        return metadata

    def resolve_results_directory(
        self,
        experiment_id: str,
        *,
        video_path: str | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """Compute the destination directory for analysis artifacts.

        For projects with metadata, returns: project/group/day/subject/
        All files for a given subject are stored together in the subject folder.
        """
        experiment_source = experiment_id or (metadata or {}).get("experiment_id")
        experiment_component = self._sanitize_path_component(
            experiment_source,
            fallback="experimento",
        )

        if self.project_path:
            meta_lookup = metadata or {}

            if not meta_lookup:
                meta_lookup = self.get_metadata_for_experiment(experiment_id) or {}

            if not meta_lookup and video_path:
                meta_lookup = self.derive_processing_metadata(
                    experiment_id,
                    video_path,
                )

            group_component = self._format_group_component(meta_lookup)
            day_component = self._format_day_component(meta_lookup)
            subject_component = self._format_subject_component(meta_lookup)

            # Simplified structure: group/day/subject (no per-video subfolder)
            # All files for a subject's session are stored together
            return Path(self.project_path) / group_component / day_component / subject_component

        base_dir = Path(video_path).parent if video_path else Path.cwd()
        return base_dir / f"{experiment_component}_results"

    @staticmethod
    def _sanitize_path_component(value, *, fallback: str) -> str:
        candidate = fallback if value is None else str(value).strip()
        if not candidate:
            candidate = fallback

        normalized = unicodedata.normalize("NFKD", candidate)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))

        sanitized = re.sub(r"[<>:\"/\\|?*]", "_", normalized)
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)
        sanitized = sanitized.strip("._")

        return sanitized or fallback

    def _format_group_component(self, metadata: dict | None) -> str:
        if metadata:
            for key in (
                "group_display_name",
                "group_label",
                "group_name",
                "group",
            ):
                value = metadata.get(key)
                if value not in (None, ""):
                    return "Grupo_" + self._sanitize_path_component(value, fallback="Sem_Grupo")

        return "Grupo_" + self._sanitize_path_component(None, fallback="Sem_Grupo")

    def _format_day_component(self, metadata: dict | None) -> str:
        candidate = None
        if metadata:
            for key in ("day", "dia", "day_id"):
                value = metadata.get(key)
                if value not in (None, ""):
                    candidate = value
                    break

        if candidate is None:
            suffix = "Indefinido"
        else:
            # Check if candidate already has "Dia" or "Day" prefix
            candidate_str = str(candidate)
            if candidate_str.lower().startswith(("dia", "day")):
                # Extract just the number/suffix part after the prefix
                # e.g., "Day01" -> "01", "Dia 5" -> "5"
                import re

                match = re.search(r"\d+", candidate_str)
                if match:
                    try:
                        day_number = int(match.group(0))
                        suffix = f"{day_number:02d}"
                    except (TypeError, ValueError):
                        suffix = self._sanitize_path_component(candidate_str, fallback="Indefinido")
                else:
                    suffix = self._sanitize_path_component(candidate_str, fallback="Indefinido")
            else:
                try:
                    day_number = float(candidate)
                    if day_number.is_integer():
                        suffix = f"{int(day_number):02d}"
                    else:
                        suffix = self._sanitize_path_component(candidate, fallback="Indefinido")
                except (TypeError, ValueError):
                    suffix = self._sanitize_path_component(candidate, fallback="Indefinido")

        return f"Dia_{suffix}"

    def _format_subject_component(self, metadata: dict | None) -> str:
        candidate = None
        if metadata:
            for key in ("subject", "subject_id", "animal", "sujeito"):
                value = metadata.get(key)
                if value not in (None, ""):
                    candidate = value
                    break

        if candidate is None:
            suffix = "Indefinido"
        else:
            try:
                subject_number = float(candidate)
                if subject_number.is_integer():
                    suffix = f"{int(subject_number):02d}"
                else:
                    suffix = self._sanitize_path_component(candidate, fallback="Indefinido")
            except (TypeError, ValueError):
                suffix = self._sanitize_path_component(candidate, fallback="Indefinido")

        return f"Sujeito_{suffix}"

    def register_processing_outputs(
        self,
        video_path: Path | str,
        *,
        results_dir: str | None = None,
        trajectory_path: str | None = None,
        summary_parquet: str | None = None,
        summary_excel: str | None = None,
        report_path: str | None = None,
    ) -> bool:
        """Update project metadata with freshly generated analysis artifacts."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = self.find_video_entry(path=video_path)
        if not video_entry:
            log.info(
                "project.outputs.adding_missing_video",
                video_path=video_path,
            )
            # Add the video to the in-memory project data
            # This can happen during single video workflows
            self.add_video_batch([{"path": video_path, "status": "processing"}], save_project=False)
            video_entry = self.find_video_entry(path=video_path)
            if not video_entry:
                log.warning(
                    "project.outputs.video_still_not_found",
                    video_path=video_path,
                )
                return False

        # Update flags, parquet mapping and persist as needed using helpers
        self._update_entry_zone_flags(video_entry, video_path)
        if results_dir:
            video_entry["results_dir"] = results_dir

        changed = self._update_parquet_files_and_status(
            video_entry,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )

        if changed:
            log.info(
                "project.outputs.registered",
                video=os.path.basename(video_path),
                trajectory=bool(trajectory_path),
                summary=bool(summary_parquet or summary_excel or report_path),
                status=video_entry.get("status"),
            )
            if self.project_path:
                self.save_project()

        return True

    def _update_entry_zone_flags(self, video_entry: dict, video_path: Path | str) -> None:
        """Update has_arena/has_rois flags from zone data when missing for a video entry."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        zone_data = self.get_zone_data(video_path, fallback_to_global=False)
        if not zone_data:
            return
        if zone_data.polygon and not video_entry.get("has_arena"):
            video_entry["has_arena"] = True
            log.info("project.outputs.arena_flag_updated", video=video_path)
        if zone_data.roi_polygons and not video_entry.get("has_rois"):
            video_entry["has_rois"] = True
            log.info("project.outputs.rois_flag_updated", video=video_path)

    def _update_parquet_files_and_status(
        self,
        video_entry: dict,
        *,
        trajectory_path: str | None = None,
        summary_parquet: str | None = None,
        summary_excel: str | None = None,
        report_path: str | None = None,
    ) -> bool:
        """Update parquet file references and derived flags/status.

        Returns True if any field changed.
        """
        parquet_files = video_entry.setdefault("parquet_files", {})
        changed = False

        if trajectory_path:
            if parquet_files.get("trajectory") != trajectory_path:
                parquet_files["trajectory"] = trajectory_path
                changed = True
            if not video_entry.get("has_trajectory"):
                video_entry["has_trajectory"] = True
                changed = True

        if summary_parquet:
            if parquet_files.get("summary") != summary_parquet:
                parquet_files["summary"] = summary_parquet
                changed = True
            if not video_entry.get("has_summary"):
                video_entry["has_summary"] = True
                changed = True

        if summary_excel:
            if parquet_files.get("summary_excel") != summary_excel:
                parquet_files["summary_excel"] = summary_excel
                changed = True
            if not video_entry.get("has_summary"):
                video_entry["has_summary"] = True
                changed = True

        if report_path:
            if parquet_files.get("report_docx") != report_path:
                parquet_files["report_docx"] = report_path
                changed = True

        if (
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
            and not video_entry.get("has_complete_data")
        ):
            video_entry["has_complete_data"] = True
            changed = True

        if video_entry.get("has_trajectory") and video_entry.get("status") != "processed":
            video_entry["status"] = "processed"
            changed = True

        return changed

    def get_next_video(self):
        """
        Return the path of the next video with 'pending' status from all batches.

        Delegates to VideoManager.
        """
        return VideoManager.get_next_video(self.project_data)

    def get_project_name(self):
        """Return the project name.

        Returns:
            Project name string, or "N/A" if not set.
        """
        return self.project_data.get("project_name", "N/A")

    def get_project_type(self):
        """Return the project type.

        Returns:
            Project type string (e.g., 'batch' or 'live'), or None if not set.
        """
        return self.project_data.get("project_type")

    def get_zone_data(
        self,
        video_path: Path | str | None = None,
        *,
        fallback_to_global: bool = True,
    ) -> ZoneData:
        """
        Retrieve zone data for a specific video or fallback to project defaults.

        Delegates to ZoneManager.
        """
        return self.zone_manager.get_zone_data(
            self.project_data, video_path=video_path, fallback_to_global=fallback_to_global
        )

    def update_main_polygon(self, points: list):
        """
        Atualiza ou define o polígono principal nos dados do projeto.

        Delegates to ZoneManager.
        """
        self.zone_manager.update_main_polygon(
            self.project_data, points, persist_callback=self.save_project
        )

    def load_metadata(self):
        """Load the metadata.csv file from the project root into a pandas DataFrame."""
        import pandas as pd  # Lazy import to avoid loading pandas during startup

        if not self.project_path:
            return

        metadata_path = os.path.join(self.project_path, "metadata.csv")
        if os.path.exists(metadata_path):
            try:
                self.metadata = pd.read_csv(metadata_path)
                log.info("project.metadata.loaded", path=metadata_path)
            except OSError as e:
                self.metadata = None
                log.error(
                    "project.metadata.io_error",
                    path=metadata_path,
                    error=str(e),
                )
            except (UnicodeDecodeError, ValueError) as e:
                self.metadata = None
                log.error(
                    "project.metadata.parse_error",
                    path=metadata_path,
                    error=str(e),
                )
            except Exception as e:
                # Catch pandas-specific errors and other unforeseen issues
                self.metadata = None
                log.error(
                    "project.metadata.unexpected_error",
                    path=metadata_path,
                    error=str(e),
                    error_type=type(e).__name__,
                )
        else:
            self.metadata = None
            log.info("project.metadata.not_found", path=metadata_path)

    def get_metadata_for_experiment(self, experiment_id: str) -> dict:
        """
        Retrieve a dictionary of metadata for a given experiment ID.

        It first checks the loaded metadata.csv file. If the experiment is not
        found, it attempts to parse the experiment_id using a regex as a fallback.

        Args:
            experiment_id: The ID of the experiment (e.g., the video file stem).

        Returns:
            A dictionary of metadata for that experiment.
        """
        # First, try to find the data in the metadata.csv file
        if self.metadata is not None and "experiment_id" in self.metadata.columns:
            row = self.metadata[self.metadata["experiment_id"] == experiment_id]
            if not row.empty:
                return row.iloc[0].to_dict()

        # Fallback: Try to extract from experiment_id using regex
        log.info(
            "metadata.fallback.attempt",
            experiment_id=experiment_id,
            reason="Not found in metadata.csv",
        )
        pattern = re.compile(r"D(\d+)_G(.+)_S(\d+)")
        match = pattern.match(experiment_id)
        if match:
            try:
                day = int(match.group(1))
                group = match.group(2)
                subject = int(match.group(3))
                log.info(
                    "metadata.fallback.success",
                    day=day,
                    group=group,
                    subject=subject,
                )
                return {"day": day, "group": group, "subject": subject}
            except (ValueError, IndexError):
                log.warning("metadata.fallback.parse_error", experiment_id=experiment_id)

        # If neither method works, return an empty dictionary
        return {}

    def save_detector_state(self, detector_config: dict) -> bool:
        """
        Save detector configuration to project data.

        Args:
            detector_config: Dictionary with keys plugin_name, confidence_threshold,
                           nms_threshold, optional track_threshold,
                           optional match_threshold, context, last_updated

        Returns:
            bool: True if saved successfully, False if no project/data available.

        Raises:
            ProjectInvalidError: If save operation fails.
        """
        if not self.project_data:
            log.debug("project.detector_state.save.no_project_data")
            return False

        log.info("project.detector_state.save.start", config=detector_config)

        # Add timestamp if not provided
        if "last_updated" not in detector_config:
            detector_config["last_updated"] = datetime.now().isoformat()

        self.project_data["detector_config"] = detector_config

        overrides = self.project_data.setdefault("model_overrides", {})
        normalized_thresholds = self._normalize_detector_thresholds(detector_config)
        if normalized_thresholds:
            merged = dict(overrides.get("detector_parameters") or {})
            merged.update(normalized_thresholds)
            overrides["detector_parameters"] = merged
        elif not detector_config:
            overrides.pop("detector_parameters", None)

        if self.project_path:
            self.save_project()  # Raises ProjectInvalidError on failure
            log.info(
                "project.detector_state.save.success",
                plugin=detector_config.get("plugin_name"),
            )
        else:
            log.info(
                "project.detector_state.save.in_memory",
                plugin=detector_config.get("plugin_name"),
                reason="single_video_workflow",
            )

        return True

    def get_detector_state(self) -> dict:
        """
        Retrieve detector configuration from project data.

        Returns:
            dict: Detector configuration or empty dict if not found
        """
        return self.project_data.get("detector_config", {})

    @staticmethod
    def _normalize_detector_thresholds(detector_config: dict | None) -> dict[str, float]:
        mapping = {
            "conf_threshold": "confidence_threshold",
            "confidence_threshold": "confidence_threshold",
            "nms_threshold": "nms_threshold",
            "track_threshold": "track_threshold",
            "match_threshold": "match_threshold",
        }

        normalized: dict[str, float] = {}
        if not detector_config:
            return normalized

        for source_key, target_key in mapping.items():
            if source_key not in detector_config:
                continue
            try:
                normalized[target_key] = float(detector_config[source_key])
            except (TypeError, ValueError):
                log.warning(
                    "project.detector_state.normalize_failed",
                    key=source_key,
                    value=detector_config[source_key],
                )

        return normalized

    def get_completed_sessions(self) -> set[tuple[int, str, int]]:
        """
        Scan the project directory for completed session folders and returns them.

        A session is a tuple of (day, group_name, subject_id).
        """
        if not self.project_path:
            return set()

        completed = set()
        # Regex to capture day, group name, and subject ID from folder names
        # like "D1_GControl_S3" or "D12_GGroup Name with spaces_S15"
        pattern = re.compile(r"^D(\d+)_G(.+)_S(\d+)$")

        for item in os.scandir(self.project_path):
            if not item.is_dir():
                continue

            match = pattern.match(item.name)
            if match:
                try:
                    day = int(match.group(1))
                    group_name = match.group(2)
                    subject_id = int(match.group(3))
                    completed.add((day, group_name, subject_id))
                except (ValueError, IndexError):
                    log.warning("project.scan.invalid_folder_name", name=item.name)
                    continue

        return completed

    def save_last_session_details(self, day: int, group: str):
        """Save the last selected day and group to the project config."""
        if not self.project_path:
            return
        self.project_data["last_selected_day"] = day
        self.project_data["last_selected_group"] = group
        self.save_project()

    def get_last_session_details(self) -> tuple[int | None, str | None]:
        """Retrieve the last selected day and group from the project config."""
        if not self.project_data:
            return None, None

        day = self.project_data.get("last_selected_day")
        group = self.project_data.get("last_selected_group")
        return day, group

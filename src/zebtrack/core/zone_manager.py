"""Zone management module for ZebTrack-AI projects.

Handles all zone-related operations including:
- Arena polygon management
- ROI (Region of Interest) management
- Zone data serialization/deserialization
- Zone data persistence and retrieval
- Zone parquet file operations

This module was extracted from ProjectManager during Phase 2 refactoring
to reduce the God Object pattern and improve maintainability.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from zebtrack.core.detector import ZoneData

log = structlog.get_logger()


class ZoneManager:
    """Manages zone-related operations for ZebTrack-AI projects.

    Responsibilities:
    - Serializing/deserializing ZoneData objects
    - Storing and retrieving zone data per video
    - Managing active zone video state
    - Copying zone data between videos
    - Loading zones from parquet files
    - Updating video entry zone flags

    This class operates on project_data dictionaries and maintains
    minimal state for active zone video tracking.
    """

    def __init__(self):
        """Initialize ZoneManager with tracking state."""
        self._active_zone_video: str | None = None
        self._last_zone_source_video: str | None = None

    @staticmethod
    def normalize_video_path(path: Path | str | None) -> str | None:
        """Normalize a video path for consistent comparison.

        Args:
            path: Path to normalize

        Returns:
            Normalized path as string, or None if path is None
        """
        if not path:
            return None
        path = Path(path) if isinstance(path, str) else path
        try:
            resolved = path.resolve(strict=False)
        except Exception:
            resolved = path
        return resolved.as_posix()

    @staticmethod
    def ensure_zone_structures(project_data: dict) -> None:
        """Ensure zone-related structures exist in project data.

        Args:
            project_data: The project data dictionary to modify
        """
        if "detection_zones" not in project_data:
            project_data["detection_zones"] = {}
        if "zones_by_video" not in project_data:
            project_data["zones_by_video"] = {}
        if "roi_templates" not in project_data or not isinstance(
            project_data.get("roi_templates"), list
        ):
            project_data["roi_templates"] = []

    @staticmethod
    def zone_data_to_dict(zone_data: ZoneData | None) -> dict:
        """Serialize ZoneData into a JSON-friendly dictionary.

        Args:
            zone_data: ZoneData object to serialize

        Returns:
            Dictionary with serialized zone data
        """
        if not zone_data:
            return {
                "polygon": [],
                "roi_polygons": [],
                "roi_names": [],
                "roi_colors": [],
            }

        serialized = {
            "polygon": [list(point) for point in (zone_data.polygon or [])],
            "roi_polygons": [
                [list(point) for point in polygon] for polygon in (zone_data.roi_polygons or [])
            ],
            "roi_names": list(zone_data.roi_names or []),
            "roi_colors": [list(color) for color in (zone_data.roi_colors or [])],
        }
        return serialized

    @staticmethod
    def zone_data_from_dict(data: dict | None) -> ZoneData:
        """Deserialize zone data stored in JSON back into ZoneData.

        Args:
            data: Dictionary with zone data

        Returns:
            ZoneData object
        """
        if not data:
            return ZoneData()

        polygon = [list(point) for point in data.get("polygon", [])]
        roi_polygons = []
        for polygon_points in data.get("roi_polygons", []):
            roi_polygons.append([list(point) for point in polygon_points])

        roi_names = list(data.get("roi_names", []))
        roi_colors = [tuple(color) for color in data.get("roi_colors", [])]

        return ZoneData(
            polygon=polygon,
            roi_polygons=roi_polygons,
            roi_names=roi_names,
            roi_colors=roi_colors,
        )

    def resolve_zone_entry(
        self, project_data: dict, video_path: Path | str | None
    ) -> tuple[str | None, dict | None]:
        """Locate a stored zone entry matching the provided video path.

        Args:
            project_data: The project data dictionary to search
            video_path: Video path to look up

        Returns:
            Tuple of (key, zone_data_dict) where key is the storage key
            and zone_data_dict is the stored data, or (None, None) if not found
        """
        if not video_path:
            return None, None
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        self.ensure_zone_structures(project_data)
        zones_map = project_data.get("zones_by_video", {})
        normalized = self.normalize_video_path(video_path)

        if normalized and normalized in zones_map:
            return normalized, zones_map[normalized]

        video_path_str = str(video_path)
        if video_path_str in zones_map:
            return video_path_str, zones_map[video_path_str]

        if normalized:
            for key, value in zones_map.items():
                if self.normalize_video_path(key) == normalized:
                    return key, value

        return normalized or video_path_str, None

    @staticmethod
    def deduplicate_zone_keys(project_data: dict, preferred_key: str | None) -> None:
        """Remove duplicate zone entries that resolve to the same canonical path.

        Args:
            project_data: The project data dictionary to modify
            preferred_key: The preferred key to keep
        """
        if not preferred_key:
            return

        zones_map = project_data.get("zones_by_video", {})
        normalized = ZoneManager.normalize_video_path(preferred_key)
        if not normalized:
            return

        for key in list(zones_map.keys()):
            if key == preferred_key:
                continue
            if ZoneManager.normalize_video_path(key) == normalized:
                del zones_map[key]

    @staticmethod
    def update_video_zone_flags(
        project_data: dict,
        video_path: Path | str,
        zone_data: ZoneData | None,
    ) -> None:
        """Update has_arena/has_rois flags for a given video entry.

        Args:
            project_data: The project data dictionary to modify
            video_path: Path to the video to update
            zone_data: Zone data to determine flags from
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)

        if not project_data or not video_path_str:
            return

        has_arena = bool(zone_data and zone_data.polygon)
        has_rois = bool(zone_data and zone_data.roi_polygons)
        normalized_target = ZoneManager.normalize_video_path(video_path_str)

        for batch in project_data.get("batches", []):
            for video in batch.get("videos", []):
                candidate_path = video.get("path")
                if not candidate_path:
                    continue
                if ZoneManager.normalize_video_path(candidate_path) == normalized_target:
                    video["has_arena"] = has_arena
                    video["has_rois"] = has_rois
                    video["zones_finalized"] = False
                    return

    def refresh_last_zone_source(
        self, project_data: dict, removed_path: Path | str | None = None
    ) -> None:
        """Refresh cache for last zone source video when data changes.

        Args:
            project_data: The project data dictionary
            removed_path: Optional path that was removed
        """
        if removed_path is not None:
            removed_path = Path(removed_path) if isinstance(removed_path, str) else removed_path
        zones_map = project_data.get("zones_by_video", {})

        if removed_path and self._last_zone_source_video:
            normalized_removed = self.normalize_video_path(removed_path)
            if normalized_removed:
                current_normalized = self.normalize_video_path(self._last_zone_source_video)
                if current_normalized == normalized_removed:
                    self._last_zone_source_video = None

        if self._last_zone_source_video:
            normalized_last = self.normalize_video_path(self._last_zone_source_video)
            for key in zones_map.keys():
                if self.normalize_video_path(key) == normalized_last:
                    self._last_zone_source_video = key
                    return
            self._last_zone_source_video = None

        # Pick the most recently inserted entry in zones_by_video
        if zones_map:
            self._last_zone_source_video = next(reversed(zones_map.keys()))
        else:
            self._last_zone_source_video = None

    def set_active_zone_video(self, project_data: dict, video_path: Path | str | None) -> None:
        """Set the video whose zones should be considered active in memory.

        Args:
            project_data: The project data dictionary to modify
            video_path: Path to the video to set as active, or None to clear
        """
        self.ensure_zone_structures(project_data)

        if video_path is None:
            self._active_zone_video = None
            return

        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        normalized_path = self.normalize_video_path(video_path)
        key, stored = self.resolve_zone_entry(project_data, video_path)
        zones_map = project_data.get("zones_by_video", {})
        preferred_key = normalized_path or key or str(video_path)

        if stored:
            zone_copy = self.zone_data_from_dict(stored)
            project_data["detection_zones"] = self.zone_data_to_dict(zone_copy)

            if key and key != preferred_key:
                zones_map[preferred_key] = stored
                del zones_map[key]
            elif preferred_key not in zones_map:
                zones_map[preferred_key] = stored

            self.deduplicate_zone_keys(project_data, preferred_key)
            self._last_zone_source_video = preferred_key
        else:
            project_data["detection_zones"] = self.zone_data_to_dict(ZoneData())
            self.deduplicate_zone_keys(project_data, preferred_key)

        self._active_zone_video = preferred_key

    def get_active_zone_video(self) -> str | None:
        """Return the currently active video for zone operations.

        Returns:
            Path to active video or None
        """
        return self._active_zone_video

    def get_last_zone_video(self, project_data: dict, exclude: str | None = None) -> str | None:
        """Return the last video that had zones saved, excluding optional target.

        Args:
            project_data: The project data dictionary
            exclude: Optional video path to exclude from results

        Returns:
            Path to last zone video or None
        """
        zones_map = project_data.get("zones_by_video", {})
        normalized_exclude = self.normalize_video_path(exclude) if exclude else None

        if self._last_zone_source_video:
            normalized_last = self.normalize_video_path(self._last_zone_source_video)
            if normalized_last and normalized_last != normalized_exclude:
                for key in zones_map.keys():
                    if self.normalize_video_path(key) == normalized_last:
                        return key

        for path in reversed(list(zones_map.keys())):
            if self.normalize_video_path(path) != normalized_exclude:
                return path

        return None

    def has_zone_data(self, project_data: dict, video_path: Path | str | None) -> bool:
        """Check whether the given video currently stores arena or ROI data.

        Args:
            project_data: The project data dictionary
            video_path: Video path to check

        Returns:
            True if video has zone data, False otherwise
        """
        if not video_path:
            return False

        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self.ensure_zone_structures(project_data)
        _, stored = self.resolve_zone_entry(project_data, video_path)

        if not stored:
            return False

        zone_data = self.zone_data_from_dict(stored)
        return bool(zone_data.polygon or zone_data.roi_polygons)

    def save_zone_data(
        self,
        project_data: dict,
        zone_data: ZoneData,
        video_path: Path | str | None = None,
        *,
        persist_callback: callable | None = None,
    ) -> None:
        """Persist zone data for the active video and project defaults.

        Args:
            project_data: The project data dictionary to modify
            zone_data: ZoneData to save
            video_path: Optional video path to save for (uses active if None)
            persist_callback: Optional callback to persist project after save
        """
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self.ensure_zone_structures(project_data)

        target_video = video_path if video_path is not None else self._active_zone_video

        serialized = self.zone_data_to_dict(zone_data)
        project_data["detection_zones"] = serialized

        if target_video:
            normalized = self.normalize_video_path(target_video)
            existing_key, _ = self.resolve_zone_entry(project_data, target_video)
            # Ensure store_key is always a string (not Path object) for JSON serialization
            store_key = normalized or existing_key or str(Path(target_video).as_posix())

            project_data["zones_by_video"][store_key] = serialized
            self.deduplicate_zone_keys(project_data, store_key)

            self._last_zone_source_video = store_key
            self.update_video_zone_flags(project_data, target_video, zone_data)

        if persist_callback:
            persist_callback()

    def clear_zone_data_for_video(
        self,
        project_data: dict,
        video_path: Path | str,
        *,
        persist_callback: callable | None = None,
    ) -> None:
        """Remove stored zone data for a specific video.

        Args:
            project_data: The project data dictionary to modify
            video_path: Video path to clear zones for
            persist_callback: Optional callback to persist project after clear
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)

        self.ensure_zone_structures(project_data)

        key, _ = self.resolve_zone_entry(project_data, video_path_str)
        if key and key in project_data["zones_by_video"]:
            del project_data["zones_by_video"][key]

        normalized_target = self.normalize_video_path(video_path_str)
        if self._active_zone_video and normalized_target == self._active_zone_video:
            project_data["detection_zones"] = self.zone_data_to_dict(ZoneData())

        self.update_video_zone_flags(project_data, video_path_str, None)
        self.refresh_last_zone_source(project_data, removed_path=video_path_str)

        if persist_callback:
            persist_callback()

    def clone_zone_data_from_video(self, project_data: dict, video_path: Path | str) -> ZoneData:
        """Return a deep copy of zone data stored for another video.

        Args:
            project_data: The project data dictionary
            video_path: Video path to clone zones from

        Returns:
            ZoneData object (deep copy)
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)

        _, stored = self.resolve_zone_entry(project_data, video_path_str)
        return self.zone_data_from_dict(stored)

    def get_zone_data(
        self,
        project_data: dict,
        video_path: Path | str | None = None,
        *,
        fallback_to_global: bool = True,
    ) -> ZoneData:
        """Retrieve zone data for a specific video or fallback to project defaults.

        Args:
            project_data: The project data dictionary
            video_path: Optional video path to get zones for (uses active if None)
            fallback_to_global: Whether to fall back to global zones if video has none

        Returns:
            ZoneData object
        """
        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self.ensure_zone_structures(project_data)

        target_video = video_path if video_path is not None else self._active_zone_video
        _key, stored = self.resolve_zone_entry(project_data, target_video)

        if stored:
            return self.zone_data_from_dict(stored)

        if target_video and not fallback_to_global:
            return ZoneData()

        return self.zone_data_from_dict(project_data.get("detection_zones"))

    def update_main_polygon(
        self, project_data: dict, points: list, persist_callback: callable | None = None
    ) -> None:
        """Update or define the main polygon in project data.

        Args:
            project_data: The project data dictionary to modify
            points: List of polygon points
            persist_callback: Optional callback to persist project after update
        """
        log.info(
            "zone_manager.polygon.updating",
            points_count=len(points),
            has_project_data=bool(project_data),
        )

        try:
            # Validation
            if not project_data:
                log.error("zone_manager.polygon.no_project_data")
                raise ValueError("Dados do projeto não inicializados")

            # Get current zone data
            zone_data = self.get_zone_data(project_data)
            log.debug(
                "zone_manager.polygon.zone_data_loaded",
                current_polygon_exists=bool(zone_data.polygon),
                current_roi_count=len(zone_data.roi_polygons),
            )

            # Update polygon
            old_polygon = zone_data.polygon
            zone_data.polygon = points
            log.info(
                "zone_manager.polygon.polygon_updated",
                old_points=len(old_polygon) if old_polygon else 0,
                new_points=len(points),
            )

            # Persist changes
            self.save_zone_data(project_data, zone_data, persist_callback=persist_callback)
            log.debug("zone_manager.polygon.data_structure_updated")

            log.info("zone_manager.polygon.saved_successfully")

        except Exception as e:
            log.error(
                "zone_manager.polygon.update_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

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
                "zone_manager.load_zones.no_files",
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
                        "zone_manager.load_zones.arena_loaded",
                        path=arena_path,
                        points=len(polygon_points),
                    )
                else:
                    log.warning(
                        "zone_manager.load_zones.arena_empty",
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
                            (0, 128, 0),  # Dark Green (was 0, 255, 0)
                            (255, 0, 0),  # Red
                            (0, 0, 255),  # Blue
                            (0, 204, 204),  # Darker Yellow (was 0, 255, 255)
                            (255, 0, 255),  # Magenta
                            (0, 255, 255),  # Cyan
                        ]
                        zone_data.roi_colors = [
                            default_colors[i % len(default_colors)] for i in range(len(roi_names))
                        ]

                        log.info(
                            "zone_manager.load_zones.rois_loaded",
                            path=rois_path,
                            count=len(roi_names),
                            names=roi_names,
                        )
                    else:
                        log.warning(
                            "zone_manager.load_zones.rois_invalid_schema",
                            path=rois_path,
                            columns=list(rois_df.columns),
                        )
                else:
                    log.warning(
                        "zone_manager.load_zones.rois_empty",
                        path=rois_path,
                    )

            return zone_data

        except Exception as e:
            log.error(
                "zone_manager.load_zones.error",
                video=video_info.get("path"),
                error=str(e),
                exc_info=True,
            )
            return None

    @staticmethod
    def update_entry_zone_flags(
        project_data: dict,
        video_entry: dict,
        video_path: Path | str,
        zone_manager_instance: ZoneManager,
    ) -> None:
        """Update has_arena/has_rois flags from zone data when missing for a video entry.

        Args:
            project_data: The project data dictionary
            video_entry: Video entry dictionary to update
            video_path: Path to the video
            zone_manager_instance: ZoneManager instance to use for getting zone data
        """
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        zone_data = zone_manager_instance.get_zone_data(
            project_data, video_path_str, fallback_to_global=False
        )
        if not zone_data:
            return
        if zone_data.polygon and not video_entry.get("has_arena"):
            video_entry["has_arena"] = True
            log.info("zone_manager.arena_flag_updated", video=video_path_str)
        if zone_data.roi_polygons and not video_entry.get("has_rois"):
            video_entry["has_rois"] = True
            log.info("zone_manager.rois_flag_updated", video=video_path_str)

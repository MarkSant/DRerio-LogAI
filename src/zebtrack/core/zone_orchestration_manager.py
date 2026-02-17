"""Zone orchestration — cross-cutting zone persistence workflows.

Phase 4.2: Extracted from ProjectManager to reduce class size.
Coordinates ZoneManager, ParquetIOManager, and video entry flags
during zone save / load / sync workflows.

All methods are static — they receive explicit dependency callbacks
to avoid circular imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

    from zebtrack.core.detector import MultiAquariumZoneData, ZoneData

log = structlog.get_logger()


class ZoneOrchestrationManager:
    """Coordinates zone save/load workflows across multiple sub-managers.

    Every method is static and receives explicit callbacks so that this
    class has **no** import-time dependency on ``ProjectManager``.
    """

    # ------------------------------------------------------------------
    # set_active_zone_video orchestration
    # ------------------------------------------------------------------

    @staticmethod
    def sync_active_zone_video(
        video_path_str: str,
        *,
        find_video_entry_fn: Callable,
        resolve_results_directory_fn: Callable,
        load_zones_from_parquet_fn: Callable,
        get_zone_data_fn: Callable,
        save_zone_data_fn: Callable,
    ) -> None:
        """Sync in-memory zone data from disk parquets for *video_path_str*.

        Called by ``ProjectManager.set_active_zone_video`` before setting the
        active pointer.  Loads arena/ROI parquets from the expected results
        directory and merges them into memory when the current in-memory data
        is incomplete.
        """
        video_entry = find_video_entry_fn(path=video_path_str)
        metadata = video_entry.get("metadata") if video_entry else None
        experiment_id = Path(video_path_str).stem

        try:
            results_dir = resolve_results_directory_fn(
                experiment_id, video_path=video_path_str, metadata=metadata
            )

            # Check for parquet files in the project structure
            arena_path = results_dir / f"1_ProcessingArea_{experiment_id}.parquet"
            rois_path = results_dir / f"2_AreasOfInterest_{experiment_id}.parquet"

            found_parquets: dict[str, str] = {}
            if arena_path.exists():
                found_parquets["arena"] = str(arena_path)
            if rois_path.exists():
                found_parquets["rois"] = str(rois_path)

            if not found_parquets:
                return

            log.info(
                "project.set_active.found_project_parquets",
                files=list(found_parquets.keys()),
            )

            video_info = {"path": video_path_str, "parquet_files": found_parquets}
            loaded_zones = load_zones_from_parquet_fn(video_info)

            if not loaded_zones:
                return

            current_zones = get_zone_data_fn(video_path_str, fallback_to_global=False)

            should_update = False
            if not current_zones.polygon and loaded_zones.polygon:
                should_update = True
            if not current_zones.roi_polygons and loaded_zones.roi_polygons:
                should_update = True

            needs_sync = should_update or (
                not current_zones.polygon and not current_zones.roi_polygons
            )
            if needs_sync:
                log.info(
                    "project.set_active.syncing_memory_from_disk",
                    video=video_path_str,
                )
                save_zone_data_fn(loaded_zones, video_path=video_path_str, persist=False)

                if video_entry:
                    video_entry.setdefault("parquet_files", {}).update(found_parquets)
                    if loaded_zones.polygon:
                        video_entry["has_arena"] = True
                    if loaded_zones.roi_polygons:
                        video_entry["has_rois"] = True

        # except Exception justified: pandas parquet I/O — heterogeneous data errors
        except Exception as e:
            log.warning("project.set_active.load_failed", error=str(e))

    # ------------------------------------------------------------------
    # save_zone_data persistence
    # ------------------------------------------------------------------

    @staticmethod
    def persist_zone_data(
        zone_data: ZoneData,
        target_video: str | None,
        project_path: Path | None,
        *,
        update_video_zone_flags_fn: Callable,
        export_zones_to_parquet_fn: Callable,
        find_video_entry_fn: Callable,
        save_project_fn: Callable,
    ) -> None:
        """Handle persistence side of ``save_zone_data``.

        Updates video-entry flags, exports parquets, and persists the project.
        """
        if target_video:
            update_video_zone_flags_fn(target_video, zone_data)
            log.debug(
                "project.save_zone_data.flags_updated",
                video=target_video,
                has_arena=bool(zone_data.polygon),
                has_rois=bool(zone_data.roi_polygons),
            )

        if target_video and project_path:
            try:
                exported = export_zones_to_parquet_fn(target_video, zone_data)

                video_entry = find_video_entry_fn(path=target_video)
                if video_entry:
                    parquet_map = video_entry.setdefault("parquet_files", {})
                    parquet_map.update(exported)

                    if "arena" in exported:
                        video_entry["has_arena"] = True
                    if "rois" in exported:
                        video_entry["has_rois"] = True

            # except Exception justified: pandas data pipeline — heterogeneous failures
            except Exception as e:
                log.error("project.save_zone_data.parquet_export_failed", error=str(e))

            save_project_fn()
        else:
            log.info(
                "project.zone_data.save.in_memory",
                video_path=target_video,
                reason="single_video_workflow",
            )
            if project_path:
                save_project_fn()

    # ------------------------------------------------------------------
    # save_multi_aquarium_zone_data persistence
    # ------------------------------------------------------------------

    @staticmethod
    def persist_multi_aquarium_zone_data(
        video_path: str,
        multi_data: MultiAquariumZoneData,
        project_path: Path | None,
        *,
        export_zones_to_parquet_fn: Callable,
        find_video_entry_fn: Callable,
        add_video_batch_fn: Callable,
        save_project_fn: Callable,
        persist: bool = True,
    ) -> None:
        """Handle persistence side of ``save_multi_aquarium_zone_data``.

        Exports AQ0 parquet for backward compatibility, updates video entry
        flags, adds the video to batches if missing, then persists.
        """
        if not multi_data.aquariums:
            if persist and project_path:
                save_project_fn()
            return

        try:
            # Use AQ0 as the "main" parquet for compatibility
            exported = export_zones_to_parquet_fn(video_path, multi_data.to_zone_data(0))

            video_entry = find_video_entry_fn(path=video_path)

            # DEFENSIVE FIX: Ensure video is in project batches
            if not video_entry:
                log.info(
                    "project_manager.multi_aquarium.adding_video_to_batches",
                    video=str(video_path),
                )
                has_arena = any(aq.polygon for aq in multi_data.aquariums)
                has_rois = any(aq.roi_polygons for aq in multi_data.aquariums)
                video_dict = {
                    "path": Path(video_path).as_posix(),
                    "status": "pending",
                    "has_arena": has_arena,
                    "has_rois": has_rois,
                    "is_multi_aquarium": True,
                    "num_aquariums": len(multi_data.aquariums),
                }
                add_video_batch_fn([video_dict], save_project=False)
                video_entry = find_video_entry_fn(path=video_path)

            if video_entry:
                if exported:
                    parquet_map = video_entry.setdefault("parquet_files", {})
                    parquet_map.update(exported)

                has_arena = any(aq.polygon for aq in multi_data.aquariums)
                has_rois = any(aq.roi_polygons for aq in multi_data.aquariums)
                video_entry["has_arena"] = has_arena
                video_entry["has_rois"] = has_rois
                video_entry["zones_finalized"] = False
                video_entry["is_multi_aquarium"] = True
                video_entry["num_aquariums"] = len(multi_data.aquariums)

                log.info(
                    "project_manager.multi_aquarium.video_entry_updated",
                    video=str(video_path),
                    has_arena=has_arena,
                    has_rois=has_rois,
                    parquet_count=len(exported) if exported else 0,
                )
        # except Exception justified: pandas data pipeline — heterogeneous failures
        except Exception as e:
            log.error(
                "project_manager.multi_aquarium.parquet_export_failed",
                error=str(e),
            )

        if persist and project_path:
            save_project_fn()

    # ------------------------------------------------------------------
    # _sync_multi_aquarium_flags
    # ------------------------------------------------------------------

    @staticmethod
    def sync_multi_aquarium_flags(
        project_data: dict[str, Any],
        *,
        iter_project_videos_fn: Callable,
        get_multi_aquarium_zone_data_fn: Callable,
    ) -> None:
        """Synchronize has_arena/has_rois flags for multi-aquarium videos.

        Ensures that video entries reflect the state of the multi-aquarium
        zone registry upon project load.
        """
        updates = 0
        for _, video_entry in iter_project_videos_fn():
            path = video_entry.get("path")
            if not path:
                continue

            multi_data = get_multi_aquarium_zone_data_fn(path)
            if multi_data and multi_data.aquariums:
                check_arena = False
                check_rois = False
                for aq in multi_data.aquariums:
                    if aq.polygon and len(aq.polygon) >= 3:
                        check_arena = True
                    if aq.roi_polygons:
                        check_rois = True

                if check_arena and not video_entry.get("has_arena"):
                    video_entry["has_arena"] = True
                    updates += 1
                if check_rois and not video_entry.get("has_rois"):
                    video_entry["has_rois"] = True
                    updates += 1

        if updates > 0:
            log.info("project.load.synced_multi_aquarium_flags", updates=updates)

    # ------------------------------------------------------------------
    # Zone data removal
    # ------------------------------------------------------------------

    @staticmethod
    def clear_zone_data_for_video(
        video_path: str,
        project_data: dict[str, Any],
        *,
        get_active_zone_video_fn: Callable[[], str | None],
        save_project_fn: Callable[[], None] | None = None,
    ) -> None:
        """Remove stored zone data for a specific video.

        Clears the zone entry from ``zones_by_video``, resets the active
        detection zones if affected, nullifies video flags, and refreshes
        the last-zone-source cache.

        Args:
            video_path: Normalised video path string.
            project_data: Mutable project dict.
            get_active_zone_video_fn: Returns the currently active zone video.
            save_project_fn: Optional persistence callback.
        """
        from zebtrack.core.detector import ZoneData
        from zebtrack.core.zone_manager import ZoneManager

        ZoneManager.ensure_zone_structures(project_data)

        zm = ZoneManager()
        key, _ = zm.resolve_zone_entry(project_data, video_path)
        if key and key in project_data["zones_by_video"]:
            del project_data["zones_by_video"][key]

        normalized_target = ZoneManager.normalize_video_path(video_path)
        active_zone_video = get_active_zone_video_fn()
        if active_zone_video and normalized_target == active_zone_video:
            project_data["detection_zones"] = ZoneManager.zone_data_to_dict(ZoneData())

        ZoneManager.update_video_zone_flags(project_data, video_path, None)
        zm.refresh_last_zone_source(project_data, removed_path=video_path)

        if save_project_fn:
            save_project_fn()

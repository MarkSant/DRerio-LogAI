"""Parquet I/O manager for ZebTrack-AI.

Handles all parquet file operations: exporting zones to parquet,
copying zone parquets between videos, and importing parquets from the wizard.

Phase 4.2: Extracted from ProjectManager to reduce god-class complexity.
All methods are stateless — they receive project_data, project_path, and
zone_manager as parameters from the ProjectManager facade.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.detector import ZoneData
from zebtrack.core.exceptions import ProjectInvalidError

if TYPE_CHECKING:
    from collections.abc import Callable

log = structlog.get_logger()


class ParquetIOManager:
    """Manages parquet file I/O for zone data and wizard imports.

    Phase 4.2: Extracted from ProjectManager. This class is stateless;
    all project state (project_path, project_data) is passed as parameters.
    """

    def __init__(self) -> None:
        """Initialize ParquetIOManager."""

    def export_zones_to_parquet(
        self,
        video_path: Path | str,
        zone_data: ZoneData,
        *,
        project_path: Path | str | None,
        find_video_entry_fn: Callable[..., dict | None],
        resolve_results_directory_fn: Callable[..., Path],
    ) -> dict[str, str]:
        """Export zone data (arena and ROIs) to parquet files.

        Args:
            video_path: Path to the video file.
            zone_data: ZoneData object to export.
            project_path: Path to the project directory.
            find_video_entry_fn: Callable to find a video entry by path.
            resolve_results_directory_fn: Callable to resolve results directory.

        Returns:
            Dictionary mapping asset type ('arena', 'rois') to generated file path.
        """
        import pandas as pd

        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        exported: dict[str, str] = {}

        if not project_path:
            return exported

        # Resolve destination directory
        video_stem = Path(video_path).stem
        video_entry = find_video_entry_fn(path=video_path)
        metadata_hint = video_entry.get("metadata") if video_entry else None

        results_dir = resolve_results_directory_fn(
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
            for name, poly in zip(zone_data.roi_names, zone_data.roi_polygons, strict=False):
                for idx, point in enumerate(poly):
                    roi_data.append(
                        {"roi_name": name, "point_index": idx, "x": point[0], "y": point[1]}
                    )

            if roi_data:
                rois_df = pd.DataFrame(roi_data)
                rois_path = results_dir / f"2_AreasOfInterest_{video_stem}.parquet"
                rois_df.to_parquet(rois_path)
                exported["rois"] = str(rois_path)

        return exported

    def copy_zone_parquet_files(  # noqa: C901
        self,
        source_video_path: Path | str,
        target_video_path: Path | str,
        *,
        project_data: dict[str, Any],
        set_active_zone_video_fn: Callable,
        scan_input_paths_fn: Callable,
        find_video_entry_fn: Callable[..., dict | None],
        resolve_results_directory_fn: Callable[..., Path],
        save_project_fn: Callable,
        persist: bool = True,
    ) -> dict[str, str]:
        """Copy arena/ROI parquet files from one video to another.

        Returns a mapping with the copied parquet types and their new paths.
        """
        # Force sync of source video to ensure files are registered
        set_active_zone_video_fn(source_video_path)

        source_video_path = str(
            Path(source_video_path) if isinstance(source_video_path, str) else source_video_path
        )
        target_video_path = str(
            Path(target_video_path) if isinstance(target_video_path, str) else target_video_path
        )

        copied: dict[str, str] = {}

        if not source_video_path or not target_video_path:
            return copied

        scan_results = scan_input_paths_fn([source_video_path])
        if not scan_results:
            log.info(
                "project_manager.zones.copy_missing_source_scan",
                source=source_video_path,
            )
            return copied

        parquet_files: dict[str, str] = scan_results[0].get("parquet_files", {})

        # Enrich with registered files if missing (Fix for hierarchical project structure)
        if not parquet_files.get("arena") or not parquet_files.get("rois"):
            source_entry = find_video_entry_fn(path=source_video_path)
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

        target_video_entry = find_video_entry_fn(path=target_video_path)
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

        hierarchical_results_dir = resolve_results_directory_fn(
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
            video_entry = target_video_entry or find_video_entry_fn(path=target_video_path)
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
            save_project_fn()

        return copied

    def import_parquets_from_wizard(
        self,
        import_config: list[dict],
        roi_merge_strategy: str = "replace",
        scanned_videos: list[dict] | None = None,
        *,
        project_data: dict[str, Any],
        project_path: Path | str | None,
        get_zone_data_fn: Callable,
        save_zone_data_fn: Callable,
        resolve_results_directory_fn: Callable[..., Path],
        save_project_fn: Callable,
    ) -> bool:
        """Import arena, ROIs, and trajectory data from existing parquet files.

        This method is called after project creation to import data from parquet files
        based on the wizard's import configuration.

        Args:
            import_config: List of per-video import configurations from wizard.
            roi_merge_strategy: How to handle ROI conflicts ("replace", "merge", "manual").
            scanned_videos: List of scanned video info containing parquet file paths.
            project_data: Project data dictionary.
            project_path: Path to the project directory.
            get_zone_data_fn: Callable to retrieve zone data for a video.
            save_zone_data_fn: Callable to save zone data for a video.
            resolve_results_directory_fn: Callable to resolve results directory.
            save_project_fn: Callable to save the project.

        Returns:
            bool: True if import succeeded, False otherwise
        """
        if not project_data:
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
        video_parquet_map: dict[str, dict] = {}
        if scanned_videos:
            for video_info in scanned_videos:
                video_parquet_map[video_info["path"]] = video_info.get("parquet_files", {})

        imported_count = {"arena": 0, "rois": 0, "trajectory": 0}

        try:
            for config in import_config:
                per_counts = self._process_single_parquet_import(
                    config,
                    video_parquet_map,
                    roi_merge_strategy,
                    project_path=project_path,
                    get_zone_data_fn=get_zone_data_fn,
                    save_zone_data_fn=save_zone_data_fn,
                    resolve_results_directory_fn=resolve_results_directory_fn,
                )
                for k, v in per_counts.items():
                    imported_count[k] += v

            # Save updated zone data to project
            save_project_fn()

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
        # except Exception justified: pandas parquet I/O — heterogeneous data errors
        except Exception as e:
            log.error(
                "project_manager.import_parquets.unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return False

    def _process_single_parquet_import(
        self,
        config: dict,
        video_parquet_map: dict,
        roi_merge_strategy: str,
        *,
        project_path: Path | str | None,
        get_zone_data_fn: Callable,
        save_zone_data_fn: Callable,
        resolve_results_directory_fn: Callable[..., Path],
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

        zone_data = get_zone_data_fn(video_path=video_path, fallback_to_global=False)

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
                        imported_roi_polygons: list[list] = []
                        imported_roi_names: list[str] = []

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
                            zone_data.roi_polygons = list(zone_data.roi_polygons)
                            zone_data.roi_names = list(zone_data.roi_names)
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
        save_zone_data_fn(zone_data, video_path, persist=False)

        # Trajectory import
        if config.get("import_trajectory", False):
            trajectory_path = parquet_files.get("trajectory")
            if trajectory_path and os.path.exists(trajectory_path):
                video_name = Path(video_path).stem
                if not project_path:
                    log.warning("project_manager.import_parquets.no_project_path", video=video_name)
                    return counts

                results_dir = resolve_results_directory_fn(video_name, video_path=video_path)
                results_dir.mkdir(parents=True, exist_ok=True)
                dest_path = results_dir / f"3_CoordMovimento_{video_name}.parquet"

                shutil.copy2(trajectory_path, dest_path)

                counts["trajectory"] += 1
                log.info(
                    "project_manager.import_parquets.trajectory_imported",
                    video=video_name,
                    source=trajectory_path,
                    dest=str(dest_path),
                )

        return counts

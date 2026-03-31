"""Project management module for ZebTrack-AI.

Provides the ProjectManager class for handling project lifecycle operations including
creation, loading, configuration management, and asset tracking for zebrafish behavioral analysis.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Literal

import structlog

from zebtrack.core.detection import MultiAquariumZoneData, ZoneData
from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.project.asset_manager import AssetManager
from zebtrack.core.project.metadata_manager import MetadataManager
from zebtrack.core.project.output_registration_manager import OutputRegistrationManager
from zebtrack.core.project.parquet_io_manager import ParquetIOManager
from zebtrack.core.project.project_lifecycle_manager import ProjectLifecycleManager
from zebtrack.core.project.project_service import ProjectService
from zebtrack.core.project.types import AssetType
from zebtrack.core.project.video_manager import VideoManager
from zebtrack.core.project.zone_manager import ZoneManager
from zebtrack.core.project.zone_orchestration_manager import ZoneOrchestrationManager
from zebtrack.core.state_manager import StateManager

# Re-export for backward compatibility — external code imports ProjectInvalidError from here
__all__ = ["ProjectInvalidError", "ProjectManager"]


CONFIG_FILE_NAME = "project_config.json"

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

        # Phase 4.2: New specialized managers
        self.parquet_io_manager = ParquetIOManager()
        self.output_registration_manager = OutputRegistrationManager()
        self.metadata_manager = MetadataManager()
        self.lifecycle_manager = ProjectLifecycleManager()

        # In-memory project state
        self.project_path: Path | str | None = None
        self.project_data: dict[str, Any] = {}
        self.metadata = None  # Will hold the DataFrame for metadata.csv
        # Compatibility: keep roi_template_manager reference for legacy code
        self.roi_template_manager = self.asset_manager.roi_template_manager

        # Cache for get_available_groups (performance optimization)
        self._groups_cache: list[str] | None = None
        self._groups_cache_valid: bool = False

    # ------------------------------------------------------------------
    # Internal helpers for zone management
    # ------------------------------------------------------------------

    def _resolve_zone_entry(self, video_path: Path | str | None) -> tuple[str | None, dict | None]:
        """Locate a stored zone entry for the provided video path."""
        return self.zone_manager.resolve_zone_entry(self.project_data, video_path)

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
        if save_location in (None, "project") and self.project_path is None:
            raise ValueError(
                "Não é possível salvar o template no projeto atual: projeto não carregado."
            )
        return self.asset_manager.save_roi_template(
            project_data=self.project_data,
            project_path=self.project_path or "",
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

    def _zone_data_to_dict(self, zone_data: ZoneData | None) -> dict[str, Any]:
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
        """Set the video whose zones should be considered active in memory.

        Robustly attempts to load zone data from the project structure if
        in-memory data is incomplete (delegate to ZoneOrchestrationManager).
        """
        if video_path:
            video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
            ZoneOrchestrationManager.sync_active_zone_video(
                video_path_str,
                find_video_entry_fn=self.find_video_entry,
                resolve_results_directory_fn=self.resolve_results_directory,
                load_zones_from_parquet_fn=self.load_zones_from_parquet,
                get_zone_data_fn=lambda vp, **kw: self.zone_manager.get_zone_data(
                    self.project_data, vp, **kw
                ),
                save_zone_data_fn=self.save_zone_data,
            )

        # Delegate to manager to set the active pointer
        self.zone_manager.set_active_zone_video(self.project_data, video_path)

    def get_active_zone_video(self) -> str | None:
        """Return the currently active video for zone operations. Delegates to ZoneManager."""
        return self.zone_manager.get_active_zone_video()

    def get_last_zone_video(self, exclude: str | None = None) -> str | None:
        """Return the last video that had zones saved, excluding optional target."""
        return self.zone_manager.get_last_zone_video(self.project_data, exclude)

    def has_zone_data(self, video_path: Path | str | None) -> bool:
        """Check whether the given video currently stores arena or ROI data."""
        return self.zone_manager.has_zone_data(self.project_data, video_path)

    def _has_asset(self, video_path: Path | str | None, asset: AssetType) -> bool:
        entry = self.find_video_entry(path=video_path)
        return AssetManager.video_has_asset(entry, asset) if entry else False

    def has_arena_data(self, video_path: Path | str | None) -> bool:
        """Check if arena data exists for the given video."""
        return self._has_asset(video_path, "arena")

    def has_roi_data(self, video_path: Path | str | None) -> bool:
        """Check if ROI data exists for the given video."""
        return self._has_asset(video_path, "rois")

    def has_trajectory_data(self, video_path: Path | str | None) -> bool:
        """Check if trajectory data exists for the given video."""
        return self._has_asset(video_path, "trajectory")

    def has_summary_data(self, video_path: Path | str | None) -> bool:
        """Check if summary data exists for the given video."""
        return self._has_asset(video_path, "summary")

    def save_zone_data(
        self,
        zone_data: ZoneData,
        video_path: Path | str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        """Persist zone data for the active video and project defaults."""
        self.zone_manager.save_zone_data(
            self.project_data, zone_data, video_path=video_path, persist_callback=None
        )

        if persist:
            target_video = video_path or self.get_active_zone_video()
            ZoneOrchestrationManager.persist_zone_data(
                zone_data,
                target_video=str(target_video) if target_video else None,
                project_path=Path(self.project_path) if self.project_path else None,
                update_video_zone_flags_fn=self._update_video_zone_flags,
                export_zones_to_parquet_fn=self.export_zones_to_parquet,
                find_video_entry_fn=self.find_video_entry,
                save_project_fn=self.save_project,
            )

    def clear_zone_data_for_video(
        self,
        video_path: Path | str,
        *,
        persist: bool = True,
    ) -> None:
        """Remove stored zone data for a specific video."""
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        ZoneOrchestrationManager.clear_zone_data_for_video(
            video_path_str,
            self.project_data,
            get_active_zone_video_fn=self.get_active_zone_video,
            save_project_fn=self.save_project if persist else None,
        )

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
        """Export zone data (arena and ROIs) to parquet files. Delegates to ParquetIOManager."""
        return self.parquet_io_manager.export_zones_to_parquet(
            video_path,
            zone_data,
            project_path=self.project_path,
            find_video_entry_fn=self.find_video_entry,
            resolve_results_directory_fn=self.resolve_results_directory,
        )

    def copy_zone_parquet_files(
        self,
        source_video_path: Path | str,
        target_video_path: Path | str,
        *,
        persist: bool = True,
    ) -> dict[str, str]:
        """Copy arena/ROI parquet files from one video to another. Delegates to ParquetIOManager."""
        return self.parquet_io_manager.copy_zone_parquet_files(
            source_video_path,
            target_video_path,
            project_data=self.project_data,
            set_active_zone_video_fn=self.set_active_zone_video,
            persist=persist,
            scan_input_paths_fn=self.scan_input_paths,
            find_video_entry_fn=self.find_video_entry,
            resolve_results_directory_fn=self.resolve_results_directory,
            save_project_fn=self.save_project,
        )

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
        """Load zone data (arena/ROIs) from parquet files in video_info."""
        parquet_files = video_info.get("parquet_files", {})
        if not parquet_files.get("arena") and not parquet_files.get("rois"):
            log.warning("project_manager.load_zones.no_files", video=video_info.get("path"))
            return None
        return ZoneManager.load_zones_from_parquet(video_info)

    def import_parquets_from_wizard(
        self,
        import_config: list[dict],
        roi_merge_strategy: str = "replace",
        scanned_videos: list[dict] | None = None,
    ) -> bool:
        """Import parquets from wizard configuration. Delegates to ParquetIOManager."""
        return self.parquet_io_manager.import_parquets_from_wizard(
            import_config,
            roi_merge_strategy=roi_merge_strategy,
            scanned_videos=scanned_videos,
            project_data=self.project_data,
            project_path=self.project_path,
            get_zone_data_fn=self.get_zone_data,
            save_zone_data_fn=self.save_zone_data,
            resolve_results_directory_fn=self.resolve_results_directory,
            save_project_fn=self.save_project,
        )

    # ------------------------------------------------------------------
    # Phase 4.2 delegates → ProjectLifecycleManager
    # ------------------------------------------------------------------

    def _save_settings_snapshot(self):
        """Save a snapshot of the current settings to the project directory."""
        return ProjectLifecycleManager.save_settings_snapshot(
            project_path=Path(self.project_path) if self.project_path else None,
            settings_obj=self.settings,
        )

    def _validate_project_parameters(self, **kwargs) -> None:
        """Validate project creation parameters (delegate)."""
        ProjectLifecycleManager.validate_project_parameters(**kwargs)

    def create_new_project(
        self,
        project_path: Path | str,
        project_type: str,
        **kwargs: Any,
    ):
        """Initialize a new project. Delegates to ProjectLifecycleManager.

        Accepts all keyword arguments defined by ``ProjectLifecycleManager.create_new_project``
        (e.g. use_openvino, video_files, num_aquariums, etc.).
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        self.project_path = project_path
        video_files = kwargs.pop("video_files", None)

        self.project_data = ProjectLifecycleManager.create_new_project(
            project_path=project_path,
            project_type=project_type,
            settings_obj=self.settings,
            default_analysis_profile_fn=self.asset_manager._default_analysis_profile,
            add_video_batch_fn=self.add_video_batch,
            save_project_fn=self.save_project,
            video_files=video_files,
            **kwargs,
        )

        # Handle initial video batch and persist
        if video_files:
            self.add_video_batch(video_files, save_project=False)
        self.save_project()

    def add_video_batch(self, video_files: list[dict], save_project: bool = True):
        """Add a new batch of videos to the project (delegate)."""
        ProjectLifecycleManager.add_video_batch(self.project_data, video_files)
        self.invalidate_groups_cache()
        if save_project:
            self.save_project()

    def _apply_project_migrations(
        self, loaded_data: dict, log_context: Any
    ) -> tuple[dict, bool, list[str]]:
        """Apply backward compatibility migrations (delegate)."""
        return ProjectLifecycleManager.apply_project_migrations(
            loaded_data=loaded_data,
            log_context=log_context,
            settings_obj=self.settings,
            default_analysis_profile_fn=self.asset_manager._default_analysis_profile,
        )

    @_threadsafe
    def load_project(self, project_path: Path | str) -> None:
        """Load project data from disk (thread-safe). Delegates to ProjectLifecycleManager."""
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        loaded_data, migration_applied, _ = ProjectLifecycleManager.load_project_data(
            project_path,
            load_config_fn=self.project_service.load_project_config,
            apply_migrations_fn=self._apply_project_migrations,
        )
        self.project_path = project_path
        self.project_data = loaded_data
        if migration_applied:
            self.save_project()
        self._sync_multi_aquarium_flags()
        self.load_metadata()
        self.invalidate_groups_cache()

    def _sync_multi_aquarium_flags(self) -> None:
        """Synchronize has_arena/has_rois flags for multi-aquarium videos (delegate)."""
        ZoneOrchestrationManager.sync_multi_aquarium_flags(
            self.project_data,
            iter_project_videos_fn=self._iter_project_videos,
            get_multi_aquarium_zone_data_fn=self.get_multi_aquarium_zone_data,
        )

    @_threadsafe
    def save_project(self) -> None:
        """Save project data to disk (thread-safe). Delegates to ProjectLifecycleManager."""
        ProjectLifecycleManager.save_project_data(
            self.project_path,
            self.project_data,
            save_config_fn=self.project_service.save_project_config,
        )

    def get_analysis_profiles(self) -> list[dict]:
        """Get analysis profiles."""
        return self.asset_manager.get_analysis_profiles(self.project_data)

    def resolve_analysis_profile(self, metadata: dict | None) -> dict:
        """Resolve analysis profile for metadata."""
        return self.asset_manager.resolve_analysis_profile(self.project_data, metadata)

    def update_video_status(self, video_path: Path | str, new_status) -> bool:
        """Update the status of a specific video. Delegates to VideoManager."""
        # Pass POSIX path since project_data stores paths in POSIX format
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        changed = VideoManager.update_video_status(
            self.project_data, video_path.as_posix(), new_status
        )
        if changed and self.project_path:
            self.save_project()
        return changed

    def reset_all_video_statuses(self, to_status: str = "pending") -> bool:
        """Reset every video status. Delegates to VideoManager."""
        changed = VideoManager.reset_all_video_statuses(self.project_data, to_status)
        if changed:
            self.save_project()
        return changed

    def get_all_videos(self) -> list[dict]:
        """Return a flat list of all videos from all batches. Delegates to VideoManager."""
        return VideoManager.get_all_videos(self.project_data)

    def _iter_project_videos(self) -> Iterator[tuple[dict, dict]]:
        """Yield (batch_dict, video_dict) pairs for every registered video."""
        return VideoManager.iter_project_videos(self.project_data)

    def can_remove_asset(self, video_path: Path | str, asset: AssetType) -> tuple[bool, str | None]:
        """Check if an asset can be removed. Delegates to AssetManager."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = self.find_video_entry(path=video_path)
        if not video_entry:
            return False, "Vídeo não encontrado no projeto."
        return self.asset_manager.can_remove_asset(video_entry, asset)

    def remove_asset(
        self,
        video_path: Path | str,
        asset: AssetType,
        *,
        delete_files: bool = True,
    ) -> bool:
        """Remove an asset from a video entry. Delegates to AssetManager."""
        video_path_str = str(Path(video_path) if isinstance(video_path, str) else video_path)
        video_entry = self.find_video_entry(path=video_path_str)
        if not video_entry:
            log.warning("project_manager.asset.remove_video_missing", path=video_path_str)
            return False

        if asset == "arena":
            changed = self.asset_manager.remove_arena_asset(
                video_path_str,
                video_entry,
                delete_files,
                clear_zone_data_fn=lambda vp: self.clear_zone_data_for_video(vp, persist=False),
            )
        elif asset == "rois":
            changed = self.asset_manager.remove_rois_asset(
                video_path_str,
                video_entry,
                delete_files,
                get_zone_data_fn=self.get_zone_data,
                save_zone_data_fn=self.save_zone_data,
            )
        elif asset == "trajectory":
            changed = self.asset_manager.remove_trajectory_asset(video_entry, delete_files)
        elif asset == "summary":
            changed = self.asset_manager.remove_summary_asset(video_entry, delete_files)
        elif asset == "video":
            changed = self.asset_manager.remove_video_entry(
                video_path_str,
                video_entry,
                delete_files,
                project_data=self.project_data,
                clear_zone_data_fn=lambda vp: self.clear_zone_data_for_video(vp, persist=False),
                refresh_last_zone_source_fn=self._refresh_last_zone_source,
            )
        else:  # pragma: no cover - guarded by type
            raise ValueError(f"Asset type '{asset}' desconhecido.")

        if changed:
            if asset == "video":
                self.invalidate_groups_cache()
            self.save_project()

        return changed

    def find_video_entry(
        self,
        *,
        path: Path | str | None = None,
        experiment_id: str | None = None,
    ) -> dict | None:
        """Return the project entry for a given video path or experiment id."""
        path_str = str(path) if path is not None else None
        return VideoManager.find_video_entry(
            self.project_data, path=path_str, experiment_id=experiment_id
        )

    @staticmethod
    def resolve_group_name(regex_value: str, available_groups: list[str]) -> str:
        """Resolve raw regex value to match project group names."""
        return OutputRegistrationManager.resolve_group_name(regex_value, available_groups)

    def derive_processing_metadata(
        self,
        experiment_id: str,
        video_path: Path | str | None = None,
    ) -> dict:
        """Construct metadata for processing. Delegates to OutputRegistrationManager."""
        return self.output_registration_manager.derive_processing_metadata(
            experiment_id,
            video_path,
            project_data=self.project_data,
            find_video_entry_fn=self.find_video_entry,
            get_available_groups_fn=self.get_available_groups,
        )

    def resolve_results_directory(
        self,
        experiment_id: str,
        *,
        video_path: str | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """Compute the destination directory for analysis artifacts."""
        return self.output_registration_manager.resolve_results_directory(
            experiment_id,
            project_path=self.project_path,
            video_path=video_path,
            metadata=metadata,
            get_metadata_for_experiment_fn=self.get_metadata_for_experiment,
            derive_processing_metadata_fn=self.derive_processing_metadata,
        )

    def register_processing_outputs(
        self,
        video_path: Path | str,
        *,
        results_dir: str | None = None,
        trajectory_path: str | None = None,
        summary_parquet: str | None = None,
        summary_excel: str | None = None,
        report_path: str | None = None,
        experiment_id: str | None = None,
        group: str | None = None,
        day: str | None = None,
        subject_id: str | None = None,
    ) -> bool:
        """Update project metadata with analysis artifacts."""
        return self.output_registration_manager.register_processing_outputs(
            video_path,
            project_path=self.project_path,
            find_video_entry_fn=self.find_video_entry,
            add_video_batch_fn=self.add_video_batch,
            get_zone_data_fn=self.get_zone_data,
            save_project_fn=self.save_project,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
            experiment_id=experiment_id,
            group=group,
            day=day,
            subject_id=subject_id,
        )

    # =========================================================================
    # Multi-Aquarium Support Methods (Phase 8) — delegates
    # =========================================================================

    def resolve_multi_aquarium_results_directories(
        self,
        experiment_id: str,
        aquarium_configs: list[dict],
    ) -> dict[int, Path]:
        """Resolve results directories for multiple aquariums."""
        return self.output_registration_manager.resolve_multi_aquarium_results_directories(
            experiment_id,
            aquarium_configs,
            project_path=self.project_path,
        )

    def register_multi_aquarium_outputs(
        self,
        video_path: Path | str,
        outputs_by_aquarium: dict[int, dict],
    ) -> bool:
        """Register outputs from multiple aquariums. Delegates to OutputRegistrationManager."""
        return self.output_registration_manager.register_multi_aquarium_outputs(
            video_path,
            outputs_by_aquarium,
            project_path=self.project_path,
            find_video_entry_fn=self.find_video_entry,
            save_project_fn=self.save_project,
        )

    def get_multi_aquarium_outputs(
        self,
        video_path: Path | str,
    ) -> dict[int, dict] | None:
        """Get multi-aquarium outputs for a video. Delegates to OutputRegistrationManager."""
        return self.output_registration_manager.get_multi_aquarium_outputs(
            video_path,
            find_video_entry_fn=self.find_video_entry,
        )

    @_threadsafe
    def register_batch_outputs(
        self,
        batch_id: str,
        unified_excel: str,
        session_count: int,
        group: str | None = None,
        day: str | None = None,
        subject_id: str | None = None,
    ) -> bool:
        """Register unified batch report outputs. Delegates to OutputRegistrationManager."""
        return self.output_registration_manager.register_batch_outputs(
            batch_id,
            unified_excel,
            session_count,
            project_data=self.project_data,
            project_path=self.project_path,
            save_project_fn=self.save_project,
            group=group,
            day=day,
            subject_id=subject_id,
        )

    def get_batch_reports(self) -> dict[str, dict]:
        """Get all registered batch reports. Delegates to OutputRegistrationManager."""
        return OutputRegistrationManager.get_batch_reports(self.project_data)

    def get_next_video(self) -> str | None:
        """Return the path of the next video with 'pending' status."""
        return VideoManager.get_next_video(self.project_data)

    def get_project_name(self) -> str:
        """Return the project name, or 'N/A' if not set."""
        return self.project_data.get("project_name", "N/A")

    def get_available_groups(self) -> list[str]:
        """Collect all unique group names used in the project. Delegates to MetadataManager."""
        # Return cached result if valid
        if self._groups_cache_valid and self._groups_cache is not None:
            return self._groups_cache

        self._groups_cache = MetadataManager.get_available_groups(
            self.project_data,
            self.metadata,
            self.get_all_videos,
        )
        self._groups_cache_valid = True
        return self._groups_cache

    def invalidate_groups_cache(self) -> None:
        """Invalidate the groups cache."""
        self._groups_cache_valid = False
        self._groups_cache = None

    def get_project_type(self) -> str | None:
        """Return the project type (e.g. 'batch' or 'live'), or None."""
        return self.project_data.get("project_type")

    def get_zone_data(
        self,
        video_path: Path | str | None = None,
        *,
        fallback_to_global: bool = True,
    ) -> ZoneData:
        """Retrieve zone data for a specific video or fallback to project defaults."""
        return self.zone_manager.get_zone_data(
            self.project_data, video_path=video_path, fallback_to_global=fallback_to_global
        )

    # ------------------------------------------------------------------
    # Convenience arena/ROI accessors
    # ------------------------------------------------------------------

    def set_arena_for_video(
        self,
        video_path: str,
        polygon: Sequence[Sequence[int]] | None,
    ) -> None:
        """Set the arena polygon for a specific video."""
        zone_data = self.get_zone_data(video_path=video_path, fallback_to_global=False)
        zone_data.polygon = polygon or []
        self.save_zone_data(zone_data, video_path, persist=True)

    def get_arena_for_video(
        self,
        video_path: str,
    ) -> Sequence[Sequence[int]] | None:
        """Get the arena polygon for a specific video."""
        zone_data = self.get_zone_data(video_path=video_path, fallback_to_global=False)
        return zone_data.polygon if zone_data.polygon else None

    def set_rois_for_video(
        self,
        video_path: str,
        roi_polygons: Sequence[Sequence[Sequence[int]]] | None = None,
        roi_names: Sequence[str] | None = None,
        roi_colors: Sequence[tuple[int, int, int]] | None = None,
    ) -> None:
        """Set ROIs for a specific video."""
        zone_data = self.get_zone_data(video_path=video_path, fallback_to_global=False)
        zone_data.roi_polygons = roi_polygons or []
        zone_data.roi_names = roi_names or []
        zone_data.roi_colors = roi_colors or []
        self.save_zone_data(zone_data, video_path, persist=True)

    def get_rois_for_video(self, video_path: str) -> dict[str, Any]:
        """Get ROIs for a specific video as a dict."""
        zone_data = self.get_zone_data(video_path=video_path, fallback_to_global=False)
        return {
            "roi_polygons": zone_data.roi_polygons,
            "roi_names": zone_data.roi_names,
            "roi_colors": zone_data.roi_colors,
        }

    def get_multi_aquarium_zone_data(
        self,
        video_path: Path | str | None,
    ) -> MultiAquariumZoneData | None:
        """Retrieve multi-aquarium zone data for a specific video."""
        if video_path is None:
            return None
        return self.zone_manager.get_multi_aquarium_zone_data(self.project_data, video_path)

    def save_multi_aquarium_zone_data(
        self,
        video_path: Path | str | None,
        multi_data: MultiAquariumZoneData,
        *,
        persist: bool = True,
    ) -> None:
        """Save multi-aquarium zone data for a specific video."""
        if video_path is None:
            return

        self.zone_manager.save_multi_aquarium_zone_data(
            self.project_data,
            video_path,
            multi_data,
            persist_callback=None,
        )

        ZoneOrchestrationManager.persist_multi_aquarium_zone_data(
            str(Path(video_path) if isinstance(video_path, str) else video_path),
            multi_data,
            Path(self.project_path) if self.project_path else None,
            export_zones_to_parquet_fn=self.export_zones_to_parquet,
            find_video_entry_fn=self.find_video_entry,
            add_video_batch_fn=self.add_video_batch,
            save_project_fn=self.save_project,
            persist=persist,
        )

    def is_multi_aquarium_video(self, video_path: Path | str | None) -> bool:
        """Check if a video has multi-aquarium configuration."""
        if video_path is None:
            return False

        # Check zone data first (preferred source of truth)
        if self.zone_manager.is_multi_aquarium_video(self.project_data, video_path):
            return True

        # Fallback: check if multi-aquarium outputs are registered
        video_entry = self.find_video_entry(path=video_path)
        if video_entry:
            outputs = video_entry.get("multi_aquarium_outputs", {})
            if len(outputs) >= 2:
                return True

        return False

    def get_aquarium_count(self, video_path: Path | str | None) -> int:
        """Get the number of aquariums configured for a video (1 or 2)."""
        if video_path is None:
            return 1
        return self.zone_manager.get_aquarium_count(self.project_data, video_path)

    def clear_multi_aquarium_zone_data(
        self,
        video_path: Path | str | None,
        *,
        persist: bool = True,
    ) -> None:
        """Clear multi-aquarium zone data for a video."""
        if video_path is None:
            return

        persist_callback = self.save_project if persist else None
        self.zone_manager.clear_multi_aquarium_zone_data(
            self.project_data,
            video_path,
            persist_callback=persist_callback,
        )

    def update_main_polygon(self, points: list) -> None:
        """Update or set the main polygon in project data."""
        self.zone_manager.update_main_polygon(
            self.project_data, points, persist_callback=self.save_project
        )

    def load_metadata(self) -> None:
        """Load the metadata.csv file from the project root. Delegates to MetadataManager."""
        self.metadata = MetadataManager.load_metadata(self.project_path)

    def get_metadata_for_experiment(
        self, experiment_id: str | None, video_path: str | None = None
    ) -> dict:
        """Retrieve metadata for an experiment. Delegates to MetadataManager."""
        return MetadataManager.get_metadata_for_experiment(
            experiment_id,
            video_path,
            metadata_df=self.metadata,
            project_data=self.project_data,
            find_video_entry_fn=self.find_video_entry,
        )

    def save_detector_state(self, detector_config: dict) -> bool:
        """Save detector configuration to project data. Delegates to MetadataManager."""
        return MetadataManager.save_detector_state(
            detector_config,
            project_data=self.project_data,
            project_path=self.project_path,
            save_project_fn=self.save_project,
        )

    def get_detector_state(self) -> dict:
        """Retrieve detector configuration from project data. Delegates to MetadataManager."""
        return MetadataManager.get_detector_state(self.project_data)

    @staticmethod
    def _normalize_detector_thresholds(detector_config: dict | None) -> dict[str, float]:
        """Normalize detector threshold keys. Delegates to MetadataManager."""
        return MetadataManager._normalize_detector_thresholds(detector_config)

    def get_completed_sessions(self) -> set[tuple[int, str, str]]:
        """Scan project for completed session folders. Delegates to MetadataManager."""
        return MetadataManager.get_completed_sessions(self.project_path)

    def save_last_session_details(self, day: int, group: str) -> None:
        """Save last selected day and group. Delegates to MetadataManager."""
        MetadataManager.save_last_session_details(
            day,
            group,
            project_data=self.project_data,
            project_path=self.project_path,
            save_project_fn=self.save_project,
        )

    def get_last_session_details(self) -> tuple[int | None, str | None]:
        """Retrieve last selected day and group. Delegates to MetadataManager."""
        return MetadataManager.get_last_session_details(self.project_data)

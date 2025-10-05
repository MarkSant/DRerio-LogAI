import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import pandas as pd
import structlog
import yaml

from zebtrack.core.detector import ZoneData
from zebtrack.settings import settings
from zebtrack.utils import IntegrityError, calculate_sha256

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"

log = structlog.get_logger()


class ProjectManager:
    def __init__(self):
        self.project_path = None
        self.project_data = {}
        self.metadata = None  # Will hold the DataFrame for metadata.csv

    @staticmethod
    def scan_input_paths(paths: list[str]) -> list[dict]:
        """
        Scans a list of input paths (files or directories) and identifies video files.
        For each video, it checks if corresponding parquet files exist and identifies
        their types (arena, ROIs, trajectory).

        Args:
            paths: A list of file or directory paths.

        Returns:
            A list of dictionaries, where each dictionary represents a video and
            contains detailed information about existing parquet files.
            Example: [{
                'path': 'path/to/video.mp4',
                'has_arena': True,
                'has_rois': True,
                'has_trajectory': True,
                'has_complete_data': True,
                'has_data': True,  # Backward compatibility
                'parquet_files': {
                    'arena': 'path/to/1_ProcessingArea_video.parquet',
                    'rois': 'path/to/2_AreasOfInterest_video.parquet',
                    'trajectory': 'path/to/3_CoordMovimento_video.parquet'
                }
            }, ...]
        """
        video_files = []
        video_extensions = {".mp4", ".avi", ".mov"}

        for p_str in paths:
            p = Path(p_str)
            if p.is_dir():
                # Recursively find all video files in the directory
                for video_path in p.rglob("*"):
                    if video_path.suffix.lower() in video_extensions:
                        video_files.append(video_path)
            elif p.is_file() and p.suffix.lower() in video_extensions:
                video_files.append(p)

        results = []
        for video_path in sorted(list(set(video_files))):  # Sorted unique list
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
                "path": str(video_path),
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

            results.append(result)
            log.info(
                "project_manager.scan_video",
                video=base_name,
                has_arena=has_arena,
                has_rois=has_rois,
                has_trajectory=has_trajectory,
            )

        return results

    @staticmethod
    def load_zones_from_parquet(video_info: dict) -> ZoneData | None:
        """
        Loads zone data (arena and ROIs) from existing parquet files.

        Args:
            video_info: Dictionary returned by scan_input_paths containing
                       'parquet_files' with paths to arena and ROI files.

        Returns:
            ZoneData object with loaded zones, or None if loading failed.
        """
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
                            (0, 255, 0),    # Green
                            (255, 0, 0),    # Blue
                            (0, 0, 255),    # Red
                            (255, 255, 0),  # Cyan
                            (255, 0, 255),  # Magenta
                            (0, 255, 255),  # Yellow
                        ]
                        zone_data.roi_colors = [
                            default_colors[i % len(default_colors)]
                            for i in range(len(roi_names))
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

        except Exception as e:
            log.error(
                "project_manager.load_zones.error",
                video=video_info.get("path"),
                error=str(e),
                exc_info=True,
            )
            return None

    def import_parquets_from_wizard(
        self,
        import_config: list[dict],
        roi_merge_strategy: str = "replace",
        scanned_videos: list[dict] = None,
    ) -> bool:
        """
        Imports arena, ROIs, and trajectory data from existing parquet files.

        This method is called after project creation to import data from parquet files
        based on the wizard's import configuration.

        Args:
            import_config: List of per-video import configurations from wizard:
                [
                    {
                        "video": str,  # Video path
                        "import_arena": bool,
                        "import_rois": bool,
                        "import_trajectory": bool,
                        "action": str,  # ImportAction.value
                    },
                    ...
                ]
            roi_merge_strategy: How to handle ROI conflicts
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

        # Get current zone data
        zone_data = self.get_zone_data()
        imported_count = {"arena": 0, "rois": 0, "trajectory": 0}

        try:
            for config in import_config:
                video_path = config.get("video")
                import_arena = config.get("import_arena", False)
                import_rois = config.get("import_rois", False)
                import_trajectory = config.get("import_trajectory", False)

                if not any([import_arena, import_rois, import_trajectory]):
                    continue  # Skip if nothing to import for this video

                # Get parquet file paths for this video
                parquet_files = video_parquet_map.get(video_path, {})
                if not parquet_files:
                    log.warning(
                        "project_manager.import_parquets.no_parquets",
                        video=Path(video_path).name,
                    )
                    continue

                # Import arena
                if import_arena:
                    arena_path = parquet_files.get("arena")
                    if arena_path and os.path.exists(arena_path):
                        arena_df = pd.read_parquet(arena_path)
                        if not arena_df.empty and "x" in arena_df.columns and "y" in arena_df.columns:
                            polygon_points = arena_df[["x", "y"]].values.tolist()
                            zone_data.polygon = polygon_points
                            imported_count["arena"] += 1
                            log.info(
                                "project_manager.import_parquets.arena_imported",
                                video=Path(video_path).name,
                                points=len(polygon_points),
                            )

                # Import ROIs
                if import_rois:
                    rois_path = parquet_files.get("rois")
                    if rois_path and os.path.exists(rois_path):
                        rois_df = pd.read_parquet(rois_path)
                        if not rois_df.empty:
                            required_cols = {"roi_name", "point_index", "x", "y"}
                            if required_cols.issubset(rois_df.columns):
                                # Load imported ROIs
                                imported_roi_polygons = []
                                imported_roi_names = []

                                for roi_name in rois_df["roi_name"].unique():
                                    roi_df = rois_df[rois_df["roi_name"] == roi_name].sort_values(
                                        "point_index"
                                    )
                                    roi_points = roi_df[["x", "y"]].values.tolist()
                                    imported_roi_polygons.append(roi_points)
                                    imported_roi_names.append(roi_name)

                                # Apply merge strategy
                                if roi_merge_strategy == "replace":
                                    # Replace all existing ROIs
                                    zone_data.roi_polygons = imported_roi_polygons
                                    zone_data.roi_names = imported_roi_names
                                elif roi_merge_strategy == "merge":
                                    # Keep existing ROIs, add imported ones
                                    # Rename conflicts by adding "_imported" suffix
                                    existing_names = set(zone_data.roi_names)
                                    for roi_poly, roi_name in zip(imported_roi_polygons, imported_roi_names):
                                        final_name = roi_name
                                        if roi_name in existing_names:
                                            # Find unique name
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
                                elif roi_merge_strategy == "manual":
                                    # TODO: Implement interactive conflict resolution
                                    log.warning(
                                        "project_manager.import_parquets.manual_strategy_not_implemented",
                                        fallback="replace",
                                    )
                                    zone_data.roi_polygons = imported_roi_polygons
                                    zone_data.roi_names = imported_roi_names

                                # Regenerate colors for all ROIs
                                default_colors = [
                                    (0, 255, 0),    # Green
                                    (255, 0, 0),    # Blue
                                    (0, 0, 255),    # Red
                                    (255, 255, 0),  # Cyan
                                    (255, 0, 255),  # Magenta
                                    (0, 255, 255),  # Yellow
                                ]
                                zone_data.roi_colors = [
                                    default_colors[i % len(default_colors)]
                                    for i in range(len(zone_data.roi_names))
                                ]

                                imported_count["rois"] += len(imported_roi_names)
                                log.info(
                                    "project_manager.import_parquets.rois_imported",
                                    video=Path(video_path).name,
                                    count=len(imported_roi_names),
                                    names=imported_roi_names,
                                    strategy=roi_merge_strategy,
                                )

                # Import trajectory (copy parquet to project folder)
                if import_trajectory:
                    trajectory_path = parquet_files.get("trajectory")
                    if trajectory_path and os.path.exists(trajectory_path):
                        # Copy trajectory parquet to project results folder
                        video_name = Path(video_path).stem
                        results_dir = Path(self.project_path) / f"{video_name}_results"
                        results_dir.mkdir(exist_ok=True)

                        dest_path = results_dir / f"3_CoordMovimento_{video_name}.parquet"

                        import shutil
                        shutil.copy2(trajectory_path, dest_path)

                        imported_count["trajectory"] += 1
                        log.info(
                            "project_manager.import_parquets.trajectory_imported",
                            video=video_name,
                            source=trajectory_path,
                            dest=str(dest_path),
                        )

            # Save updated zone data to project
            from dataclasses import asdict
            self.project_data["detection_zones"] = asdict(zone_data)
            self.save_project()

            log.info(
                "project_manager.import_parquets.success",
                arena_count=imported_count["arena"],
                roi_count=imported_count["rois"],
                trajectory_count=imported_count["trajectory"],
            )
            return True

        except Exception as e:
            log.error(
                "project_manager.import_parquets.error",
                error=str(e),
                exc_info=True,
            )
            return False

    def _save_settings_snapshot(self):
        """Saves a snapshot of the current settings to the project directory."""
        if not self.project_path:
            return False

        snapshot_path = os.path.join(self.project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            settings_dict = settings.model_dump(mode="json")
            with open(snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(settings_dict, f, indent=4, sort_keys=False)
            log.info("settings.snapshot.saved", path=snapshot_path)
            return True
        except (IOError, TypeError) as e:
            log.error("settings.snapshot.save_error", error=str(e))
            return False

    def create_new_project(
        self,
        project_path,
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
        Initializes a new project, creating its directory and config file.
        It no longer handles OpenVINO conversion, just records the settings.
        """
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

        if project_type == "pre-recorded" and not video_files:
            raise ValueError("Pre-recorded projects require a list of video files.")

        try:
            os.makedirs(self.project_path, exist_ok=True)
        except OSError as e:
            log.error("project.create.dir_error", error=str(e))
            messagebox.showerror(
                "Erro na Criação",
                (
                    f"Não foi possível criar o diretório do projeto:\n{e}\n\n"
                    "Por favor, verifique as permissões da pasta e se o "
                    "caminho é válido."
                ),
            )
            return False

        self._save_settings_snapshot()

        safe_camera_index = camera_index if camera_index is not None else 0
        safe_use_arduino = bool(use_arduino)
        safe_arduino_port = arduino_port or ""
        safe_external_trigger = bool(external_trigger_mode) and safe_use_arduino

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
        }

        # Add wizard metadata if provided (from wizard v1.5+)
        if _wizard_metadata:
            self.project_data["_wizard_metadata"] = _wizard_metadata

        if video_files:
            # The initial set of videos becomes the first batch
            self.add_video_batch(video_files, save_project=False)

        return self.save_project()

    def add_video_batch(self, video_files: list[dict], save_project: bool = True):
        """
        Adds a new batch of videos to the project.

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
            video_path = video_info["path"]
            video_hash = calculate_sha256(video_path)
            new_batch["videos"].append(
                {
                    "path": video_path,
                    "sha256": video_hash,
                    "status": "processed" if video_info["has_data"] else "pending",
                }
            )

        self.project_data.setdefault("batches", []).append(new_batch)
        log.info("project.batch.added", count=len(video_files))

        if save_project:
            self.save_project()

    def load_project(self, project_path):
        """
        Loads project data from a config file in the given directory.
        """
        config_path = os.path.join(project_path, CONFIG_FILE_NAME)
        log_context = log.bind(path=config_path)
        log_context.info("project.load.start")

        if not os.path.exists(config_path):
            log_context.error("project.load.not_found")
            messagebox.showerror(
                "Erro ao Carregar",
                (
                    f"Arquivo de configuração do projeto '{CONFIG_FILE_NAME}' não "
                    f"encontrado no diretório selecionado:\n{project_path}\n\n"
                    "Por favor, garanta que você selecionou uma pasta de "
                    "projeto válida."
                ),
            )
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)

            # --- Security Check: File Integrity ---
            expected_hash = loaded_data.pop("file_hash", None)
            if expected_hash:
                canonical_string = json.dumps(
                    loaded_data, sort_keys=True, separators=(",", ":")
                )
                actual_hash = hashlib.sha256(
                    canonical_string.encode("utf-8")
                ).hexdigest()

                if actual_hash != expected_hash:
                    raise IntegrityError(
                        "O arquivo de configuração do projeto está corrompido."
                    )
            # --- End Security Check ---

            # --- Backward Compatibility ---
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
                    message=(
                        "Added missing animals_per_aquarium field with default value 1"
                    ),
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
            # --- End Backward Compatibility ---

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
            return True
        except (json.JSONDecodeError, IOError, IntegrityError) as e:
            log_context.error("project.load.error", exc_info=e)
            messagebox.showerror(
                "Erro ao Carregar",
                f"Falha ao carregar ou analisar o arquivo de configuração do "
                f"projeto:\n{config_path}\n\nO arquivo pode estar corrompido ou "
                f"ilegível.\n\nErro: {e}",
            )
            return False

    def save_project(self):
        """
        Saves the current project data to the config file with an integrity hash.
        """
        # Critical Fix #5: Add validation before saving
        if not self.project_path:
            log.error("project.save.no_path")
            return False

        config_path = os.path.join(self.project_path, CONFIG_FILE_NAME)

        try:
            # Create a copy for hashing to avoid modifying the live object state
            data_to_save = self.project_data.copy()

            # Remove any old hash to ensure it's not part of the new hash
            data_to_save.pop("file_hash", None)

            # Create a canonical JSON string (sorted keys, no extra whitespace)
            # to get a consistent hash.
            canonical_string = json.dumps(
                data_to_save, sort_keys=True, separators=(",", ":")
            )
            new_hash = hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

            # Add the new hash to the data to be saved
            data_to_save["file_hash"] = new_hash

            with open(config_path, "w", encoding="utf-8") as f:
                # Save with indentation for human readability, but hash was
                # calculated on the canonical string.
                json.dump(data_to_save, f, indent=4, sort_keys=True)

            # Update the in-memory project data with the new hash as well
            self.project_data = data_to_save

            log.info("project.save.success", path=config_path, hash=new_hash)
            return True
        except IOError as e:
            log.error("project.save.error", path=config_path, exc_info=e)
            messagebox.showerror(
                "Erro ao Salvar",
                f"Falha ao salvar o arquivo de configuração do projeto:\n"
                f"{config_path}\n\nPor favor, verifique as permissões da "
                f"pasta.\n\nErro: {e}",
            )
            return False

    def update_video_status(self, video_path, new_status):
        """
        Updates the status of a specific video across all batches and saves the project.
        """
        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                if video["path"] == video_path:
                    video["status"] = new_status
                    log.info(
                        "video.status.update",
                        video_path=video_path,
                        status=new_status,
                    )
                    return self.save_project()
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
        """Returns a flat list of all videos from all batches."""
        all_vids = []
        for batch in self.project_data.get("batches", []):
            all_vids.extend(batch.get("videos", []))
        return all_vids

    def get_next_video(self):
        """
        Returns the path of the next video with 'pending' status from all batches.
        """
        for video in self.get_all_videos():
            if video["status"] == "pending":
                return video["path"]
        return None

    def get_project_name(self):
        return self.project_data.get("project_name", "N/A")

    def get_project_type(self):
        return self.project_data.get("project_type")

    def get_zone_data(self) -> ZoneData:
        """
        Retrieves zone data from the project configuration, returning a ZoneData object.
        """
        zone_dict = self.project_data.get("detection_zones", {})
        if zone_dict:
            # Pydantic dataclasses can be instantiated from dictionaries
            return ZoneData(**zone_dict)
        return ZoneData()

    def update_main_polygon(self, points: list):
        """Atualiza ou define o polígono principal nos dados do projeto."""
        from dataclasses import asdict

        log.info(
            "project_manager.polygon.updating",
            points_count=len(points),
            project_path=self.project_path,
            has_project_data=bool(self.project_data),
        )

        try:
            # Validação de estado interno
            if not self.project_data:
                log.error("project_manager.polygon.no_project_data")
                raise ValueError("Dados do projeto não inicializados")

            # Obter dados de zona atual
            zone_data = self.get_zone_data()
            log.debug(
                "project_manager.polygon.zone_data_loaded",
                current_polygon_exists=bool(zone_data.polygon),
                current_roi_count=len(zone_data.roi_polygons),
            )

            # Atualizar polígono
            old_polygon = zone_data.polygon
            zone_data.polygon = points
            log.info(
                "project_manager.polygon.polygon_updated",
                old_points=len(old_polygon) if old_polygon else 0,
                new_points=len(points),
            )

            # Salvar estrutura atualizada
            self.project_data["detection_zones"] = asdict(zone_data)
            log.debug("project_manager.polygon.data_structure_updated")

            # Persistir no arquivo
            self.save_project()
            log.info(
                "project_manager.polygon.saved_successfully",
                project_file=f"{self.project_path}/project.json"
                if self.project_path
                else "unknown",
            )

        except Exception as e:
            log.error(
                "project_manager.polygon.update_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def load_metadata(self):
        """Loads the metadata.csv file from the project root into a pandas DataFrame."""
        if not self.project_path:
            return

        metadata_path = os.path.join(self.project_path, "metadata.csv")
        if os.path.exists(metadata_path):
            try:
                self.metadata = pd.read_csv(metadata_path)
                log.info("project.metadata.loaded", path=metadata_path)
            except Exception as e:
                self.metadata = None
                log.error(
                    "project.metadata.load_error", path=metadata_path, error=str(e)
                )
                messagebox.showwarning(
                    "Aviso de Metadados",
                    "Não foi possível carregar ou analisar 'metadata.csv'.\n\n"
                    f"Erro: {e}",
                )
        else:
            self.metadata = None
            log.info("project.metadata.not_found", path=metadata_path)

    def get_metadata_for_experiment(self, experiment_id: str) -> dict:
        """
        Retrieves a dictionary of metadata for a given experiment ID.
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
                log.warning(
                    "metadata.fallback.parse_error", experiment_id=experiment_id
                )

        # If neither method works, return an empty dictionary
        return {}

    def save_detector_state(self, detector_config: dict) -> bool:
        """
        Saves detector configuration to project data.

        Args:
            detector_config: Dictionary with keys plugin_name, confidence_threshold,
                           nms_threshold, context, last_updated

        Returns:
            bool: True if saved successfully, False otherwise
        """
        if not self.project_data:
            log.error("project.detector_state.save.no_project_data")
            return False

        log.info("project.detector_state.save.start", config=detector_config)

        try:
            # Add timestamp if not provided
            if "last_updated" not in detector_config:
                detector_config["last_updated"] = datetime.now().isoformat()

            self.project_data["detector_config"] = detector_config
            result = self.save_project()

            if result:
                log.info("project.detector_state.save.success",
                        plugin=detector_config.get("plugin_name"))
            else:
                log.error("project.detector_state.save.error",
                         message="save_project returned False")

            return result

        except Exception as e:
            log.error("project.detector_state.save.error", error=str(e), exc_info=True)
            return False

    def get_detector_state(self) -> dict:
        """
        Retrieves detector configuration from project data.

        Returns:
            dict: Detector configuration or empty dict if not found
        """
        return self.project_data.get("detector_config", {})

    def get_completed_sessions(self) -> set[tuple[int, str, int]]:
        """
        Scans the project directory for completed session folders and returns them.
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
        """Saves the last selected day and group to the project config."""
        if not self.project_path:
            return
        self.project_data["last_selected_day"] = day
        self.project_data["last_selected_group"] = group
        self.save_project()

    def get_last_session_details(self) -> tuple[int | None, str | None]:
        """Retrieves the last selected day and group from the project config."""
        if not self.project_data:
            return None, None

        day = self.project_data.get("last_selected_day")
        group = self.project_data.get("last_selected_group")
        return day, group

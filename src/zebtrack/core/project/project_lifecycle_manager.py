"""Project lifecycle management — creation, migration, and batch assembly.

Phase 4.2: Extracted from ProjectManager to reduce class size.
Handles project initialization, parameter validation, settings snapshot,
video batch construction, and backward-compatibility migrations.

All methods are static or class-level — they receive explicit data/callbacks
instead of holding references, avoiding circular dependencies.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.utils import IntegrityError, calculate_sha256

if TYPE_CHECKING:
    from collections.abc import Callable

log = structlog.get_logger()

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"


class ProjectLifecycleManager:
    """Handles project creation, migration, and video batch assembly.

    All public methods are static — they receive explicit parameters and
    callback functions, keeping this class free of circular import issues.
    """

    # ------------------------------------------------------------------
    # Project persistence (load / save)
    # ------------------------------------------------------------------

    @staticmethod
    def load_project_data(
        project_path: Path,
        load_config_fn: Callable[[Path], dict],
        apply_migrations_fn: Callable[[dict, Any], tuple[dict, bool, list[str]]],
    ) -> tuple[dict, bool, list[str]]:
        """Load, validate, and migrate project data from disk.

        Args:
            project_path: Directory containing the project config.
            load_config_fn: Callable that reads config from project_path.
            apply_migrations_fn: Callable(loaded_data, log_context) → (data, applied, fields).

        Returns:
            Tuple of (project_data, migration_applied, migrated_fields).

        Raises:
            ProjectInvalidError: If config file not found or unreadable.
        """
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
            loaded_data = load_config_fn(project_path)
            loaded_data, migration_applied, migrated_fields = apply_migrations_fn(
                loaded_data, log_context
            )
            log_context.info(
                "project.load.success",
                project_name=loaded_data.get("project_name"),
            )
            return loaded_data, migration_applied, migrated_fields
        except (OSError, json.JSONDecodeError, IntegrityError) as e:
            log_context.error("project.load.error", exc_info=e)
            raise ProjectInvalidError(
                message=f"Falha ao carregar ou analisar o arquivo de configuração do projeto: "
                f"{config_path}\n\nO arquivo pode estar corrompido ou ilegível.\n\nErro: {e}",
                path=project_path,
                cause=e,
            ) from e

    @staticmethod
    def save_project_data(
        project_path: Path | str | None,
        project_data: dict,
        save_config_fn: Callable[[Path | str, dict], None],
    ) -> None:
        """Persist project data to disk with validation and error handling.

        Args:
            project_path: Directory where the config file lives.
            project_data: The project dict to serialize.
            save_config_fn: Callable(project_path, project_data) that writes JSON.

        Raises:
            ProjectInvalidError: If project path is not set or save fails.
        """
        if not project_path:
            log.debug("project.save.no_path", reason="project not yet created")
            raise ProjectInvalidError(
                message="Não é possível salvar o projeto: caminho do projeto não definido.\n\n"
                "O projeto deve ser criado antes de ser salvo.",
            )

        try:
            save_config_fn(project_path, project_data)
            log.info("project.save.success", path=project_path)
        except PermissionError as e:
            log.error("project.save.permission_denied", path=project_path, exc_info=e)
            raise ProjectInvalidError(
                message=(
                    f"Permissão negada ao salvar o projeto: {project_path}\n\n"
                    f"Verifique se você tem permissão de escrita na pasta.\n\nErro: {e}"
                ),
                path=project_path,
                cause=e,
            ) from e
        except OSError as e:
            log.error("project.save.io_error", path=project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro de I/O ao salvar o projeto: "
                f"{project_path}\n\nVerifique o espaço em disco e permissões.\n\nErro: {e}",
                path=project_path,
                cause=e,
            ) from e
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.error("project.save.serialization_error", path=project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro ao serializar dados do projeto: "
                f"{project_path}\n\nDados do projeto podem estar corrompidos.\n\nErro: {e}",
                path=project_path,
                cause=e,
            ) from e
        # except Exception justified: project persistence boundary — heterogeneous I/O
        except Exception as e:
            log.error("project.save.unexpected_error", path=project_path, exc_info=e)
            raise ProjectInvalidError(
                message=f"Erro inesperado ao salvar o projeto: "
                f"{project_path}\n\nPor favor, verifique as permissões da pasta.\n\nErro: {e}",
                path=project_path,
                cause=e,
            ) from e

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_project_parameters(
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

        # Phase 1.2: Calibration dimensions — 0 means "no calibration", valid
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

    # ------------------------------------------------------------------
    # Settings snapshot
    # ------------------------------------------------------------------

    @staticmethod
    def save_settings_snapshot(
        project_path: Path | None,
        settings_obj: Any,
    ) -> bool:
        """Save a snapshot of the current settings to the project directory.

        Args:
            project_path: Path to the project directory.
            settings_obj: Pydantic Settings object (or None / mock).

        Returns:
            True if saved successfully (or gracefully skipped), False on error.
        """
        if not project_path:
            return False

        snapshot_path = os.path.join(project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            # Check if settings is available and is a real settings object (not a mock)
            if settings_obj is None:
                log.debug("settings.snapshot.skipped", reason="settings not injected")
                return True  # Don't block project creation in tests

            if not hasattr(settings_obj, "model_dump_json") or not callable(
                settings_obj.model_dump_json
            ):
                log.debug(
                    "settings.snapshot.skipped",
                    reason="settings not available or mocked",
                )
                return True

            json_str = settings_obj.model_dump_json()
            # Verify it's actually a string (not a mock)
            if not isinstance(json_str, str):
                log.debug(
                    "settings.snapshot.skipped",
                    reason="model_dump_json returned non-string",
                )
                return True

            settings_dict = json.loads(json_str)
            with open(snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(settings_dict, f, indent=4, sort_keys=False)
            log.info("settings.snapshot.saved", path=snapshot_path)
            return True
        except (OSError, TypeError, ValueError) as e:
            log.error("settings.snapshot.save_error", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Project creation
    # ------------------------------------------------------------------

    @staticmethod
    def create_new_project(
        project_path: Path | str,
        project_type: str,
        settings_obj: Any,
        default_analysis_profile_fn,
        add_video_batch_fn,
        save_project_fn,
        *,
        use_openvino: bool = False,
        openvino_device: str = "AUTO",
        active_weight: str | None = None,
        video_files: list | None = None,
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
        experiment_days: int | None = None,
        subjects_per_group: int | None = None,
        num_groups: int | None = None,
        group_names: list[str] | None = None,
        _wizard_metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Initialize a new project, creating its directory and config file.

        Returns the assembled ``project_data`` dict (the caller must assign it
        to ``self.project_data`` and ``self.project_path``).

        Args:
            project_path: Directory where the project lives.
            project_type: "Pre-recorded" or "Live".
            settings_obj: Injected Settings instance (may be None in tests).
            default_analysis_profile_fn: Callable returning a default profile dict.
            add_video_batch_fn: Callable(video_files, save_project=False) for initial videos.
            save_project_fn: Callable() to persist the project JSON.
            **kwargs: All remaining project parameters — see ``ProjectManager.create_new_project``.

        Returns:
            The fully assembled ``project_data`` dictionary.
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path

        log_context = log.bind(
            project_path=project_path,
            project_type=project_type,
            use_openvino=use_openvino,
            active_weight=active_weight,
            num_aquariums=num_aquariums,
            animals_per_aquarium=animals_per_aquarium,
        )
        log_context.info("project.create.start")

        # Validate all parameters
        ProjectLifecycleManager.validate_project_parameters(
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

        try:
            os.makedirs(project_path, exist_ok=True)
        except OSError as e:
            log.error("project.create.dir_error", error=str(e))
            raise ProjectInvalidError(
                message=(
                    f"Não foi possível criar o diretório do projeto: {e}\n\n"
                    "Por favor, verifique as permissões da pasta e se o caminho é válido."
                ),
                path=project_path,
                cause=e,
            ) from e

        ProjectLifecycleManager.save_settings_snapshot(project_path, settings_obj)

        safe_camera_index = camera_index if camera_index is not None else 0
        safe_use_arduino = bool(use_arduino)
        safe_arduino_port = arduino_port or ""
        safe_external_trigger = bool(external_trigger_mode) and safe_use_arduino
        if use_single_subject_tracker is None:
            tracker_pref = animals_per_aquarium == 1
        else:
            tracker_pref = bool(use_single_subject_tracker)

        project_data: dict[str, Any] = {
            "project_name": os.path.basename(project_path),
            "project_type": project_type,
            "calibration": {
                "num_aquariums": num_aquariums,
                "animals_per_aquarium": animals_per_aquarium,
                "aquarium_width_cm": aquarium_width_cm,
                "aquarium_height_cm": aquarium_height_cm,
            },
            "use_openvino": use_openvino,
            "openvino_device": (openvino_device or "AUTO").upper(),
            "active_weight": active_weight,
            "model_overrides": {
                "active_weight": None,
                "use_openvino": None,
                "device": (openvino_device or "AUTO").upper(),
            },
            "use_timed_recording": use_timed_recording,
            "recording_duration_s": recording_duration_s,
            "use_countdown": use_countdown,
            "countdown_duration_s": countdown_duration_s,
            "batches": [],
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
            "analysis_profiles": [default_analysis_profile_fn()],
            "roi_templates": [],
        }

        # Add wizard metadata if provided (from wizard v1.5+)
        if _wizard_metadata:
            project_data["_wizard_metadata"] = _wizard_metadata
            _apply_wizard_multi_aquarium(project_data, _wizard_metadata)

        log_context.info("project.create.success")
        return project_data

    # ------------------------------------------------------------------
    # Video batch construction
    # ------------------------------------------------------------------

    @staticmethod
    def add_video_batch(
        project_data: dict[str, Any],
        video_files: list[dict],
    ) -> None:
        """Build a new batch dict from *video_files* and append it to *project_data*.

        This is a pure data-manipulation helper; it does **not** call
        ``save_project`` — the caller decides when to persist.

        Args:
            project_data: The mutable project data dictionary.
            video_files: A list of video dicts from ``scan_input_paths``.
        """
        if not video_files:
            return

        new_batch: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "videos": [],
        }

        for video_info in video_files:
            # Handle both string paths and dict formats
            if isinstance(video_info, str):
                video_path = video_info
                has_data = False
                metadata: dict[str, Any] = {}
                video_info = {"path": video_path}
            else:
                video_path = video_info["path"]
                has_data = bool(
                    video_info.get(
                        "has_data",
                        video_info.get("has_complete_data", False),
                    )
                )
                metadata = dict(video_info.get("metadata") or {})

            # Ensure video_path is always a POSIX string for consistency
            video_path = Path(video_path).as_posix()
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
                    value != "" or isinstance(value, int | float | bool | list)
                ):
                    metadata.setdefault(key, value)

            # Remove empty values to keep JSON compact
            filtered_metadata: dict[str, Any] = {
                key: value
                for key, value in metadata.items()
                if value is not None
                and (value != "" or isinstance(value, int | float | bool | list | dict))
            }

            video_entry: dict[str, Any] = {
                "path": video_path,
                "sha256": video_hash,
                "status": "processed" if has_data else "pending",
                "has_arena": bool(video_info.get("has_arena", False)),
                "has_rois": bool(video_info.get("has_rois", False)),
                "has_trajectory": bool(video_info.get("has_trajectory", False)),
                "has_complete_data": bool(
                    video_info.get("has_complete_data", has_data),
                ),
                "zones_finalized": False,
            }

            if filtered_metadata:
                video_entry["metadata"] = filtered_metadata

            new_batch["videos"].append(video_entry)

        project_data.setdefault("batches", []).append(new_batch)

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

    # ------------------------------------------------------------------
    # Backward-compatibility migrations
    # ------------------------------------------------------------------

    @staticmethod
    def apply_project_migrations(
        loaded_data: dict,
        log_context: Any,
        settings_obj: Any = None,
        default_analysis_profile_fn=None,
    ) -> tuple[dict, bool, list[str]]:
        """Apply backward compatibility migrations to loaded project data.

        Args:
            loaded_data: Raw project data dictionary loaded from JSON.
            log_context: Bound structlog logger for contextual logging.
            settings_obj: Settings instance (for tracker default).
            default_analysis_profile_fn: Callable returning a default profile dict.

        Returns:
            Tuple of (migrated_data, migration_applied, migrated_fields).
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
                message="Added missing animals_per_aquarium field with default value 1",
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
            default_profile = (
                default_analysis_profile_fn()
                if default_analysis_profile_fn
                else {
                    "name": "Padrão",
                    "description": "Perfil padrão de análise",
                    "settings": {},
                }
            )
            loaded_data["analysis_profiles"] = [default_profile]
            migration_applied = True
            migrated_fields.append("analysis_profiles")

        # Use settings if available, otherwise default to False
        tracker_flag = False
        if settings_obj and hasattr(settings_obj, "tracking"):
            tracker_flag = settings_obj.tracking.use_single_subject_tracker
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

        if "openvino_device" not in loaded_data or loaded_data["openvino_device"] is None:
            loaded_data["openvino_device"] = "AUTO"
            migration_applied = True
            migrated_fields.append("openvino_device")

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
            overrides = {"active_weight": None, "use_openvino": None, "device": "AUTO"}
            overrides_updated = True
        else:
            if "active_weight" not in overrides:
                overrides["active_weight"] = None
                overrides_updated = True
            if "use_openvino" not in overrides:
                overrides["use_openvino"] = None
                overrides_updated = True
            if "device" not in overrides:
                overrides["device"] = loaded_data.get("openvino_device", "AUTO")
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


# ------------------------------------------------------------------
# Module-level helper (avoids method bloat)
# ------------------------------------------------------------------


def _apply_wizard_multi_aquarium(
    project_data: dict[str, Any],
    wizard_metadata: dict,
) -> None:
    """Inject ``multi_aquarium`` config from wizard regex patterns.

    Called during ``create_new_project`` when ``_wizard_metadata`` is provided.
    """
    custom_patterns = wizard_metadata.get("custom_regex_patterns")
    if not custom_patterns or not isinstance(custom_patterns, dict):
        return

    from zebtrack.ui.wizard.models import MultiAquariumData

    try:
        combined_pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=custom_patterns.get("group_pattern"),
            day_pattern=custom_patterns.get("day_pattern"),
            subject_pattern=custom_patterns.get("subject_pattern"),
        )

        if combined_pattern:
            project_data["calibration"]["multi_aquarium"] = {
                "enabled": False,
                "regex_pattern": combined_pattern,
                "regex_group_field": "group",
                "regex_subject_field": "subject",
                "regex_day_field": "day",
                "aquarium_configs": [],
            }
            log.info(
                "project.create.multi_aquarium_config_saved",
                has_regex=True,
                regex_pattern_preview=combined_pattern[:80],
            )
        else:
            log.warning(
                "project.create.multi_aquarium_no_combined_pattern",
                group_pattern=custom_patterns.get("group_pattern"),
                day_pattern=custom_patterns.get("day_pattern"),
                subject_pattern=custom_patterns.get("subject_pattern"),
            )
    # except Exception justified: legacy data migration — unknown data format variants
    except Exception as e:
        log.error(
            "project.create.multi_aquarium_conversion_failed",
            error=str(e),
            patterns=custom_patterns,
        )

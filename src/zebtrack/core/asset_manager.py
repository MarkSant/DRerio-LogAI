"""Asset management module for ZebTrack-AI projects.

Handles all asset-related operations including:
- ROI template management (save, load, import, list)
- Analysis profile management
- Asset removal (arena, ROIs, trajectory, summary, video)
- File deletion operations

This module was extracted from ProjectManager during Phase 2 refactoring
to reduce the God Object pattern and improve maintainability.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import unicodedata
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import structlog

from zebtrack.core.detector import ZoneData
from zebtrack.core.roi_template_manager import ROITemplateManager
from zebtrack.core.types import AssetType

log = structlog.get_logger()


class AssetManager:
    """Manages asset-related operations for ZebTrack-AI projects.

    Responsibilities:
    - ROI template persistence and retrieval
    - Analysis profile matching and resolution
    - Asset validation and removal
    - File deletion operations

    This class operates on project_data dictionaries and uses
    ROITemplateManager for low-level template operations.
    """

    _PROFILE_SYNONYMS: ClassVar[dict[str, tuple[str, ...]]] = {
        "group": (
            "group",
            "group_id",
            "group_name",
            "group_display_name",
        ),
        "day": (
            "day",
            "day_id",
            "day_label",
            "day_display_name",
        ),
        "subject": (
            "subject",
            "subject_id",
            "subject_label",
            "individual",
            "individuo",
            "animal",
            "animal_id",
            "cobaia",
        ),
        "experiment_id": ("experiment_id", "video_name"),
    }

    def __init__(self):
        """Initialize AssetManager with ROITemplateManager."""
        self.roi_template_manager = ROITemplateManager()

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert a string into a URL-friendly slug.

        Args:
            value: String to slugify

        Returns:
            Slugified string
        """
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", normalized).strip("-")
        return normalized.lower() or "template"

    @staticmethod
    def ensure_roi_template_dir(project_path: Path | str) -> Path:
        """Ensure ROI template directory exists in project.

        Args:
            project_path: Path to the project directory

        Returns:
            Path to ROI template directory

        Raises:
            ValueError: If project_path is None
        """
        if not project_path:
            raise ValueError("Projeto não inicializado para salvar templates de ROI.")
        target = Path(project_path) / "roi_templates"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def list_roi_templates(
        self,
        project_data: dict,
        *,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        """List all available ROI templates (project + global).

        Args:
            project_data: The project data dictionary
            include_global: Whether to include global templates

        Returns:
            List of template metadata dictionaries
        """
        # Ensure zone structures exist
        if "roi_templates" not in project_data or not isinstance(
            project_data.get("roi_templates"), list
        ):
            project_data["roi_templates"] = []

        aggregated: list[dict[str, Any]] = []

        for item in project_data.get("roi_templates", []):
            if not isinstance(item, dict):
                continue

            entry = deepcopy(item)
            entry.setdefault("location", "project")
            entry.setdefault("includes_arena", True)
            entry.setdefault("includes_rois", True)
            aggregated.append(entry)

        if include_global:
            try:
                global_entries = self.roi_template_manager.list_global_templates()
            except Exception as exc:  # pragma: no cover - defensive telemetry
                log.warning(
                    "asset_manager.roi_templates.global_list_failed",
                    error=str(exc),
                )
                global_entries = []

            for item in global_entries:
                if not isinstance(item, dict):
                    continue
                entry = dict(item)
                entry.setdefault("location", "global")
                entry.setdefault("includes_arena", True)
                entry.setdefault("includes_rois", True)
                aggregated.append(entry)

        def _sort_key(template: dict[str, Any]) -> tuple[int, str]:
            location = template.get("location", "project")
            priority = 0 if location == "project" else 1
            name = str(template.get("name", "")).lower()
            return priority, name

        return sorted(aggregated, key=_sort_key)

    @staticmethod
    def _resolve_roi_template_entry(
        project_data: dict, name: str
    ) -> tuple[int, dict[str, Any]] | tuple[None, None]:
        """Find a ROI template entry by name in project data.

        Args:
            project_data: The project data dictionary
            name: Template name to search for

        Returns:
            Tuple of (index, entry_dict) if found, (None, None) otherwise
        """
        templates = project_data.get("roi_templates", [])
        for idx, entry in enumerate(templates):
            if not isinstance(entry, dict):
                continue
            if entry.get("name") == name:
                return idx, entry
        return None, None

    def save_roi_template(
        self,
        project_data: dict,
        project_path: Path | str,
        name: str,
        zone_data: ZoneData,
        zone_data_to_dict_fn: Callable[[ZoneData | None], dict],
        *,
        save_arena: bool = True,
        save_rois: bool = True,
        save_location: Literal["project", "global", "custom"] | None = "project",
        custom_path: str | Path | None = None,
        overwrite: bool = True,
        persist_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Save a ROI template to project or global storage.

        Args:
            project_data: The project data dictionary to modify
            project_path: Path to the project directory
            name: Template name
            zone_data: ZoneData to save
            zone_data_to_dict_fn: Function to serialize ZoneData
            save_arena: Whether to include arena polygon
            save_rois: Whether to include ROIs
            save_location: Where to save ("project", "global", "custom")
            custom_path: Custom path for custom location
            overwrite: Whether to overwrite existing template
            persist_callback: Optional callback to persist project after save

        Returns:
            Template metadata dictionary

        Raises:
            ValueError: If validation fails
        """
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise ValueError("O nome do template não pode ficar vazio.")

        if zone_data is None:
            raise ValueError("Dados de zona inválidos para salvar o template.")

        if not save_arena and not save_rois:
            raise ValueError("Selecione ao menos arena ou ROIs para salvar.")

        target_location: Literal["project", "global", "custom"]
        target_location = save_location or "project"

        if target_location == "project":
            if not project_path:
                raise ValueError(
                    "Não é possível salvar o template no projeto atual: projeto não carregado."
                )

            # Ensure zone structures
            if "roi_templates" not in project_data or not isinstance(
                project_data.get("roi_templates"), list
            ):
                project_data["roi_templates"] = []

            existing_index, existing_entry = self._resolve_roi_template_entry(
                project_data, normalized_name
            )
            if existing_entry and not overwrite:
                raise ValueError(f"Template '{normalized_name}' já existe.")

            if existing_entry:
                slug = existing_entry.get("slug") or self._slugify(normalized_name)
            else:
                slug = self._slugify(normalized_name)
                collision = any(
                    entry.get("slug") == slug
                    for entry in project_data.get("roi_templates", [])
                    if isinstance(entry, dict)
                )
                counter = 2
                base_slug = slug
                while collision:
                    slug = f"{base_slug}-{counter}"
                    collision = any(
                        entry.get("slug") == slug
                        for entry in project_data.get("roi_templates", [])
                        if isinstance(entry, dict)
                    )
                    counter += 1

            metadata = self.roi_template_manager.save_template(
                normalized_name,
                zone_data,
                slug=slug,
                save_arena=save_arena,
                save_rois=save_rois,
                save_location="project",
                project_path=str(project_path) if project_path else None,
                overwrite=overwrite,
            )

            project_path_obj = Path(project_path)
            metadata["file"] = os.path.relpath(metadata["file"], project_path_obj)
            metadata["location"] = "project"
            metadata.setdefault("includes_arena", save_arena)
            metadata.setdefault("includes_rois", save_rois)

            if existing_entry:
                metadata["created_at"] = existing_entry.get(
                    "created_at", metadata.get("created_at")
                )

            stored_metadata = {
                "name": metadata.get("name", normalized_name),
                "slug": metadata.get("slug"),
                "file": metadata.get("file"),
                "roi_count": metadata.get("roi_count", 0),
                "updated_at": metadata.get("updated_at"),
                "created_at": metadata.get("created_at"),
                "location": metadata.get("location", "project"),
                "includes_arena": metadata.get("includes_arena", True),
                "includes_rois": metadata.get("includes_rois", True),
            }

            templates = project_data.setdefault("roi_templates", [])
            if existing_index is not None:
                templates[existing_index] = stored_metadata
            else:
                templates.append(stored_metadata)

            if persist_callback:
                persist_callback()

            return deepcopy(stored_metadata)

        metadata = self.roi_template_manager.save_template(
            normalized_name,
            zone_data,
            save_arena=save_arena,
            save_rois=save_rois,
            save_location=target_location,
            project_path=str(project_path) if project_path else None,
            custom_path=custom_path,
            overwrite=overwrite,
        )
        metadata["location"] = target_location
        return metadata

    def import_roi_template(
        self,
        project_data: dict,
        project_path: Path | str | None,
        file_path: Path | str,
        zone_data_from_dict_fn: Callable[[dict], ZoneData],
        zone_data_to_dict_fn: Callable[[ZoneData | None], dict],
        *,
        name: str | None = None,
        persist_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Import a ROI template from a JSON file.

        Args:
            project_data: The project data dictionary to modify
            project_path: Path to the project directory (None if no project loaded)
            file_path: Path to the template JSON file
            zone_data_from_dict_fn: Function to deserialize ZoneData
            zone_data_to_dict_fn: Function to serialize ZoneData
            name: Optional custom name for imported template
            persist_callback: Optional callback to persist project after import

        Returns:
            Template metadata dictionary

        Raises:
            FileNotFoundError: If file_path doesn't exist
            ValueError: If file is invalid
        """
        file_path = Path(file_path) if isinstance(file_path, str) else file_path
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        with open(file_path, encoding="utf-8") as handle:
            payload = json.load(handle)

        data_block = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data_block, dict):
            raise ValueError("Arquivo de template inválido: bloco 'data' ausente.")

        zone_data = zone_data_from_dict_fn(data_block)
        template_name = name or payload.get("name") or file_path.stem

        has_arena = bool(zone_data.polygon)
        has_rois = bool(zone_data.roi_polygons)

        project_available = bool(project_path)
        target_location: Literal["project", "global"] = "project" if project_available else "global"
        effective_persist_callback = persist_callback if project_available else None

        return self.save_roi_template(
            project_data=project_data,
            project_path=project_path or "",
            name=template_name,
            zone_data=zone_data,
            zone_data_to_dict_fn=zone_data_to_dict_fn,
            save_arena=has_arena,
            save_rois=has_rois,
            save_location=target_location,
            persist_callback=effective_persist_callback,
        )

    def load_roi_template(
        self,
        project_data: dict,
        project_path: Path | str | None,
        name: str,
        zone_data_from_dict_fn: Callable[[dict], ZoneData],
        *,
        location: Literal["project", "global", "custom"] | None = None,
        file_path: str | Path | None = None,
    ) -> ZoneData:
        """Load a ROI template by name from project or global storage.

        Args:
            project_data: The project data dictionary
            project_path: Path to the project directory
            name: Template name to load
            zone_data_from_dict_fn: Function to deserialize ZoneData
            location: Where to look ("project", "global", "custom", or None for both)
            file_path: Optional custom file path

        Returns:
            ZoneData object

        Raises:
            ValueError: If template not found or invalid
            FileNotFoundError: If template file doesn't exist
        """
        if location in (None, "project"):
            _, entry = self._resolve_roi_template_entry(project_data, name)
            if entry:
                relative_file = entry.get("file")
                if not relative_file:
                    raise ValueError("Arquivo do template não registrado no projeto.")

                template_path = (
                    Path(project_path) / relative_file if project_path else Path(relative_file)
                )
                if not template_path.exists():
                    raise FileNotFoundError(str(template_path))

                with open(template_path, encoding="utf-8") as handle:
                    payload = json.load(handle)

                data_block = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data_block, dict):
                    raise ValueError("Conteúdo do template inválido.")

                return zone_data_from_dict_fn(data_block)

            if location == "project":
                raise ValueError(f"Template de ROI '{name}' não encontrado no projeto.")

        template_path = Path(file_path) if file_path else None

        if template_path is None and location in (None, "global"):
            for entry in self.roi_template_manager.list_global_templates():
                if entry.get("name") == name:
                    file_candidate = entry.get("file")
                    if file_candidate:
                        template_path = Path(file_candidate)
                        break

        if template_path is None:
            raise ValueError(f"Template de ROI '{name}' não encontrado para o contexto solicitado.")

        if not template_path.exists():
            raise FileNotFoundError(str(template_path))

        with open(template_path, encoding="utf-8") as handle:
            payload = json.load(handle)

        data_block = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data_block, dict):
            raise ValueError("Conteúdo do template inválido.")

        return zone_data_from_dict_fn(data_block)

    # ------------------------------------------------------------------
    # Analysis Profile Management
    # ------------------------------------------------------------------

    @staticmethod
    def _default_analysis_profile() -> dict:
        """Return the default analysis profile.

        Returns:
            Default profile dictionary
        """
        return {
            "name": "default",
            "criteria": {},
            "track_ids": [],
            "social": {"enabled": False, "radius_cm": 5.0},
        }

    def get_analysis_profiles(self, project_data: dict) -> list[dict]:
        """Get all analysis profiles from project data.

        Args:
            project_data: The project data dictionary

        Returns:
            List of analysis profile dictionaries
        """
        profiles = project_data.get("analysis_profiles")
        if not profiles:
            profiles = [self._default_analysis_profile()]
            project_data["analysis_profiles"] = profiles
        return deepcopy(profiles)

    def resolve_analysis_profile(self, project_data: dict, metadata: dict | None) -> dict:
        """Resolve which analysis profile to use based on metadata.

        Args:
            project_data: The project data dictionary
            metadata: Video metadata to match against

        Returns:
            Matched profile dictionary (or default fallback)
        """
        metadata = metadata or {}
        profiles = self.get_analysis_profiles(project_data)

        fallback = profiles[0] if profiles else self._default_analysis_profile()
        for profile in profiles:
            criteria = profile.get("criteria") or {}
            if not criteria:
                fallback = profile
                continue
            if self._profile_matches(criteria, metadata):
                return profile

        return fallback

    def _profile_matches(self, criteria: dict, metadata: dict) -> bool:
        """Check if metadata matches profile criteria.

        Args:
            criteria: Profile criteria dictionary
            metadata: Video metadata dictionary

        Returns:
            True if all criteria match, False otherwise
        """
        for key, expected_values in criteria.items():
            if expected_values in (None, [], ()):  # pragma: no cover - defensive
                continue

            expected_set = {
                str(value).strip().lower()
                for value in (
                    expected_values
                    if isinstance(expected_values, list | tuple | set)
                    else [expected_values]
                )
                if value not in (None, "")
            }
            if not expected_set:
                continue

            keys_to_check = [key]
            if key in self._PROFILE_SYNONYMS:
                keys_to_check.extend(self._PROFILE_SYNONYMS[key])

            match_found = False
            for metadata_key in keys_to_check:
                if metadata_key not in metadata:
                    continue
                value = metadata.get(metadata_key)
                if value in (None, ""):
                    continue
                if isinstance(value, list | tuple | set):
                    candidates = [str(item).strip().lower() for item in value]
                else:
                    candidates = [str(value).strip().lower()]
                if any(candidate in expected_set for candidate in candidates):
                    match_found = True
                    break

            if not match_found:
                return False

        return True

    # ------------------------------------------------------------------
    # Asset Removal
    # ------------------------------------------------------------------

    @staticmethod
    def delete_file_if_exists(path: Path | str | None) -> bool:
        """Delete a file if it exists.

        Args:
            path: Path to the file to delete

        Returns:
            True if file was deleted, False otherwise
        """
        if not path:
            return False

        path = Path(path) if isinstance(path, str) else path
        try:
            os.remove(path)
            log.info("asset_manager.file_deleted", path=str(path))
            return True
        except FileNotFoundError:
            log.debug("asset_manager.file_missing", path=str(path))
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning(
                "asset_manager.file_delete_failed",
                path=str(path),
                error=str(exc),
            )
            return False

    @staticmethod
    def video_has_asset(video_entry: dict, asset: AssetType) -> bool:
        """Check if a video entry has a specific asset type.

        Args:
            video_entry: Video entry dictionary
            asset: Asset type to check for

        Returns:
            True if asset exists, False otherwise

        Raises:
            ValueError: If asset type is unknown
        """
        parquet_files = video_entry.get("parquet_files") or {}

        if asset == "arena":
            return bool(video_entry.get("has_arena") or parquet_files.get("arena"))
        if asset == "rois":
            return bool(video_entry.get("has_rois") or parquet_files.get("rois"))
        if asset == "trajectory":
            return bool(video_entry.get("has_trajectory") or parquet_files.get("trajectory"))
        if asset == "summary":
            return bool(
                video_entry.get("has_summary")
                or parquet_files.get("summary")
                or parquet_files.get("summary_excel")
                or parquet_files.get("report_docx")
            )
        if asset == "video":
            return bool(video_entry.get("path"))

        raise ValueError(f"Asset type '{asset}' desconhecido.")

    def can_remove_asset(self, video_entry: dict, asset: AssetType) -> tuple[bool, str | None]:
        """Check if an asset can be removed (dependency validation).

        Args:
            video_entry: Video entry dictionary
            asset: Asset type to check

        Returns:
            Tuple of (can_remove, error_message)
        """
        has_summary_outputs = self.video_has_asset(video_entry, "summary")

        if asset in {"arena", "rois", "trajectory"}:
            if has_summary_outputs:
                return (
                    False,
                    ("Remova os relatórios e sumários antes de apagar arena, ROIs ou trajetórias."),
                )
            if not self.video_has_asset(video_entry, asset):
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
                self.video_has_asset(video_entry, cast(AssetType, dependency))
                for dependency in ("trajectory", "rois", "arena")
            ):
                return (
                    False,
                    ("Remova arena, ROIs e trajetórias antes de excluir o vídeo do projeto."),
                )

        return True, None

    def remove_summary_asset(
        self,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        """Remove summary assets from a video entry.

        Args:
            video_entry: Video entry dictionary to modify
            delete_files: Whether to delete the physical files

        Returns:
            True if any changes were made, False otherwise
        """
        changed = False
        parquet_files = video_entry.get("parquet_files") or {}

        for key in ("summary", "summary_excel", "report_docx"):
            file_path = parquet_files.pop(key, None)
            if file_path:
                changed = True
                if delete_files:
                    self.delete_file_if_exists(file_path)

        if video_entry.get("has_summary"):
            video_entry["has_summary"] = False
            changed = True

        return changed

    def remove_trajectory_asset(
        self,
        video_entry: dict,
        delete_files: bool,
    ) -> bool:
        """Remove trajectory assets from a video entry.

        Args:
            video_entry: Video entry dictionary to modify
            delete_files: Whether to delete the physical files

        Returns:
            True if any changes were made, False otherwise
        """
        changed = False

        parquet_files = video_entry.get("parquet_files") or {}
        trajectory_path = parquet_files.pop("trajectory", None)
        if trajectory_path:
            changed = True
            if delete_files:
                self.delete_file_if_exists(trajectory_path)

        if video_entry.get("has_trajectory"):
            video_entry["has_trajectory"] = False
            changed = True

        # Refresh complete flag
        video_entry["has_complete_data"] = bool(
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
        )

        return changed

    # ------------------------------------------------------------------
    # Phase 4.2: Additional asset removal methods
    # Extracted from ProjectManager
    # ------------------------------------------------------------------

    def remove_arena_asset(
        self,
        video_path: str,
        video_entry: dict,
        delete_files: bool,
        *,
        clear_zone_data_fn: Callable[[str], None],
    ) -> bool:
        """Remove arena asset from a video entry.

        Args:
            video_path: String path to the video.
            video_entry: Video entry dictionary to modify.
            delete_files: Whether to delete physical files.
            clear_zone_data_fn: Callback to clear zone data for the video.

        Returns:
            True if any changes were made, False otherwise.
        """
        changed = False

        clear_zone_data_fn(video_path)
        parquet_files = video_entry.get("parquet_files") or {}

        for key in ("arena", "rois"):
            file_path = parquet_files.pop(key, None)
            if file_path:
                changed = True
                if delete_files:
                    self.delete_file_if_exists(file_path)

        if video_entry.get("has_arena"):
            video_entry["has_arena"] = False
            changed = True
        if video_entry.get("has_rois"):
            video_entry["has_rois"] = False
            changed = True

        self._refresh_complete_flag_static(video_entry)

        return changed

    def remove_rois_asset(
        self,
        video_path: str,
        video_entry: dict,
        delete_files: bool,
        *,
        get_zone_data_fn: Callable[..., Any],
        save_zone_data_fn: Callable[..., None],
    ) -> bool:
        """Remove ROIs asset from a video entry.

        Args:
            video_path: String path to the video.
            video_entry: Video entry dictionary to modify.
            delete_files: Whether to delete physical files.
            get_zone_data_fn: Callback to get zone data for the video.
            save_zone_data_fn: Callback to save zone data for the video.

        Returns:
            True if any changes were made, False otherwise.
        """
        changed = False

        zone_data = get_zone_data_fn(video_path, fallback_to_global=False)
        if zone_data and zone_data.roi_polygons:
            zone_data.roi_polygons = []
            zone_data.roi_names = []
            zone_data.roi_colors = []
            save_zone_data_fn(zone_data, video_path=video_path, persist=False)
            changed = True

        parquet_files = video_entry.get("parquet_files") or {}
        roi_path = parquet_files.pop("rois", None)
        if roi_path:
            changed = True
            if delete_files:
                self.delete_file_if_exists(roi_path)

        if video_entry.get("has_rois"):
            video_entry["has_rois"] = False
            changed = True

        self._refresh_complete_flag_static(video_entry)

        return changed

    def remove_video_entry(  # noqa: C901
        self,
        video_path: str,
        video_entry: dict,
        delete_files: bool,
        *,
        project_data: dict[str, Any],
        clear_zone_data_fn: Callable[[str], None],
        refresh_last_zone_source_fn: Callable[..., None],
    ) -> bool:
        """Remove a video entry and associated files from the project.

        Args:
            video_path: String path to the video.
            video_entry: Video entry dictionary.
            delete_files: Whether to delete physical files.
            project_data: The project data dictionary.
            clear_zone_data_fn: Callback to clear zone data for the video.
            refresh_last_zone_source_fn: Callback to refresh zone source after removal.

        Returns:
            True if any changes were made, False otherwise.
        """
        normalized_video_path = video_path.replace("\\", "/").lower()
        changed = False

        parquet_files = dict(video_entry.get("parquet_files") or {})
        if delete_files:
            # Delete associated parquet/output files
            for path in parquet_files.values():
                self.delete_file_if_exists(path)
            # Delete the video file itself
            if self.delete_file_if_exists(video_path):
                changed = True

            # Delete results_dir if registered
            results_dir = video_entry.get("results_dir")
            if results_dir:
                results_path = Path(results_dir)
                if results_path.exists() and results_path.is_dir():
                    try:
                        shutil.rmtree(results_path, ignore_errors=True)
                        log.info(
                            "project_manager.results_dir_deleted",
                            results_dir=str(results_path),
                        )
                        changed = True
                    except OSError as e:
                        log.warning(
                            "project_manager.results_dir_delete_failed",
                            results_dir=str(results_path),
                            error=str(e),
                        )

            # Delete zone parquets and results folder
            video_dir = Path(video_path).parent
            if video_dir.exists():
                for pattern in ["1_ProcessingArea_*.parquet", "2_ZonasROI_*.parquet"]:
                    for zone_file in glob.glob(str(video_dir / pattern)):
                        self.delete_file_if_exists(zone_file)

                # Force delete subject folder
                try:
                    shutil.rmtree(video_dir, ignore_errors=True)
                    log.info("project_manager.video_folder_deleted", folder=str(video_dir))
                    changed = True
                except OSError as e:
                    log.warning("project_manager.folder_cleanup_failed", error=str(e))

            # Delete multi-aquarium output directories if present
            multi_aq_outputs = video_entry.get("multi_aquarium_outputs", {})
            if multi_aq_outputs:
                for aq_key, aq_data in multi_aq_outputs.items():
                    aq_results_dir = aq_data.get("results_dir")
                    if aq_results_dir:
                        aq_results_path = Path(aq_results_dir)
                        if aq_results_path.exists() and aq_results_path.is_dir():
                            try:
                                shutil.rmtree(aq_results_path, ignore_errors=True)
                                log.info(
                                    "project_manager.multi_aquarium_results_dir_deleted",
                                    aquarium=aq_key,
                                    results_dir=str(aq_results_path),
                                )
                            except OSError as e:
                                log.warning(
                                    "project_manager.multi_aquarium_results_dir_delete_failed",
                                    aquarium=aq_key,
                                    results_dir=str(aq_results_path),
                                    error=str(e),
                                )
                    # Also delete individual parquet files
                    for pq_path in (aq_data.get("parquet_files") or {}).values():
                        if pq_path:
                            self.delete_file_if_exists(pq_path)

        clear_zone_data_fn(video_path)

        for batch in project_data.get("batches", []):
            original_count = len(batch.get("videos", []))
            batch["videos"] = [
                item
                for item in batch.get("videos", [])
                if item.get("path", "").replace("\\", "/").lower() != normalized_video_path
            ]
            if len(batch["videos"]) != original_count:
                changed = True

        if changed:
            refresh_last_zone_source_fn(removed_path=video_path)

        return changed

    @staticmethod
    def _refresh_complete_flag_static(video_entry: dict) -> None:
        """Refresh complete data flag on a video entry."""
        video_entry["has_complete_data"] = bool(
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
        )

from __future__ import annotations

import json
import os
import re
import shutil
import time
import unicodedata
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Any, ClassVar, Literal

import pandas as pd
import structlog
import yaml

from zebtrack.core.detector import ZoneData
from zebtrack.core.project_service import ProjectService
from zebtrack.core.roi_template_manager import ROITemplateManager
from zebtrack.core.state_manager import StateManager
from zebtrack.settings import settings
from zebtrack.utils import IntegrityError, calculate_sha256

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"
ROI_TEMPLATE_VERSION = 1

log = structlog.get_logger()

AssetType = Literal["arena", "rois", "trajectory", "summary", "video"]


class ProjectManager:
    _SCAN_CACHE_TTL_SECONDS: ClassVar[float] = 30.0
    _scan_cache: ClassVar[dict[str, dict[str, Any]]] = {}

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

    def __init__(self, state_manager: StateManager | None = None):
        # Phase 1, Step 3: Delegate file I/O to ProjectService
        self.project_service = ProjectService()

        # Phase 2, Step 4: Optional StateManager reference for state propagation
        self.state_manager = state_manager

        # In-memory project state
        self.project_path = None
        self.project_data = {}
        self.metadata = None  # Will hold the DataFrame for metadata.csv
        self._active_zone_video: str | None = None
        self._last_zone_source_video: str | None = None
        self.roi_template_manager = ROITemplateManager()

    # ------------------------------------------------------------------
    # Internal helpers for zone management
    # ------------------------------------------------------------------

    def _ensure_zone_structures(self) -> None:
        """Ensure zone-related structures exist in project data."""

        if "detection_zones" not in self.project_data:
            self.project_data["detection_zones"] = {}
        if "zones_by_video" not in self.project_data:
            self.project_data["zones_by_video"] = {}
        if "roi_templates" not in self.project_data or not isinstance(
            self.project_data.get("roi_templates"), list
        ):
            self.project_data["roi_templates"] = []

    @staticmethod
    def _normalize_video_path(path: Path | str | None) -> str | None:
        if not path:
            return None
        path = Path(path) if isinstance(path, str) else path
        try:
            resolved = path.resolve(strict=False)
        except Exception:
            resolved = path
        return resolved.as_posix()

    def _resolve_zone_entry(self, video_path: Path | str | None) -> tuple[str | None, dict | None]:
        """Locate a stored zone entry matching the provided video path."""

        if not video_path:
            return None, None
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        self._ensure_zone_structures()
        zones_map = self.project_data.get("zones_by_video", {})
        normalized = self._normalize_video_path(video_path)

        if normalized and normalized in zones_map:
            return normalized, zones_map[normalized]

        if video_path in zones_map:
            return video_path, zones_map[video_path]

        if normalized:
            for key, value in zones_map.items():
                if self._normalize_video_path(key) == normalized:
                    return key, value

        return normalized or video_path, None

    def _deduplicate_zone_keys(self, preferred_key: str | None) -> None:
        """Remove duplicate zone entries that resolve to the same canonical path."""

        if not preferred_key:
            return

        zones_map = self.project_data.get("zones_by_video", {})
        normalized = self._normalize_video_path(preferred_key)
        if not normalized:
            return

        for key in list(zones_map.keys()):
            if key == preferred_key:
                continue
            if self._normalize_video_path(key) == normalized:
                del zones_map[key]

    def _ensure_roi_template_dir(self) -> Path:
        if not self.project_path:
            raise ValueError("Projeto não inicializado para salvar templates de ROI.")
        target = Path(self.project_path) / "roi_templates"
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", normalized).strip("-")
        return normalized.lower() or "template"

    def list_roi_templates(
        self,
        *,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        self._ensure_zone_structures()
        aggregated: list[dict[str, Any]] = []

        for item in self.project_data.get("roi_templates", []):
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
                    "project_manager.roi_templates.global_list_failed",
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

    def _resolve_roi_template_entry(
        self, name: str
    ) -> tuple[int, dict[str, Any]] | tuple[None, None]:
        templates = self.project_data.get("roi_templates", [])
        for idx, entry in enumerate(templates):
            if not isinstance(entry, dict):
                continue
            if entry.get("name") == name:
                return idx, entry
        return None, None

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
            if not self.project_path:
                raise ValueError(
                    "Não é possível salvar o template no projeto atual: projeto não carregado."
                )

            self._ensure_zone_structures()

            existing_index, existing_entry = self._resolve_roi_template_entry(normalized_name)
            if existing_entry and not overwrite:
                raise ValueError(f"Template '{normalized_name}' já existe.")

            if existing_entry:
                slug = existing_entry.get("slug") or self._slugify(normalized_name)
            else:
                slug = self._slugify(normalized_name)
                collision = any(
                    entry.get("slug") == slug
                    for entry in self.project_data.get("roi_templates", [])
                    if isinstance(entry, dict)
                )
                counter = 2
                base_slug = slug
                while collision:
                    slug = f"{base_slug}-{counter}"
                    collision = any(
                        entry.get("slug") == slug
                        for entry in self.project_data.get("roi_templates", [])
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
                project_path=self.project_path,
                overwrite=overwrite,
            )

            project_path = Path(self.project_path)
            metadata["file"] = os.path.relpath(metadata["file"], project_path)
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

            templates = self.project_data.setdefault("roi_templates", [])
            if existing_index is not None:
                templates[existing_index] = stored_metadata
            else:
                templates.append(stored_metadata)

            if persist:
                self.save_project()

            return deepcopy(stored_metadata)

        metadata = self.roi_template_manager.save_template(
            normalized_name,
            zone_data,
            save_arena=save_arena,
            save_rois=save_rois,
            save_location=target_location,
            project_path=self.project_path,
            custom_path=custom_path,
            overwrite=overwrite,
        )
        metadata["location"] = target_location
        return metadata

    def import_roi_template(
        self,
        file_path: Path | str,
        *,
        name: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        file_path = Path(file_path) if isinstance(file_path, str) else file_path
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        with open(file_path, encoding="utf-8") as handle:
            payload = json.load(handle)

        data_block = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data_block, dict):
            raise ValueError("Arquivo de template inválido: bloco 'data' ausente.")

        zone_data = self._zone_data_from_dict(data_block)
        template_name = name or payload.get("name") or file_path.stem

        has_arena = bool(zone_data.polygon)
        has_rois = bool(zone_data.roi_polygons)

        project_available = bool(self.project_path)
        target_location: Literal["project", "global"] = "project" if project_available else "global"
        effective_persist = persist and project_available

        return self.save_roi_template(
            template_name,
            zone_data,
            save_arena=has_arena,
            save_rois=has_rois,
            save_location=target_location,
            persist=effective_persist,
        )

    def load_roi_template(
        self,
        name: str,
        *,
        location: Literal["project", "global", "custom"] | None = None,
        file_path: str | Path | None = None,
    ) -> ZoneData:
        if location in (None, "project"):
            self._ensure_zone_structures()
            _, entry = self._resolve_roi_template_entry(name)
            if entry:
                relative_file = entry.get("file")
                if not relative_file:
                    raise ValueError("Arquivo do template não registrado no projeto.")

                template_path = (
                    Path(self.project_path) / relative_file
                    if self.project_path
                    else Path(relative_file)
                )
                if not template_path.exists():
                    raise FileNotFoundError(str(template_path))

                with open(template_path, encoding="utf-8") as handle:
                    payload = json.load(handle)

                data_block = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data_block, dict):
                    raise ValueError("Conteúdo do template inválido.")

                return self._zone_data_from_dict(data_block)

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

        return self.roi_template_manager.load_template(template_path)

    def _zone_data_to_dict(self, zone_data: ZoneData) -> dict:
        """Serialize ZoneData into a JSON-friendly dictionary."""

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

    def _zone_data_from_dict(self, data: dict | None) -> ZoneData:
        """Deserialize zone data stored in JSON back into ZoneData."""

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

    def _update_video_zone_flags(
        self,
        video_path: Path | str,
        zone_data: ZoneData | None,
    ) -> None:
        """Update has_arena/has_rois flags for a given video entry."""
        video_path = str(Path(video_path) if isinstance(video_path, str) else video_path)

        if not self.project_data or not video_path:
            return

        has_arena = bool(zone_data and zone_data.polygon)
        has_rois = bool(zone_data and zone_data.roi_polygons)
        normalized_target = self._normalize_video_path(video_path)

        for batch in self.project_data.get("batches", []):
            for video in batch.get("videos", []):
                candidate_path = video.get("path")
                if not candidate_path:
                    continue
                if self._normalize_video_path(candidate_path) == normalized_target:
                    video["has_arena"] = has_arena
                    video["has_rois"] = has_rois
                    video["zones_finalized"] = False
                    return

    def _refresh_last_zone_source(self, removed_path: Path | str | None = None) -> None:
        """Refresh cache for last zone source video when data changes."""

        if removed_path is not None:
            removed_path = Path(removed_path) if isinstance(removed_path, str) else removed_path
        zones_map = self.project_data.get("zones_by_video", {})

        if removed_path and self._last_zone_source_video:
            normalized_removed = self._normalize_video_path(removed_path)
            if normalized_removed:
                current_normalized = self._normalize_video_path(self._last_zone_source_video)
                if current_normalized == normalized_removed:
                    self._last_zone_source_video = None

        if self._last_zone_source_video:
            normalized_last = self._normalize_video_path(self._last_zone_source_video)
            for key in zones_map.keys():
                if self._normalize_video_path(key) == normalized_last:
                    self._last_zone_source_video = key
                    return
            self._last_zone_source_video = None

        # Pick the most recently inserted entry in zones_by_video
        if zones_map:
            self._last_zone_source_video = next(reversed(zones_map.keys()))
        else:
            self._last_zone_source_video = None

    # ------------------------------------------------------------------
    # Public helpers for zone lifecycle
    # ------------------------------------------------------------------

    def set_active_zone_video(self, video_path: Path | str | None) -> None:
        """Set the video whose zones should be considered active in memory."""

        self._ensure_zone_structures()

        if video_path is None:
            self._active_zone_video = None
            return

        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        normalized_path = self._normalize_video_path(video_path)
        key, stored = self._resolve_zone_entry(video_path)
        zones_map = self.project_data.get("zones_by_video", {})
        preferred_key = normalized_path or key or video_path

        if stored:
            zone_copy = self._zone_data_from_dict(stored)
            self.project_data["detection_zones"] = self._zone_data_to_dict(zone_copy)

            if key and key != preferred_key:
                zones_map[preferred_key] = stored
                del zones_map[key]
            elif preferred_key not in zones_map:
                zones_map[preferred_key] = stored

            self._deduplicate_zone_keys(preferred_key)
            self._last_zone_source_video = preferred_key
        else:
            self.project_data["detection_zones"] = self._zone_data_to_dict(ZoneData())
            self._deduplicate_zone_keys(preferred_key)

        self._active_zone_video = preferred_key

    def get_active_zone_video(self) -> str | None:
        """Return the currently active video for zone operations."""

        return self._active_zone_video

    def get_last_zone_video(self, exclude: str | None = None) -> str | None:
        """Return the last video that had zones saved, excluding optional target."""

        zones_map = self.project_data.get("zones_by_video", {})
        normalized_exclude = self._normalize_video_path(exclude) if exclude else None

        if self._last_zone_source_video:
            normalized_last = self._normalize_video_path(self._last_zone_source_video)
            if normalized_last and normalized_last != normalized_exclude:
                for key in zones_map.keys():
                    if self._normalize_video_path(key) == normalized_last:
                        return key

        for path in reversed(list(zones_map.keys())):
            if self._normalize_video_path(path) != normalized_exclude:
                return path

        return None

    def has_zone_data(self, video_path: Path | str | None) -> bool:
        """Check whether the given video currently stores arena or ROI data."""

        if not video_path:
            return False

        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self._ensure_zone_structures()
        _, stored = self._resolve_zone_entry(video_path)

        if not stored:
            return False

        zone_data = self._zone_data_from_dict(stored)
        return bool(zone_data.polygon or zone_data.roi_polygons)

    def save_zone_data(
        self,
        zone_data: ZoneData,
        video_path: Path | str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        """Persist zone data for the active video and project defaults."""

        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self._ensure_zone_structures()

        target_video = video_path if video_path is not None else self._active_zone_video

        serialized = self._zone_data_to_dict(zone_data)
        self.project_data["detection_zones"] = serialized

        if target_video:
            normalized = self._normalize_video_path(target_video)
            existing_key, _ = self._resolve_zone_entry(target_video)
            store_key = normalized or existing_key or target_video

            self.project_data["zones_by_video"][store_key] = serialized
            self._deduplicate_zone_keys(store_key)

            self._last_zone_source_video = store_key
            self._update_video_zone_flags(target_video, zone_data)

        if persist:
            self.save_project()

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
        if self._active_zone_video and normalized_target == self._active_zone_video:
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
                except Exception as exc:  # pragma: no cover - defensive
                    log.error(
                        "project_manager.zones.copy_failed",
                        source=source_file_path,
                        destination=dest_file_path,
                        error=str(exc),
                    )

        if updated_video_entry and copied:
            video_entry = target_video_entry or self.find_video_entry(path=target_video_path)
            if video_entry is not None:
                parquet_map = video_entry.setdefault("parquet_files", {})
                parquet_map.update(copied)

        if persist and updated_video_entry:
            self.save_project()

        return copied

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
        video_files: set[Path] = set()
        video_extensions = {".mp4", ".avi", ".mov"}

        for p_str in paths:
            p = Path(p_str)
            if not p.exists():
                log.debug(
                    "project_manager.scan_input_paths.missing_path",
                    path=str(p),
                )
                continue

            if p.is_dir():
                video_files.update(ProjectManager._scan_directory_for_videos(p, video_extensions))
            elif p.is_file() and p.suffix.lower() in video_extensions:
                video_files.update(ProjectManager._scan_file_entry(p, video_extensions))

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

    @classmethod
    def _scan_directory_for_videos(
        cls, directory: Path | str, video_extensions: set[str]
    ) -> list[Path]:
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
                "project_manager.scan_input_paths.directory_error",
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
        path = Path(path) if isinstance(path, str) else path
        try:
            stat_result = path.stat()
        except FileNotFoundError:
            return ("missing", 0)

        return (str(stat_result.st_mtime_ns), stat_result.st_size)

    @classmethod
    def clear_scan_cache(cls, target_path: Path | str | None = None) -> None:
        if target_path is None:
            cls._scan_cache.clear()
            return

        target_path = Path(target_path) if isinstance(target_path, str) else target_path
        resolved = str(target_path.resolve())
        cls._scan_cache.pop(resolved, None)
        cls._scan_cache.pop(target_path, None)

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
                            (0, 255, 0),  # Green
                            (255, 0, 0),  # Blue
                            (0, 0, 255),  # Red
                            (255, 255, 0),  # Cyan
                            (255, 0, 255),  # Magenta
                            (0, 255, 255),  # Yellow
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
        scanned_videos: list[dict] | None = None,
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

        except Exception as e:
            log.error(
                "project_manager.import_parquets.error",
                error=str(e),
                exc_info=True,
            )
            return False

    def _process_single_parquet_import(
        self, config: dict, video_parquet_map: dict, roi_merge_strategy: str
    ) -> dict:
        """Process a single video import configuration and return counts.

        Returns a dict with keys: arena, rois, trajectory (counts)
        """
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
                            (0, 255, 0),
                            (255, 0, 0),
                            (0, 0, 255),
                            (255, 255, 0),
                            (255, 0, 255),
                            (0, 255, 255),
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
        """Saves a snapshot of the current settings to the project directory."""
        if not self.project_path:
            return False

        snapshot_path = os.path.join(self.project_path, SETTINGS_SNAPSHOT_FILE_NAME)
        try:
            # Use model_dump with proper serialization to ensure YAML compatibility
            import json

            # Check if settings is a real settings object (not a mock)
            if not hasattr(settings, "model_dump_json") or not callable(settings.model_dump_json):
                log.debug("settings.snapshot.skipped", reason="settings not available or mocked")
                return True  # Return True to not block project creation in tests

            json_str = settings.model_dump_json()
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
        Initializes a new project, creating its directory and config file.
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
        if use_single_subject_tracker is None:
            tracker_pref = animals_per_aquarium == 1 or bool(
                settings.tracking.use_single_subject_tracker
            )
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
            "analysis_profiles": [self._default_analysis_profile()],
            "roi_templates": [],
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

    def load_project(self, project_path: Path | str):
        """
        Loads project data from a config file in the given directory.

        Phase 1, Step 3: Delegates file I/O to ProjectService.
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
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
            # Phase 1, Step 3: Delegate to ProjectService for file I/O
            loaded_data = self.project_service.load_project_config(project_path)

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
                loaded_data["analysis_profiles"] = [self._default_analysis_profile()]
                migration_applied = True
                migrated_fields.append("analysis_profiles")

            tracker_flag = settings.tracking.use_single_subject_tracker
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
        except (OSError, json.JSONDecodeError, IntegrityError) as e:
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

        Phase 1, Step 3: Delegates file I/O to ProjectService.
        """
        # Critical Fix #5: Add validation before saving
        if not self.project_path:
            log.debug("project.save.no_path", reason="project not yet created")
            return False

        try:
            # Delegate to ProjectService for file I/O
            self.project_service.save_project_config(self.project_path, self.project_data)

            log.info("project.save.success", path=self.project_path)
            return True
        except Exception as e:
            log.error("project.save.error", path=self.project_path, exc_info=e)
            messagebox.showerror(
                "Erro ao Salvar",
                f"Falha ao salvar o arquivo de configuração do projeto:\n"
                f"{self.project_path}\n\nPor favor, verifique as permissões da "
                f"pasta.\n\nErro: {e}",
            )
            return False

    def _default_analysis_profile(self) -> dict:
        return {
            "name": "default",
            "criteria": {},
            "track_ids": [],
            "social": {"enabled": False, "radius_cm": 5.0},
        }

    def get_analysis_profiles(self) -> list[dict]:
        profiles = self.project_data.get("analysis_profiles")
        if not profiles:
            profiles = [self._default_analysis_profile()]
            self.project_data["analysis_profiles"] = profiles
        return deepcopy(profiles)

    def resolve_analysis_profile(self, metadata: dict | None) -> dict:
        metadata = metadata or {}
        profiles = self.get_analysis_profiles()

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
        for key, expected_values in criteria.items():
            if expected_values in (None, [], ()):  # pragma: no cover - defensive
                continue

            expected_set = {
                str(value).strip().lower()
                for value in (
                    expected_values
                    if isinstance(expected_values, (list, tuple, set))
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
                if isinstance(value, (list, tuple, set)):
                    candidates = [str(item).strip().lower() for item in value]
                else:
                    candidates = [str(value).strip().lower()]
                if any(candidate in expected_set for candidate in candidates):
                    match_found = True
                    break

            if not match_found:
                return False

        return True

    def update_video_status(self, video_path: Path | str, new_status):
        """
        Updates the status of a specific video across all batches and saves the project.
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

    def _iter_project_videos(self):
        """Yield (batch_dict, video_dict) pairs for every registered video."""

        for batch in self.project_data.get("batches", []):
            videos = batch.get("videos", [])
            for video in videos:
                yield batch, video

    def _video_has_asset(self, video_entry: dict, asset: AssetType) -> bool:
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

    @staticmethod
    def _refresh_complete_flag(video_entry: dict) -> None:
        video_entry["has_complete_data"] = bool(
            video_entry.get("has_arena")
            and video_entry.get("has_rois")
            and video_entry.get("has_trajectory")
        )

    def _delete_file_if_exists(self, path: Path | str | None) -> bool:
        if not path:
            return False

        path = Path(path) if isinstance(path, str) else path
        try:
            os.remove(path)
            log.info("project_manager.asset.file_deleted", path=path)
            return True
        except FileNotFoundError:
            log.debug("project_manager.asset.file_missing", path=path)
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            log.warning(
                "project_manager.asset.file_delete_failed",
                path=path,
                error=str(exc),
            )
            return False

    def can_remove_asset(self, video_path: Path | str, asset: AssetType) -> tuple[bool, str | None]:
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
        """Return the project entry for a given video path or experiment id."""

        if not self.project_data:
            return None

        normalized_target = None
        if path:
            normalized_target = os.path.normcase(os.path.normpath(path))

        for _batch, video in self._iter_project_videos():
            candidate_path = video.get("path")
            if candidate_path and normalized_target:
                candidate_norm = os.path.normcase(os.path.normpath(candidate_path))
                if candidate_norm == normalized_target:
                    return video

            if experiment_id:
                candidate_name = os.path.basename(candidate_path or "")
                candidate_id = os.path.splitext(candidate_name)[0]
                if candidate_id == experiment_id:
                    return video

        return None

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

    def get_zone_data(
        self,
        video_path: Path | str | None = None,
        *,
        fallback_to_global: bool = True,
    ) -> ZoneData:
        """Retrieve zone data for a specific video or fallback to project defaults."""

        if video_path is not None:
            video_path = Path(video_path) if isinstance(video_path, str) else video_path
        self._ensure_zone_structures()

        target_video = video_path if video_path is not None else self._active_zone_video
        key, stored = self._resolve_zone_entry(target_video)

        if stored:
            return self._zone_data_from_dict(stored)

        if target_video and not fallback_to_global:
            return ZoneData()

        return self._zone_data_from_dict(self.project_data.get("detection_zones"))

    def update_main_polygon(self, points: list):
        """Atualiza ou define o polígono principal nos dados do projeto."""

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

            # Persistir alterações
            self.save_zone_data(zone_data)
            log.debug("project_manager.polygon.data_structure_updated")

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
                    "project.metadata.load_error",
                    path=metadata_path,
                    error=str(e),
                )
                messagebox.showwarning(
                    "Aviso de Metadados",
                    f"Não foi possível carregar ou analisar 'metadata.csv'.\n\nErro: {e}",
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
                log.warning("metadata.fallback.parse_error", experiment_id=experiment_id)

        # If neither method works, return an empty dictionary
        return {}

    def save_detector_state(self, detector_config: dict) -> bool:
        """
        Saves detector configuration to project data.

        Args:
            detector_config: Dictionary with keys plugin_name, confidence_threshold,
                           nms_threshold, optional track_threshold,
                           optional match_threshold, context, last_updated

        Returns:
            bool: True if saved successfully, False otherwise
        """
        if not self.project_data:
            log.debug("project.detector_state.save.no_project_data")
            return False

        # Skip saving if no project path (e.g., single video workflow before project creation)
        if not self.project_path:
            log.debug("project.detector_state.save.no_project_path", reason="skipping save")
            return False

        log.info("project.detector_state.save.start", config=detector_config)

        try:
            # Add timestamp if not provided
            if "last_updated" not in detector_config:
                detector_config["last_updated"] = datetime.now().isoformat()

            self.project_data["detector_config"] = detector_config
            result = self.save_project()

            if result:
                log.info(
                    "project.detector_state.save.success",
                    plugin=detector_config.get("plugin_name"),
                )
            else:
                log.debug(
                    "project.detector_state.save.skipped",
                    reason="project not yet persisted",
                )

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

"""
ProjectService: Single Responsibility Service for Project File I/O Operations.

This service handles all file system operations related to project management:
- Project creation, loading, and saving
- Asset management (add, remove, scan)
- Path resolution and directory structure
- Parquet import/export
- ROI template persistence
- Session management

Phase 1, Step 3: Extracted from AppController and ProjectManager to achieve
Single Responsibility Principle and improve testability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog

from zebtrack.utils import IntegrityError

if TYPE_CHECKING:
    import pandas as pd

log = structlog.get_logger()

AssetType = Literal["arena", "rois", "trajectory", "summary", "video"]

CONFIG_FILE_NAME = "project_config.json"
SETTINGS_SNAPSHOT_FILE_NAME = "config_snapshot.yaml"


class ProjectService:
    """
    Service layer for all project-related file I/O operations.

    Responsibilities:
    - Create/load/save project configuration files
    - Manage project directory structure
    - Handle asset files (parquet, video, summaries)
    - Scan and import video/parquet files
    - Persist ROI templates
    - Manage session history

    This service is stateless - it operates on paths and data provided by callers.
    Project state is managed by ProjectManager; this service handles persistence only.
    """

    def __init__(self):
        """Initialize the ProjectService."""
        self.log = structlog.get_logger(__name__)

    # -------------------------------------------------------------------------
    # Core Project File Operations
    # -------------------------------------------------------------------------

    def create_project_directory(
        self,
        project_path: Path | str,
        project_name: str,
        project_type: str,
        initial_data: dict | None = None,
    ) -> dict:
        """
        Create a new project directory with initial configuration.

        Args:
            project_path: Path where project should be created
            project_name: Name of the project
            project_type: Type of project (e.g., "project", "exploratory")
            initial_data: Optional initial project data dictionary

        Returns:
            dict: Initial project data structure

        Raises:
            FileExistsError: If project directory already exists
            OSError: If directory creation fails
        """
        project_path_obj = Path(project_path) if isinstance(project_path, str) else project_path

        if project_path_obj.exists():
            raise FileExistsError(f"Project directory already exists: {project_path}")

        try:
            project_path_obj.mkdir(parents=True, exist_ok=False)
            self.log.info(
                "project_service.create_directory.success",
                path=project_path,
            )
        except OSError as e:
            self.log.error(
                "project_service.create_directory.failed",
                path=project_path,
                error=str(e),
            )
            raise

        # Initialize project data structure
        project_data = initial_data or {}
        project_data.update(
            {
                "project_name": project_name,
                "project_type": project_type,
                "created_at": datetime.now().isoformat(),
                "last_modified": datetime.now().isoformat(),
                "videos": project_data.get("videos", []),
                "detection_zones": project_data.get("detection_zones", {}),
                "zones_by_video": project_data.get("zones_by_video", {}),
                "roi_templates": project_data.get("roi_templates", []),
            }
        )

        # Write initial project configuration
        self.save_project_config(project_path, project_data)

        # Note: Settings snapshot is now handled by ProjectManager
        # which has access to injected settings via DI
        # self._save_settings_snapshot(project_path) - DEPRECATED

        return project_data

    def load_project_config(self, project_path: Path | str) -> dict:
        """
        Load project configuration from JSON file.

        Args:
            project_path: Path to project directory

        Returns:
            dict: Project configuration data

        Raises:
            FileNotFoundError: If project config file doesn't exist
            IntegrityError: If integrity hash doesn't match
            json.JSONDecodeError: If JSON is malformed
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        config_file = project_path / CONFIG_FILE_NAME

        if not config_file.exists():
            raise FileNotFoundError(f"Project configuration not found: {config_file}")

        try:
            with open(config_file, encoding="utf-8") as f:
                project_data = json.load(f)

            # Verify integrity if hash exists
            stored_hash = project_data.pop("_integrity_hash", None)
            if stored_hash:
                computed_hash = self._compute_project_hash(project_data)
                if stored_hash != computed_hash:
                    raise IntegrityError(f"Project integrity check failed for {config_file}")

            self.log.info(
                "project_service.load_config.success",
                path=str(config_file),
            )
            return project_data

        except (json.JSONDecodeError, IntegrityError) as e:
            self.log.error(
                "project_service.load_config.failed",
                path=str(config_file),
                error=str(e),
            )
            raise

    def save_project_config(self, project_path: Path | str, project_data: dict) -> None:
        """
        Save project configuration to JSON file with integrity hash.

        Args:
            project_path: Path to project directory
            project_data: Project configuration data to save

        Raises:
            OSError: If file write fails
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        config_file = project_path / CONFIG_FILE_NAME

        # Update last modified timestamp
        project_data["last_modified"] = datetime.now().isoformat()

        # Compute integrity hash
        data_to_save = project_data.copy()
        integrity_hash = self._compute_project_hash(project_data)
        data_to_save["_integrity_hash"] = integrity_hash

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            self.log.info(
                "project_service.save_config.success",
                path=str(config_file),
            )
        except OSError as e:
            self.log.error(
                "project_service.save_config.failed",
                path=str(config_file),
                error=str(e),
            )
            raise

    def _compute_project_hash(self, project_data: dict) -> str:
        """
        Compute SHA256 integrity hash of project data.

        Args:
            project_data: Project data dictionary (without hash)

        Returns:
            str: SHA256 hash hex string
        """
        # Serialize project data deterministically
        json_str = json.dumps(project_data, sort_keys=True, ensure_ascii=False)
        # Use hashlib directly for in-memory data hashing
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    # Asset Management
    # -------------------------------------------------------------------------

    def delete_file_if_exists(self, file_path: str | Path) -> bool:
        """
        Delete a file if it exists.

        Args:
            file_path: Path to file

        Returns:
            bool: True if file was deleted, False if it didn't exist
        """
        path = Path(file_path)
        if path.exists():
            try:
                path.unlink()
                self.log.info(
                    "project_service.delete_file.success",
                    path=str(path),
                )
                return True
            except OSError as e:
                self.log.error(
                    "project_service.delete_file.failed",
                    path=str(path),
                    error=str(e),
                )
                raise
        return False

    def ensure_directory(self, dir_path: str | Path) -> Path:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            dir_path: Path to directory

        Returns:
            Path: Path object for the directory
        """
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -------------------------------------------------------------------------
    # Path Resolution
    # -------------------------------------------------------------------------

    def resolve_results_directory(
        self,
        project_path: Path | str,
        metadata: dict | None = None,
    ) -> Path:
        """
        Resolve the results directory path for a project.

        Args:
            project_path: Path to project directory
            metadata: Optional metadata for path construction

        Returns:
            Path: Results directory path
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        results_dir = project_path / "results"

        if metadata:
            # Build hierarchical path from metadata
            # e.g., results/group_A/day_1/subject_01/
            if "group" in metadata:
                results_dir = results_dir / self._sanitize_path_component(str(metadata["group"]))
            if "day" in metadata:
                results_dir = results_dir / self._sanitize_path_component(str(metadata["day"]))
            if "subject" in metadata:
                results_dir = results_dir / self._sanitize_path_component(str(metadata["subject"]))

        return results_dir

    def _sanitize_path_component(self, component: str) -> str:
        """
        Sanitize a path component to be filesystem-safe.

        Args:
            component: Path component string

        Returns:
            str: Sanitized component
        """
        # Remove or replace problematic characters
        component = component.replace("/", "_").replace("\\", "_")
        component = component.replace(":", "_").replace("*", "_")
        component = component.replace("?", "_").replace('"', "_")
        component = component.replace("<", "_").replace(">", "_")
        component = component.replace("|", "_")

        # Remove leading/trailing whitespace and dots
        component = component.strip(". ")

        return component if component else "untitled"

    # -------------------------------------------------------------------------
    # Metadata Operations
    # -------------------------------------------------------------------------

    def load_metadata_csv(self, project_path: Path | str) -> pd.DataFrame | None:
        """
        Load metadata.csv from project directory.

        Args:
            project_path: Path to project directory

        Returns:
            pd.DataFrame | None: Metadata dataframe or None if file doesn't exist
        """
        import pandas as pd  # Lazy import to avoid loading pandas during startup

        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        metadata_file = project_path / "metadata.csv"

        if not metadata_file.exists():
            self.log.warning(
                "project_service.load_metadata.not_found",
                path=str(metadata_file),
            )
            return None

        try:
            df = pd.read_csv(metadata_file)
            self.log.info(
                "project_service.load_metadata.success",
                path=str(metadata_file),
                rows=len(df),
            )
            return df
        except Exception as e:
            self.log.error(
                "project_service.load_metadata.failed",
                path=str(metadata_file),
                error=str(e),
            )
            return None

    # -------------------------------------------------------------------------
    # ROI Template Persistence
    # -------------------------------------------------------------------------

    def ensure_roi_template_directory(self, project_path: Path | str) -> Path:
        """
        Ensure ROI template directory exists.

        Args:
            project_path: Path to project directory

        Returns:
            Path: Template directory path
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        template_dir = project_path / "templates"
        return self.ensure_directory(template_dir)

    def save_roi_template(
        self,
        project_path: Path | str,
        template_name: str,
        template_data: dict,
    ) -> Path:
        """
        Save an ROI template to JSON file.

        Args:
            project_path: Path to project directory
            template_name: Name of the template
            template_data: Template data dictionary

        Returns:
            Path: Path to saved template file
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        template_dir = self.ensure_roi_template_directory(project_path)
        template_file = template_dir / f"{template_name}.json"

        try:
            with open(template_file, "w", encoding="utf-8") as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)

            self.log.info(
                "project_service.save_roi_template.success",
                path=str(template_file),
            )
            return template_file
        except OSError as e:
            self.log.error(
                "project_service.save_roi_template.failed",
                path=str(template_file),
                error=str(e),
            )
            raise

    def load_roi_template(self, project_path: Path | str, template_name: str) -> dict | None:
        """
        Load an ROI template from JSON file.

        Args:
            project_path: Path to project directory
            template_name: Name of the template

        Returns:
            dict | None: Template data or None if not found
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        template_dir = project_path / "templates"
        template_file = template_dir / f"{template_name}.json"

        if not template_file.exists():
            self.log.warning(
                "project_service.load_roi_template.not_found",
                path=str(template_file),
            )
            return None

        try:
            with open(template_file, encoding="utf-8") as f:
                template_data = json.load(f)

            self.log.info(
                "project_service.load_roi_template.success",
                path=str(template_file),
            )
            return template_data
        except (json.JSONDecodeError, OSError) as e:
            self.log.error(
                "project_service.load_roi_template.failed",
                path=str(template_file),
                error=str(e),
            )
            return None

    def list_roi_templates(self, project_path: Path | str) -> list[str]:
        """
        List all available ROI templates in project.

        Args:
            project_path: Path to project directory

        Returns:
            list[str]: List of template names (without .json extension)
        """
        project_path = Path(project_path) if isinstance(project_path, str) else project_path
        template_dir = project_path / "templates"

        if not template_dir.exists():
            return []

        try:
            templates = [f.stem for f in template_dir.glob("*.json")]
            self.log.info(
                "project_service.list_roi_templates.success",
                path=str(template_dir),
                count=len(templates),
            )
            return sorted(templates)
        except Exception as e:
            self.log.error(
                "project_service.list_roi_templates.failed",
                path=str(template_dir),
                error=str(e),
            )
            return []

    # -------------------------------------------------------------------------
    # Model Settings Management (Phase 2.1)
    # -------------------------------------------------------------------------

    def save_model_overrides(
        self,
        project_path: Path | str,
        project_data: dict,
        active_weight: str | None,
        use_openvino: bool,
    ) -> dict:
        """
        Save model configuration overrides to project.

        Args:
            project_path: Path to project directory
            project_data: Current project data dictionary
            active_weight: Active weight name or None
            use_openvino: Whether to use OpenVINO

        Returns:
            dict: Updated model overrides

        Phase 2.1: Extracted from MainViewModel._persist_project_model_settings
        """
        # Ensure model_overrides exists in project data
        overrides = project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None},
        )

        # Update overrides
        overrides["active_weight"] = active_weight
        overrides["use_openvino"] = use_openvino

        # Update root-level settings for backward compatibility
        project_data["active_weight"] = active_weight
        project_data["use_openvino"] = bool(use_openvino)

        # Save updated configuration
        self.save_project_config(project_path, project_data)

        self.log.info(
            "project_service.save_model_overrides.success",
            weight=active_weight,
            openvino=use_openvino,
        )

        return overrides

    def save_arena_polygon(
        self,
        project_path: Path | str,
        project_data: dict,
        polygon_points: list[list[int]],
    ) -> None:
        """
        Save arena polygon to project zone data.

        Args:
            project_path: Path to project directory
            project_data: Current project data dictionary
            polygon_points: List of [x, y] coordinates defining the arena

        Phase 2.1: Extracted from MainViewModel.save_manual_arena
        """
        # Get or create detection_zones structure
        detection_zones = project_data.setdefault("detection_zones", {})

        # Update arena polygon
        detection_zones["polygon"] = polygon_points

        # Save updated configuration
        self.save_project_config(project_path, project_data)

        self.log.info(
            "project_service.save_arena_polygon.success",
            points_count=len(polygon_points),
        )

"""
Wizard Template System

Allows saving and loading project configuration templates for quick project creation.
"""

from copy import deepcopy
import json
from datetime import datetime
from pathlib import Path

import structlog

log = structlog.get_logger()


TEMPLATE_SCHEMA_VERSION = 2


class TemplateManager:
    """
    Manages wizard configuration templates.

    Templates are saved as JSON files in the user's config directory.
    Each template tracks a schema version and contains the key wizard
    preferences:
    - Project type (experimental/exploratory/live)
    - Calibration settings (dimensions, animal count)
    - Analysis interval configuration
    - Design information (groups, days)
    - Parquet import scope and regex patterns
    - Model selection preferences (methods, weights, OpenVINO)
    - Detector thresholds (confidence/NMS/ByteTrack)
    """

    def __init__(self, templates_dir: Path | None = None):
        """
        Initialize template manager.

        Args:
            templates_dir: Directory to store templates. If None, uses default
                          location in user's home directory.
        """
        if templates_dir is None:
            # Default location: ~/.zebtrack/wizard_templates/
            templates_dir = Path.home() / ".zebtrack" / "wizard_templates"

        self.templates_dir = templates_dir
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        log.info("template_manager.initialized", templates_dir=str(self.templates_dir))

    def save_template(
        self,
        name: str,
        wizard_data: dict,
        destination_path: str | Path | None = None,
    ) -> bool:
        """
        Save wizard configuration as a template.

        Args:
            name: Template name (will be sanitized for filesystem)
            wizard_data: Wizard configuration dict

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Sanitize template name
            if destination_path:
                template_path = Path(destination_path)
                if template_path.suffix.lower() != ".json":
                    template_path = template_path.with_suffix(".json")
                template_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                safe_name = self._sanitize_name(name)
                template_path = self.templates_dir / f"{safe_name}.json"

            # Extract relevant fields for template
            template = {
                "schema_version": TEMPLATE_SCHEMA_VERSION,
                "wizard_schema_version": wizard_data.get("wizard_schema_version"),
                "name": name,
                "created_at": datetime.now().isoformat(),
                "project_type": wizard_data.get("project_type"),
                "num_aquariums": wizard_data.get("num_aquariums", 1),
                "animals_per_aquarium": wizard_data.get("animals_per_aquarium", 1),
                "aquarium_width_cm": wizard_data.get("aquarium_width_cm", 10.0),
                "aquarium_height_cm": wizard_data.get("aquarium_height_cm", 10.0),
                "analysis_interval_frames": wizard_data.get("analysis_interval_frames"),
                "display_interval_frames": wizard_data.get("display_interval_frames"),
                "parquet_import_scope": wizard_data.get("parquet_import_scope"),
                "detected_design": deepcopy(wizard_data.get("detected_design")),
                "custom_regex_patterns": deepcopy(wizard_data.get("custom_regex_patterns")),
                "model_selection": deepcopy(wizard_data.get("model_selection")),
                "weight_assignments": deepcopy(wizard_data.get("weight_assignments")),
                "detector_parameters": deepcopy(wizard_data.get("detector_parameters")),
                "use_openvino": wizard_data.get("use_openvino"),
            }

            # Write template to file
            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2, ensure_ascii=False)

            log.info(
                "template_manager.template_saved",
                name=name,
                path=str(template_path),
            )
            return True

        except Exception as e:
            log.error(
                "template_manager.save_error",
                name=name,
                error=str(e),
                exc_info=True,
            )
            return False

    def load_template(self, name: str) -> dict | None:
        """
        Load a template by name.

        Args:
            name: Template name

        Returns:
            dict: Template data or None if not found/invalid
        """
        try:
            safe_name = self._sanitize_name(name)
            template_path = self.templates_dir / f"{safe_name}.json"

            if not template_path.exists():
                log.warning("template_manager.template_not_found", name=name)
                return None

            with open(template_path, encoding="utf-8") as f:
                template = json.load(f)

            log.info("template_manager.template_loaded", name=name)
            return template

        except Exception as e:
            log.error(
                "template_manager.load_error",
                name=name,
                error=str(e),
                exc_info=True,
            )
            return None

    def load_template_from_path(self, path: str | Path) -> dict | None:
        """
        Load a template directly from a filesystem path.

        Args:
            path: Full path to template file

        Returns:
            dict | None: Template data or None if load fails
        """
        try:
            template_path = Path(path)
            if not template_path.exists():
                log.warning(
                    "template_manager.template_not_found",
                    name=str(template_path.name),
                )
                return None

            with open(template_path, encoding="utf-8") as f:
                template = json.load(f)

            log.info(
                "template_manager.template_loaded",
                name=template.get("name", template_path.stem),
                path=str(template_path),
            )
            return template

        except Exception as e:
            log.error(
                "template_manager.load_error",
                name=str(path),
                error=str(e),
                exc_info=True,
            )
            return None

    def list_templates(self) -> list[dict]:
        """
        List all available templates.

        Returns:
            list[dict]: List of template metadata (name, created_at)
        """
        templates = []

        try:
            for template_path in self.templates_dir.glob("*.json"):
                try:
                    with open(template_path, encoding="utf-8") as f:
                        template = json.load(f)

                    templates.append(
                        {
                            "name": template.get("name", template_path.stem),
                            "created_at": template.get("created_at", "Unknown"),
                            "project_type": template.get("project_type", "Unknown"),
                        }
                    )
                except Exception as e:
                    log.warning(
                        "template_manager.template_read_error",
                        path=str(template_path),
                        error=str(e),
                    )

            templates.sort(key=lambda t: t.get("created_at", ""), reverse=True)
            log.info("template_manager.templates_listed", count=len(templates))

        except Exception as e:
            log.error(
                "template_manager.list_error",
                error=str(e),
                exc_info=True,
            )

        return templates

    def delete_template(self, name: str) -> bool:
        """
        Delete a template.

        Args:
            name: Template name

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            safe_name = self._sanitize_name(name)
            template_path = self.templates_dir / f"{safe_name}.json"

            if not template_path.exists():
                log.warning("template_manager.template_not_found", name=name)
                return False

            template_path.unlink()
            log.info("template_manager.template_deleted", name=name)
            return True

        except Exception as e:
            log.error(
                "template_manager.delete_error",
                name=name,
                error=str(e),
                exc_info=True,
            )
            return False

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """
        Sanitize template name for filesystem.

        Args:
            name: Original template name

        Returns:
            str: Sanitized name (lowercase, no special chars)
        """
        # Replace spaces with underscores, remove special characters
        safe_name = name.lower().strip()
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in safe_name)
        # Remove consecutive underscores
        safe_name = "_".join(filter(None, safe_name.split("_")))
        return safe_name or "template"


def format_template_banner(metadata: dict | None) -> str:
    """Format banner text for loaded templates."""

    if not metadata:
        return ""

    name = metadata.get("name") or metadata.get("template_name")
    path = metadata.get("path")

    if not name and path:
        name = Path(path).stem

    if not name:
        return ""

    banner = f"Template carregado: {name}"

    if path:
        banner += f"  ({Path(path).name})"

    return banner

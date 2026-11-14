"""
Wizard Template System.

Allows saving and loading project configuration templates for quick project creation.
"""

import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.core.conditions import WindowSpec
from zebtrack.core.conditions.presets import external_trigger_preset
from zebtrack.core.detection.class_roles import parse_class_roles
from zebtrack.i18n import _

log = structlog.get_logger()


#: v4 (DRerio 8.0) adds ``analysis_window`` — the START/STOP conditions of the
#: analysis (ADR-011), stored as ``WindowSpec.model_dump(mode="json")`` or None.
#: v5 adds ``model_overrides`` — the class roles of the animal weight (ADR-009,
#: #646), see :data:`TEMPLATE_OVERRIDES_KEY`.
TEMPLATE_SCHEMA_VERSION = 5

#: Tokens a migration leaves for the confirmation step. Never translated: the
#: text is built at display time by :func:`template_migration_note_text`.
NOTE_EXTERNAL_TRIGGER_CONVERTED = "external_trigger_converted"
NOTE_ANALYSIS_WINDOW_DROPPED = "analysis_window_dropped"
NOTE_CLASS_ROLES_DROPPED = "class_roles_dropped"

#: Template block that mirrors ``project_data["model_overrides"]`` (persistence
#: contract — the same keys a project stores, so a template can be written by
#: copying a project's block)::
#:
#:     {"class_roles": {normalised class name: role token},
#:      "class_roles_weight_sha256": "<sha256 of the weight they were set for>" | null}
#:
#: Roles are keyed by class NAME, never by id. The sha only records which file
#: they were chosen for; a template applied with ANY weight (another file, or a
#: shipped template with ``null``) re-validates the names against that weight
#: (``class_roles.fit_class_roles``) and never trusts ids or positions.
TEMPLATE_OVERRIDES_KEY = "model_overrides"
TEMPLATE_ROLES_KEY = "class_roles"
TEMPLATE_ROLES_SHA_KEY = "class_roles_weight_sha256"
#: Where the wizard keeps the block of the template it loaded (``wizard_data``).
WIZARD_TEMPLATE_ROLES_KEY = "template_class_roles"


def _normalised_sha(raw: Any) -> str | None:
    """A recorded sha256 as lowercase hex, or ``None`` when it is not one."""
    if not isinstance(raw, str):
        return None
    sha = raw.strip().lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return None
    return sha


def normalise_model_overrides(raw: Any) -> dict[str, Any] | None:
    """Validate a template's ``model_overrides`` block.

    Returns:
        ``{"class_roles": {...}, "class_roles_weight_sha256": sha | None}`` with
        normalised names, or ``None`` when the block holds no roles.

    Raises:
        ValueError: the block is present but its roles cannot be read.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("model_overrides must be a mapping")
    raw_roles = raw.get(TEMPLATE_ROLES_KEY)
    if raw_roles is None:
        return None
    roles = parse_class_roles(raw_roles)
    if roles is None:
        raise ValueError("class_roles is not a {class name: role} mapping")
    return {
        TEMPLATE_ROLES_KEY: {name: role.value for name, role in roles.items()},
        TEMPLATE_ROLES_SHA_KEY: _normalised_sha(raw.get(TEMPLATE_ROLES_SHA_KEY)),
    }


def template_model_overrides(wizard_data: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ``model_overrides`` block a template saves from the wizard's data.

    The roles edited (or fitted) in this wizard win, with the sha of the weight
    they were made for; otherwise the block of the template that was loaded is
    carried forward unchanged, so re-saving a template never loses its roles
    just because they matched the weight's automatic ones on this machine.
    """
    edited = {
        TEMPLATE_ROLES_KEY: wizard_data.get("class_roles"),
        TEMPLATE_ROLES_SHA_KEY: wizard_data.get("class_roles_weight_sha256"),
    }
    for candidate in (edited, wizard_data.get(WIZARD_TEMPLATE_ROLES_KEY)):
        try:
            block = normalise_model_overrides(candidate)
        except ValueError:
            log.warning("template_manager.class_roles.unreadable", roles=candidate)
            continue
        if block is not None:
            return block
    return None


def _template_schema_version(template: Mapping[str, Any]) -> int:
    """The template's declared schema; a missing or garbled value counts as v1."""
    raw = template.get("schema_version")
    if isinstance(raw, bool):
        return 1
    try:
        return int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        return 1


def migrate_template(template: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Bring a loaded template up to :data:`TEMPLATE_SCHEMA_VERSION` (pure).

    Returns ``(migrated_copy, notes)``; the input is never modified, and the file
    on disk is left alone (the next save writes the current schema).

    - **v3 and older** had no analysis window. ``external_trigger_mode=True``
      becomes the equivalent window — Arduino code 1 starts it, code 0 stops it
      and ends the live session (``external_trigger_preset``) — and the legacy
      flag is turned off, because a project configured with BOTH is invalid
      (ADR-011, external-trigger gate). Any other v3 template gets
      ``analysis_window=None`` (whole recording).
    - **v4 and later** keep their window if it validates. One that does not is
      dropped with a note rather than carried into a project that would refuse
      to read it.

    - **v4 and older** saved no class roles: ``model_overrides`` becomes None
      (the roles resolve automatically, as they did for those templates).
    - **v5 and later** keep ``model_overrides`` normalised (names lowercased, the
      sha checked). Roles that cannot be read are dropped with a note.

    ``schema_version`` is left as found, so the confirmation step still shows
    which version the file was.
    """
    migrated = deepcopy(dict(template))
    version = _template_schema_version(template)
    notes = _migrate_analysis_window(migrated, version)
    notes.extend(_migrate_model_overrides(migrated, version))
    return migrated, tuple(notes)


def _migrate_analysis_window(migrated: dict[str, Any], version: int) -> list[str]:
    if version < 4:
        if bool(migrated.get("external_trigger_mode")):
            migrated["analysis_window"] = external_trigger_preset().model_dump(
                mode="json", by_alias=True
            )
            migrated["external_trigger_mode"] = False
            return [NOTE_EXTERNAL_TRIGGER_CONVERTED]
        migrated["analysis_window"] = None
        return []

    raw_window = migrated.get("analysis_window")
    if raw_window is None:
        migrated["analysis_window"] = None
        return []
    try:
        spec = WindowSpec.model_validate(raw_window)
    except ValidationError as exc:
        log.warning("template_manager.analysis_window.invalid", errors=exc.error_count())
        migrated["analysis_window"] = None
        return [NOTE_ANALYSIS_WINDOW_DROPPED]
    migrated["analysis_window"] = spec.model_dump(mode="json", by_alias=True)
    return []


def _migrate_model_overrides(migrated: dict[str, Any], version: int) -> list[str]:
    if version < 5:
        migrated[TEMPLATE_OVERRIDES_KEY] = None
        return []
    try:
        migrated[TEMPLATE_OVERRIDES_KEY] = normalise_model_overrides(
            migrated.get(TEMPLATE_OVERRIDES_KEY)
        )
    except ValueError as exc:
        log.warning("template_manager.class_roles.invalid", error=str(exc))
        migrated[TEMPLATE_OVERRIDES_KEY] = None
        return [NOTE_CLASS_ROLES_DROPPED]
    return []


def template_migration_note_text(note: str) -> str:
    """User-facing sentence for a :func:`migrate_template` note."""
    texts = {
        NOTE_EXTERNAL_TRIGGER_CONVERTED: _(
            "This template used 'External Trigger Mode'. It was converted into an "
            "analysis window: Arduino code 1 starts it, code 0 stops it and ends the "
            "live session. Review it in the Zone Configuration tab once the project exists."
        ),
        NOTE_ANALYSIS_WINDOW_DROPPED: _(
            "The template's analysis window could not be read and was dropped: the "
            "whole recording will be analysed."
        ),
        NOTE_CLASS_ROLES_DROPPED: _(
            "The template's class roles could not be read and were dropped: the roles "
            "of the weight's classes will be resolved automatically."
        ),
    }
    return texts.get(note, note)


class TemplateManager:
    """
    Manages wizard configuration templates.

    Templates are saved as JSON files in the user's config directory.
    Each template tracks a schema version and contains the key wizard
    preferences:
    - Project type (experimental/live)
    - Calibration settings (dimensions, animal count)
    - Analysis interval configuration
    - Design information (groups, days)
    - Parquet import scope and regex patterns
    - Model selection preferences (methods, weights, OpenVINO)
    - Detector thresholds (confidence/NMS/ByteTrack)
    - Live capture settings (camera, Arduino, timed recording, countdown)
    - Behavioral analysis configuration

    Schema v5 added ``model_overrides`` (class roles by name, see
    :data:`TEMPLATE_OVERRIDES_KEY`). Schema v4 added ``analysis_window`` (see
    :func:`migrate_template`). Schema v3
    added the live-capture block (camera/Arduino/recording/countdown)
    and ``behavioral_analysis``. The saved camera/Arduino selection is
    reconciled against the host hardware on load (see ``LiveConfigStep``); a
    saved device that is absent degrades gracefully instead of being applied
    blindly.
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
                # Live project experimental design fields
                "experiment_days": wizard_data.get("experiment_days"),
                "num_groups": wizard_data.get("num_groups"),
                "subjects_per_group": wizard_data.get("subjects_per_group"),
                "group_names": deepcopy(wizard_data.get("group_names")),
                # Live capture configuration (LiveConfig step). Camera/Arduino
                # are reconciled against host hardware on load (graceful
                # fallback when the saved device is absent).
                "camera_index": wizard_data.get("camera_index"),
                "camera_friendly_name": wizard_data.get("camera_friendly_name"),
                "use_arduino": wizard_data.get("use_arduino"),
                "arduino_port": wizard_data.get("arduino_port"),
                "external_trigger_mode": wizard_data.get("external_trigger_mode"),
                "use_timed_recording": wizard_data.get("use_timed_recording"),
                "recording_duration_s": wizard_data.get("recording_duration_s"),
                "use_countdown": wizard_data.get("use_countdown"),
                "countdown_duration_s": wizard_data.get("countdown_duration_s"),
                "preserve_real_aquarium_shape": wizard_data.get("preserve_real_aquarium_shape"),
                "selected_live_mode": wizard_data.get("selected_live_mode"),
                # Behavioral analysis configuration (Calibration step)
                "behavioral_analysis": deepcopy(wizard_data.get("behavioral_analysis")),
                # Analysis window (v4): START/STOP conditions, or None.
                "analysis_window": deepcopy(wizard_data.get("analysis_window")),
                # Class roles of the animal weight (v5), by name + sha, or None.
                TEMPLATE_OVERRIDES_KEY: template_model_overrides(wizard_data),
                # Folder organization fields
                "has_folder_structure": wizard_data.get("has_folder_structure"),
                "folder_meaning": wizard_data.get("folder_meaning"),
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

        except (OSError, json.JSONDecodeError, ValueError) as e:
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

        except (OSError, json.JSONDecodeError, KeyError) as e:
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

        except (OSError, json.JSONDecodeError, KeyError) as e:
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
                except (OSError, json.JSONDecodeError, KeyError) as e:
                    log.warning(
                        "template_manager.template_read_error",
                        path=str(template_path),
                        error=str(e),
                    )

            templates.sort(key=lambda t: t.get("created_at", ""), reverse=True)
            log.info("template_manager.templates_listed", count=len(templates))

        except (OSError, json.JSONDecodeError) as e:
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

        except (OSError, PermissionError) as e:
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


def format_template_banner_details(metadata: dict | None) -> str:
    """Return only the template identity — name plus file — with no prefix.

    ``format_template_banner`` wraps this in a translated "Template loaded:"
    prefix. ConfirmationStep's summary wants the identity *without* that prefix
    and used to obtain it by calling ``str.replace`` on the rendered banner,
    which silently stops matching the moment the prefix is translated. Anything
    that needs the bare identity must call this instead.
    """
    if not metadata:
        return ""

    name = metadata.get("name") or metadata.get("template_name")
    path = metadata.get("path")

    if not name and path:
        name = Path(path).stem

    if not name:
        return ""

    details = str(name)

    if path:
        details += f"  ({Path(path).name})"

    return details


def format_template_banner(metadata: dict | None) -> str:
    """Format banner text for loaded templates."""
    details = format_template_banner_details(metadata)

    if not details:
        return ""

    return _("Template loaded: {details}").format(details=details)

"""Model weight management and OpenVINO conversion module.

Manages YOLO model weights catalog, provides weight discovery, validation,
and handles conversion to OpenVINO format for optimized inference.
"""

import json
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Any

import structlog

from zebtrack.settings import Settings

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except ImportError:
    YOLO = None  # type: ignore[misc,assignment]
    ULTRALYTICS_AVAILABLE = False

from zebtrack.utils import calculate_sha256

WEIGHTS_CONFIG_FILE = "weights_config.json"
OPENVINO_CACHE_DIR = "openvino_model_cache"
DEFAULT_WEIGHTS_DIR = "weights"

log = structlog.get_logger()

OPENVINO_STATUS_NOT_CONVERTED = "not_converted"
OPENVINO_STATUS_CONVERTING = "converting"
OPENVINO_STATUS_READY = "ready"
OPENVINO_STATUS_FAILED = "failed"

# Target taxonomy: a weight is intended either to detect/segment the aquarium
# (background container) or the zebrafish (the animal subject). This is
# orthogonal to the model `type` (seg vs det), allowing 4 default-slot
# combinations: det+aquarium, det+zebrafish, seg+aquarium, seg+zebrafish.
TARGET_AQUARIUM = "aquarium"
TARGET_ZEBRAFISH = "zebrafish"
VALID_TARGETS = (TARGET_AQUARIUM, TARGET_ZEBRAFISH)
VALID_METHODS = ("seg", "det")


def _default_target_for_type(weight_type: str) -> str:
    """Return the default target inferred from a weight's type.

    Convention used by ZebTrack until v3.x: segmentation models track the
    zebrafish, detection models track the aquarium. Used as the migration
    fallback when an existing weight has no explicit `target` field.
    """
    return TARGET_ZEBRAFISH if weight_type == "seg" else TARGET_AQUARIUM


def _default_flag_key(method: str, target: str) -> str:
    """Build the dict key for a (method, target) default flag."""
    return f"is_default_{method}_{target}"


class OpenVINOExportError(Exception):
    """Exception raised when OpenVINO export or conversion fails.

    Raised when:
    - Model export to OpenVINO format fails
    - Required .xml file is missing after conversion
    - Model conversion process encounters an error
    - Ultralytics package is not available

    This exception replaces GUI messagebox calls for thread-safe error handling.

    Attributes:
        message: Human-readable error description
        weight_name: Optional name of the weight being converted
        model_path: Optional path to the model file
        cause: Optional underlying exception that caused this error
    """

    def __init__(
        self,
        message: str,
        weight_name: str | None = None,
        model_path: Path | str | None = None,
        cause: Exception | None = None,
    ):
        """
        Initialize OpenVINOExportError with structured error information.

        Args:
            message: Human-readable error description
            weight_name: Optional name of the weight being converted
            model_path: Optional path to the model file
            cause: Optional underlying exception that caused this error
        """
        self.weight_name = weight_name
        self.model_path = (
            Path(model_path) if model_path and not isinstance(model_path, Path) else model_path
        )
        self.cause = cause
        super().__init__(message)


class WeightManager:
    """Manages YOLO model weights catalog and OpenVINO conversion.

    Provides weight discovery, validation, metadata management, and handles
    conversion of PyTorch models to OpenVINO format for optimized inference.
    """

    def __init__(
        self,
        settings_obj: Settings | None = None,
        config_dir: Path | str = ".",
        weights_dir: Path | str | None = None,
    ):
        """Initialize WeightManager with settings dependency injection.

        Args:
            settings_obj: Settings instance (injected, required for non-test usage)
            config_dir: Directory for weights configuration file (and OpenVINO cache).
            weights_dir: Folder where ``.pt`` weight files live. When ``None`` it
                is resolved from ``settings_obj.weights.source_dir`` (default:
                ``"weights"``) joined with ``config_dir``. Created if missing.
        """
        self.settings = settings_obj
        self.config_dir = str(config_dir)
        self.config_path = os.path.join(self.config_dir, WEIGHTS_CONFIG_FILE)
        self.weights_dir = str(self._resolve_weights_dir(weights_dir))
        # Ensure the weights folder exists so discovery + add_weight can target it.
        try:
            os.makedirs(self.weights_dir, exist_ok=True)
        except OSError as e:
            log.warning(
                "weights.dir.create_failed",
                path=self.weights_dir,
                error=str(e),
            )
        self.weights: dict[str, Any] = {}
        self._runtime_slot_overrides: dict[tuple[str, str], str] = {}
        self._load_weights()

    def _resolve_weights_dir(self, override: Path | str | None) -> Path:
        """Resolve the weights folder path.

        Priority: explicit override > settings.weights.source_dir > DEFAULT_WEIGHTS_DIR.
        Relative paths are anchored at ``config_dir``. Defensive: any
        non-string/path value (e.g. a Mock from a partially-stubbed test
        settings) is silently ignored in favour of the default.
        """
        if override is not None:
            try:
                candidate = Path(os.fspath(override))
            except TypeError:
                candidate = Path(DEFAULT_WEIGHTS_DIR)
        else:
            source_dir: str | None = None
            if self.settings is not None:
                weights_settings = getattr(self.settings, "weights", None)
                if weights_settings is not None:
                    raw = getattr(weights_settings, "source_dir", None)
                    if isinstance(raw, str | os.PathLike):
                        source_dir = os.fspath(raw)
            candidate = Path(source_dir or DEFAULT_WEIGHTS_DIR)

        if not candidate.is_absolute():
            candidate = Path(self.config_dir) / candidate
        return candidate

    def _load_weights(self) -> None:
        """Load the weights configuration from the JSON file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    self.weights = json.load(f)

                # Migrate old format weights to new format with type support
                migrated = False
                for name, details in self.weights.items():
                    if "type" not in details:
                        # Classify weight type based on filename
                        weight_type = self._classify_weight_type(name) or "seg"
                        details["type"] = weight_type
                        details["is_default_seg"] = (
                            details.get("is_default", False) and weight_type == "seg"
                        )
                        details["is_default_det"] = (
                            details.get("is_default", False) and weight_type == "det"
                        )
                        migrated = True
                        log.info("weights.migration.type_added", name=name, type=weight_type)

                    # Migrate perspective field
                    if "perspective" not in details:
                        details["perspective"] = self._classify_perspective(name)
                        migrated = True
                        log.info(
                            "weights.migration.perspective_added",
                            name=name,
                            perspective=details["perspective"],
                        )

                    if "openvino_status" not in details:
                        if details.get("openvino_path"):
                            details["openvino_status"] = OPENVINO_STATUS_READY
                        else:
                            details["openvino_status"] = OPENVINO_STATUS_NOT_CONVERTED
                        migrated = True

                    if "last_conversion_error" not in details:
                        details["last_conversion_error"] = None
                        migrated = True

                    # Migrate `target` field (aquarium vs zebrafish).
                    if "target" not in details:
                        details["target"] = _default_target_for_type(details.get("type", "seg"))
                        migrated = True
                        log.info(
                            "weights.migration.target_added",
                            name=name,
                            target=details["target"],
                        )

                    # Migrate granular default flags (4 method×target slots).
                    # Promote legacy `is_default_seg` / `is_default_det` flags
                    # into the corresponding `is_default_<method>_<target>` slot
                    # using the weight's current target as anchor.
                    weight_type = details.get("type", "seg")
                    target = details.get("target", _default_target_for_type(weight_type))
                    legacy_default = bool(details.get(f"is_default_{weight_type}", False))
                    new_key = _default_flag_key(weight_type, target)
                    if new_key not in details:
                        details[new_key] = legacy_default
                        migrated = True
                    # Ensure all 4 slots exist (False unless already set).
                    for m in VALID_METHODS:
                        for t in VALID_TARGETS:
                            slot = _default_flag_key(m, t)
                            if slot not in details:
                                details[slot] = False
                                migrated = True

                    # Relocate stale absolute paths pointing to the project root
                    # to the new `weights/` folder when the file exists there.
                    new_path = self._maybe_relocate_path(name, details.get("path", ""))
                    if new_path is not None and new_path != details.get("path"):
                        details["path"] = new_path
                        migrated = True
                        log.info(
                            "weights.migration.path_relocated",
                            name=name,
                            new_path=new_path,
                        )

                if migrated:
                    self.save_weights()
                    log.info("weights.migration.completed")

                log.info("weights.config.loaded", path=self.config_path)
                # Auto-discover any new perspective weight files
                self.discover_perspective_weights()
            except (OSError, json.JSONDecodeError) as e:
                log.error("weights.config.load_error", error=str(e))
                self.weights = {}
                self._initialize_default_weight()
        else:
            self._initialize_default_weight()

    def get_weight_path_by_method(
        self,
        method: str,
        task: str,
        perspective: str | None = None,
    ) -> str | None:
        """
        Get the weight path for a specific method and task.

        Resolution precedence (most specific wins):
            1. Default flagged for ``(method, target, perspective)`` (perspective-aware)
            2. Default flagged for ``(method, target)`` regardless of perspective
            3. Any registered weight of ``(method, target)``
            4. Any registered weight of ``method`` (legacy / catch-all)

        Args:
            method: ``"seg"`` or ``"det"``.
            task: ``"aquarium"`` or ``"animal"`` (alias for ``"zebrafish"``).
                Used to look up the corresponding ``target``.
            perspective: Optional ``"lateral"`` or ``"top_down"``.

        Returns:
            Path to the appropriate weight file, or ``None`` if not found.
        """
        if method not in VALID_METHODS:
            log.error("weights.get_path.invalid_method", method=method, task=task)
            return None
        target = self._normalize_target_alias(task)

        if target:
            override_name, override_details = self.get_runtime_slot_override(method, target)
            if override_details is not None:
                path = override_details.get("path")
                log.info(
                    "weights.get_path.runtime_override",
                    method=method,
                    task=task,
                    target=target,
                    name=override_name,
                    path=path,
                )
                return path

        # 1. Perspective-aware lookup respecting target (when both provided).
        name: str | None = None
        details: dict | None = None
        if target and perspective:
            name, details = self._find_weight(
                method=method, target=target, perspective=perspective, default_only=True
            )
            if details is None:
                name, details = self._find_weight(
                    method=method,
                    target=target,
                    perspective=perspective,
                    default_only=False,
                )

        # 2. Default flag for (method, target) without perspective constraint.
        if details is None and target:
            name, details = self.get_default_weight_for(method, target)

        # 3. Legacy default for `method` only (back-compat).
        if details is None:
            if method == "seg":
                name, details = self.get_default_seg_weight()
            else:
                name, details = self.get_default_det_weight()

        # 4. Last-resort: any weight of the requested method.
        if details is None:
            for weight_name, weight_details in self.weights.items():
                if weight_details.get("type") == method:
                    name, details = weight_name, weight_details
                    break

        if details:
            path = details.get("path")
            log.info(
                "weights.get_path.selected",
                method=method,
                task=task,
                target=target,
                name=name,
                path=path,
            )
            return path
        log.warning("weights.get_path.not_found", method=method, task=task, target=target)
        return None

    @staticmethod
    def _normalize_target_alias(task: str | None) -> str | None:
        """Translate legacy ``task`` aliases into canonical target names."""
        if not task:
            return None
        task = task.lower().strip()
        if task in ("animal", "zebrafish", "fish"):
            return TARGET_ZEBRAFISH
        if task in ("aquarium", "aquario", "tank"):
            return TARGET_AQUARIUM
        return None

    def _find_weight(
        self,
        *,
        method: str,
        target: str,
        perspective: str | None,
        default_only: bool,
    ) -> tuple[str, dict] | tuple[None, None]:
        """Locate a weight matching the requested combination.

        Args:
            method: ``"seg"`` or ``"det"``.
            target: ``"aquarium"`` or ``"zebrafish"``.
            perspective: Required perspective (``"lateral"``/``"top_down"``) or ``None``.
            default_only: When ``True`` only weights flagged as default for the
                ``(method, target)`` slot are returned.
        """
        slot_key = _default_flag_key(method, target)
        for name, details in self.weights.items():
            if details.get("type") != method:
                continue
            if details.get("target") != target:
                continue
            if perspective is not None and details.get("perspective") != perspective:
                continue
            if default_only and not details.get(slot_key, False):
                continue
            return name, details
        return None, None

    def _classify_weight_type(self, filename: str) -> str | None:
        """
        Classifies weight type based on filename patterns.

        Supports both old and new naming conventions:
        - Old: ``*_seg.pt``, ``*_oi.pt``
        - New: ``*_seg_lateral.pt``, ``*_det_topdown.pt``, ``*_seg_topdown.pt``, etc.

        Args:
            filename: The weight filename

        Returns:
            "seg" for segmentation models, "det" for detection models,
            None if classification can't be determined from suffix.
        """
        filename_lower = filename.lower()
        # New perspective-aware patterns first (more specific)
        if "_seg_" in filename_lower or filename_lower.startswith("best_seg"):
            return "seg"
        if "_det_" in filename_lower or filename_lower.startswith("best_det"):
            return "det"
        # Legacy patterns
        if filename_lower.endswith("_seg.pt"):
            return "seg"
        if filename_lower.endswith("_oi.pt"):
            return "det"
        return None

    def _classify_perspective(self, filename: str) -> str | None:
        """Classify camera perspective from a weight filename.

        Recognizes ``*_lateral.pt`` and ``*_topdown.pt`` patterns.

        Args:
            filename: The weight filename

        Returns:
            "lateral", "top_down", or None if perspective can't be determined.
        """
        filename_lower = filename.lower()
        if "_lateral" in filename_lower:
            return "lateral"
        if "_topdown" in filename_lower:
            return "top_down"
        return None

    def discover_perspective_weights(self) -> int:
        """Auto-discover perspective weight files in the configured weights folder.

        Scans for ``best_*_lateral.pt`` and ``best_*_topdown.pt`` files that
        are not already registered and adds them to the catalog. Falls back
        to the legacy project-root location when the weights folder is empty,
        so migrated installs don't lose their pre-existing files.

        Returns:
            Number of newly discovered weights.
        """
        scan_dirs: list[Path] = [Path(self.weights_dir)]
        # Legacy fallback: also look at config_dir (project root) if it differs
        # — handles users who haven't yet copied their .pt files into weights/.
        legacy_root = Path(self.config_dir).resolve()
        if Path(self.weights_dir).resolve() != legacy_root:
            scan_dirs.append(legacy_root)

        discovered = 0
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for pattern in ("best_*_lateral.pt", "best_*_topdown.pt"):
                for pt_file in scan_dir.glob(pattern):
                    weight_name = pt_file.name
                    if weight_name in self.weights:
                        continue
                    weight_type = self._classify_weight_type(weight_name) or "seg"
                    perspective = self._classify_perspective(weight_name)
                    target = _default_target_for_type(weight_type)
                    self.weights[weight_name] = {
                        "path": str(pt_file.absolute()),
                        "is_default": True,
                        "type": weight_type,
                        "target": target,
                        "perspective": perspective,
                        "is_default_seg": weight_type == "seg",
                        "is_default_det": weight_type == "det",
                        "is_default_seg_aquarium": False,
                        "is_default_seg_zebrafish": False,
                        "is_default_det_aquarium": False,
                        "is_default_det_zebrafish": False,
                        "openvino_path": "",
                        "openvino_hash": "",
                        "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
                        "last_conversion_error": None,
                    }
                    discovered += 1
                    log.info(
                        "weights.auto_discover.found",
                        name=weight_name,
                        type=weight_type,
                        target=target,
                        perspective=perspective,
                        location=str(scan_dir),
                    )
        if discovered:
            self.save_weights()
        return discovered

    def _maybe_relocate_path(self, weight_name: str, current_path: Path | str) -> str | None:
        """Return a relocated absolute path if the weight now lives in `weights_dir`.

        When ``current_path`` points to a file that no longer exists (typically
        because the project was migrated from project-root weights to the
        ``weights/`` folder) but a same-named file exists inside ``weights_dir``,
        return the new absolute path. Otherwise return ``None`` (no change).
        """
        current_path = Path(current_path) if isinstance(current_path, str) else current_path
        if not weight_name:
            return None
        target = Path(self.weights_dir) / weight_name
        if not target.exists():
            return None
        # If current path already points at the same file, no relocation needed.
        try:
            if current_path and current_path.resolve() == target.resolve():
                return None
        except OSError:
            # current path may be malformed — fall through and relocate.
            pass
        # Only relocate when the previously-registered file is gone.
        if current_path and current_path.exists():
            return None
        return str(target.absolute())

    def _initialize_default_weight(self) -> None:
        """Initialize the config with the default weight from settings."""
        if self.settings is None:
            log.warning(
                "weight_manager.init.no_settings",
                message="Settings not injected, skipping initialization",
            )
            return

        log.info("weights.config.initializing_default")
        self.weights = {}

        # Check for both seg and det weights from settings
        potential_weights: list[tuple[str, str, str | None]] = []

        def _coerce_path(candidate: Any, *, source: str) -> str | None:
            """Convert candidate to filesystem path if possible, otherwise log and skip."""
            if not candidate:
                return None
            try:
                coerced = os.fspath(candidate)
            except TypeError:
                log.debug(
                    "weights.config.invalid_path_value",
                    source=source,
                    value_type=type(candidate).__name__,
                )
                return None
            return coerced

        # Add weights from the new settings - register them even if files don't
        # exist yet. This allows the weight management system to be configured
        # before files are available.
        weights_settings = getattr(self.settings, "weights", None)
        if weights_settings is not None:
            for perspective in ("lateral", "top_down"):
                pw = getattr(weights_settings, perspective, None)
                if pw is None:
                    continue
                seg_src = f"{perspective}_seg"
                seg_path = _coerce_path(getattr(pw, "seg_filename", None), source=seg_src)
                if seg_path:
                    potential_weights.append(("seg", seg_path, perspective))
                det_src = f"{perspective}_det"
                det_path = _coerce_path(getattr(pw, "det_filename", None), source=det_src)
                if det_path:
                    potential_weights.append(("det", det_path, perspective))

        # Check the legacy yolo_model.path for backward compatibility
        legacy_candidate = getattr(getattr(self.settings, "yolo_model", None), "path", None)
        legacy_path = _coerce_path(legacy_candidate, source="legacy_path")
        if legacy_path:
            legacy_name = os.path.basename(legacy_path)
            legacy_type = self._classify_weight_type(legacy_name)
            # Add legacy path if it's not already in potential_weights
            legacy_already_added = any(
                filename == legacy_path for _, filename, *_ in potential_weights
            )
            if not legacy_already_added:
                potential_weights.append((legacy_type or "seg", legacy_path, None))

        weights_found = False
        for weight_type, filename, perspective in potential_weights:
            resolved_filename = self._resolve_weight_filename(filename)
            # Only register weights if the file actually exists
            if not os.path.exists(resolved_filename):
                log.debug(
                    "weights.config.file_not_found",
                    filename=resolved_filename,
                    type=weight_type,
                )
                continue

            weight_name = os.path.basename(resolved_filename)
            classified_type = self._classify_weight_type(weight_name)
            # Use classified type if available, otherwise use the expected type
            final_type = classified_type or weight_type
            classified_perspective = self._classify_perspective(weight_name) or perspective
            target = _default_target_for_type(final_type)

            self.weights[weight_name] = {
                "path": str(Path(resolved_filename).absolute()),
                "is_default": True,  # Keep for backward compatibility
                "type": final_type,
                "target": target,
                "perspective": classified_perspective,
                "is_default_seg": final_type == "seg",
                "is_default_det": final_type == "det",
                "is_default_seg_aquarium": False,
                "is_default_seg_zebrafish": False,
                "is_default_det_aquarium": False,
                "is_default_det_zebrafish": False,
                "openvino_path": "",
                "openvino_hash": "",
                "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
                "last_conversion_error": None,
            }
            weights_found = True
            log.info(
                "weights.config.weight_initialized",
                name=weight_name,
                type=final_type,
                target=target,
                path=resolved_filename,
            )

        if weights_found:
            self.save_weights()
        else:
            log.warning(
                "weights.config.no_weights_found",
                lateral_seg=self.settings.weights.lateral.seg_filename,
                lateral_det=self.settings.weights.lateral.det_filename,
                topdown_seg=self.settings.weights.top_down.seg_filename,
                topdown_det=self.settings.weights.top_down.det_filename,
                legacy_path=legacy_path,
            )

        # Always sweep the weights folder so freshly-dropped .pt files are
        # registered even when the settings filenames are blank.
        self.discover_perspective_weights()

    def save_weights(self) -> None:
        """Save the current weights configuration to the JSON file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.weights, f, indent=4)
            log.info("weights.config.saved", path=self.config_path)
        except OSError as e:
            log.error("weights.config.save_error", error=str(e))
            raise OSError(f"Não foi possível salvar o arquivo de configuração de pesos: {e}") from e

    def get_all_weights(self) -> list[str]:
        """Return a list of names of all available weights."""
        return list(self.weights.keys())

    def get_weight_details(self, name: str) -> dict | None:
        """Return the details dictionary for a given weight name."""
        return self.weights.get(name)

    def get_default_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Return the name and details of the default weight."""
        for name, details in self.weights.items():
            if details.get("is_default"):
                return name, details
        # Gracefully fall back to type-specific defaults when legacy data lacks `is_default`
        # Gracefully fall back to type-specific defaults when legacy data lacks `is_default`
        seg_name, seg_details = self.get_default_seg_weight()
        if seg_name and seg_details:
            return seg_name, seg_details
        det_name, det_details = self.get_default_det_weight()
        if det_name and det_details:
            return det_name, det_details
        return None, None

    def get_default_weight_by_type(self, weight_type: str) -> tuple[str, dict] | tuple[None, None]:
        """
        Return the name and details of the default weight for a specific type.

        Args:
            weight_type: "seg" or "det"

        Returns:
            Tuple of (name, details) or (None, None) if not found
        """
        default_key = f"is_default_{weight_type}"
        for name, details in self.weights.items():
            if details.get(default_key):
                return name, details
        return None, None

    def get_default_seg_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Return the name and details of the default segmentation weight."""
        return self.get_default_weight_by_type("seg")

    def get_default_det_weight(self) -> tuple[str, dict] | tuple[None, None]:
        """Return the name and details of the default detection weight."""
        return self.get_default_weight_by_type("det")

    def get_weight_by_perspective_and_type(
        self,
        perspective: str,
        weight_type: str,
    ) -> tuple[str, dict] | tuple[None, None]:
        """Return the best matching weight for a perspective and type.

        Lookup order:
        1. Exact match on both ``perspective`` and ``weight_type``.
        2. Fallback to any weight of the requested ``weight_type`` (ignoring perspective).
        3. ``(None, None)`` if nothing matches.

        Args:
            perspective: "lateral" or "top_down"
            weight_type: "seg" or "det"

        Returns:
            Tuple of (name, details) or (None, None)
        """
        fallback: tuple[str, dict] | tuple[None, None] = (None, None)
        for name, details in self.weights.items():
            if details.get("type") != weight_type:
                continue
            if details.get("perspective") == perspective:
                return name, details
            # Keep first type-matching entry as fallback
            if fallback[0] is None:
                fallback = (name, details)
        return fallback

    def set_default_weight_by_type(self, name_to_set: str, weight_type: str) -> None:
        """Set a new default weight for a specific type (legacy wrapper).

        .. deprecated:: 3.4
            Prefer :meth:`set_default_weight_for` which lets callers specify
            both ``method`` and ``target`` independently. This wrapper keeps
            existing call sites working by inferring the target from the
            weight's current ``target`` field (falling back to the type
            convention).
        """
        if name_to_set not in self.weights:
            log.error(
                "weights.default_by_type.not_found",
                name=name_to_set,
                type=weight_type,
            )
            return

        weight_details = self.weights[name_to_set]
        if weight_details.get("type") != weight_type:
            log.warning(
                "weights.default_by_type.type_mismatch",
                name=name_to_set,
                expected_type=weight_type,
                actual_type=weight_details.get("type"),
            )
            return

        target = weight_details.get("target") or _default_target_for_type(weight_type)
        self.set_default_weight_for(name_to_set, method=weight_type, target=target)

    def set_default_weight(self, name: str) -> bool:
        """Set a new default weight with proper type handling."""
        target_weight = self.get_weight_details(name)
        if not target_weight:
            log.warning("set_default.not_found", name=name)
            return False

        weight_type = target_weight.get("type", "unknown")
        if weight_type not in ("seg", "det"):
            log.error("set_default.unknown_type", name=name, type=weight_type)
            return False

        # Reset all defaults
        for weight in self.weights.values():
            weight["is_default"] = False
            if weight.get("type") == "seg":
                weight["is_default_seg"] = False
            if weight.get("type") == "det":
                weight["is_default_det"] = False

        # Set the new default
        target_weight["is_default"] = True
        if weight_type == "seg":
            target_weight["is_default_seg"] = True
        elif weight_type == "det":
            target_weight["is_default_det"] = True

        log.info("set_default.success", name=name, type=weight_type)
        self.save_weights()
        return True

    def _resolve_weight_filename(self, filename: str) -> str:
        """Resolve a bare filename to ``weights_dir/<filename>`` when needed.

        When ``filename`` already has a directory component or is absolute,
        it is returned unchanged. Bare filenames (e.g. ``"best_seg.pt"``)
        are anchored at :attr:`weights_dir`. This keeps `config.yaml`
        configuration concise while honouring the configured weights folder.
        """
        candidate = Path(filename)
        if candidate.is_absolute() or candidate.parent != Path("."):
            return str(candidate)
        return str(Path(self.weights_dir) / candidate)

    def add_weight(
        self,
        new_path: Path | str,
        set_as_default: bool,
        weight_type: str | None = None,
        target: str | None = None,
    ) -> None:
        """
        Add a new weight from a given path after performing security checks.

        External ``.pt`` files (outside the project directory) are copied into
        :attr:`weights_dir` so the registered path remains stable across
        environments.

        Args:
            new_path: The file path to the new .pt weight file.
            set_as_default: If True, this new weight will become the default.
            weight_type: Optional weight type ("seg" or "det"). If None, will be
                classified from filename.
            target: Optional ``"aquarium"``/``"zebrafish"``. When ``None`` it
                is inferred from ``weight_type`` (seg→zebrafish, det→aquarium).
        """
        new_path = Path(new_path) if isinstance(new_path, str) else new_path
        # --- Security Check: Path Traversal ---
        try:
            project_dir = Path(self.config_dir).resolve()
            weights_dir = Path(self.weights_dir).resolve()
            # strict=True checks existence
            model_path = new_path.resolve(strict=True)
            stored_path = new_path.absolute()

            # If the file is outside the project tree, copy it into weights_dir.
            if not model_path.is_relative_to(project_dir):
                log.info("weights.add.external_file.copying", source=str(model_path))
                try:
                    weights_dir.mkdir(parents=True, exist_ok=True)
                    target_path = weights_dir / model_path.name
                    if target_path.exists():
                        if target_path.resolve() == model_path.resolve():
                            model_path = target_path
                            stored_path = target_path.absolute()
                            log.info(
                                "weights.add.external_file.same_file",
                                path=str(target_path),
                            )
                        else:
                            raise ValueError(
                                f"Um arquivo de peso com o nome '{model_path.name}' já existe "
                                f"no diretório de pesos.\n\n"
                                f"Arquivo existente: {target_path}\n"
                                f"Arquivo sendo adicionado: {model_path}\n\n"
                                f"Por favor, renomeie um dos arquivos antes de adicionar."
                            )
                    else:
                        shutil.copy2(model_path, target_path)
                        model_path = target_path
                        stored_path = target_path.absolute()
                        log.info(
                            "weights.add.external_file.copied",
                            target=str(target_path),
                        )
                except OSError as e:
                    log.error("weights.add.external_file.copy_failed", error=str(e))
                    raise ValueError(f"Falha ao copiar o arquivo de peso externo: {e}") from e
        except FileNotFoundError:
            log.error("weights.add.not_found", path=new_path)
            raise FileNotFoundError(f"O arquivo de modelo não foi encontrado: {new_path}") from None
        except OSError as e:
            log.error("weights.add.invalid_path", path=new_path, error=str(e))
            raise ValueError(f"O caminho do modelo é inválido ou inacessível: {e}") from e
        # --- End Security Check ---

        new_name = os.path.basename(model_path)
        if new_name in self.weights:
            raise ValueError(f"Um peso com o nome '{new_name}' já existe.")

        # Determine weight type
        if weight_type is None:
            weight_type = self._classify_weight_type(new_name)

        # If still can't classify, this will need to be handled by the caller
        # (GUI should prompt user for type)
        if weight_type is None:
            log.warning("weights.add.type_unclassified", name=new_name)
            # For backward compatibility, default to "seg"
            weight_type = "seg"

        # Resolve target (caller-provided or convention-based default).
        if target is None:
            target = _default_target_for_type(weight_type)
        if target not in VALID_TARGETS:
            log.warning("weights.add.invalid_target_fallback", target=target)
            target = _default_target_for_type(weight_type)

        if set_as_default:
            # Unset legacy global default
            _, current_default = self.get_default_weight()
            if current_default:
                current_default["is_default"] = False

        slot_key = _default_flag_key(weight_type, target)

        # Store the safe, resolved path
        self.weights[new_name] = {
            "path": str(stored_path),
            "is_default": set_as_default,
            "type": weight_type,
            "target": target,
            "perspective": self._classify_perspective(new_name),
            "is_default_seg": weight_type == "seg" and set_as_default,
            "is_default_det": weight_type == "det" and set_as_default,
            "is_default_seg_aquarium": False,
            "is_default_seg_zebrafish": False,
            "is_default_det_aquarium": False,
            "is_default_det_zebrafish": False,
            "openvino_path": "",
            "openvino_hash": "",
            "openvino_status": OPENVINO_STATUS_NOT_CONVERTED,
            "last_conversion_error": None,
        }
        if set_as_default:
            # Promote to the granular default slot too.
            self.weights[new_name][slot_key] = True

        self.save_weights()
        log.info(
            "weights.add.success",
            name=new_name,
            path=str(model_path),
            type=weight_type,
            target=target,
        )

    def delete_weight(self, name_to_delete: str) -> None:
        """Delete a weight from the configuration."""
        if name_to_delete not in self.weights:
            log.warning("weights.delete.not_found", name=name_to_delete)
            raise ValueError(f"Peso '{name_to_delete}' não encontrado.")

        if len(self.weights) <= 1:
            log.error("weights.delete.last_weight", name=name_to_delete)
            raise ValueError("Você não pode excluir o último peso disponível.")

        details = self.weights[name_to_delete]
        was_default = details.get("is_default")

        # Delete the OpenVINO cache if it exists
        if details.get("openvino_path") and os.path.exists(details["openvino_path"]):
            shutil.rmtree(details["openvino_path"], ignore_errors=True)
            log.info(
                "weights.delete.openvino_cache_removed",
                path=details["openvino_path"],
            )

        # We don't delete the .pt file itself, just the entry from our config

        del self.weights[name_to_delete]

        # If the deleted weight was the default, set another one as default
        if was_default:
            first_remaining_weight = next(iter(self.weights.keys()))
            self.set_default_weight(first_remaining_weight)

        self.save_weights()
        log.info("weights.delete.success", name=name_to_delete)

    # ------------------------------------------------------------------
    # New API: 4-slot defaults + target reclassification + maintenance
    # ------------------------------------------------------------------

    def get_default_weight_for(
        self, method: str, target: str
    ) -> tuple[str, dict] | tuple[None, None]:
        """Return the weight flagged as default for a (method, target) slot.

        Args:
            method: ``"seg"`` or ``"det"``.
            target: ``"aquarium"`` or ``"zebrafish"``.
        """
        if method not in VALID_METHODS or target not in VALID_TARGETS:
            return None, None
        slot_key = _default_flag_key(method, target)
        for name, details in self.weights.items():
            if details.get(slot_key):
                return name, details
        return None, None

    def get_runtime_slot_override(
        self, method: str, target: str
    ) -> tuple[str, dict] | tuple[None, None]:
        """Return the temporary runtime override for a (method, target) slot."""
        if method not in VALID_METHODS or target not in VALID_TARGETS:
            return None, None

        name = self._runtime_slot_overrides.get((method, target))
        if not name:
            return None, None

        details = self.get_weight_details(name)
        if details is None:
            log.warning(
                "weights.runtime_override.missing_weight",
                method=method,
                target=target,
                name=name,
            )
            self._runtime_slot_overrides.pop((method, target), None)
            return None, None

        if details.get("type") != method:
            log.warning(
                "weights.runtime_override.type_mismatch",
                method=method,
                target=target,
                name=name,
                actual=details.get("type"),
            )
            return None, None

        return name, details

    def set_runtime_slot_overrides(
        self, overrides: dict[tuple[str, str], str | None] | None
    ) -> None:
        """Apply temporary per-slot overrides used only during runtime.

        These overrides do not touch persisted default flags and are intended
        for project-scoped model selection while preserving the global catalog.
        Invalid slot keys or unknown weights are ignored.
        """
        self._runtime_slot_overrides.clear()
        if not overrides:
            return

        for (method, target), name in overrides.items():
            if not name or method not in VALID_METHODS or target not in VALID_TARGETS:
                continue
            details = self.get_weight_details(name)
            if details is None or details.get("type") != method:
                log.warning(
                    "weights.runtime_override.skipped",
                    method=method,
                    target=target,
                    name=name,
                )
                continue
            self._runtime_slot_overrides[(method, target)] = name

    def clear_runtime_slot_overrides(self) -> None:
        """Remove all temporary runtime slot overrides."""
        self._runtime_slot_overrides.clear()

    def set_default_weight_for(self, name: str, *, method: str, target: str) -> bool:
        """Set ``name`` as the default weight for the (method, target) slot.

        The weight's ``type`` must equal ``method`` (a det weight cannot be a
        segmentation default). If the weight's ``target`` differs from the
        requested ``target`` it is reclassified — the user is intentionally
        repurposing it. Other weights' default flag for the same slot is
        cleared. Legacy ``is_default_<method>`` flag is also kept in sync for
        backward compatibility with code paths that still read it.

        Returns:
            True on success, False if the weight is unknown or method invalid.
        """
        if method not in VALID_METHODS or target not in VALID_TARGETS:
            log.error(
                "weights.set_default_for.invalid_args",
                name=name,
                method=method,
                target=target,
            )
            return False
        if name not in self.weights:
            log.error("weights.set_default_for.not_found", name=name)
            return False

        details = self.weights[name]
        if details.get("type") != method:
            log.warning(
                "weights.set_default_for.type_mismatch",
                name=name,
                expected=method,
                actual=details.get("type"),
            )
            return False

        # Reclassify target if necessary (explicit user choice).
        if details.get("target") != target:
            details["target"] = target
            log.info(
                "weights.set_default_for.target_reclassified",
                name=name,
                target=target,
            )

        slot_key = _default_flag_key(method, target)
        # Clear current default for this slot
        for other in self.weights.values():
            other[slot_key] = False
        details[slot_key] = True
        # Keep legacy flag in sync so old consumers still resolve a default.
        legacy_key = f"is_default_{method}"
        for other in self.weights.values():
            other[legacy_key] = False
        details[legacy_key] = True

        self.save_weights()
        log.info(
            "weights.set_default_for.success",
            name=name,
            method=method,
            target=target,
        )
        return True

    def set_weight_target(self, name: str, target: str) -> bool:
        """Reclassify the ``target`` of an existing weight.

        Useful for legacy weights or when the user wants to reuse a model
        across both aquarium and zebrafish workflows.
        """
        if target not in VALID_TARGETS:
            log.error("weights.set_target.invalid", name=name, target=target)
            return False
        if name not in self.weights:
            log.error("weights.set_target.not_found", name=name)
            return False
        self.weights[name]["target"] = target
        self.save_weights()
        log.info("weights.set_target.success", name=name, target=target)
        return True

    @staticmethod
    def _rmtree_with_unlock(path: str | Path, retries: int = 3) -> bool:
        """``shutil.rmtree`` with chmod-unlock + retry for OneDrive locks.

        Mirrors the pattern in ``asset_manager._rmtree_safe`` and
        ``report_generator_actions.delete_all_unified_reports``: when a file
        is read-only or locked by OneDrive sync, ``onerror`` clears the
        read-only bit and retries the deletion. The whole rmtree is
        attempted up to ``retries`` times with a short sleep between
        attempts to ride out transient locks (e.g. antivirus scans).

        Returns ``True`` on success, ``False`` if every attempt failed.
        Note: open file handles (e.g. an OpenVINO runtime that still has
        the .xml/.bin mapped into memory) cannot be unlocked this way —
        the caller must drop the handle first or the user must restart
        the app.
        """

        def _on_rm_error(func: Any, fpath: str | Path, _exc_info: Any) -> None:
            try:
                os.chmod(fpath, stat.S_IWRITE)
                func(fpath)
            except OSError:
                # Best-effort: caller's outer retry loop may still recover.
                pass

        for attempt in range(retries):
            try:
                shutil.rmtree(path, onerror=_on_rm_error)
                return True
            except OSError:
                if attempt < retries - 1:
                    time.sleep(0.5)
        return False

    def clear_openvino_cache(self, name: str | None = None) -> dict[str, Any]:
        """Remove OpenVINO cache directories and reset their status.

        Uses :meth:`_rmtree_with_unlock` for OneDrive/read-only resilience.
        Caches are deleted **and** the in-memory + on-disk registry status
        is reset for every weight processed, even when the directory could
        not be removed (so the UI doesn't show stale "ready" state).

        Args:
            name: If provided, only the cache for this weight is removed.
                When ``None`` (default), all OpenVINO conversions are wiped
                — including orphaned folders inside ``openvino_model_cache``
                that don't correspond to any registered weight.

        Returns:
            Dict with three lists for UI feedback:
              ``cleared``: weight names whose cache was removed (or already absent)
              ``locked``:  weight names whose .xml/.bin couldn't be deleted
                           (typically because the running detector still has
                           the file open — ask the user to restart the app)
              ``orphans_locked``: orphan folders that resisted deletion
        """
        cleared: list[str] = []
        locked: list[str] = []
        orphans_locked: list[str] = []

        targets: list[str]
        if name is not None:
            if name not in self.weights:
                log.warning("weights.clear_cache.not_found", name=name)
                return {"cleared": [], "locked": [], "orphans_locked": []}
            targets = [name]
        else:
            targets = list(self.weights.keys())

        for weight_name in targets:
            details = self.weights[weight_name]
            cache_path = details.get("openvino_path")
            removed = True
            if cache_path and os.path.isdir(cache_path):
                removed = self._rmtree_with_unlock(cache_path)
                if removed:
                    log.info(
                        "weights.clear_cache.removed",
                        name=weight_name,
                        path=cache_path,
                    )
                else:
                    locked.append(weight_name)
                    log.warning(
                        "weights.clear_cache.locked",
                        name=weight_name,
                        path=cache_path,
                        message=(
                            "Cache could not be deleted (OneDrive sync lock "
                            "or open file handle). Restart the app and retry."
                        ),
                    )
            # Reset metadata regardless: keeping a 'ready' status pointing at
            # a half-deleted folder is worse than reporting 'not_converted'.
            details["openvino_path"] = ""
            details["openvino_hash"] = ""
            details["openvino_status"] = OPENVINO_STATUS_NOT_CONVERTED
            details["last_conversion_error"] = None
            for k in ("openvino_int8_path", "openvino_int8_hash", "openvino_int8_status"):
                if k in details:
                    details[k] = OPENVINO_STATUS_NOT_CONVERTED if k.endswith("status") else ""
            if removed:
                cleared.append(weight_name)

        # When wiping everything, also delete orphan folders not tied to a
        # registered weight (e.g. conversions of since-deleted weights).
        if name is None:
            cache_root = Path(self.config_dir) / OPENVINO_CACHE_DIR
            if cache_root.exists():
                for entry in cache_root.iterdir():
                    if not (entry.is_dir() and entry.name.endswith("_openvino_model")):
                        continue
                    if self._rmtree_with_unlock(entry):
                        log.info("weights.clear_cache.orphan_removed", path=str(entry))
                    else:
                        orphans_locked.append(entry.name)
                        log.warning(
                            "weights.clear_cache.orphan_locked",
                            path=str(entry),
                        )

        self.save_weights()
        return {
            "cleared": cleared,
            "locked": locked,
            "orphans_locked": orphans_locked,
        }

    def rescan_source_folder(self) -> int:
        """Re-run discovery against the configured weights folder.

        Convenience wrapper around :meth:`discover_perspective_weights` that
        simply reports how many new files were registered. Existing entries
        are left untouched (use :meth:`reset_registry` for a clean slate).
        """
        added = self.discover_perspective_weights()
        log.info("weights.rescan.completed", added=added, weights_dir=self.weights_dir)
        return added

    def reset_registry(self) -> int:
        """Wipe ``weights_config.json`` and rebuild from defaults + discovery.

        Returns:
            The number of weights present in the registry after the reset.
        """
        # Drop in-memory state first to avoid persisting stale entries.
        self.weights = {}
        try:
            if os.path.exists(self.config_path):
                os.unlink(self.config_path)
                log.info("weights.reset.registry_removed", path=self.config_path)
        except OSError as e:
            log.warning(
                "weights.reset.registry_remove_failed",
                path=self.config_path,
                error=str(e),
            )
        # Re-seed from settings and rescan the weights folder.
        self._initialize_default_weight()
        self.discover_perspective_weights()
        return len(self.weights)

    def validate_weight_files(self) -> dict[str, bool]:
        """Check on-disk presence of every registered weight's ``.pt`` file.

        Returns:
            Mapping ``{weight_name: file_exists}``. Useful for the UI to mark
            broken/missing weights without unregistering them automatically.
        """
        result: dict[str, bool] = {}
        for name, details in self.weights.items():
            path = details.get("path", "")
            result[name] = bool(path) and os.path.isfile(path)
        return result

    def convert_to_openvino(self, name: str) -> str | None:
        """
        Convert the specified weight to OpenVINO format.

        Handles caching and updates the config file.
        Returns the path to the converted model directory or None on failure.
        """
        details = self.get_weight_details(name)
        if not details:
            log.error("openvino.convert.not_found", name=name)
            return None

        pt_path = details["path"]
        base_model_name = os.path.splitext(os.path.basename(pt_path))[0]
        cached_model_dir_name = f"{base_model_name}_openvino_model"

        # The cache should be relative to the manager's config directory
        openvino_base_cache_dir = os.path.join(self.config_dir, OPENVINO_CACHE_DIR)
        cached_model_dir = os.path.join(openvino_base_cache_dir, cached_model_dir_name)

        if os.path.exists(cached_model_dir):
            log.info("openvino.cache.found", path=cached_model_dir)
            # Ensure the path is absolute for consistency
            details["openvino_path"] = os.path.abspath(cached_model_dir)
            details["openvino_status"] = OPENVINO_STATUS_READY
            details["last_conversion_error"] = None
            self.save_weights()
            return details["openvino_path"]

        log.info("openvino.export.start", model=name)
        temp_export_path = None

        if not ULTRALYTICS_AVAILABLE:
            details["openvino_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = "Ultralytics package is required for OpenVINO export"
            details["openvino_path"] = ""
            details["openvino_hash"] = ""
            self.save_weights()
            raise ImportError(
                "Ultralytics is not available for OpenVINO export. "
                "Please install ultralytics package."
            )

        details["openvino_status"] = OPENVINO_STATUS_CONVERTING
        details["last_conversion_error"] = None
        self.save_weights()

        try:
            assert YOLO is not None  # Satisfy type checkers after availability guard
            model = YOLO(pt_path)
            # The 'half=True' argument enables FP16 quantization.
            # The export will create a directory named e.g., 'yolov8n_openvino_model'.
            temp_export_path = model.export(format="openvino", half=True)

            os.makedirs(openvino_base_cache_dir, exist_ok=True)

            # In case of a previous failed attempt, remove the destination first.
            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)

            # Atomically move the exported model to its final destination.
            shutil.move(temp_export_path, cached_model_dir)
            temp_export_path = None  # The move was successful

            # Determina o tipo de modelo e cria metadata apropriado
            weight_type = details.get("type", "seg")

            # Extract real class names from the model
            class_names = {str(k): v for k, v in model.names.items()}
            num_classes = len(class_names)

            if weight_type == "seg":
                metadata = {
                    "model_type": "instance_segmentation",
                    "num_classes": num_classes,
                    "class_names": class_names,
                    "task": "segment",
                    "weight_type": "seg",
                    "description": (
                        "Modelo de segmentação convertido (classes extraídas do modelo)"
                    ),
                    "original_model": os.path.basename(pt_path),
                    "conversion_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            else:  # det
                metadata = {
                    "model_type": "object_detection",
                    "num_classes": num_classes,
                    "class_names": class_names,
                    "task": "detect",
                    "weight_type": "det",
                    "description": "Modelo de detecção convertido (classes extraídas do modelo)",
                    "original_model": os.path.basename(pt_path),
                    "conversion_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

            metadata_path = os.path.join(cached_model_dir, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            log.info(
                "openvino.metadata.created",
                path=metadata_path,
                model_type=metadata["model_type"],
                weight_type=weight_type,
            )

            # Now that the model is in place, calculate its hash and save.
            openvino_model_path = os.path.abspath(cached_model_dir)
            xml_files = list(Path(cached_model_dir).glob("*.xml"))
            if not xml_files:
                log.error("openvino.export.xml_not_found", path=cached_model_dir)
                # Clean up the corrupted cache dir
                shutil.rmtree(cached_model_dir, ignore_errors=True)
                details["openvino_status"] = OPENVINO_STATUS_FAILED
                details["last_conversion_error"] = (
                    "Arquivo .xml do modelo OpenVINO não encontrado após a conversão."
                )
                self.save_weights()
                raise OpenVINOExportError(
                    "Arquivo .xml do modelo OpenVINO não encontrado após a conversão."
                )

            xml_path = xml_files[0]
            model_hash = calculate_sha256(str(xml_path))

            details["openvino_path"] = openvino_model_path
            details["openvino_hash"] = model_hash
            details["openvino_status"] = OPENVINO_STATUS_READY
            details["last_conversion_error"] = None
            self.save_weights()

            log.info(
                "openvino.export.success",
                path=openvino_model_path,
                hash=model_hash,
            )
            return openvino_model_path

        # except Exception justified: OpenVINO model export
        except Exception as e:
            log.error("openvino.export.failed", exc_info=e)
            # Clean up any partial export directory if it exists
            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)
            details["openvino_path"] = ""
            details["openvino_hash"] = ""
            details["openvino_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = str(e)
            self.save_weights()
            raise OpenVINOExportError(
                f"Falha ao converter '{name}' para o formato OpenVINO: {e}"
            ) from e
        finally:
            # Clean up the temporary export directory if the move failed
            if temp_export_path and os.path.exists(temp_export_path):
                shutil.rmtree(temp_export_path, ignore_errors=True)
                log.info("openvino.export.cleanup", path=temp_export_path)

    def convert_to_openvino_int8(self, name: str) -> str | None:
        """Convert the specified weight to OpenVINO INT8 quantized format.

        Uses Ultralytics built-in INT8 quantization (NNCF under the hood)
        with default COCO calibration data. Provides 2-4x speedup on CPU
        with minimal accuracy loss (<1%).

        Args:
            name: Weight name from weights_config.json.

        Returns:
            Path to the converted INT8 model directory or None on failure.

        Raises:
            OpenVINOExportError: If conversion fails.
        """
        details = self.get_weight_details(name)
        if not details:
            log.error("openvino.convert_int8.not_found", name=name)
            return None

        pt_path = details["path"]
        base_model_name = os.path.splitext(os.path.basename(pt_path))[0]
        cached_model_dir_name = f"{base_model_name}_openvino_int8_model"

        openvino_base_cache_dir = os.path.join(self.config_dir, OPENVINO_CACHE_DIR)
        cached_model_dir = os.path.join(openvino_base_cache_dir, cached_model_dir_name)

        if os.path.exists(cached_model_dir):
            log.info("openvino.int8_cache.found", path=cached_model_dir)
            details["openvino_int8_path"] = os.path.abspath(cached_model_dir)
            details["openvino_int8_status"] = OPENVINO_STATUS_READY
            self.save_weights()
            return details["openvino_int8_path"]

        log.info("openvino.export_int8.start", model=name)
        temp_export_path = None

        if not ULTRALYTICS_AVAILABLE:
            details["openvino_int8_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = "Ultralytics package is required for INT8 export"
            self.save_weights()
            raise ImportError(
                "Ultralytics is not available for INT8 export. Please install ultralytics package."
            )

        details["openvino_int8_status"] = OPENVINO_STATUS_CONVERTING
        details["last_conversion_error"] = None
        self.save_weights()

        try:
            assert YOLO is not None
            model = YOLO(pt_path)
            # int8=True enables INT8 quantization via NNCF with default calibration
            temp_export_path = model.export(format="openvino", int8=True)

            os.makedirs(openvino_base_cache_dir, exist_ok=True)

            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)

            shutil.move(temp_export_path, cached_model_dir)
            temp_export_path = None

            weight_type = details.get("type", "seg")
            class_names = {str(k): v for k, v in model.names.items()}
            num_classes = len(class_names)

            model_type = "instance_segmentation" if weight_type == "seg" else "object_detection"
            metadata = {
                "model_type": model_type,
                "num_classes": num_classes,
                "class_names": class_names,
                "task": "segment" if weight_type == "seg" else "detect",
                "weight_type": weight_type,
                "quantization": "INT8",
                "description": f"Modelo {weight_type} convertido com quantização INT8",
                "original_model": os.path.basename(pt_path),
                "conversion_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            metadata_path = os.path.join(cached_model_dir, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            log.info(
                "openvino.int8_metadata.created",
                path=metadata_path,
                model_type=metadata["model_type"],
            )

            openvino_model_path = os.path.abspath(cached_model_dir)
            xml_files = list(Path(cached_model_dir).glob("*.xml"))
            if not xml_files:
                log.error("openvino.export_int8.xml_not_found", path=cached_model_dir)
                shutil.rmtree(cached_model_dir, ignore_errors=True)
                details["openvino_int8_status"] = OPENVINO_STATUS_FAILED
                details["last_conversion_error"] = (
                    "Arquivo .xml do modelo INT8 não encontrado após conversão."
                )
                self.save_weights()
                raise OpenVINOExportError(
                    "Arquivo .xml do modelo INT8 não encontrado após conversão."
                )

            xml_path = xml_files[0]
            model_hash = calculate_sha256(str(xml_path))

            details["openvino_int8_path"] = openvino_model_path
            details["openvino_int8_hash"] = model_hash
            details["openvino_int8_status"] = OPENVINO_STATUS_READY
            details["last_conversion_error"] = None
            self.save_weights()

            log.info(
                "openvino.export_int8.success",
                path=openvino_model_path,
                hash=model_hash,
            )
            return openvino_model_path

        except Exception as e:
            log.error("openvino.export_int8.failed", exc_info=e)
            if os.path.exists(cached_model_dir):
                shutil.rmtree(cached_model_dir, ignore_errors=True)
            details["openvino_int8_path"] = ""
            details["openvino_int8_hash"] = ""
            details["openvino_int8_status"] = OPENVINO_STATUS_FAILED
            details["last_conversion_error"] = str(e)
            self.save_weights()
            raise OpenVINOExportError(f"Falha ao converter '{name}' para INT8: {e}") from e
        finally:
            if temp_export_path and os.path.exists(temp_export_path):
                shutil.rmtree(temp_export_path, ignore_errors=True)
                log.info("openvino.export_int8.cleanup", path=temp_export_path)

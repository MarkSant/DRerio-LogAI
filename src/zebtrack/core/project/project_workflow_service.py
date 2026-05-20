"""
Project Workflow Service for ZebTrack-AI.

Phase 5: Project Workflow Simplification
Consolidates all project workflow logic (creation, opening, configuration)
from the controller into a dedicated service.

This service provides:
- Project creation orchestration with wizard integration
- Project opening and state restoration
- Model settings resolution and application
- Parameter validation and preparation
- Post-creation user guidance
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.core.exceptions import ProjectInvalidError
from zebtrack.core.services.weight_manager import TARGET_AQUARIUM, TARGET_ZEBRAFISH, VALID_METHODS

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.model_service import ModelService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.settings import Settings

log = structlog.get_logger()


class ProjectWorkflowService:
    """
    Service for managing project workflows.

    Phase 5: Consolidates project creation, opening, and configuration logic
    from MainViewModel, making project workflows testable and reducing controller complexity.

    Responsibilities:
    - Orchestrate project creation with wizard data
    - Orchestrate project opening and state restoration
    - Validate and prepare project parameters
    - Resolve and apply model settings
    - Import wizard data (parquets, ROIs, etc.)
    - Display post-creation guidance
    """

    _SLOT_SEPARATOR = ":"

    def __init__(
        self,
        project_manager: ProjectManager,
        model_service: ModelService,
        state_manager: StateManager,
        ui_coordinator: UIScheduler | None = None,
        settings_obj: Settings | None = None,
    ):
        """
        Initialize ProjectWorkflowService.

        Args:
            project_manager: ProjectManager instance for project operations
            model_service: ModelService instance for model configuration
            state_manager: StateManager instance for state updates
            ui_coordinator: Optional UIScheduler for UI updates
            settings_obj: Settings instance (injected, optional for backward compatibility)
        """
        self.project_manager = project_manager
        self.model_service = model_service
        self.state_manager = state_manager
        self.ui_coordinator = ui_coordinator
        self.settings = settings_obj

        # Tracking state
        self._using_project_overrides = False
        self._global_model_defaults: dict[str, Any] = {}

        log.info("project_workflow_service.initialized")

    def set_global_model_defaults(self, active_weight: str | None, use_openvino: bool) -> None:
        """
        Set global model defaults for fallback when project has no overrides.

        Args:
            active_weight: Default weight name
            use_openvino: Default OpenVINO usage
        """
        self._global_model_defaults = {
            "active_weight": active_weight,
            "use_openvino": use_openvino,
        }
        log.info(
            "project_workflow_service.defaults_set",
            active_weight=active_weight,
            use_openvino=use_openvino,
        )

    # === Parameter Validation and Preparation ===

    def validate_project_parameters(self, **kwargs: Any) -> tuple[bool, str | None]:
        """
        Validate project creation parameters.

        Phase 5: Extracted from create_project_workflow.

        Args:
            **kwargs: Project parameters to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        animal_method = kwargs.get("animal_method")
        animals_per_aquarium = kwargs.get("animals_per_aquarium", 1)

        # Validate detection mode compatibility
        if animal_method == "det" and animals_per_aquarium != 1:
            error_msg = (
                "O modo de detecção (det) para animais só é compatível com 1 "
                f"animal por aquário.\n"
                f"Configuração atual: {animals_per_aquarium} "
                "animais por aquário.\n\n"
                "Para usar múltiplos animais por aquário, altere o método de "
                "detecção de animais para 'seg' (segmentação) nas configurações."
            )
            log.warning(
                "project_workflow_service.validation_failed",
                reason="det_mode_incompatible_with_multi_animal",
                animal_method=animal_method,
                animals_per_aquarium=animals_per_aquarium,
            )
            return False, error_msg

        return True, None

    def prepare_controller_parameters(self, **kwargs: Any) -> dict[str, Any]:
        """
        Prepare and filter parameters for project creation.

        Phase 5: Extracted from create_project_workflow.

        This uses a whitelist approach to ensure only valid parameters
        are passed to ProjectManager.create_new_project().

        Args:
            **kwargs: Raw parameters from wizard or dialog

        Returns:
            dict: Filtered parameters safe for create_new_project()
        """
        # WHITELIST APPROACH: Only pass parameters that create_new_project() accepts
        allowed_params = {
            "project_path",
            "project_type",
            "use_openvino",
            "openvino_device",
            "active_weight",
            "video_files",
            "num_aquariums",
            "animals_per_aquarium",
            "aquarium_width_cm",
            "aquarium_height_cm",
            "use_timed_recording",
            "recording_duration_s",
            "use_countdown",
            "countdown_duration_s",
            "analysis_interval_frames",
            "display_interval_frames",
            "camera_index",
            "camera_friendly_name",
            "use_arduino",
            "arduino_port",
            "external_trigger_mode",
            "preserve_real_aquarium_shape",
            "use_single_subject_tracker",
            # Live project params
            "experiment_days",
            "subjects_per_group",
            "num_groups",
            "group_names",
            # Wizard metadata
            "_wizard_metadata",
        }

        # Filter kwargs to only allowed parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

        log.info(
            "project_workflow_service.parameters_prepared",
            total_params=len(kwargs),
            filtered_params=len(filtered_kwargs),
        )

        return filtered_kwargs

    # === Model Settings Resolution and Application ===

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """
        Resolve model settings from project data and overrides.

        Phase 5: Moved from controller.resolve_project_model_settings().

        Resolution order:
        1. Explicit overrides parameter
        2. Project model_overrides
        3. Project active_weight/use_openvino
        4. Global model defaults
        5. Default weight from weight manager

        Args:
            overrides: Optional overrides to apply

        Returns:
            tuple: (resolved_weight_name, resolved_use_openvino)
        """
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}
        legacy_project_data_fallback = not isinstance(project_data.get("model_overrides"), dict)

        if overrides is not None:
            merged_overrides = base_overrides.copy()
            merged_overrides.update(overrides)
        else:
            merged_overrides = base_overrides

        merged_slot_weights = self._resolve_slot_weights_from_overrides(merged_overrides)
        legacy_animal_slot = self._get_legacy_animal_slot_key(merged_slot_weights)

        weight_override = (
            merged_slot_weights.get(legacy_animal_slot) if legacy_animal_slot else None
        )
        if not weight_override:
            weight_override = self._normalize_weight_name(merged_overrides.get("active_weight"))

        # Parse OpenVINO override
        openvino_override = self._normalize_openvino_override(merged_overrides.get("use_openvino"))

        # Resolve weight with fallback chain
        resolved_weight = weight_override
        if not resolved_weight and legacy_project_data_fallback:
            resolved_weight = project_data.get("active_weight") or None
        if not resolved_weight:
            resolved_weight = self._global_model_defaults.get("active_weight")
        if not resolved_weight:
            resolved_weight = self._get_default_weight_name()

        # Validate weight exists
        available_weights = set(self.model_service.get_all_weight_names())
        if resolved_weight and resolved_weight not in available_weights:
            log.warning(
                "project_workflow_service.weight_missing",
                weight=resolved_weight,
                available=list(available_weights),
            )
            # Fallback to global default or first available
            fallback_weight = self._global_model_defaults.get("active_weight")
            if fallback_weight and fallback_weight in available_weights:
                resolved_weight = fallback_weight
            else:
                default_weight = self._get_default_weight_name()
                resolved_weight = default_weight if default_weight else None

        # Resolve OpenVINO
        if openvino_override is None:
            if legacy_project_data_fallback and project_data.get("use_openvino") is not None:
                resolved_openvino = bool(project_data.get("use_openvino"))
            else:
                resolved_openvino = bool(self._global_model_defaults.get("use_openvino", False))
        else:
            resolved_openvino = bool(openvino_override)

        # Validate OpenVINO is actually available for the resolved weight
        # If OpenVINO is requested but not ready, fall back to PyTorch
        if resolved_openvino and resolved_weight:
            if not self.model_service.is_openvino_ready(resolved_weight):
                log.warning(
                    "project_workflow_service.openvino_not_ready_fallback",
                    weight=resolved_weight,
                    message="OpenVINO requested but model not converted. Falling back to PyTorch.",
                )
                resolved_openvino = False

        log.info(
            "project_workflow_service.model_settings_resolved",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
        )

        return resolved_weight, resolved_openvino

    def _resolve_openvino_device(self, overrides: dict | None = None) -> str:
        """Resolve OpenVINO target device from overrides/project/settings."""
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}
        merged_overrides = base_overrides.copy()
        if overrides is not None:
            merged_overrides.update(overrides)

        device_override = merged_overrides.get("device")
        if isinstance(device_override, str):
            candidate = device_override.strip().upper()
            if candidate:
                return candidate

        project_device = project_data.get("openvino_device")
        if isinstance(project_device, str):
            candidate = project_device.strip().upper()
            if candidate:
                return candidate

        if self.settings and hasattr(self.settings, "openvino"):
            configured = getattr(self.settings.openvino, "device", "AUTO")
            if isinstance(configured, str) and configured.strip():
                return configured.strip().upper()

        return "AUTO"

    def apply_project_model_overrides(
        self,
        overrides: dict | None = None,
        active_weight_setter: Callable[..., Any] | None = None,
        use_openvino_setter: Callable[..., Any] | None = None,
    ) -> tuple[str | None, bool]:
        """
        Apply project model overrides and update project data.

        Phase 5: Moved from controller.apply_project_model_overrides().

        Args:
            overrides: Optional overrides to apply
            active_weight_setter: Callback to set active_weight in controller
            use_openvino_setter: Callback to set use_openvino in controller

        Returns:
            tuple: (resolved_weight_name, resolved_use_openvino)
        """
        if not getattr(self.project_manager, "project_data", None):
            self._set_runtime_slot_overrides({})
            # No project loaded, return current global defaults
            return (
                self._global_model_defaults.get("active_weight"),
                bool(self._global_model_defaults.get("use_openvino", False)),
            )

        project_data = self.project_manager.project_data
        had_model_overrides = isinstance(project_data.get("model_overrides"), dict)
        model_overrides = project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None, "device": "AUTO", "slot_weights": {}},
        )

        merged_overrides = dict(model_overrides)
        if not had_model_overrides:
            merged_overrides["active_weight"] = project_data.get("active_weight")
            merged_overrides["use_openvino"] = project_data.get("use_openvino")
        if overrides is not None:
            merged_overrides.update(overrides)
        merged_slot_weights = self._resolve_slot_weights_from_overrides(merged_overrides)
        explicit_slot_weights = self._normalize_slot_weights(merged_overrides.get("slot_weights"))
        explicit_active_weight = self._normalize_weight_name(merged_overrides.get("active_weight"))
        explicit_openvino = self._normalize_openvino_override(merged_overrides.get("use_openvino"))

        self._set_runtime_slot_overrides(merged_slot_weights)

        resolved_weight, resolved_openvino = self.resolve_project_model_settings(merged_overrides)
        resolved_device = self._resolve_openvino_device(overrides)

        self._using_project_overrides = True

        # Apply settings via setters if provided
        if active_weight_setter and resolved_weight:
            active_weight_setter(resolved_weight)

        if use_openvino_setter is not None:
            use_openvino_setter(resolved_openvino)

        # Update project data
        updated = False
        if project_data.get("active_weight") != resolved_weight:
            project_data["active_weight"] = resolved_weight
            updated = True

        if project_data.get("use_openvino") != resolved_openvino:
            project_data["use_openvino"] = resolved_openvino
            updated = True

        if model_overrides.get("active_weight") != explicit_active_weight:
            model_overrides["active_weight"] = explicit_active_weight
            updated = True
        if model_overrides.get("use_openvino") != explicit_openvino:
            model_overrides["use_openvino"] = explicit_openvino
            updated = True
        if model_overrides.get("slot_weights") != explicit_slot_weights:
            model_overrides["slot_weights"] = explicit_slot_weights
            updated = True
        if model_overrides.get("device") != resolved_device:
            model_overrides["device"] = resolved_device
            updated = True

        if project_data.get("openvino_device") != resolved_device:
            project_data["openvino_device"] = resolved_device
            updated = True

        if self.settings and hasattr(self.settings, "openvino"):
            self.settings.openvino.device = resolved_device  # type: ignore[assignment]
            if hasattr(self.settings.openvino, "device_batch"):
                self.settings.openvino.device_batch = resolved_device  # type: ignore[assignment]

        # Save project if updated
        if updated and getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()
            log.info(
                "project_workflow_service.model_settings_saved",
                weight=resolved_weight,
                openvino=resolved_openvino,
                device=resolved_device,
            )

        return resolved_weight, resolved_openvino

    def get_global_project_slot_weights(self) -> dict[str, str]:
        """Return current global defaults for the slots consumed by the active project."""
        weight_manager = getattr(self.model_service, "weight_manager", None)
        if weight_manager is None or not hasattr(weight_manager, "get_default_weight_for"):
            return {}

        slot_weights: dict[str, str] = {}
        for method, target in self._get_project_slot_pairs():
            name, _details = weight_manager.get_default_weight_for(method, target)
            if name:
                slot_weights[self._slot_key(method, target)] = name
        return slot_weights

    def save_project_model_slot_overrides(
        self,
        slot_weights: dict[str, str | None] | None,
        use_openvino_override: bool | None,
    ) -> tuple[str | None, bool]:
        """Persist explicit slot overrides for the active project."""
        if not getattr(self.project_manager, "project_path", None):
            return self.resolve_project_model_settings(), bool(use_openvino_override)  # type: ignore[return-value]

        overrides = self.project_manager.project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None, "device": "AUTO", "slot_weights": {}},
        )
        normalized_slot_weights = self._normalize_slot_weights(slot_weights)
        legacy_animal_slot = self._get_legacy_animal_slot_key(normalized_slot_weights)

        overrides["slot_weights"] = normalized_slot_weights
        overrides["active_weight"] = (
            normalized_slot_weights.get(legacy_animal_slot) if legacy_animal_slot else None
        )
        overrides["use_openvino"] = use_openvino_override

        return self.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=lambda _weight: None,
            use_openvino_setter=lambda _enabled: None,
        )

    # === Project Creation Orchestration ===

    def create_project(
        self,
        active_weight_setter: Callable[..., Any] | None = None,
        use_openvino_setter: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Orchestrate project creation workflow."""
        prepared_kwargs, context = self._prepare_project_input(**kwargs)
        animal_method = context["animal_method"]
        animals_per_aquarium = context["animals_per_aquarium"]
        wizard_metadata = context["wizard_metadata"]
        initial_slot_weights = context.get("initial_slot_weights") or {}
        detector_hyperparams = context.get("detector_hyperparams") or {}

        is_valid, error_msg = self._validate_project_input(**prepared_kwargs)
        if not is_valid:
            log.warning(
                "project_workflow_service.create_project.validation_failed",
                error=error_msg,
            )
            return {
                "success": False,
                "error_message": error_msg,
                "wizard_metadata": None,
                "animal_method": None,
                "project_path": None,
                "import_success": None,
            }

        if animal_method == "det" and animals_per_aquarium == 1:
            log.info(
                "project_workflow_service.create_project.det_single_animal",
                animal_method=animal_method,
                animals_per_aquarium=animals_per_aquarium,
            )

        self._apply_runtime_model_defaults(
            prepared_kwargs,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

        filtered_kwargs = self.prepare_controller_parameters(**prepared_kwargs)
        created, create_error = self._create_project_structure(filtered_kwargs)
        if not created:
            return {
                "success": False,
                "error_message": create_error,
                "wizard_metadata": None,
                "animal_method": None,
                "project_path": None,
                "import_success": None,
            }

        self._persist_project_data(prepared_kwargs)

        # Persist wizard-derived slot weights and detector hyperparams into
        # model_overrides BEFORE apply_project_model_overrides runs, so
        # WeightManager runtime resolution and detector setup pick them up.
        self._persist_initial_project_overrides(
            initial_slot_weights,
            detector_hyperparams,
        )

        self._emit_project_created_event()

        self._using_project_overrides = True
        self.apply_project_model_overrides(
            overrides=None,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

        import_success = self._import_wizard_parquets(wizard_metadata)

        return {
            "success": True,
            "error_message": None,
            "wizard_metadata": wizard_metadata if wizard_metadata else None,
            "animal_method": animal_method,
            "project_path": Path(self.project_manager.project_path)
            if self.project_manager.project_path
            else None,
            "import_success": import_success,
        }

    def _prepare_project_input(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        default_animal_method = "det"
        if self.settings and hasattr(self.settings, "model_selection"):
            default_animal_method = self.settings.model_selection.animal_method
        animal_method = kwargs.get("animal_method", default_animal_method)
        animals_per_aquarium = kwargs.get("animals_per_aquarium", 1)

        if "animal_method" not in kwargs:
            kwargs["animal_method"] = animal_method

        if "use_single_subject_tracker" not in kwargs:
            kwargs["use_single_subject_tracker"] = animals_per_aquarium == 1
        else:
            kwargs["use_single_subject_tracker"] = bool(kwargs["use_single_subject_tracker"])

        from zebtrack.ui.wizard.enums import ProjectType

        project_type_value = kwargs.get("project_type", ProjectType.EXPERIMENTAL.value)
        is_live = project_type_value == ProjectType.LIVE.value
        is_exploratory = project_type_value == ProjectType.EXPLORATORY.value

        if "project_type" in kwargs:
            kwargs["project_type"] = "live" if is_live else "pre-recorded"

        scanned_videos = kwargs.get("scanned_videos", [])
        detected_design = kwargs.get("detected_design")
        custom_patterns = kwargs.get("custom_regex_patterns")
        enriched_scanned_videos = copy.deepcopy(scanned_videos)

        if scanned_videos and not is_live:
            if detected_design:
                group_display_names = detected_design.get("group_display_names")
                enriched_scanned_videos = self._enrich_videos_with_design_metadata(
                    scanned_videos,
                    detected_design,
                    custom_patterns,
                    group_display_names,
                )
            kwargs["scanned_videos"] = enriched_scanned_videos

            parquet_import_scope = kwargs.get("parquet_import_scope")
            if not parquet_import_scope:
                log.info(
                    "project_workflow_service.clearing_parquet_flags",
                    reason="parquet_import_scope is None - user chose not to import",
                )
                for video_info in enriched_scanned_videos:
                    video_info["has_arena"] = False
                    video_info["has_rois"] = False
                    video_info["has_trajectory"] = False
                    video_info["has_complete_data"] = False
                    video_info["has_data"] = False

            video_files = []
            for video_info in enriched_scanned_videos:
                converted = copy.deepcopy(video_info)
                converted["has_data"] = bool(
                    video_info.get("has_data", video_info.get("has_complete_data", False))
                )
                video_files.append(converted)
            kwargs["video_files"] = video_files

        if not is_exploratory and detected_design:
            groups = detected_design.get("groups", [])
            days = detected_design.get("days", [])
            subjects_dict = detected_design.get("subjects_per_group", {})

            if groups and "num_groups" not in kwargs:
                kwargs["num_groups"] = len(groups)
                kwargs["group_names"] = groups

            if days and "experiment_days" not in kwargs:
                kwargs["experiment_days"] = len(days)

            if (
                subjects_dict
                and isinstance(subjects_dict, dict)
                and "subjects_per_group" not in kwargs
            ):
                subject_counts = [len(subjects) for subjects in subjects_dict.values() if subjects]
                if subject_counts:
                    kwargs["subjects_per_group"] = max(subject_counts)

        weight_assignments = kwargs.get("weight_assignments")
        if (
            weight_assignments
            and isinstance(weight_assignments, dict)
            and "active_weight" not in kwargs
        ):
            animal_weight = weight_assignments.get("animal")
            if animal_weight:
                kwargs["active_weight"] = animal_weight

        # Migrate the wizard's legacy 2-key weight_assignments
        # ({"aquarium": ..., "animal": ...}) into the 4-slot
        # {method:target -> name} dict consumed by WeightManager. The
        # aquarium weight had been silently dropped before; the animal
        # weight survived only via the active_weight fallback in
        # _resolve_slot_weights_from_overrides.
        initial_slot_weights = self._build_initial_slot_weights(
            weight_assignments=weight_assignments,
            animal_method=animal_method,
            aquarium_method=kwargs.get("aquarium_method"),
        )

        # Capture detector hyperparameter overrides emitted by the wizard
        # (confidence_threshold, nms_threshold). Stored alongside the slot
        # weights so create_project can persist them into model_overrides
        # before apply_project_model_overrides runs.
        detector_hyperparams = self._build_detector_hyperparam_overrides(
            kwargs.get("detector_parameters")
        )

        model_selection = kwargs.get("model_selection")
        if (
            "openvino_device" not in kwargs
            and isinstance(model_selection, dict)
            and model_selection.get("openvino_device")
        ):
            kwargs["openvino_device"] = str(model_selection.get("openvino_device"))

        wizard_metadata = {
            "wizard_schema_version": kwargs.get("wizard_schema_version"),
            "created_at": kwargs.get("created_at"),
            "has_folder_structure": kwargs.get("has_folder_structure"),
            "folder_meaning": kwargs.get("folder_meaning"),
            "has_parquets": kwargs.get("has_parquets"),
            "parquet_import_scope": kwargs.get("parquet_import_scope"),
            "detected_design": detected_design,
            "scanned_videos": enriched_scanned_videos if not is_live else scanned_videos,
            "import_config": kwargs.get("import_config"),
            "roi_merge_strategy": kwargs.get("roi_merge_strategy"),
            "parquet_summary": kwargs.get("parquet_summary"),
            "video_count": kwargs.get("video_count"),
            "folder_preview": kwargs.get("folder_preview"),
            "weight_assignments": weight_assignments,
            "detector_parameters": kwargs.get("detector_parameters"),
            "model_selection": kwargs.get("model_selection"),
            "use_openvino": kwargs.get("use_openvino"),
            "openvino_device": kwargs.get("openvino_device"),
            "custom_regex_patterns": custom_patterns,
        }
        kwargs["_wizard_metadata"] = wizard_metadata

        return kwargs, {
            "animal_method": animal_method,
            "animals_per_aquarium": animals_per_aquarium,
            "wizard_metadata": wizard_metadata,
            "initial_slot_weights": initial_slot_weights,
            "detector_hyperparams": detector_hyperparams,
        }

    def _validate_project_input(self, **kwargs: Any) -> tuple[bool, str | None]:
        return self.validate_project_parameters(**kwargs)

    def _apply_runtime_model_defaults(
        self,
        kwargs: dict[str, Any],
        *,
        active_weight_setter: Callable[..., Any] | None,
        use_openvino_setter: Callable[..., Any] | None,
    ) -> None:
        if "use_openvino" in kwargs and use_openvino_setter:
            use_openvino_setter(kwargs["use_openvino"])

        if active_weight_setter is not None and "active_weight" not in kwargs:
            kwargs["active_weight"] = self._global_model_defaults.get("active_weight")
        if use_openvino_setter is not None and "use_openvino" not in kwargs:
            kwargs["use_openvino"] = self._global_model_defaults.get("use_openvino", False)
        if "openvino_device" not in kwargs:
            if self.settings and hasattr(self.settings, "openvino"):
                kwargs["openvino_device"] = str(self.settings.openvino.device or "AUTO").upper()
            else:
                kwargs["openvino_device"] = "AUTO"

    @classmethod
    def _slot_key(cls, method: str, target: str) -> str:
        return f"{method}{cls._SLOT_SEPARATOR}{target}"

    def _get_project_slot_pairs(self) -> list[tuple[str, str]]:
        model_selection = getattr(self.settings, "model_selection", None)
        aquarium_method = getattr(model_selection, "aquarium_method", None)
        animal_method = getattr(model_selection, "animal_method", None)

        pairs: list[tuple[str, str]] = []
        if aquarium_method in VALID_METHODS:
            pairs.append((aquarium_method, TARGET_AQUARIUM))
        if animal_method in VALID_METHODS:
            pairs.append((animal_method, TARGET_ZEBRAFISH))
        return pairs

    # Detector hyperparameters that may be persisted as project overrides.
    # Kept narrow on purpose (Phase 2): conf and NMS thresholds have plugin
    # setters today and zero pre-compilation impact. imgsz / half_precision
    # / OpenVINO device/precision require new plugin setters or recompile
    # logic and are deferred.
    _DETECTOR_HYPERPARAM_KEYS: tuple[str, ...] = (
        "confidence_threshold",
        "nms_threshold",
    )

    def _build_initial_slot_weights(
        self,
        *,
        weight_assignments: Any,
        animal_method: str | None,
        aquarium_method: str | None,
    ) -> dict[str, str]:
        """Translate the wizard's legacy weight_assignments into the 4-slot dict.

        The wizard's ModelSelectionStep emits ``{"aquarium": <name>, "animal":
        <name>}`` together with ``aquarium_method`` and ``animal_method``.
        The 4-slot WeightManager expects ``"<method>:<target>" -> name`` pairs
        (e.g. ``"det:zebrafish"``). Returns the migrated dict (possibly empty).
        """
        slot_weights: dict[str, str] = {}
        if not isinstance(weight_assignments, dict):
            return slot_weights

        animal_name = self._normalize_weight_name(weight_assignments.get("animal"))
        aquarium_name = self._normalize_weight_name(weight_assignments.get("aquarium"))

        if animal_name and isinstance(animal_method, str) and animal_method in VALID_METHODS:
            slot_weights[self._slot_key(animal_method, TARGET_ZEBRAFISH)] = animal_name

        if aquarium_name and isinstance(aquarium_method, str) and aquarium_method in VALID_METHODS:
            slot_weights[self._slot_key(aquarium_method, TARGET_AQUARIUM)] = aquarium_name

        return slot_weights

    def _build_detector_hyperparam_overrides(
        self,
        detector_parameters: Any,
    ) -> dict[str, float]:
        """Extract per-project detector hyperparameter overrides from wizard data.

        The wizard's detector_parameters dict carries inference-time knobs
        (confidence/NMS thresholds, etc.). We persist a narrow subset that
        the active plugins already accept via setters at session start.
        """
        overrides: dict[str, float] = {}
        if not isinstance(detector_parameters, dict):
            return overrides

        for key in self._DETECTOR_HYPERPARAM_KEYS:
            raw = detector_parameters.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            # Reject sentinel out-of-range values so a stale wizard payload
            # cannot poison the override record. 0–1 is the meaningful band
            # for both confidence and NMS thresholds.
            if 0.0 <= value <= 1.0:
                overrides[key] = value
        return overrides

    def _persist_initial_project_overrides(
        self,
        slot_weights: dict[str, str] | None,
        detector_hyperparams: dict[str, float] | None,
    ) -> None:
        """Write wizard-derived slot weights and hyperparams into project_data.

        Called after the project structure is created and before
        ``apply_project_model_overrides`` runs, so the project's
        ``model_overrides`` block already contains the wizard's choices when
        runtime resolution kicks in.
        """
        if not slot_weights and not detector_hyperparams:
            return

        project_data = self.project_manager.project_data
        if not isinstance(project_data, dict):
            return

        overrides = project_data.setdefault(
            "model_overrides",
            {
                "active_weight": None,
                "use_openvino": None,
                "device": "AUTO",
                "slot_weights": {},
            },
        )

        updated = False
        if slot_weights:
            existing = overrides.setdefault("slot_weights", {})
            for slot_key, name in slot_weights.items():
                if existing.get(slot_key) != name:
                    existing[slot_key] = name
                    updated = True

        if detector_hyperparams:
            for key, value in detector_hyperparams.items():
                if overrides.get(key) != value:
                    overrides[key] = value
                    updated = True

        if updated and self.project_manager.project_path:
            self.project_manager.save_project()

    def _normalize_slot_weights(self, raw_slot_weights: Any) -> dict[str, str]:
        normalized: dict[str, str] = {}
        if not isinstance(raw_slot_weights, dict):
            return normalized

        for raw_key, raw_name in raw_slot_weights.items():
            if isinstance(raw_key, tuple) and len(raw_key) == 2:
                method, target = raw_key
            elif isinstance(raw_key, str) and self._SLOT_SEPARATOR in raw_key:
                method, target = raw_key.split(self._SLOT_SEPARATOR, 1)
            else:
                continue

            if not isinstance(method, str) or not isinstance(target, str):
                continue

            method = method.strip().lower()
            target = target.strip().lower()
            name = self._normalize_weight_name(raw_name)
            if (
                not name
                or method not in VALID_METHODS
                or target not in {TARGET_AQUARIUM, TARGET_ZEBRAFISH}
            ):
                continue
            normalized[self._slot_key(method, target)] = name

        return normalized

    @staticmethod
    def _normalize_weight_name(raw_name: Any) -> str | None:
        if not isinstance(raw_name, str):
            return None
        name = raw_name.strip()
        return name or None

    @staticmethod
    def _normalize_openvino_override(raw_value: Any) -> bool | None:
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {"", "inherit", "auto"}:
                return None
            return lowered in {"true", "1", "yes", "on"}
        if raw_value is None:
            return None
        return bool(raw_value)

    def _get_legacy_animal_slot_key(self, slot_weights: dict[str, str] | None = None) -> str | None:
        for method, target in self._get_project_slot_pairs():
            if target == TARGET_ZEBRAFISH:
                return self._slot_key(method, target)

        if slot_weights:
            for slot_key in slot_weights:
                if slot_key.endswith(f"{self._SLOT_SEPARATOR}{TARGET_ZEBRAFISH}"):
                    return slot_key
        return None

    def _resolve_slot_weights_from_overrides(
        self, merged_overrides: dict[str, Any]
    ) -> dict[str, str]:
        slot_weights = self._normalize_slot_weights(merged_overrides.get("slot_weights"))
        legacy_weight = self._normalize_weight_name(merged_overrides.get("active_weight"))
        legacy_slot = self._get_legacy_animal_slot_key(slot_weights)
        if legacy_weight and legacy_slot and legacy_slot not in slot_weights:
            slot_weights[legacy_slot] = legacy_weight
        return slot_weights

    def _set_runtime_slot_overrides(self, slot_weights: dict[str, str]) -> None:
        weight_manager = getattr(self.model_service, "weight_manager", None)
        if weight_manager is None or not hasattr(weight_manager, "set_runtime_slot_overrides"):
            return

        runtime_overrides: dict[tuple[str, str], str] = {}
        for slot_key, name in slot_weights.items():
            method, target = slot_key.split(self._SLOT_SEPARATOR, 1)
            runtime_overrides[(method, target)] = name
        weight_manager.set_runtime_slot_overrides(runtime_overrides)

    def _get_default_weight_name(self) -> str | None:
        default_weight = self.model_service.get_default_weight()
        if isinstance(default_weight, tuple) and default_weight:
            candidate = default_weight[0]
            return candidate if isinstance(candidate, str) else None
        return None

    def _create_project_structure(self, filtered_kwargs: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            self.project_manager.create_new_project(**filtered_kwargs)
        except ProjectInvalidError as e:
            log.error("project_workflow_service.create_project.failed", error=str(e))
            return False, str(e)

        log.info(
            "project_workflow_service.create_project.success",
            path=self.project_manager.project_path,
        )
        return True, None

    def _persist_project_data(self, kwargs: dict[str, Any]) -> None:
        project_updated = False
        behavioral_analysis = kwargs.get("behavioral_analysis")
        if isinstance(behavioral_analysis, dict) and behavioral_analysis:
            if self.project_manager.project_data.get("behavioral_config") != behavioral_analysis:
                self.project_manager.project_data["behavioral_config"] = behavioral_analysis
                project_updated = True

        live_defaults = {
            "selected_live_mode": kwargs.get("selected_live_mode"),
        }
        live_defaults = {k: v for k, v in live_defaults.items() if v is not None}
        if live_defaults:
            existing_live_defaults = self.project_manager.project_data.get("live_session_defaults")
            if existing_live_defaults != live_defaults:
                self.project_manager.project_data["live_session_defaults"] = live_defaults
                project_updated = True

        if project_updated and self.project_manager.project_path:
            self.project_manager.save_project()

        self.state_manager.update_project_state(
            source="project_workflow_service.create_project",
            project_path=Path(self.project_manager.project_path)
            if self.project_manager.project_path
            else None,
            project_data=self.project_manager.project_data.copy()
            if self.project_manager.project_data
            else {},
            active_zone_video=self.project_manager.get_active_zone_video(),
        )

    def _emit_project_created_event(self) -> None:
        log.info(
            "project_workflow_service.create_project.emitted",
            project_path=self.project_manager.project_path,
        )

    def _import_wizard_parquets(self, wizard_metadata: dict | None) -> bool | None:
        import_success = None
        if wizard_metadata:
            import_config = wizard_metadata.get("import_config", [])
            roi_merge_strategy = wizard_metadata.get("roi_merge_strategy", "replace")
            scanned_videos = wizard_metadata.get("scanned_videos", [])

            if import_config:
                log.info(
                    "project_workflow_service.create_project.importing_parquets",
                    video_count=len(import_config),
                    strategy=roi_merge_strategy,
                )
                import_success = self.project_manager.import_parquets_from_wizard(
                    import_config=import_config,
                    roi_merge_strategy=roi_merge_strategy,
                    scanned_videos=scanned_videos,
                )
                if import_success:
                    log.info("project_workflow_service.create_project.parquets_imported")
                else:
                    log.warning("project_workflow_service.create_project.parquet_import_failed")

        return import_success

    # === Project Opening Orchestration ===

    def open_project(
        self,
        project_path: Path | str,
        active_weight_setter: Callable[..., Any] | None = None,
        use_openvino_setter: Callable[..., Any] | None = None,
        restore_detector_callback: Callable[..., Any] | None = None,
        setup_zones_callback: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        """
        Orchestrate project opening workflow.

        Phase 5: Extracted from controller.open_project_workflow().

        This method handles:
        1. Loading project via ProjectManager
        2. Applying model overrides
        3. Restoring detector settings (via callback)
        4. Setting up zones (via callback)
        5. Collecting project information for display

        The controller is responsible for:
        - Setting up the detector
        - Loading the project view
        - Updating UI controls (checkboxes, dropdowns)
        - Displaying the success dialog

        Args:
            project_path: Path to project directory
            active_weight_setter: Optional callback to set active_weight
            use_openvino_setter: Optional callback to set use_openvino
            restore_detector_callback: Optional callback to restore detector settings
            setup_zones_callback: Optional callback to setup zones

        Returns:
            dict with:
                - success: bool
                - error_message: str | None
                - project_info: dict | None (name, videos_count, zone_status, etc.)
                - zone_data: ZoneData | None
                - resolved_weight: str | None
                - resolved_openvino: bool
        """
        from pathlib import Path

        log.info("project_workflow_service.open_project.start", path=project_path)

        # Load the project
        try:
            self.project_manager.load_project(project_path)
        except ProjectInvalidError as e:
            log.error("project_workflow_service.open_project.failed", error=str(e))
            return {
                "success": False,
                "error_message": str(e),
                "project_info": None,
                "zone_data": None,
                "resolved_weight": None,
                "resolved_openvino": False,
            }

        # Apply project-specific overrides
        self._using_project_overrides = True
        resolved_weight, resolved_openvino = self.apply_project_model_overrides(
            overrides=None,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

        log.info(
            "project_workflow_service.open_project.model_settings_applied",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
        )

        # Restore detector settings if callback provided
        if restore_detector_callback:
            saved_detector_config = self.project_manager.get_detector_state()
            if saved_detector_config:
                restore_detector_callback(saved_detector_config)

        # Load and setup zones
        zone_data = self.project_manager.get_zone_data()
        if zone_data and (zone_data.polygon or zone_data.roi_polygons):
            log.info(
                "project_workflow_service.open_project.zones_found",
                has_polygon=bool(zone_data.polygon),
                roi_count=len(zone_data.roi_polygons),
            )

            # Setup zones via callback
            if setup_zones_callback:
                setup_zones_callback()

            log.info("project_workflow_service.open_project.zones_applied")

        # Collect project information for display
        project_name = self.project_manager.get_project_name()
        all_videos = self.project_manager.get_all_videos()
        videos_count = len(all_videos)
        zone_status = "✓" if zone_data and zone_data.polygon else "✗"
        roi_count = len(zone_data.roi_polygons) if zone_data else 0

        project_info = {
            "name": project_name,
            "videos_count": videos_count,
            "zone_status": zone_status,
            "roi_count": roi_count,
            "active_weight": resolved_weight or "Padrão",
            "use_openvino": resolved_openvino,
        }

        # Update StateManager
        self.state_manager.update_project_state(
            source="project_workflow_service.open_project",
            project_path=Path(project_path),
            project_data=self.project_manager.project_data.copy()
            if self.project_manager.project_data
            else {},
            active_zone_video=self.project_manager.get_active_zone_video(),
        )

        log.info(
            "project_workflow_service.open_project.success",
            project_name=project_name,
            videos=videos_count,
        )

        return {
            "success": True,
            "error_message": None,
            "project_info": project_info,
            "zone_data": zone_data,
            "resolved_weight": resolved_weight,
            "resolved_openvino": resolved_openvino,
        }

    # === Post-Creation Guide ===

    def generate_post_creation_guide(
        self, wizard_metadata: dict, check_suppression: bool = True
    ) -> dict[str, str] | None:
        """
        Generate post-creation guide content.

        Phase 5: Extracted from controller._show_post_creation_guide().

        This method analyzes the project and wizard metadata to generate
        a contextual onboarding message with recommended next steps.

        Args:
            wizard_metadata: Metadata from wizard with import_config, scanned_videos
            check_suppression: Whether to check suppression flags

        Returns:
            dict with 'title' and 'message' keys, or None if suppressed
        """
        import os

        if not wizard_metadata:
            return None

        # Check suppression flags
        if check_suppression:
            suppressed = os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get(
                "ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE"
            )

            if suppressed:
                reason = (
                    "env_flag"
                    if os.environ.get("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE")
                    else "pytest"
                )
                log.info("project_workflow_service.post_creation_guide.skipped", reason=reason)
                return None

        # Extract wizard data
        import_config = wizard_metadata.get("import_config") or []
        scanned_videos = wizard_metadata.get("scanned_videos") or []

        # Build video source list
        project_videos = self.project_manager.get_all_videos()
        videos_source: list[dict] = []

        if project_videos:
            videos_source = project_videos
        elif scanned_videos:
            for video in scanned_videos:
                video_copy = dict(video)
                video_copy.setdefault("path", video_copy.get("video"))
                videos_source.append(video_copy)

        if not videos_source:
            return None

        # Build import lookup
        import_lookup = {
            config.get("video"): config for config in import_config if config.get("video")
        }

        key_map = {
            "has_arena": "import_arena",
            "has_rois": "import_rois",
            "has_trajectory": "import_trajectory",
        }

        def _feature_available(video: dict, feature_key: str) -> bool:
            """Check if a feature is available for a video."""
            if bool(video.get(feature_key)):
                return True

            metadata = video.get("metadata") or {}
            if bool(metadata.get(feature_key)):
                return True

            video_path = video.get("path") or video.get("video")
            if not video_path:
                return False

            import_cfg = import_lookup.get(video_path)
            if not import_cfg:
                return False

            import_key = key_map.get(feature_key)
            if not import_key:
                return False

            return bool(import_cfg.get(import_key))

        # Calculate statistics
        total_videos = len(videos_source)
        videos_with_arena = sum(
            1 for video in videos_source if _feature_available(video, "has_arena")
        )
        videos_with_rois = sum(
            1 for video in videos_source if _feature_available(video, "has_rois")
        )
        videos_with_trajectory = sum(
            1 for video in videos_source if _feature_available(video, "has_trajectory")
        )
        videos_pending = sum(
            1 for video in videos_source if not _feature_available(video, "has_trajectory")
        )

        # Build message
        lines: list[str] = []
        lines.append("🎉 Projeto criado com sucesso!")
        lines.append("")
        lines.append("📊 Status dos vídeos:")
        lines.append(f"  • Total de vídeos: {total_videos}")
        lines.append(f"  • Com arena definida: {videos_with_arena}")
        lines.append(f"  • Com ROIs definidas: {videos_with_rois}")
        lines.append(f"  • Com trajetória pronta: {videos_with_trajectory}")
        lines.append(f"  • Pendentes de processamento: {videos_pending}")
        lines.append("")
        lines.append("🚀 Próximos passos recomendados:")
        lines.append("")

        step_num = 1

        if videos_with_arena > 0 or videos_with_rois > 0:
            lines.append(f"{step_num}. Visualizar e ajustar zonas importadas")
            lines.append("   - Abra a aba 'Configuração de Zonas'")
            lines.append("   - Use o painel 'Selecionar Vídeo para Desenho'")
            lines.append("   - Clique duas vezes ou use 'Carregar Frame' para revisar")
            lines.append("   - Ajuste arena e ROIs conforme necessário")
            lines.append("")
            step_num += 1

        if videos_pending > 0:
            lines.append(f"{step_num}. Processar vídeos pendentes")
            lines.append("   - Vá até a aba 'Controle Principal'")
            lines.append("   - Confirme os intervalos de processamento")
            lines.append("   - Clique em 'Adicionar e Processar Novos Vídeos'")
            lines.append("")
            step_num += 1

        if videos_with_trajectory > 0:
            lines.append(f"{step_num}. Gerar relatórios")
            lines.append("   - Acesse a aba 'Relatórios'")
            lines.append("   - Navegue pela hierarquia de grupos, dias e sujeitos")
            lines.append("   - Gere relatórios individuais ou unificados conforme necessário")
            lines.append("")

        lines.append("💡 Dicas:")
        lines.append("  • Use a busca para localizar vídeos rapidamente")
        lines.append("  • Os símbolos de status indicam arenas, ROIs e trajetórias disponíveis")
        lines.append("  • Ajuste zonas antes de processar se necessário")

        message = "\n".join(lines)

        log.info(
            "project_workflow_service.post_creation_guide.generated",
            total_videos=total_videos,
            with_arena=videos_with_arena,
            with_rois=videos_with_rois,
            with_trajectory=videos_with_trajectory,
            pending=videos_pending,
        )

        return {"title": "Bem-vindo ao Projeto!", "message": message}

    # === Wizard Data Enrichment (Moved from wizard_adapter.py) ===

    def _normalise_subject_id(self, raw_subject: str | None) -> str | None:
        """Normalize subject identifiers to the ``SXX`` format when possible.

        Accepts None and returns None when input is absent to match callers
        that may pass missing values.
        """
        if raw_subject is None:
            return None

        value = raw_subject.strip()
        if not value:
            return None

        # Remove common prefixes for digits-only normalization
        # Examples: "Subject01", "S01", "s1" → "S01"
        match = re.match(r"(?i)(?:subject|subj|s)?\s*([0-9]{1,3})", value)
        if match:
            return f"S{int(match.group(1)):02d}"

        return raw_subject

    def _normalise_day_label(self, day_value) -> str | None:
        if day_value in (None, ""):
            return None
        if isinstance(day_value, int | float) and not isinstance(day_value, bool):
            try:
                return f"{int(day_value):02d}"
            except (TypeError, ValueError):
                return str(day_value)

        value_str = str(day_value).strip()
        if not value_str:
            return None

        lower_value = value_str.lower()
        if lower_value == "sem dia":
            return "Sem Dia"

        match = re.search(r"(\d+)", value_str)
        if match:
            try:
                return f"{int(match.group(1)):02d}"
            except ValueError:
                return value_str

        return value_str

    def _build_design_lookups(
        self,
        groups: list,
        days: list,
        subjects_per_group: dict,
    ) -> tuple[dict, dict, dict]:
        """Build lookup dictionaries for groups, days, and subjects."""
        import re

        group_lookup = {str(g).lower(): g for g in groups if isinstance(g, str)}
        day_lookup = {str(d).lower(): d for d in days if isinstance(d, str)}
        for canonical_day in list(day_lookup.values()):
            if isinstance(canonical_day, str):
                digit_match = re.search(r"(\d+)", canonical_day)
                if digit_match:
                    day_lookup[digit_match.group(1)] = canonical_day

        subject_lookup: dict = {}
        for group_id, subjects in subjects_per_group.items():
            if not isinstance(subjects, list | tuple | set):
                continue
            subject_lookup[group_id] = {
                str(subject).lower(): subject for subject in subjects if subject is not None
            }

        return group_lookup, day_lookup, subject_lookup

    def _build_pattern(
        self,
        explicit: str | None,
        values: list[str],
    ) -> str | None:
        """Build regex pattern from explicit pattern or list of values."""
        import re

        if explicit:
            return explicit

        valid_values = [v for v in values if isinstance(v, str) and v]
        if not valid_values:
            return None

        escaped = [re.escape(v) for v in valid_values]
        return f"({'|'.join(escaped)})"

    def _extract_group(
        self,
        metadata: dict,
        enriched: dict,
        path_str: Path | str,
        group_pattern: str | None,
        group_lookup: dict,
        group_display_names: dict | None = None,
    ) -> str | None:
        """Extract group metadata from path string."""
        import re

        path_text = str(path_str)

        group_id = metadata.get("group") or enriched.get("group")
        if not group_id and group_pattern:
            match = re.search(group_pattern, path_text, re.IGNORECASE)
            if match:
                matched_group = match.group(1) if match.groups() else match.group(0)
                lookup_key = matched_group.lower()
                group_id = group_lookup.get(lookup_key, matched_group)

        if isinstance(group_id, str):
            metadata["group"] = group_id
            enriched["group"] = group_id
            # Prefer an explicit display-name mapping when provided by the detected design
            display_name = None
            if group_display_names:
                # Try exact key first, then lowercase key
                if group_id in group_display_names:
                    display_name = group_display_names.get(group_id)
                elif group_id.lower() in group_display_names:
                    display_name = group_display_names.get(group_id.lower())

            if display_name is None:
                display_name = group_lookup.get(group_id.lower(), group_id)

            metadata.setdefault("group_display_name", display_name)
            enriched["group_display_name"] = metadata.get("group_display_name")

        return group_id

    def _extract_day(
        self,
        metadata: dict,
        enriched: dict,
        path_str: Path | str,
        day_pattern: str | None,
        day_lookup: dict,
    ) -> str | None:
        """Extract day metadata from path string."""
        import re

        path_text = str(path_str)

        day_value = metadata.get("day") or enriched.get("day")
        if not day_value and day_pattern:
            match = re.search(day_pattern, path_text, re.IGNORECASE)
            if match:
                matched_day = match.group(1) if match.groups() else match.group(0)
                if isinstance(matched_day, str) and matched_day.isdigit():
                    matched_day = f"Day{int(matched_day):02d}"
                lookup_key = matched_day.lower()
                day_value = day_lookup.get(lookup_key, matched_day)

        if day_value is not None:
            metadata["day"] = day_value
            enriched["day"] = day_value
            day_label = self._normalise_day_label(day_value)
            if day_label:
                metadata.setdefault("day_label", day_label)
                enriched["day_label"] = day_label

        return day_value

    def _extract_subject(
        self,
        metadata: dict,
        enriched: dict,
        path_str: Path | str,
        subject_pattern: str | None,
        subject_lookup: dict,
        group_id: str | None,
    ) -> str | None:
        """Extract subject metadata from path string."""
        import re

        path_text = str(path_str)

        subject_value = metadata.get("subject") or enriched.get("subject")
        if not subject_value and subject_pattern:
            match = re.search(subject_pattern, path_text, re.IGNORECASE)
            if match:
                matched_subject = match.group(1) if match.groups() else match.group(0)
                normalised = self._normalise_subject_id(matched_subject)
                subject_value = normalised

        if subject_value is None and group_id:
            candidates = subject_lookup.get(group_id, {})
            for candidate_lower, candidate_value in candidates.items():
                if candidate_lower in path_text.lower():
                    subject_value = candidate_value
                    break

        if subject_value is not None:
            metadata["subject"] = subject_value
            enriched["subject"] = subject_value

        return subject_value

    def _enrich_videos_with_design_metadata(
        self,
        scanned_videos: list[dict],
        detected_design: dict | None,
        custom_patterns: dict | None = None,
        group_display_names: dict[str, str] | None = None,
    ) -> list[dict]:
        """Enrich scanned videos with experimental metadata derived from the design.

        Now supports multi-subject files via `subject_mappings` from detection.

        Args:
            scanned_videos: Video descriptors produced by ``scan_input_paths``.
            detected_design: Detected experimental design information.
            custom_patterns: Optional regex patterns configured by the user.
            group_display_names: Optional mapping from group IDs to friendly names.

        Returns:
            A **new** list of video descriptors with metadata persisted both at the
            root level (``group``, ``day`` ...) and inside a dedicated ``metadata``
            dictionary suitable for persistence in ``project.json``.
        """
        import copy

        if not scanned_videos:
            return []

        if not detected_design:
            return [copy.deepcopy(video) for video in scanned_videos]

        group_display_names = group_display_names or {}
        custom_patterns = custom_patterns or {}

        groups = detected_design.get("groups") or []
        days = detected_design.get("days") or []
        subjects_per_group = detected_design.get("subjects_per_group") or {}

        # NEW: Get subject_mappings from detection step
        raw_subject_mappings = detected_design.get("subject_mappings") or {}

        # Normalize paths in subject_mappings to handle Windows path differences
        # Keys may be in different format than video paths (forward vs backward slashes)
        subject_mappings: dict[str, list[dict]] = {}
        for key, value in raw_subject_mappings.items():
            # Normalize to use forward slashes and lowercase for comparison
            normalized_key = str(Path(key).as_posix())
            subject_mappings[normalized_key] = value
            # Also keep original key for exact match
            subject_mappings[key] = value

        group_lookup, day_lookup, subject_lookup = self._build_design_lookups(
            groups, days, subjects_per_group
        )

        group_pattern = self._build_pattern(custom_patterns.get("group_pattern"), groups)
        day_pattern = self._build_pattern(custom_patterns.get("day_pattern"), days)

        all_subject_values = [
            subject
            for values in subject_lookup.values()
            for subject in values.values()
            if subject is not None
        ]
        subject_pattern = self._build_pattern(
            custom_patterns.get("subject_pattern"), all_subject_values
        )

        enriched_videos: list[dict] = []
        multi_subject_count = 0

        # DEBUG: Log subject_mappings state
        log.info(
            "project_workflow_service.enrich_debug",
            subject_mappings_keys=list(subject_mappings.keys())[:5],
            subject_mappings_count=len(subject_mappings),
            scanned_videos_count=len(scanned_videos),
        )

        for original_video in scanned_videos:
            enriched = copy.deepcopy(original_video)
            path_str = str(enriched.get("path", ""))
            metadata: dict = copy.deepcopy(enriched.get("metadata") or {})

            # NEW: Check if this file has multiple subjects from detection
            # Try both original path and normalized path format
            file_subjects = subject_mappings.get(path_str, [])
            if not file_subjects:
                # Try normalized path (forward slashes)
                normalized_path = str(Path(path_str).as_posix()) if path_str else ""
                file_subjects = subject_mappings.get(normalized_path, [])

            # Fallback: if subject_mappings lookup failed but custom_patterns exist,
            # apply combined regex directly on filename with finditer to detect
            # multiple subjects. This handles path normalization mismatches
            # (e.g., Windows backslashes vs POSIX slashes, OneDrive paths).
            if not file_subjects and custom_patterns and custom_patterns.get("group_pattern"):
                from zebtrack.ui.wizard.models import MultiAquariumData

                combined = MultiAquariumData.build_combined_regex_pattern(
                    group_pattern=custom_patterns.get("group_pattern"),
                    day_pattern=custom_patterns.get("day_pattern"),
                    subject_pattern=custom_patterns.get("subject_pattern"),
                )
                if combined:
                    filename = Path(path_str).name
                    for m in re.finditer(combined, filename):
                        groups = m.groupdict()
                        file_subjects.append(
                            {
                                "group": groups.get("group", ""),
                                "subject": groups.get("subject", ""),
                                "day": groups.get("day", ""),
                            }
                        )
                    if file_subjects:
                        log.info(
                            "project_workflow_service.enrich_regex_fallback",
                            filename=filename,
                            subjects_found=len(file_subjects),
                        )

            # DEBUG: Log lookup result
            log.info(
                "project_workflow_service.enrich_video_debug",
                video_path=path_str[-50:] if path_str else "",
                file_subjects_count=len(file_subjects),
                file_subjects=file_subjects if len(file_subjects) <= 3 else "...",
            )

            if len(file_subjects) > 1:
                # Multi-subject file - mark it and store entries
                enriched["is_multi_subject"] = True
                enriched["subject_entries"] = file_subjects
                metadata["is_multi_subject"] = True
                metadata["subject_entries"] = file_subjects
                multi_subject_count += 1

                # Use first entry for primary metadata
                first_entry = file_subjects[0]
                if first_entry.get("group"):
                    group_id = first_entry["group"]
                    enriched["group"] = group_id
                    metadata["group"] = group_id
                    display_name = group_display_names.get(group_id, group_id)
                    if display_name and display_name != group_id:
                        enriched["group_display_name"] = display_name
                        metadata["group_display_name"] = display_name

                if first_entry.get("day"):
                    day_val = first_entry["day"]
                    enriched["day"] = day_val
                    metadata["day"] = day_val

                # Don't set single subject - it's multi-subject
                enriched["subject"] = None
                metadata.pop("subject", None)

            elif len(file_subjects) == 1:
                # Single subject from mapping
                entry = file_subjects[0]
                if entry.get("group"):
                    enriched["group"] = entry["group"]
                    metadata["group"] = entry["group"]
                if entry.get("day"):
                    enriched["day"] = entry["day"]
                    metadata["day"] = entry["day"]
                if entry.get("subject"):
                    enriched["subject"] = entry["subject"]
                    metadata["subject"] = entry["subject"]

            else:
                # Fallback: Use legacy extraction patterns
                group_id = self._extract_group(
                    metadata,
                    enriched,
                    path_str,
                    group_pattern,
                    group_lookup,
                    group_display_names,
                )
                self._extract_day(metadata, enriched, path_str, day_pattern, day_lookup)
                self._extract_subject(
                    metadata,
                    enriched,
                    path_str,
                    subject_pattern,
                    subject_lookup,
                    group_id,
                )

            if metadata:
                enriched["metadata"] = metadata

            enriched_videos.append(enriched)

        log.info(
            "wizard.videos_enriched",
            total=len(enriched_videos),
            with_group=sum(1 for v in enriched_videos if v.get("group")),
            with_day=sum(1 for v in enriched_videos if v.get("day")),
            with_subject=sum(1 for v in enriched_videos if v.get("subject")),
            multi_subject_files=multi_subject_count,
        )

        return enriched_videos

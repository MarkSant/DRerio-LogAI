"""Model Override Service - Project-specific model settings management.

Extracted from ProjectLifecycleCoordinator (Phase 5B decomposition).
Manages project-specific model overrides: apply, save, resolve, copy.

Single Responsibility: Model override state and persistence.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui import payloads

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class ModelOverrideService:
    """Service for managing project-specific model override settings.

    Responsibilities:
    - Track whether project overrides are active
    - Persist model override settings to project data
    - Resolve effective model settings (project vs global)
    - Copy global settings to project overrides
    - Save calibration settings as project overrides

    Phase 5B: Extracted from ProjectLifecycleCoordinator Group C + Group E helpers.
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        project_workflow_service: ProjectWorkflowService,
        settings_obj: Settings,
        event_bus: EventBusV2 | None = None,
    ) -> None:
        """Initialize ModelOverrideService.

        Args:
            state_manager: StateManager for state queries
            project_manager: ProjectManager for project data access
            project_workflow_service: Service for workflow-level operations
            settings_obj: Application settings
            event_bus: Optional event bus for UI notifications
        """
        self.state_manager = state_manager
        self.project_manager = project_manager
        self.project_workflow_service = project_workflow_service
        self.settings = settings_obj
        self.event_bus = event_bus
        self.logger = log.bind(service="model_override_service")

        # Internal state (migrated from ProjectLifecycleCoordinator)
        self._using_project_overrides: bool = False
        self._global_model_defaults: dict[str, Any] = {}

        log.info("model_override_service.initialized")

    # ------------------------------------------------------------------
    # Event helper (mirrors BaseCoordinator._publish_event)
    # ------------------------------------------------------------------

    def _publish_event(self, event_type: Any, data: Any = None) -> None:
        """Publish an event via EventBusV2.

        Args:
            event_type: UIEvents enum member.
            data: Optional event payload.
        """
        if self.event_bus is not None:
            from zebtrack.ui.event_bus_v2 import Event

            self.event_bus.publish(Event(type=event_type, data=data))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def are_project_overrides_active(self) -> bool:
        """Check if project-specific model overrides are currently active.

        Returns:
            True if using project overrides, False if using global settings
        """
        return bool(self._using_project_overrides)

    def has_project_override_settings(self) -> bool:
        """Check if project has any non-empty model override settings.

        Returns:
            True if project has model overrides, False otherwise
        """
        if not getattr(self.project_manager, "project_path", None):
            return False
        overrides = self._ensure_project_overrides_record()
        slot_weights = overrides.get("slot_weights")
        if isinstance(slot_weights, dict) and any(
            isinstance(value, str) and value.strip() for value in slot_weights.values()
        ):
            return True

        for key, value in overrides.items():
            if key in {"slot_weights", "device"}:
                continue
            if value not in (None, "", "inherit"):
                return True
        return False

    def copy_global_model_settings_to_project(
        self,
        get_global_defaults: Callable[[], dict],
        get_active_weight_name: Callable[[], str | None],
        refresh_callback: Callable[[str, bool], None] | None = None,
        active_weight_setter: Callable[[str], None] | None = None,
        use_openvino_setter: Callable[[bool], None] | None = None,
        apply_runtime_callback: Callable[[str | None, bool], None] | None = None,
    ) -> tuple[str | None, bool] | None:
        """Copy global model settings to current project as overrides.

        Args:
            get_global_defaults: Callback to get global model defaults
            get_active_weight_name: Callback to get active weight name
            refresh_callback: Optional callback to refresh project views
            active_weight_setter: Real setter that updates state_manager
                ``detector_state.active_weight_name``. Sem ele o ``apply``
                interno do workflow service rodava com lambda no-op e o
                detector ativo nao sentia o copy.
            use_openvino_setter: Real setter that updates state_manager
                ``detector_state.use_openvino``. Mesma razao.
            apply_runtime_callback: Callback invoked AFTER the override is
                persisted and applied, receiving ``(resolved_weight,
                resolved_openvino)``. Usado para reconstruir o detector e
                publicar eventos de UI (checkbox/status).

        Returns:
            Tuple of (weight_name, use_openvino) if successful, None otherwise
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        if not getattr(self.project_manager, "project_path", None):
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Nenhum Projeto",
                    message="Abra um projeto antes de copiar configurações globais.",
                ),
            )
            return None

        defaults = get_global_defaults()
        use_openvino = bool(defaults.get("use_openvino", False))
        slot_weights = self.project_workflow_service.get_global_project_slot_weights()
        if not slot_weights:
            legacy_weight = defaults.get("active_weight") or get_active_weight_name()
            legacy_slot = self.project_workflow_service._get_legacy_animal_slot_key({})
            if legacy_weight and legacy_slot:
                slot_weights = {legacy_slot: legacy_weight}

        resolved_weight, resolved_openvino = (
            self.project_workflow_service.save_project_model_slot_overrides(
                slot_weights,  # type: ignore[arg-type]
                use_openvino,
                active_weight_setter=active_weight_setter,
                use_openvino_setter=use_openvino_setter,
            )
        )

        log.info(
            "model_override_service.copy_global.applied",
            resolved_weight=resolved_weight,
            resolved_openvino=resolved_openvino,
            had_runtime_callback=apply_runtime_callback is not None,
        )

        # Runtime hook: rebuild detector + publish UI events with the
        # newly resolved settings. Mantido opcional para preservar callers
        # antigos (testes).
        if apply_runtime_callback is not None:
            apply_runtime_callback(resolved_weight, resolved_openvino)

        message = "Configurações globais aplicadas ao projeto."
        self._publish_event(UIEvents.UI_SET_STATUS, payloads.StatusPayload(message=message))

        if refresh_callback:
            refresh_callback(message, True)

        return resolved_weight, resolved_openvino

    def copy_global_model_settings_to_project_path(
        self,
        target_dir: Path | str,
        get_global_defaults: Callable[[], dict],
        get_active_weight_name: Callable[[], str | None],
    ) -> tuple[str | None, bool] | None:
        """Copy global model settings into another project's config file.

        Grava os padrões globais como overrides no ``project_config.json``
        do projeto-alvo SEM abri-lo nem tocar o estado da aplicação. Quando
        o alvo é o próprio projeto aberto, delega ao fluxo em memória.
        A mensageria de erro fica a cargo do chamador (UI); aqui apenas
        logamos e retornamos ``None`` em caso de falha.

        Args:
            target_dir: Diretório do projeto-alvo.
            get_global_defaults: Callback com os defaults globais.
            get_active_weight_name: Callback com o peso ativo (fallback legacy).

        Returns:
            Tupla (active_weight, use_openvino) gravada, ou None em falha.
        """
        from zebtrack.core.project.project_lifecycle_manager import CONFIG_FILE_NAME

        target = Path(target_dir)
        current_path = getattr(self.project_manager, "project_path", None)
        if current_path and Path(current_path).resolve() == target.resolve():
            return self.copy_global_model_settings_to_project(
                get_global_defaults, get_active_weight_name
            )

        config_path = target / CONFIG_FILE_NAME
        if not config_path.exists():
            self.logger.warning(
                "project.copy_globals_to_path.invalid_target",
                target=str(target),
                reason="config_file_missing",
            )
            return None

        defaults = get_global_defaults()
        use_openvino = bool(defaults.get("use_openvino", False))
        slot_weights = self.project_workflow_service.get_global_project_slot_weights()
        if not slot_weights:
            legacy_weight = defaults.get("active_weight") or get_active_weight_name()
            legacy_slot = self.project_workflow_service._get_legacy_animal_slot_key({})
            if legacy_weight and legacy_slot:
                slot_weights = {legacy_slot: legacy_weight}

        project_service = getattr(self.project_manager, "project_service", None)
        if project_service is None:
            self.logger.warning("project.copy_globals_to_path.no_project_service")
            return None

        try:
            target_data = project_service.load_project_config(target)
        # except Exception justified: leitura de projeto externo — pode falhar
        # por corrupção, hash de integridade ou permissão; reportamos via None.
        except Exception as exc:
            self.logger.error(
                "project.copy_globals_to_path.load_failed",
                target=str(target),
                error=str(exc),
            )
            return None

        normalized_slot_weights = self.project_workflow_service._normalize_slot_weights(
            slot_weights
        )
        legacy_animal_slot = self.project_workflow_service._get_legacy_animal_slot_key(
            normalized_slot_weights
        )
        resolved_weight = (
            normalized_slot_weights.get(legacy_animal_slot) if legacy_animal_slot else None
        )

        overrides = target_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None, "device": "AUTO", "slot_weights": {}},
        )
        overrides["slot_weights"] = normalized_slot_weights
        overrides["active_weight"] = resolved_weight
        overrides["use_openvino"] = use_openvino
        # Espelhos legacy no nível raiz (mesma forma de _persist_project_model_settings).
        target_data["active_weight"] = resolved_weight
        target_data["use_openvino"] = use_openvino

        try:
            project_service.save_project_config(target, target_data)
        # except Exception justified: escrita de projeto externo — I/O heterogêneo.
        except Exception as exc:
            self.logger.error(
                "project.copy_globals_to_path.save_failed",
                target=str(target),
                error=str(exc),
            )
            return None

        from zebtrack.ui.event_bus_v2 import UIEvents

        self.logger.info(
            "project.copy_globals_to_path.success",
            target=str(target),
            active_weight=resolved_weight,
            use_openvino=use_openvino,
        )
        self._publish_event(
            UIEvents.UI_SET_STATUS,
            payloads.StatusPayload(
                message=f"Configurações globais aplicadas ao projeto em {target}."
            ),
        )
        return resolved_weight, use_openvino

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """Resolve model settings considering project overrides and global defaults.

        Args:
            overrides: Optional override dictionary to merge

        Returns:
            Tuple of (resolved_weight, resolved_openvino)
        """
        return self.project_workflow_service.resolve_project_model_settings(overrides)

    def save_current_calibration_to_project(
        self,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> tuple[str | None, bool] | None:
        """Save current model settings as project-specific overrides.

        Args:
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage
            refresh_callback: Optional callback to refresh project views

        Returns:
            Tuple of (weight_name, use_openvino) if successful, None otherwise
        """
        from zebtrack.ui.event_bus_v2 import UIEvents

        if not getattr(self.project_manager, "project_path", None):
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(
                    title="Nenhum Projeto",
                    message="Abra um projeto antes de salvar overrides de calibração.",
                ),
            )
            return None

        overrides = self._persist_project_model_settings(
            get_active_weight_name() or None,
            bool(get_use_openvino()),
        )

        # Apply overrides
        self.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=lambda w: None,  # Will be set by caller
            use_openvino_setter=lambda v: None,  # Will be set by caller
        )

        message = "Overrides do projeto atualizados a partir desta calibração."
        self._publish_event(UIEvents.UI_SET_STATUS, payloads.StatusPayload(message=message))

        if refresh_callback:
            refresh_callback(message, True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def apply_project_model_overrides(
        self,
        *,
        overrides: dict | None = None,
        active_weight_setter: Callable[[str], None],
        use_openvino_setter: Callable[[bool], None],
    ) -> tuple[str | None, bool]:
        """Apply project-specific model overrides to current settings.

        Args:
            overrides: Optional override dictionary
            active_weight_setter: Callback to set active weight
            use_openvino_setter: Callback to set OpenVINO usage

        Returns:
            Tuple of (resolved_weight, resolved_openvino)
        """
        return self.project_workflow_service.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=active_weight_setter,
            use_openvino_setter=use_openvino_setter,
        )

    def save_project_model_overrides(
        self,
        active_weight_override: str | None,
        use_openvino_override: bool | None,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
    ) -> tuple[str | None, bool]:
        """Save model settings as project overrides and apply them.

        Args:
            active_weight_override: Weight name to save as override
            use_openvino_override: OpenVINO preference to save as override
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage

        Returns:
            Tuple of (resolved_weight, resolved_openvino)
        """
        if not getattr(self.project_manager, "project_path", None):
            self.logger.warning("project.overrides.no_project_loaded")
            return (
                get_active_weight_name() or None,
                get_use_openvino(),
            )
        legacy_slot = self.project_workflow_service._get_legacy_animal_slot_key({})
        slot_weights = (
            {legacy_slot: active_weight_override} if legacy_slot and active_weight_override else {}
        )
        return self.project_workflow_service.save_project_model_slot_overrides(
            slot_weights,  # type: ignore[arg-type]
            use_openvino_override,
        )

    def save_project_model_slot_overrides(
        self,
        slot_weights: dict[str, str | None] | None,
        use_openvino_override: bool | None,
    ) -> tuple[str | None, bool]:
        """Save explicit per-slot model overrides for the active project."""
        return self.project_workflow_service.save_project_model_slot_overrides(
            slot_weights,
            use_openvino_override,
        )

    def restore_global_model_defaults(self) -> None:
        """Restore global model defaults after closing a project."""
        defaults = dict(getattr(self.project_workflow_service, "_global_model_defaults", {}) or {})
        if not defaults:
            defaults = dict(self._global_model_defaults)

        active_weight = defaults.get("active_weight")
        use_openvino = bool(defaults.get("use_openvino", False))

        self.project_workflow_service.set_global_model_defaults(active_weight, use_openvino)
        self._global_model_defaults = {
            "active_weight": active_weight,
            "use_openvino": use_openvino,
        }

        self.state_manager.update_detector_state(
            source="model_override_service.restore_global_model_defaults",
            active_weight_name=active_weight,
            use_openvino=use_openvino,
        )

        weight_manager = getattr(
            self.project_workflow_service.model_service, "weight_manager", None
        )
        if weight_manager is not None and hasattr(weight_manager, "clear_runtime_slot_overrides"):
            weight_manager.clear_runtime_slot_overrides()
        self._using_project_overrides = False
        self.logger.info("project.model_defaults.restored")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_project_overrides_record(self) -> dict:
        """Ensure project overrides record exists in project data.

        Returns:
            Model overrides dictionary
        """
        project_data: dict[str, Any] = self.project_manager.project_data
        overrides = project_data.get("model_overrides")
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None, "slot_weights": {}}
            project_data["model_overrides"] = overrides
        overrides.setdefault("slot_weights", {})
        return overrides

    def _persist_project_model_settings(
        self, weight: str | None, use_openvino: bool
    ) -> dict[str, Any]:
        """Persist model settings to project configuration.

        Args:
            weight: Weight name to persist
            use_openvino: OpenVINO usage flag to persist

        Returns:
            Updated overrides dictionary
        """
        project_data = self.project_manager.project_data
        overrides = self._ensure_project_overrides_record()

        # Update overrides
        overrides["active_weight"] = weight
        overrides["use_openvino"] = use_openvino
        project_data["active_weight"] = weight
        project_data["use_openvino"] = bool(use_openvino)

        # Update in-memory state
        self.project_manager.project_data = project_data

        # Delegate persistence to ProjectManager
        if getattr(self.project_manager, "project_path", None):
            self.project_manager.save_project()

        return overrides

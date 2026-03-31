"""Model Override Service - Project-specific model settings management.

Extracted from ProjectLifecycleCoordinator (Phase 5B decomposition).
Manages project-specific model overrides: apply, save, resolve, copy.

Single Responsibility: Model override state and persistence.
"""

from __future__ import annotations

from collections.abc import Callable
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
        return any(value not in (None, "", "inherit") for value in overrides.values())

    def copy_global_model_settings_to_project(
        self,
        get_global_defaults: Callable[[], dict],
        get_active_weight_name: Callable[[], str | None],
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> tuple[str | None, bool] | None:
        """Copy global model settings to current project as overrides.

        Args:
            get_global_defaults: Callback to get global model defaults
            get_active_weight_name: Callback to get active weight name
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
                    message="Abra um projeto antes de copiar configurações globais.",
                ),
            )
            return None

        defaults = get_global_defaults()
        weight = defaults.get("active_weight") or get_active_weight_name()
        use_openvino = bool(defaults.get("use_openvino", False))

        overrides = self._persist_project_model_settings(weight, use_openvino)

        message = "Configurações globais aplicadas ao projeto."
        self._publish_event(UIEvents.UI_SET_STATUS, payloads.StatusPayload(message=message))

        if refresh_callback:
            refresh_callback(message, True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

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

        overrides = self.project_manager.project_data.setdefault(
            "model_overrides",
            {"active_weight": None, "use_openvino": None},
        )
        overrides["active_weight"] = active_weight_override or None
        overrides["use_openvino"] = use_openvino_override

        # Apply overrides (callbacks will be set by caller)
        resolved_weight, resolved_openvino = self.apply_project_model_overrides(
            overrides=overrides,
            active_weight_setter=lambda w: None,  # Will be set by caller
            use_openvino_setter=lambda v: None,  # Will be set by caller
        )

        self.project_manager.project_data["model_overrides"] = overrides
        self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    def restore_global_model_defaults(self) -> None:
        """Restore global model defaults after closing a project."""
        detector_state = self.state_manager.get_detector_state()
        self._global_model_defaults["active_weight"] = detector_state.active_weight_name
        self._global_model_defaults["use_openvino"] = detector_state.use_openvino
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
            overrides = {"active_weight": None, "use_openvino": None}
            project_data["model_overrides"] = overrides
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

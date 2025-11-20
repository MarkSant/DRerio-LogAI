"""Project Lifecycle Coordinator - Phase 3 Super Coordinator.

Consolidates project lifecycle, asset management, model overrides, and calibration.
This is one of the 4 super coordinators created in Phase 3 of MainViewModel refactoring.

Consolidates:
- ProjectOrchestrator (Sprint 27)
- CalibrationOrchestrator (Sprint 32)
- ProjectWorkflowAdapter coordination logic

CRITICAL: No dependency on MainViewModel. All dependencies injected explicitly.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

import numpy as np
import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.calibration import Calibration
from zebtrack.core.project_manager import AssetType
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.project_manager import ProjectManager
    from zebtrack.core.project_workflow_service import ProjectWorkflowService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus
    from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter

log = structlog.get_logger()


class ProjectLifecycleCoordinator(BaseCoordinator):
    """Super coordinator for complete project lifecycle management.

    Responsibilities:
    - Project lifecycle (create, open, close)
    - Project asset management (delete, validate, register outputs)
    - Model override management (apply, save, resolve)
    - Calibration scope and context management
    - Zone setup from project data

    Phase 3: Consolidates ProjectOrchestrator + CalibrationOrchestrator
    Eliminates MainViewModel dependency through pure dependency injection.

    Example:
        coordinator = ProjectLifecycleCoordinator(
            state_manager=state_manager,
            project_manager=project_manager,
            project_workflow_service=project_workflow_service,
            project_workflow_adapter=project_workflow_adapter,
            settings_obj=settings,
            event_bus=event_bus
        )

        # Create project
        path = coordinator.create_project(name="my_project", type="pre-recorded")

        # Open project
        coordinator.open_project(path)

        # Manage calibration
        info = coordinator.get_calibration_scope_info()

        # Close project
        coordinator.close_project()
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        project_workflow_service: ProjectWorkflowService,
        project_workflow_adapter: ProjectWorkflowAdapter,
        settings_obj: Settings,
        event_bus: EventBus | None = None,
    ):
        """Initialize ProjectLifecycleCoordinator with dependency injection.

        Args:
            state_manager: StateManager for state updates
            project_manager: ProjectManager for project operations
            project_workflow_service: Service for project workflow logic
            project_workflow_adapter: Adapter for workflow coordination
            settings_obj: Settings instance
            event_bus: Optional EventBus for publishing events

        Note:
            NEVER pass MainViewModel. All dependencies must be explicit.
        """
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.project_workflow_service = project_workflow_service
        self.project_workflow_adapter = project_workflow_adapter
        self.settings = settings_obj

        # Internal state (migrated from orchestrators)
        self._using_project_overrides: bool = False
        self._global_model_defaults: dict[str, Any] = {}

        log.info("project_lifecycle_coordinator.initialized")

    # ========================================================================
    # Group A: Project Lifecycle (create, open, close)
    # ========================================================================

    def close_project(
        self,
        *,
        restore_global_defaults_callback: Callable[[], None] | None = None,
    ) -> ProjectManager:
        """Close the current project.

        Args:
            restore_global_defaults_callback: Optional callback to restore global model defaults

        Returns:
            New ProjectManager instance

        Phase 3: Consolidated from ProjectOrchestrator.close_project
        """
        self.logger.info("project.close.start")

        # Delegate to adapter which handles all UI coordination
        new_project_manager = self.project_workflow_adapter.close_project(
            restore_global_defaults_callback=restore_global_defaults_callback or self._restore_global_model_defaults,
            settings_obj=self.settings,
        )

        # Update reference
        self.project_manager = new_project_manager

        self._publish_event(Events.PROJECT_CLOSED, {})
        self.logger.info("project.close.complete")

        return new_project_manager

    def create_project(
        self,
        *,
        setup_detector_callback: Callable[[Any], None] | None = None,
        set_active_weight_callback: Callable[[str, Any], None] | None = None,
        set_openvino_usage_callback: Callable[[bool, Any], None] | None = None,
        update_openvino_status_callback: Callable[[], None] | None = None,
        get_active_weight_name: Callable[[], str | None] | None = None,
        get_use_openvino: Callable[[], bool] | None = None,
        apply_wizard_overrides_callback: Callable[[dict], None] | None = None,
        **wizard_data,
    ) -> Path:
        """Create new project with wizard data.

        Args:
            setup_detector_callback: Callback to setup detector
            set_active_weight_callback: Callback to set active weight
            set_openvino_usage_callback: Callback to set OpenVINO usage
            update_openvino_status_callback: Callback to update OpenVINO status
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage
            apply_wizard_overrides_callback: Callback to apply wizard detector overrides
            **wizard_data: Project creation data from wizard

        Returns:
            Path to created project

        Phase 3: Consolidated from ProjectOrchestrator.create_project_workflow
        """
        self.logger.info("project.create.start", wizard_data_keys=list(wizard_data.keys()))

        # Delegate to adapter which handles all UI coordination
        project_path = self.project_workflow_adapter.create_project_workflow(
            setup_detector_callback=setup_detector_callback,
            set_active_weight_callback=set_active_weight_callback,
            set_openvino_usage_callback=set_openvino_usage_callback,
            update_openvino_status_callback=update_openvino_status_callback,
            get_active_weight_name=get_active_weight_name,
            get_use_openvino=get_use_openvino,
            apply_wizard_overrides_callback=apply_wizard_overrides_callback,
            view_suppress_guide_check=lambda: False,  # Default behavior
            **wizard_data,
        )

        self._publish_event(Events.PROJECT_CREATED, {"path": str(project_path)})
        self.logger.info("project.create.complete", path=str(project_path))

        return project_path

    def open_project(
        self,
        project_path: Path | str,
        *,
        setup_detector_callback: Callable[[Any], None] | None = None,
        set_active_weight_callback: Callable[[str, Any], None] | None = None,
        set_openvino_usage_callback: Callable[[bool, Any], None] | None = None,
        update_openvino_status_callback: Callable[[], None] | None = None,
        setup_zones_callback: Callable[[], None] | None = None,
        restore_detector_callback: Callable[[], None] | None = None,
        get_active_weight_name: Callable[[], str | None] | None = None,
        get_use_openvino: Callable[[], bool] | None = None,
    ) -> bool:
        """Open existing project and configure everything automatically.

        Args:
            project_path: Path to project directory
            setup_detector_callback: Callback to setup detector
            set_active_weight_callback: Callback to set active weight
            set_openvino_usage_callback: Callback to set OpenVINO usage
            update_openvino_status_callback: Callback to update OpenVINO status
            setup_zones_callback: Callback to setup zones from project
            restore_detector_callback: Callback to restore detector settings
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage

        Returns:
            True if successful, False otherwise

        Phase 3: Consolidated from ProjectOrchestrator.open_project_workflow
        """
        self.logger.info("project.open.start", path=str(project_path))

        # Delegate to adapter which handles all UI coordination
        success = self.project_workflow_adapter.open_project_workflow(
            project_path=project_path,
            setup_detector_callback=setup_detector_callback,
            set_active_weight_callback=set_active_weight_callback,
            set_openvino_usage_callback=set_openvino_usage_callback,
            update_openvino_status_callback=update_openvino_status_callback,
            setup_zones_callback=setup_zones_callback or self._setup_zones_from_project,
            restore_detector_callback=restore_detector_callback,
            get_active_weight_name=get_active_weight_name,
            get_use_openvino=get_use_openvino,
        )

        if success:
            self._publish_event(Events.PROJECT_OPENED, {"path": str(project_path)})
            self.logger.info("project.open.complete", path=str(project_path))
        else:
            self.logger.warning("project.open.failed", path=str(project_path))

        return success

    # ========================================================================
    # Group B: Asset Management
    # ========================================================================

    def can_remove_project_asset(
        self, video_path: Path | str, asset: str
    ) -> tuple[bool, str | None]:
        """Validate whether a project asset can be safely removed.

        Args:
            video_path: Path to video file
            asset: Asset type to remove

        Returns:
            Tuple of (can_remove, error_message)

        Phase 3: Consolidated from ProjectOrchestrator.can_remove_project_asset
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            return self.project_manager.can_remove_asset(str(video_path), asset_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.asset.can_remove_failed",
                asset=asset,
                video=str(video_path),
                error=str(exc),
            )
            return False, "Não foi possível validar a remoção solicitada."

    def delete_project_asset(
        self,
        video_path: Path | str,
        asset: str,
        *,
        delete_source: bool = True,
    ) -> bool:
        """Remove a project asset (arena, ROIs, trajetória, sumário ou vídeo).

        Args:
            video_path: Path to video file
            asset: Asset type to remove
            delete_source: Whether to delete source files

        Returns:
            True if successful, False otherwise

        Phase 3: Consolidated from ProjectOrchestrator.delete_project_asset
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            removed = self.project_manager.remove_asset(
                str(video_path),
                asset_type,
                delete_files=delete_source,
            )
            self.logger.info(
                "project.asset.removal_result",
                asset=asset,
                video=str(video_path),
                removed=removed,
                delete_source=delete_source,
            )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "project.asset.remove_failed",
                asset=asset,
                video=str(video_path),
                error=str(exc),
                exc_info=True,
            )
            return False

    def register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
        refresh_callback: Callable[[str, bool], None] | None = None,
    ) -> None:
        """Register processing outputs to project.

        Args:
            video_path: Path to processed video
            results_dir: Results directory path
            trajectory_path: Trajectory parquet path
            summary_parquet: Summary parquet path
            summary_excel: Summary excel path
            report_path: Report docx path
            refresh_callback: Optional callback to refresh project views

        Phase 3: Consolidated from ProjectOrchestrator._register_project_outputs
        """
        self.logger.info("project.outputs.register.start", video=video_path)

        # Register through project manager
        if hasattr(self.project_manager, '_register_outputs'):
            self.project_manager._register_outputs(
                video_path=video_path,
                results_dir=results_dir,
                trajectory_path=trajectory_path,
                summary_parquet=summary_parquet,
                summary_excel=summary_excel,
                report_path=report_path,
            )

        # Refresh views if callback provided
        if refresh_callback:
            refresh_callback("processing_progress", True)

        self.logger.info("project.outputs.register.complete", video=video_path)

    # ========================================================================
    # Group C: Model Override Management
    # ========================================================================

    def are_project_overrides_active(self) -> bool:
        """Check if project-specific model overrides are currently active.

        Returns:
            True if using project overrides, False if using global settings

        Phase 3: Consolidated from ProjectOrchestrator.are_project_overrides_active
        """
        return bool(self._using_project_overrides)

    def has_project_override_settings(self) -> bool:
        """Check if project has any non-empty model override settings.

        Returns:
            True if project has model overrides, False otherwise

        Phase 3: Consolidated from ProjectOrchestrator.has_project_override_settings
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

        Phase 3: Consolidated from ProjectOrchestrator.copy_global_model_settings_to_project
        """
        if not getattr(self.project_manager, "project_path", None):
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de copiar configurações globais.",
                },
            )
            return None

        defaults = get_global_defaults()
        weight = defaults.get("active_weight") or get_active_weight_name()
        use_openvino = bool(defaults.get("use_openvino", False))

        overrides = self._persist_project_model_settings(weight, use_openvino)

        message = "Configurações globais aplicadas ao projeto."
        self._publish_event(Events.UI_SET_STATUS, {"message": message})

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

        Phase 3: Consolidated from ProjectOrchestrator.resolve_project_model_settings
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

        Phase 3: Consolidated from ProjectOrchestrator.save_current_calibration_to_project
        """
        if not getattr(self.project_manager, "project_path", None):
            self._publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de salvar overrides de calibração.",
                },
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
            use_openvino_setter=lambda v: None,   # Will be set by caller
        )

        message = "Overrides do projeto atualizados a partir desta calibração."
        self._publish_event(Events.UI_SET_STATUS, {"message": message})

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

        Phase 3: Consolidated from ProjectOrchestrator.apply_project_model_overrides
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

        Phase 3: Consolidated from ProjectOrchestrator.save_project_model_overrides
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
            use_openvino_setter=lambda v: None,   # Will be set by caller
        )

        self.project_manager.project_data["model_overrides"] = overrides
        self.project_manager.save_project()

        return resolved_weight, resolved_openvino

    # ========================================================================
    # Group D: Calibration Management
    # ========================================================================

    def get_calibration_scope_info(
        self,
        get_active_weight_name: Callable[[], str | None] | None = None,
        gui_instance: Any | None = None,
    ) -> dict:
        """Get calibration scope information for UI display.

        Args:
            get_active_weight_name: Callback to get active weight name
            gui_instance: Optional GUI instance for single-video mode check

        Returns:
            Dictionary with scope, project status, labels, and detail messages

        Phase 3: Consolidated from CalibrationOrchestrator.get_calibration_scope_info
        """
        project_path = getattr(self.project_manager, "project_path", None)
        project_loaded = bool(project_path)
        project_name = None
        if project_loaded and hasattr(self.project_manager, "get_project_name"):
            try:
                project_name = self.project_manager.get_project_name()
            except Exception:  # pragma: no cover - defensive
                project_name = None

        overrides_active = self.has_project_override_settings()
        inheriting_globals = project_loaded and not overrides_active
        scope = (
            "project"
            if project_loaded and self._using_project_overrides
            else "global"
        )

        # Check if in single-video analysis mode
        is_single_video_mode = False
        if gui_instance:
            is_single_video_mode = bool(getattr(gui_instance, "pending_single_video_path", None))

        if scope == "project":
            label = f"Escopo: Projeto ({project_name})" if project_name else "Escopo: Projeto"
            if overrides_active:
                detail = (
                    "Este projeto usa overrides salvos. Ajustes nesta janela são "
                    "persistidos apenas neste projeto."
                )
            else:
                detail = (
                    "Este projeto está herdando os padrões globais. Ao salvar "
                    "aqui, os valores se tornam overrides específicos."
                )
        else:
            label = "Escopo: Configuração Global"
            if project_loaded:
                detail = (
                    "Alterações atualizam o padrão global. Use a ação de cópia para "
                    "fixar estes valores no projeto atual."
                )
            else:
                detail = "Nenhum projeto carregado; ajustes atualizam os padrões globais."

        return {
            "scope": scope,
            "project_loaded": project_loaded,
            "project_name": project_name,
            "overrides_active": overrides_active,
            "inheriting_globals": inheriting_globals,
            "is_single_video_mode": is_single_video_mode,
            "label": label,
            "detail": detail,
        }

    def build_calibration_context(
        self,
        arena_polygon: list[list[int]] | list | None,
        calibration_data: dict | None,
    ) -> tuple[Calibration | None, tuple[float, float] | None]:
        """Calculate calibration and pixel/cm ratio for tracking outputs.

        Args:
            arena_polygon: Arena polygon coordinates
            calibration_data: Calibration data dictionary

        Returns:
            Tuple of (Calibration object, pixel_per_cm_ratio)

        Phase 3: Consolidated from CalibrationOrchestrator._build_calibration_context
        """
        pixel_per_cm_ratio = None
        cal = None

        calibration_source = calibration_data or (
            self.project_manager.project_data.get("calibration")
            if self.project_manager and self.project_manager.project_data
            else None
        )

        if calibration_source:
            width_cm = calibration_source.get("aquarium_width_cm")
            height_cm = calibration_source.get("aquarium_height_cm")
            if width_cm and height_cm and arena_polygon:
                polygon_array = np.array(arena_polygon)
                cal = Calibration(polygon_array, width_cm, height_cm)
                pixel_per_cm_ratio = cal.pixel_per_cm_ratio

        return cal, pixel_per_cm_ratio

    @contextmanager
    def global_calibration_session(
        self,
        get_active_weight_name: Callable[[], str | None],
        get_use_openvino: Callable[[], bool],
    ):
        """Context manager for global calibration mode.

        Temporarily disables project overrides and saves changes to global defaults.
        Restores project overrides on exit if they were active before.

        Args:
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage

        Yields:
            None

        Phase 3: Consolidated from CalibrationOrchestrator.global_calibration_session
        """
        previous_flag = self._using_project_overrides
        self._using_project_overrides = False
        try:
            yield
        finally:
            self._global_model_defaults["active_weight"] = (
                get_active_weight_name() or None
            )
            self._global_model_defaults["use_openvino"] = get_use_openvino()
            self._using_project_overrides = previous_flag

    @contextmanager
    def project_calibration_session(self):
        """Context manager for project-specific calibration mode.

        Enables project override mode and saves changes to project settings.
        Maintains override state on exit if project has overrides.

        Yields:
            None

        Phase 3: Consolidated from ProjectOrchestrator.project_calibration_session
        """
        previous_flag = self._using_project_overrides
        self._using_project_overrides = True
        try:
            yield
        finally:
            if self.has_project_override_settings():
                self._using_project_overrides = True
            else:
                self._using_project_overrides = previous_flag

    # ========================================================================
    # Group E: Supporting Methods (Private)
    # ========================================================================

    def _setup_zones_from_project(
        self,
        setup_detector_zones_callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Set up zones from project data.

        Args:
            setup_detector_zones_callback: Callback to setup detector zones

        Phase 3: Consolidated from ProjectOrchestrator._setup_zones_from_project
        """
        if setup_detector_zones_callback is None:
            self.logger.warning("project.zones.setup.no_callback")
            return

        self.project_workflow_adapter.setup_zones_from_project(
            setup_detector_zones_callback=setup_detector_zones_callback,
        )

    def _ensure_project_overrides_record(self) -> dict:
        """Ensure project overrides record exists in project data.

        Returns:
            Model overrides dictionary

        Phase 3: Consolidated from ProjectOrchestrator._ensure_project_overrides_record
        """
        project_data = self.project_manager.project_data
        overrides = project_data.get("model_overrides")
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None}
            project_data["model_overrides"] = overrides
        return overrides

    def _persist_project_model_settings(
        self, weight: str | None, use_openvino: bool
    ) -> dict:
        """Persist model settings to project configuration.

        Args:
            weight: Weight name to persist
            use_openvino: OpenVINO usage flag to persist

        Returns:
            Updated overrides dictionary

        Phase 3: Consolidated from ProjectOrchestrator._persist_project_model_settings
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

    def _restore_global_model_defaults(self) -> None:
        """Restore global model defaults after closing a project.

        Phase 3: Consolidated from ProjectOrchestrator._restore_global_model_defaults
        """
        detector_state = self.state_manager.get_detector_state()
        self._global_model_defaults["active_weight"] = detector_state.active_weight_name
        self._global_model_defaults["use_openvino"] = detector_state.use_openvino
        self._using_project_overrides = False
        self.logger.info("project.model_defaults.restored")

"""Calibration Coordinator - Calibration scope and context management.

Extracted from ProjectLifecycleCoordinator (Phase 5B decomposition).
Manages calibration sessions (global and project-scoped) and builds
calibration context from arena polygons.

Single Responsibility: Calibration workflow orchestration.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.core.detection.calibration import Calibration

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.services.model_override_service import ModelOverrideService
    from zebtrack.core.state_manager import StateManager
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class CalibrationCoordinator(BaseCoordinator):
    """Coordinator for calibration scope and context management.

    Responsibilities:
    - Determine calibration scope (global vs project)
    - Build calibration context from arena polygon + dimensions
    - Manage global calibration sessions (context manager)
    - Manage project calibration sessions (context manager)

    Phase 5B: Extracted from ProjectLifecycleCoordinator Group D.
    """

    def __init__(
        self,
        state_manager: StateManager,
        project_manager: ProjectManager,
        model_override_service: ModelOverrideService,
        event_bus: EventBusV2 | None = None,
    ) -> None:
        """Initialize CalibrationCoordinator.

        Args:
            state_manager: StateManager for state queries
            project_manager: ProjectManager for project data access
            model_override_service: Service for model override state queries
            event_bus: Optional event bus for publishing events
        """
        super().__init__(state_manager, event_bus)
        self.project_manager = project_manager
        self.model_override_service = model_override_service

        log.info("calibration_coordinator.initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_calibration_scope_info(
        self,
        get_active_weight_name: Callable[[], str | None] | None = None,
        gui_instance: Any | None = None,
    ) -> dict[str, Any]:
        """Get calibration scope information for UI display.

        Args:
            get_active_weight_name: Callback to get active weight name
            gui_instance: Optional GUI instance for single-video mode check

        Returns:
            Dictionary with scope, project status, labels, and detail messages
        """
        project_path = getattr(self.project_manager, "project_path", None)
        project_loaded = bool(project_path)
        project_name = None
        if project_loaded and hasattr(self.project_manager, "get_project_name"):
            try:
                project_name = self.project_manager.get_project_name()
            except Exception:  # pragma: no cover - defensive
                project_name = None

        overrides_active = self.model_override_service.has_project_override_settings()
        inheriting_globals = project_loaded and not overrides_active
        scope = (
            "project"
            if project_loaded and self.model_override_service._using_project_overrides
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
            "project_path": str(project_path) if project_path else None,
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
    ) -> Generator[None, None, None]:
        """Context manager for global calibration mode.

        Temporarily disables project overrides and saves changes to global defaults.
        Restores project overrides on exit if they were active before.

        Args:
            get_active_weight_name: Callback to get active weight name
            get_use_openvino: Callback to get OpenVINO usage

        Yields:
            None
        """
        mos = self.model_override_service
        previous_flag = mos._using_project_overrides
        mos._using_project_overrides = False
        try:
            yield
        finally:
            mos._global_model_defaults["active_weight"] = get_active_weight_name() or None
            mos._global_model_defaults["use_openvino"] = get_use_openvino()
            mos._using_project_overrides = previous_flag

    @contextmanager
    def project_calibration_session(self) -> Generator[None, None, None]:
        """Context manager for project-specific calibration mode.

        Enables project override mode and saves changes to project settings.
        Maintains override state on exit if project has overrides.

        Yields:
            None
        """
        mos = self.model_override_service
        previous_flag = mos._using_project_overrides
        mos._using_project_overrides = True
        try:
            yield
        finally:
            if mos.has_project_override_settings():
                mos._using_project_overrides = True
            else:
                mos._using_project_overrides = previous_flag

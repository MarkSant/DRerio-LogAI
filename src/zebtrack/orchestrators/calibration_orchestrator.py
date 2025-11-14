"""Calibration orchestration logic extracted from MainViewModel.

Sprint 32 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import numpy as np
import structlog

from zebtrack.core.calibration import Calibration

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class CalibrationOrchestrator:
    """Orchestrates calibration scope and context management.

    Extracted from MainViewModel in Sprint 32 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Calibration scope information for UI display
    - Calibration context building for tracking outputs
    - Global calibration session context management
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.project_manager = main_view_model.project_manager
        self.project_orchestrator = main_view_model.project_orchestrator

    def get_calibration_scope_info(self) -> dict:
        """Get calibration scope information for UI display.

        Returns:
            Dictionary with scope, project status, labels, and detail messages.
        """
        project_path = getattr(self.project_manager, "project_path", None)
        project_loaded = bool(project_path)
        project_name = None
        if project_loaded and hasattr(self.project_manager, "get_project_name"):
            try:
                project_name = self.project_manager.get_project_name()
            except Exception:  # pragma: no cover - defensive
                project_name = None

        overrides_active = self.main_view_model.has_project_override_settings()
        inheriting_globals = project_loaded and not overrides_active
        scope = (
            "project"
            if project_loaded and self.main_view_model._using_project_overrides
            else "global"
        )

        # Check if in single-video analysis mode
        is_single_video_mode = False
        gui = getattr(self.main_view_model, "gui", None)
        if gui:
            is_single_video_mode = bool(getattr(gui, "pending_single_video_path", None))

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

    def _build_calibration_context(
        self,
        arena_polygon: list[list[int]] | list | None,
        calibration_data: dict | None,
    ) -> tuple[Calibration | None, tuple[float, float] | None]:
        """Calculate calibration and pixel/cm ratio for tracking outputs."""
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
    def global_calibration_session(self):
        """Context manager for global calibration mode.

        Temporarily disables project overrides and saves changes to global defaults.
        Restores project overrides on exit if they were active before.

        Yields:
            None
        """
        previous_flag = self.main_view_model._using_project_overrides
        self.main_view_model._using_project_overrides = False
        try:
            yield
        finally:
            self.main_view_model._global_model_defaults["active_weight"] = (
                self.main_view_model.active_weight_name or None
            )
            self.main_view_model._global_model_defaults["use_openvino"] = (
                self.main_view_model.use_openvino
            )
            self.main_view_model._using_project_overrides = previous_flag
            if previous_flag and getattr(self.project_manager, "project_path", None):
                self.project_orchestrator.apply_project_model_overrides()

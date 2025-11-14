"""Project lifecycle and management orchestration logic extracted from MainViewModel.

Sprint 27 - Extracted to reduce MainViewModel complexity.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

from zebtrack.core.project_manager import AssetType
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

logger = structlog.get_logger()


class ProjectOrchestrator:
    """Orchestrates project lifecycle operations and model override management.

    Extracted from MainViewModel in Sprint 27 to reduce its size.
    Maintains reference to MainViewModel for delegation during gradual extraction.

    This class handles:
    - Project lifecycle (close, create, open workflows)
    - Project asset management (delete, validate, register outputs)
    - Model override management (apply, save, resolve project-specific settings)
    - Supporting methods for zones and calibration sessions
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for delegation
        """
        self.main_view_model = main_view_model

        # Cache frequently used attributes from MainViewModel
        self.project_manager = main_view_model.project_manager
        self.state_manager = main_view_model.state_manager
        self.view = main_view_model.view
        self.root = main_view_model.root
        self.settings = main_view_model.settings
        self.ui_event_bus = main_view_model.ui_event_bus
        self.project_workflow_adapter = main_view_model.project_workflow_adapter
        self.video_processing_service = main_view_model.video_processing_service
        self.video_processing_orchestrator = main_view_model.video_processing_orchestrator

    # ========================================================================
    # Group A: Lifecycle & Workflow
    # ========================================================================

    def close_project(self):
        """Close the current project.

        Phase 2, Task P2-T2: Delegates to ProjectWorkflowAdapter.
        """
        # Delegate to adapter which handles all UI coordination
        new_project_manager = self.project_workflow_adapter.close_project(
            restore_global_defaults_callback=self.main_view_model._restore_global_model_defaults,
            settings_obj=self.settings,
        )
        # Update reference to new project manager
        self.main_view_model.project_manager = new_project_manager
        self.project_manager = new_project_manager

    def create_project_workflow(self, **kwargs):
        """Create project workflow orchestration.

        Phase 2, Task P2-T2: Delegates to ProjectWorkflowAdapter.
        """
        # Delegate to adapter which handles all UI coordination
        return self.project_workflow_adapter.create_project_workflow(
            setup_detector_callback=self.main_view_model.setup_detector,
            set_active_weight_callback=self.main_view_model.set_active_weight,
            set_openvino_usage_callback=self.main_view_model.set_openvino_usage,
            update_openvino_status_callback=self.main_view_model.update_openvino_status,
            get_active_weight_name=lambda: self.main_view_model.active_weight_name,
            get_use_openvino=lambda: self.main_view_model.use_openvino,
            apply_wizard_overrides_callback=self.main_view_model._apply_wizard_detector_overrides,
            view_suppress_guide_check=lambda: getattr(
                self.view, "suppress_post_creation_guide", False
            ),
            **kwargs,
        )

    def open_project_workflow(self, project_path: Path | str):
        """Load project and configure everything automatically.

        Phase 2, Task P2-T2: Delegates to ProjectWorkflowAdapter.
        """
        return self.project_workflow_adapter.open_project_workflow(
            project_path=project_path,
            setup_detector_callback=self.main_view_model.setup_detector,
            set_active_weight_callback=self.main_view_model.set_active_weight,
            set_openvino_usage_callback=self.main_view_model.set_openvino_usage,
            update_openvino_status_callback=self.main_view_model.update_openvino_status,
            setup_zones_callback=self.main_view_model._setup_zones_from_project,
            restore_detector_callback=self.main_view_model._restore_detector_settings,
            get_active_weight_name=lambda: self.main_view_model.active_weight_name,
            get_use_openvino=lambda: self.main_view_model.use_openvino,
        )

    def start_project_processing_workflow(self, *, skip_dialog: bool = False):
        """Start processing pending project videos.

        Sprint 24: Delegates to VideoProcessingOrchestrator.
        Sprint 27: Moved delegation to ProjectOrchestrator.

        Args:
            skip_dialog: If True, processes all eligible videos without user confirmation
        """
        return self.video_processing_orchestrator.start_project_processing_workflow(
            skip_dialog=skip_dialog
        )

    def process_pending_project_videos(
        self, eligible_videos: list[dict], *, analysis_profile: dict | None = None
    ) -> None:
        """Process pending project videos with analysis profile support.

        Sprint 24: Delegates to VideoProcessingOrchestrator.
        Sprint 27: Moved delegation to ProjectOrchestrator.

        Args:
            eligible_videos: List of video info dictionaries ready for processing
            analysis_profile: Optional analysis profile configuration
        """
        return self.video_processing_orchestrator.process_pending_project_videos(
            eligible_videos=eligible_videos,
            analysis_profile=analysis_profile,
        )

    # ========================================================================
    # Group C: Asset Management
    # ========================================================================

    def can_remove_project_asset(
        self, video_path: Path | str, asset: str
    ) -> tuple[bool, str | None]:
        """Validate whether a project asset can be safely removed."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            return self.project_manager.can_remove_asset(str(video_path), asset_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "controller.project_asset.can_remove_failed",
                asset=asset,
                video=video_path,
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
        """Remove a project asset (arena, ROIs, trajetória, sumário ou vídeo)."""
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        try:
            asset_type = cast(AssetType, asset)
            removed = self.project_manager.remove_asset(
                str(video_path),
                asset_type,
                delete_files=delete_source,
            )
            logger.info(
                "controller.project_asset.removal_result",
                asset=asset,
                video=video_path,
                removed=removed,
                delete_source=delete_source,
            )
            return removed
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "controller.project_asset.remove_failed",
                asset=asset,
                video=video_path,
                error=str(exc),
                exc_info=True,
            )
            return False

    def _register_project_outputs(
        self,
        *,
        video_path: str,
        results_dir: str,
        trajectory_path: str,
        summary_parquet: str,
        summary_excel: str,
        report_path: str,
    ) -> None:
        """Delegate to VideoProcessingService._register_project_outputs, then refresh views.

        Phase 3: Refactored to delegate to service layer.
        The refresh_project_views call remains here as it's a MainViewModel responsibility.
        """
        self.video_processing_service._register_project_outputs(
            video_path=video_path,
            results_dir=results_dir,
            trajectory_path=trajectory_path,
            summary_parquet=summary_parquet,
            summary_excel=summary_excel,
            report_path=report_path,
        )
        self.main_view_model.refresh_project_views(
            reason="processing_progress",
            append_summary=True,
        )

    # ========================================================================
    # Group D: Supporting Methods
    # ========================================================================

    def _setup_zones_from_project(self) -> None:
        """Set up zones from project data.

        Phase 2, Task P2-T2: Delegates to ProjectWorkflowAdapter.
        """
        self.project_workflow_adapter.setup_zones_from_project(
            setup_detector_zones_callback=self.main_view_model.setup_detector_zones,
        )

    @contextmanager
    def project_calibration_session(self):
        """Context manager for project-specific calibration mode.

        Enables project override mode and saves changes to project settings.
        Maintains override state on exit if project has overrides.

        Yields:
            None
        """
        previous_flag = self.main_view_model._using_project_overrides
        self.main_view_model._using_project_overrides = True
        try:
            yield
        finally:
            if self.has_project_override_settings():
                self.main_view_model._using_project_overrides = True
            else:
                self.main_view_model._using_project_overrides = previous_flag

    # ========================================================================
    # Group B: Model Override Management
    # ========================================================================

    def are_project_overrides_active(self) -> bool:
        """Check if project-specific model overrides are currently active.

        Returns:
            True if using project overrides, False if using global settings.
        """
        return bool(self.main_view_model._using_project_overrides)

    def has_project_override_settings(self) -> bool:
        """Check if project has any non-empty model override settings.

        Returns:
            True if project has model overrides, False otherwise.
        """
        if not getattr(self.project_manager, "project_path", None):
            return False
        overrides = self._ensure_project_overrides_record()
        return any(value not in (None, "", "inherit") for value in overrides.values())

    def _ensure_project_overrides_record(self) -> dict:
        project_data = self.main_view_model._get_project_data_dict()
        overrides = project_data.get("model_overrides")
        if not isinstance(overrides, dict):
            overrides = {"active_weight": None, "use_openvino": None}
            project_data["model_overrides"] = overrides
        return overrides

    def copy_global_model_settings_to_project(self) -> tuple[str | None, bool] | None:
        """Copy global model settings to current project as overrides.

        Returns:
            Tuple of (weight_name, use_openvino) if successful, None otherwise.
        """
        if not getattr(self.project_manager, "project_path", None):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de copiar configurações globais.",
                },
            )
            return None

        defaults = self.main_view_model.get_global_model_defaults()
        weight = defaults.get("active_weight") or (
            self.main_view_model.active_weight_name or None
        )
        use_openvino = bool(defaults.get("use_openvino", False))

        overrides = self.main_view_model._persist_project_model_settings(weight, use_openvino)

        message = "Configurações globais aplicadas ao projeto."
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": message})
        self.main_view_model.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]:
        """Resolve model settings considering project overrides and global defaults.

        Args:
            overrides: Optional override dictionary to merge with project overrides.

        Returns:
            Tuple of (resolved_weight, resolved_openvino).
        """
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        base_overrides = project_data.get("model_overrides") or {}
        if overrides is not None:
            merged_overrides = base_overrides.copy()
            merged_overrides.update(overrides)
        else:
            merged_overrides = base_overrides

        weight_override = merged_overrides.get("active_weight")
        if isinstance(weight_override, str):
            weight_override = weight_override.strip() or None

        openvino_override = merged_overrides.get("use_openvino")
        if isinstance(openvino_override, str):
            lowered = openvino_override.strip().lower()
            if lowered in {"", "inherit", "auto"}:
                openvino_override = None
            else:
                openvino_override = lowered in {"true", "1", "yes", "on"}

        resolved_weight = weight_override
        if not resolved_weight:
            resolved_weight = project_data.get("active_weight") or None
        if not resolved_weight:
            resolved_weight = self.main_view_model._global_model_defaults.get("active_weight")
        if not resolved_weight:
            default_weight, _ = self.main_view_model._safe_get_default_weight()
            resolved_weight = default_weight

        available_weights = set(self.main_view_model.get_all_weight_names())
        if resolved_weight and resolved_weight not in available_weights:
            logger.warning(
                "controller.project_overrides.weight_missing",
                weight=resolved_weight,
                available=list(available_weights),
            )
            fallback_weight = self.main_view_model._global_model_defaults.get("active_weight")
            if fallback_weight and fallback_weight in available_weights:
                resolved_weight = fallback_weight
            else:
                default_weight, _ = self.main_view_model._safe_get_default_weight()
                resolved_weight = default_weight if default_weight else None

        if openvino_override is None:
            if project_data.get("use_openvino") is not None:
                resolved_openvino = bool(project_data.get("use_openvino"))
            else:
                resolved_openvino = bool(
                    self.main_view_model._global_model_defaults.get("use_openvino", False)
                )
        else:
            resolved_openvino = bool(openvino_override)

        return resolved_weight, resolved_openvino

    def save_current_calibration_to_project(self) -> tuple[str | None, bool] | None:
        """Save current model settings as project-specific overrides.

        Returns:
            Tuple of (weight_name, use_openvino) if successful, None otherwise.
        """
        if not getattr(self.project_manager, "project_path", None):
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Projeto",
                    "message": "Abra um projeto antes de salvar overrides de calibração.",
                },
            )
            return None

        overrides = self.main_view_model._persist_project_model_settings(
            self.main_view_model.active_weight_name or None,
            bool(self.main_view_model.use_openvino),
        )

        # Garantir que o estado em memória reflita os overrides recém-salvos
        self.main_view_model.apply_project_model_overrides(overrides)

        message = "Overrides do projeto atualizados a partir desta calibração."
        self.ui_event_bus.publish_event(Events.UI_SET_STATUS, {"message": message})
        self.main_view_model.refresh_project_views(reason=message, append_summary=True)

        return overrides.get("active_weight"), bool(overrides.get("use_openvino"))

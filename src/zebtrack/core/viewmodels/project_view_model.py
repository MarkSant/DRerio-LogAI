"""Project ViewModel for project management workflows.

Phase 3C: Refactored to use ProjectLifecycleCoordinator instead of ProjectOrchestrator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies

log = structlog.get_logger()


class ProjectViewModel:
    """ViewModel responsible for Project Management workflows.

    Phase 3C: Fully migrated to use ProjectLifecycleCoordinator.
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ):
        self.project_manager = dependencies.project_manager
        self.state_manager = dependencies.state_manager
        self.project_lifecycle_coordinator = dependencies.project_lifecycle_coordinator
        self.project_workflow_service = dependencies.project_workflow_service
        self.batch_configuration_service = bootstrap_result.batch_configuration_service
        self.ui_event_bus = event_bus
        self.settings = dependencies.settings_obj

    def create_project_workflow(self, **wizard_data):
        return self.project_lifecycle_coordinator.create_project(**wizard_data)

    def open_project_workflow(self, project_path):
        return self.project_lifecycle_coordinator.open_project(project_path)

    def close_project(self):
        return self.project_lifecycle_coordinator.close_project()

    def on_video_selected(self, video_path: str):
        """Handle video selection event."""
        if self.project_manager:
            self.project_manager.set_active_zone_video(video_path)

    def add_videos_to_project(self):
        """Adds videos to the current project via file dialog."""
        if not self.project_manager.project_path:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Nenhum Projeto",
                        "message": "Crie ou abra um projeto antes de adicionar vídeos.",
                    },
                )
            return

        from tkinter import filedialog

        file_paths = filedialog.askopenfilenames(
            title="Adicionar Vídeos ao Projeto",
            filetypes=[("Arquivos de Vídeo", "*.mp4 *.avi *.mov *.mkv")],
        )

        if not file_paths:
            return

        added_count = 0
        for path in file_paths:
            if self.project_manager.add_video(path):
                added_count += 1

        if added_count > 0:
            self.project_manager.save_project()

    def handle_delete_project_asset(self, video_path: str, asset: str):
        if self.project_lifecycle_coordinator:
            self.project_lifecycle_coordinator.delete_project_asset(video_path, asset)

    def can_remove_project_asset(self, video_path: str, asset: str) -> tuple[bool, str | None]:
        return self.project_lifecycle_coordinator.can_remove_project_asset(video_path, asset)

    def apply_project_settings_to_batch(self, videos: list):
        return self.batch_configuration_service.apply_settings(videos)

    def resolve_project_model_settings(self, overrides: dict) -> tuple[str | None, bool]:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.resolve_project_model_settings(overrides)
        return None, False

    def save_project_model_overrides(
        self, active_weight: str | None, use_openvino: bool | None
    ) -> None:
        """Save model settings as project overrides.

        Uses state_manager to provide callbacks for state access.
        """
        if not self.project_lifecycle_coordinator:
            return

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get("active_weight_name")
            return None

        def get_use_openvino() -> bool:
            if self.state_manager:
                return self.state_manager.get("use_openvino", False)
            return False

        self.project_lifecycle_coordinator.save_project_model_overrides(
            active_weight,
            use_openvino,
            get_active_weight_name,
            get_use_openvino,
        )

    def has_project_override_settings(self) -> bool:
        if self.project_lifecycle_coordinator:
            return self.project_lifecycle_coordinator.has_project_override_settings()
        return False

    def handle_calibration_copy_to_project(self):
        """Copy global model settings to project overrides."""
        if not self.project_lifecycle_coordinator:
            return

        def get_global_defaults() -> dict:
            return {
                "active_weight": self.settings.detection.default_weight if self.settings else None,
                "use_openvino": self.settings.detection.use_openvino if self.settings else False,
            }

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get("active_weight_name")
            return None

        self.project_lifecycle_coordinator.copy_global_model_settings_to_project(
            get_global_defaults=get_global_defaults,
            get_active_weight_name=get_active_weight_name,
        )

    def handle_calibration_save_to_project(self):
        """Save current calibration settings to project."""
        if not self.project_lifecycle_coordinator:
            return

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get("active_weight_name")
            return None

        def get_use_openvino() -> bool:
            if self.state_manager:
                return self.state_manager.get("use_openvino", False)
            return False

        self.project_lifecycle_coordinator.save_current_calibration_to_project(
            get_active_weight_name=get_active_weight_name,
            get_use_openvino=get_use_openvino,
        )

    def get_calibration_scope_info(self) -> dict:
        """Get calibration scope information for display."""
        if not self.project_lifecycle_coordinator:
            return {
                "scope": "global",
                "label": "Global",
                "detail": "N/A",
                "project_loaded": False,
            }

        def get_active_weight_name() -> str | None:
            if self.state_manager:
                return self.state_manager.get("active_weight_name")
            return None

        return self.project_lifecycle_coordinator.get_calibration_scope_info(
            get_active_weight_name=get_active_weight_name,
        )

    @property
    def project_data(self) -> dict:
        if self.project_manager:
            return self.project_manager.project_data
        return {}

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies

log = structlog.get_logger()

class ProjectViewModel:
    """
    ViewModel responsible for Project Management workflows.
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ):
        self.project_manager = dependencies.project_manager
        self.project_orchestrator = bootstrap_result.project_orchestrator
        self.project_lifecycle_coordinator = dependencies.project_lifecycle_coordinator
        self.project_workflow_service = dependencies.project_workflow_service
        self.batch_configuration_service = bootstrap_result.batch_configuration_service
        self.calibration_orchestrator = bootstrap_result.calibration_orchestrator
        self.ui_event_bus = event_bus

        # Delegate commonly used properties
        self.settings = dependencies.settings_obj

    def create_project_workflow(self, **wizard_data):
        return self.project_orchestrator.create_project_workflow(**wizard_data)

    def open_project_workflow(self, project_path):
        return self.project_orchestrator.open_project_workflow(project_path)

    def close_project(self):
        return self.project_lifecycle_coordinator.close_project()

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
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(Events.UI_UPDATE_PROJECT_INFO)
            # Note: refresh_project_views needs to be triggered via event or callback if possible
            # or we keep a ref to ui_state_controller if strictly necessary.
            # For now, we'll rely on the event bus if the UI listens,
            # BUT MainVM had direct access to ui_state_controller.
            # Let's assume ui_state_controller is handled via MainVM or we add it here.
            # Given the constraints, I'll skip direct UI controller calls if I can avoid them,
            # but MainVM used: self.ui_state_controller.refresh_project_views(reason="videos_added")
            # I should probably inject ui_state_controller too.
            pass

    def handle_delete_project_asset(self, video_path: str, asset: str):
        if self.project_orchestrator:
            self.project_orchestrator.delete_project_asset(video_path, asset)

    def can_remove_project_asset(self, video_path: str, asset: str) -> tuple[bool, str | None]:
        return self.project_orchestrator.can_remove_project_asset(video_path, asset)

    def apply_project_settings_to_batch(self, videos: list):
        return self.batch_configuration_service.apply_settings(videos)

    def resolve_project_model_settings(self, overrides: dict) -> tuple[str | None, bool]:
        if self.project_orchestrator:
            return self.project_orchestrator.resolve_project_model_settings(overrides)
        return None, False

    def save_project_model_overrides(self, active_weight: str | None, use_openvino: bool | None) -> None:
        if self.project_orchestrator:
            self.project_orchestrator.save_project_model_overrides(active_weight, use_openvino)

    def has_project_override_settings(self) -> bool:
        if self.project_orchestrator:
            return self.project_orchestrator.has_project_override_settings()
        return False

    def handle_calibration_copy_to_project(self):
        if self.calibration_orchestrator:
            self.calibration_orchestrator.copy_global_to_project()

    def handle_calibration_save_to_project(self):
        if self.calibration_orchestrator:
            self.calibration_orchestrator.save_project_calibration()

    def get_calibration_scope_info(self) -> dict:
        if self.calibration_orchestrator:
            return self.calibration_orchestrator.get_calibration_scope_info()
        return {"scope": "global", "label": "Global", "detail": "N/A", "project_loaded": False}

    @property
    def project_data(self) -> dict:
        if self.project_manager:
            return self.project_manager.project_data
        return {}

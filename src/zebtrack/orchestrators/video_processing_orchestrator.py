"""Video Processing Orchestrator.

Sprint 24 - Extraction from MainViewModel.
Phase 3E Consolidation - Most methods moved to ProcessingCoordinator.
Only UI-heavy workflow orchestration remains here.

This orchestrator is a THIN WRAPPER that:
1. Handles complex UI dialogs (file selection, zone validation)
2. Delegates actual processing to ProcessingCoordinator
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from zebtrack.core.processing_worker import ProcessingWorker
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class VideoProcessingOrchestrator:
    """Thin UI orchestration layer for video processing workflows.

    Phase 3E Consolidation: All processing logic has been moved to ProcessingCoordinator.
    This class only handles UI-heavy workflows that require dialog interactions.

    Remaining responsibility:
    - start_project_processing_workflow: Requires file picker dialogs and zone validation UI
    """

    def __init__(self, main_view_model: MainViewModel):
        """Initialize with MainViewModel reference.

        Args:
            main_view_model: Reference to MainViewModel for UI delegation.
        """
        self.main_view_model = main_view_model
        self.view = getattr(main_view_model, "view", None)
        self.ui_event_bus = main_view_model.ui_event_bus
        self.cancel_event = main_view_model.cancel_event
        self.project_manager = main_view_model.project_manager
        self.processing_coordinator = main_view_model.processing_coordinator

    def register_event_handlers(self) -> None:
        """No-op: All event handlers are now in ProcessingCoordinator."""
        log.debug(
            "video_processing_orchestrator.register_handlers.noop",
            reason="Phase 3E - all handlers in ProcessingCoordinator",
        )

    def start_project_processing_workflow(self):
        """Adiciona vídeos com validação robusta de zonas.

        Extracted from MainViewModel.start_project_processing_workflow in Sprint 24.

        Sprint 11: Basic validations delegated to ProcessingCoordinator.
        Complex UI interactions (zone setup dialogs) remain in ViewModel.
        """
        log.info("workflow.project_processing.start")

        # Capture members in local variables for robust MyPy type narrowing
        coordinator = self.processing_coordinator
        view = self.view
        ui_event_bus = self.ui_event_bus
        dialog_coordinator = getattr(self.main_view_model, "dialog_coordinator", None)

        if not coordinator:
            log.error("workflow.project_processing.no_coordinator")
            return

        if not view:
            log.error("workflow.project_processing.no_view")
            return

        if not dialog_coordinator:
            log.error("workflow.project_processing.no_dialog_coordinator")
            return

        # Sprint 11: Delegate basic validations to ProcessingCoordinator
        # Sprint 13: Use consolidated error handling

        if not self.processing_coordinator:
            log.error("workflow.project_processing.no_coordinator")
            return

        validation_result = coordinator.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,  # Zone validation is complex with UI, handled below
            check_videos_exist=False,
        )

        if not dialog_coordinator.handle_validation_error(validation_result):
            return

        # Sprint 13: Validate zones with UI interaction
        if not dialog_coordinator.validate_zones_with_ui():
            return

        # 1. Ask user to select files or folders
        paths = view.ask_open_filenames(
            "Selecione Vídeos ou Pastas para Adicionar ao Projeto",
            [
                ("Todos os arquivos", "*.*"),
                ("Arquivos de vídeo", "*.mp4 *.avi *.mov"),
                ("Pastas", "*/"),
            ],
        )
        if not paths:
            return

        # 2. Scan the inputs
        scanned_videos = self.project_manager.scan_input_paths(paths)
        if not scanned_videos:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_WARNING,
                    {
                        "title": "Nenhum Vídeo Encontrado",
                        "message": "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados.",  # noqa: E501
                    },
                )
            return

        # 3. Sprint 13: Handle mixed data scenario
        videos_to_process = dialog_coordinator.handle_mixed_data_scenario(scanned_videos)
        if videos_to_process is None:
            return  # User cancelled or videos already added

        if not videos_to_process:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_INFO,
                    {
                        "title": "Processamento Concluído",
                        "message": "Nenhum novo vídeo para processar.",
                    },
                )
            return

        # 4. Add the batch to the project
        self.project_manager.add_video_batch(scanned_videos)

        # 5. Process the videos that need it using worker
        # Phase 3E: Delegate to ProcessingCoordinator for callbacks and context
        self.cancel_event.clear()

        callbacks = coordinator.create_processing_callbacks(videos_to_process)
        context = coordinator.create_processing_context(
            videos_to_process, str(self.project_manager.project_path or "")
        )

        self.main_view_model._cancel_feedback_displayed = False
        coordinator.processing_worker = ProcessingWorker(context, callbacks)
        coordinator.processing_thread = coordinator.processing_worker.start_in_thread()

        ui_state_controller = getattr(self.main_view_model, "ui_state_controller", None)
        if ui_state_controller:
            ui_state_controller.activate_analysis_view_mode()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        if ui_event_bus:
            ui_event_bus.publish_event(
                Events.UI_SHOW_INFO,
                {
                    "title": "Sucesso",
                    "message": f"{len(videos_to_process)} vídeo(s) foram processados e adicionados ao projeto.",  # noqa: E501
                },
            )

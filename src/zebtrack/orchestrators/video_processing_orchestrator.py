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
        self.view = main_view_model.view
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

        # Sprint 11: Delegate basic validations to ProcessingCoordinator
        # Sprint 13: Use consolidated error handling
        validation_result = self.processing_coordinator.validate_can_start_processing(
            check_project_loaded=True,
            check_zones=False,  # Zone validation is complex with UI, handled below
            check_videos_exist=False,
        )

        if not self.main_view_model.dialog_coordinator.handle_validation_error(validation_result):
            return

        # Sprint 13: Validate zones with UI interaction
        if not self.main_view_model.dialog_coordinator.validate_zones_with_ui():
            return

        # 1. Ask user to select files or folders
        paths = self.view.ask_open_filenames(
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
            self.ui_event_bus.publish_event(
                Events.UI_SHOW_WARNING,
                {
                    "title": "Nenhum Vídeo Encontrado",
                    "message": "Nenhum novo arquivo de vídeo foi encontrado nos caminhos selecionados.",  # noqa: E501
                },
            )
            return

        # 3. Sprint 13: Handle mixed data scenario
        videos_to_process = self.main_view_model.dialog_coordinator.handle_mixed_data_scenario(
            scanned_videos
        )
        if videos_to_process is None:
            return  # User cancelled or videos already added

        if not videos_to_process:
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

        callbacks = self.processing_coordinator.create_processing_callbacks(videos_to_process)
        context = self.processing_coordinator.create_processing_context(
            videos_to_process, self.project_manager.project_path
        )

        self.main_view_model._cancel_feedback_displayed = False
        self.processing_coordinator.processing_worker = ProcessingWorker(context, callbacks)
        self.processing_coordinator.processing_thread = (
            self.processing_coordinator.processing_worker.start_in_thread()
        )

        self.main_view_model.ui_state_controller.activate_analysis_view_mode()

        # 6. Update statuses in project file
        for video in videos_to_process:
            self.project_manager.update_video_status(video["path"], "complete")

        self.ui_event_bus.publish_event(
            Events.UI_SHOW_INFO,
            {
                "title": "Sucesso",
                "message": f"{len(videos_to_process)} vídeo(s) foram processados e adicionados ao projeto.",  # noqa: E501
            },
        )

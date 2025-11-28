from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies

log = structlog.get_logger()


class AnalysisControlViewModel:
    """
    ViewModel responsible for Analysis Control workflows (Start/Stop/Pause/Processing).
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ):
        self.video_processing_orchestrator = bootstrap_result.video_processing_orchestrator
        self.video_processing_service = dependencies.video_processing_service
        self.processing_coordinator = dependencies.processing_coordinator
        self.analysis_orchestrator = bootstrap_result.analysis_orchestrator
        self.analysis_coordinator = bootstrap_result.legacy_coordinators.get("analysis_coordinator")
        self.state_manager = dependencies.state_manager
        self.ui_state_controller = bootstrap_result.ui_state_controller
        self.project_manager = dependencies.project_manager
        self.recorder = bootstrap_result.recorder
        self.settings = dependencies.settings_obj

        self.ui_event_bus = event_bus

        # Flags and state
        self.processing_thread = None
        self.processing_worker = None
        self.cancel_event = bootstrap_result.cancel_event

    @property
    def is_processing(self) -> bool:
        return self.state_manager.get_processing_state().is_processing

    def start_project_processing_workflow(self):
        if self.video_processing_orchestrator:
            self.video_processing_orchestrator.start_project_processing_workflow()

    def start_single_video_workflow(self, video_path, config, detector_vm=None):
        """
        Starts the workflow for a single video.
        Requires access to detector configuration (via HardwareStatusViewModel or passed in).
        """
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        self.project_manager.set_active_zone_video(str(video_path))

        # Validation
        animal_method = config.get("animal_method", self.settings.model_selection.animal_method)
        animals_per_aquarium = config.get("animals_per_aquarium", 1)

        if animal_method == "det" and animals_per_aquarium > 1:
            if self.ui_event_bus:
                self.ui_event_bus.publish_event(
                    Events.UI_SHOW_ERROR,
                    {
                        "title": "Configuração Inválida",
                        "message": (
                            f"O modo de detecção (det) suporta apenas 1 animal por aquário.\n"
                            f"Você configurou {animals_per_aquarium} animais por aquário.\n"
                            "Para múltiplos animais, use o modo de segmentação (seg)."
                        ),
                    },
                )
            return

        # We need to ensure detector is set up.
        # If detector_vm is provided, use it.
        if detector_vm:
            use_openvino = config.get("use_openvino", self.settings.model_selection.use_openvino)
            detector_vm.use_openvino = use_openvino  # setter

            if not detector_vm.detector:
                temp_animal_method = config.get("animal_method")
                if not detector_vm.setup_detector(temp_animal_method):
                    return

        self.ui_event_bus.publish_event(
            "ui:setup_zone_definition_for_single_video",
            {"video_path": video_path, "config": config},
        )

    def start_single_video_processing(self, **kwargs):
        if self.video_processing_orchestrator:
            self.video_processing_orchestrator.start_single_video_processing(**kwargs)

    def cancel_current_analysis(self) -> None:
        worker_running = bool(self.processing_worker and self.processing_worker.is_running)
        thread_running = bool(self.processing_thread and self.processing_thread.is_alive())

        if not worker_running and not thread_running:
            return

        self.cancel_event.set()
        self.state_manager.update_processing_state(
            source="controller.cancel_current_analysis",
            cancel_requested=True,
        )

        if self.ui_event_bus:
            self.ui_event_bus.publish_event(
                Events.UI_SET_STATUS, {"message": "Cancelando análise em andamento..."}
            )

        if self.ui_state_controller:
            self.ui_state_controller._show_cancel_feedback()

        def _await_shutdown():
            if self.processing_worker and self.processing_worker.is_running:
                self.processing_worker.cancel()
            elif self.processing_thread and self.processing_thread.is_alive():
                self.processing_thread.join(timeout=5.0)

        threading.Thread(target=_await_shutdown, daemon=True).start()

    def save_manual_arena(self, polygon: list[tuple[int, int]]):
        return self.processing_coordinator.save_manual_arena(polygon)

    def set_main_arena_polygon(self, points: list) -> bool:
        if self.processing_coordinator:
            return self.processing_coordinator.set_main_arena_polygon(points)
        return False

    def add_roi_polygon(self, points: list, name: str, color: tuple) -> bool:
        if self.processing_coordinator:
            return self.processing_coordinator.add_roi_polygon(points, name, color)
        return False

    def auto_detect_zones(self, **kwargs):
        if self.processing_coordinator:
            self.processing_coordinator.auto_detect_zones(**kwargs)

    def generate_parquet_summaries(self, video_paths: list[str]):
        self.analysis_coordinator.generate_parquet_summaries(
            video_paths, processing_thread_ref=self.processing_thread
        )

    def _process_single_video(self, detector, **kwargs):
        return self.video_processing_service.process_single_video(
            detector=detector, recorder=self.recorder, **kwargs
        )

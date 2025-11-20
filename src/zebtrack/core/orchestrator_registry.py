"""Registry centralizado para acesso direto aos orchestrators.

Este registry foi criado na Fase 2 da refatoração do MainViewModel
(PLANO_REFATORACAO_MAINVIEWMODEL.md) para eliminar métodos facade.

Em vez de chamar métodos facade no MainViewModel que apenas delegam:
    controller.close_project()  # Facade no MainViewModel

Os callers podem acessar orchestrators diretamente via registry:
    controller.orchestrators.project.close_project()  # Direto
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.coordinators.hardware_coordinator import HardwareCoordinator
    from zebtrack.coordinators.processing_coordinator import ProcessingCoordinator
    from zebtrack.coordinators.project_lifecycle_coordinator import (
        ProjectLifecycleCoordinator,
    )
    from zebtrack.coordinators.session_coordinator import SessionCoordinator
    from zebtrack.orchestrators.ui_state_controller import UIStateController


class OrchestratorRegistry:
    """Registry centralizado para todos os orchestrators do MainViewModel.

    Fornece acesso direto aos orchestrators sem passar por facades
    no MainViewModel. Isso permite que callers (GUI, event handlers)
    interajam diretamente com orchestrators.

    Phase 3: Mapped to Super Coordinators.

    Attributes:
        recording: SessionCoordinator
        project: ProjectLifecycleCoordinator
        ui_state: UIStateController
        video_processing: ProcessingCoordinator
        analysis: ProcessingCoordinator
        processing_config: ProcessingCoordinator
        model_diagnostics: HardwareCoordinator
        zone_arena: ProcessingCoordinator
        calibration: ProjectLifecycleCoordinator
        live_camera: SessionCoordinator
    """

    def __init__(
        self,
        recording_session_orchestrator: "SessionCoordinator",
        project_orchestrator: "ProjectLifecycleCoordinator",
        ui_state_controller: "UIStateController",
        video_processing_orchestrator: "ProcessingCoordinator",
        analysis_orchestrator: "ProcessingCoordinator",
        processing_config_orchestrator: "ProcessingCoordinator",
        model_diagnostics_orchestrator: "HardwareCoordinator",
        zone_arena_orchestrator: "ProcessingCoordinator",
        calibration_orchestrator: "ProjectLifecycleCoordinator",
        live_camera_coordinator: "SessionCoordinator",
    ):
        """Initialize registry with all orchestrators.

        Args:
            recording_session_orchestrator: Mapped to SessionCoordinator
            project_orchestrator: Mapped to ProjectLifecycleCoordinator
            ui_state_controller: Controller para estado da UI
            video_processing_orchestrator: Mapped to ProcessingCoordinator
            analysis_orchestrator: Mapped to ProcessingCoordinator
            processing_config_orchestrator: Mapped to ProcessingCoordinator
            model_diagnostics_orchestrator: Mapped to HardwareCoordinator
            zone_arena_orchestrator: Mapped to ProcessingCoordinator
            calibration_orchestrator: Mapped to ProjectLifecycleCoordinator
            live_camera_coordinator: Mapped to SessionCoordinator
        """
        # Atribuir com nomes curtos e descritivos
        self.recording = recording_session_orchestrator
        self.project = project_orchestrator
        self.ui_state = ui_state_controller
        self.video_processing = video_processing_orchestrator
        self.analysis = analysis_orchestrator
        self.processing_config = processing_config_orchestrator
        self.model_diagnostics = model_diagnostics_orchestrator
        self.zone_arena = zone_arena_orchestrator
        self.calibration = calibration_orchestrator
        self.live_camera = live_camera_coordinator

    def get_all_orchestrators(self) -> dict[str, object]:
        """Retorna dict com todos os orchestrators registrados.

        Returns:
            Dict mapeando nome curto para instância do orchestrator
        """
        return {
            "recording": self.recording,
            "project": self.project,
            "ui_state": self.ui_state,
            "video_processing": self.video_processing,
            "analysis": self.analysis,
            "processing_config": self.processing_config,
            "model_diagnostics": self.model_diagnostics,
            "zone_arena": self.zone_arena,
            "calibration": self.calibration,
            "live_camera": self.live_camera,
        }

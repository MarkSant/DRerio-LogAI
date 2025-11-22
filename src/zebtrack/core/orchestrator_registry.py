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
    from zebtrack.coordinators.live_camera_coordinator import LiveCameraCoordinator
    from zebtrack.orchestrators.analysis_orchestrator import AnalysisOrchestrator
    from zebtrack.orchestrators.calibration_orchestrator import CalibrationOrchestrator
    from zebtrack.orchestrators.model_diagnostics_orchestrator import (
        ModelDiagnosticsOrchestrator,
    )
    from zebtrack.orchestrators.processing_config_orchestrator import (
        ProcessingConfigOrchestrator,
    )
    from zebtrack.orchestrators.project_orchestrator import ProjectOrchestrator
    from zebtrack.orchestrators.recording_session_orchestrator import (
        RecordingSessionOrchestrator,
    )
    from zebtrack.orchestrators.ui_state_controller import UIStateController
    from zebtrack.orchestrators.video_processing_orchestrator import (
        VideoProcessingOrchestrator,
    )
    from zebtrack.orchestrators.zone_arena_orchestrator import ZoneArenaOrchestrator


class OrchestratorRegistry:
    """Registry centralizado para todos os orchestrators do MainViewModel.

    Fornece acesso direto aos orchestrators sem passar por facades
    no MainViewModel. Isso permite que callers (GUI, event handlers)
    interajam diretamente com orchestrators.

    Attributes:
        recording: RecordingSessionOrchestrator (15 facades removidos)
        project: ProjectOrchestrator (17 facades removidos)
        ui_state: UIStateController (23 facades removidos)
        video_processing: VideoProcessingOrchestrator (7 facades removidos)
        analysis: AnalysisOrchestrator (3 facades removidos)
        processing_config: ProcessingConfigOrchestrator (7 facades removidos)
        model_diagnostics: ModelDiagnosticsOrchestrator (7 facades removidos)
        zone_arena: ZoneArenaOrchestrator (3 facades removidos)
        calibration: CalibrationOrchestrator (3 facades removidos)
        live_camera: LiveCameraCoordinator (1 facade removido)

    Example:
        # ANTES (facade no MainViewModel):
        controller.close_project()

        # DEPOIS (acesso direto):
        controller.orchestrators.project.close_project()
    """

    def __init__(
        self,
        recording_session_orchestrator: "RecordingSessionOrchestrator",
        project_orchestrator: "ProjectOrchestrator",
        ui_state_controller: "UIStateController",
        video_processing_orchestrator: "VideoProcessingOrchestrator",
        analysis_orchestrator: "AnalysisOrchestrator",
        processing_config_orchestrator: "ProcessingConfigOrchestrator",
        model_diagnostics_orchestrator: "ModelDiagnosticsOrchestrator",
        zone_arena_orchestrator: "ZoneArenaOrchestrator",
        calibration_orchestrator: "CalibrationOrchestrator",
        live_camera_coordinator: "LiveCameraCoordinator",
    ):
        """Initialize registry with all orchestrators.

        Args:
            recording_session_orchestrator: Orchestrator para sessões de gravação
            project_orchestrator: Orchestrator para workflows de projeto
            ui_state_controller: Controller para estado da UI
            video_processing_orchestrator: Orchestrator para processamento de vídeo
            analysis_orchestrator: Orchestrator para análise
            processing_config_orchestrator: Orchestrator para configuração de processamento
            model_diagnostics_orchestrator: Orchestrator para diagnósticos de modelo
            zone_arena_orchestrator: Orchestrator para gerenciamento de zonas
            calibration_orchestrator: Orchestrator para calibração
            live_camera_coordinator: Coordinator para câmera ao vivo
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

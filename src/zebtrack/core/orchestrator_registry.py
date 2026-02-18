"""Registry centralizado para acesso direto aos orchestrators.

Este registry foi criado na Fase 2 da refatoração do MainViewModel
(PLANO_REFATORACAO_MAINVIEWMODEL.md) para eliminar métodos facade.

Phase 3A/3B/3C/3D: Removed unused orchestrators:
- AnalysisOrchestrator → ProcessingCoordinator
- ProcessingConfigOrchestrator → ProcessingCoordinator
- ZoneArenaOrchestrator → ProcessingCoordinator
- CalibrationOrchestrator → ProjectLifecycleCoordinator
- ModelDiagnosticsOrchestrator → HardwareCoordinator
- ProjectOrchestrator → ProjectLifecycleCoordinator
- RecordingSessionOrchestrator → SessionCoordinator

Phase 3 Structural Unification:
- VideoProcessingOrchestrator removed (dead stub)
- UIStateController moved to coordinators.ui_state_coordinator
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebtrack.coordinators.ui_state_coordinator import UIStateController


class OrchestratorRegistry:
    """Registry centralizado para todos os orchestrators do MainViewModel.

    Fornece acesso direto aos orchestrators sem passar por facades
    no MainViewModel. Isso permite que callers (GUI, event handlers)
    interajam diretamente com orchestrators.

    Attributes:
        ui_state: UIStateController (23 facades removidos)

    Removed in Phase 3A/3B/3C/3D (superseded by Super Coordinators):
        - analysis: Superseded by ProcessingCoordinator
        - processing_config: Superseded by ProcessingCoordinator
        - zone_arena: Superseded by ProcessingCoordinator
        - calibration: Superseded by ProjectLifecycleCoordinator
        - model_diagnostics: Superseded by HardwareCoordinator
        - project: Superseded by ProjectLifecycleCoordinator
        - recording: Superseded by SessionCoordinator

    Removed in Phase 3 Structural Unification:
        - video_processing: Dead stub, logic in ProcessingCoordinator

    Removed in Phase 4.7:
        - live_camera: Superseded by LiveCameraSessionCoordinator
    """

    def __init__(
        self,
        ui_state_controller: "UIStateController",
    ):
        """Initialize registry with all orchestrators.

        Args:
            ui_state_controller: Controller para estado da UI
        """
        # Atribuir com nomes curtos e descritivos
        self.ui_state = ui_state_controller

    def get_all_orchestrators(self) -> dict[str, object]:
        """Retorna dict com todos os orchestrators registrados.

        Returns:
            Dict mapeando nome curto para instância do orchestrator
        """
        return {
            "ui_state": self.ui_state,
        }

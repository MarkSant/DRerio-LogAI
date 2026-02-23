"""Centralized registry for direct access to orchestrators.

Created in Phase 2 of the MainViewModel refactoring
(PLANO_REFATORACAO_MAINVIEWMODEL.md) to eliminate facade methods.

Phase 3A/3B/3C/3D: Removed unused orchestrators:
- AnalysisOrchestrator → ProcessingCoordinator
- ProcessingConfigOrchestrator → ProcessingCoordinator
- ZoneArenaOrchestrator → ProcessingCoordinator
- CalibrationOrchestrator → ProjectLifecycleCoordinator
- ModelDiagnosticsOrchestrator → ModelDiagnosticsCoordinator (Phase 4.9)
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
    """Centralized registry for all MainViewModel orchestrators.

    Provides direct access to orchestrators without going through facades
    in MainViewModel. This allows callers (GUI, event handlers)
    to interact directly with orchestrators.

    Attributes:
        ui_state: UIStateController (23 facades removidos)

    Removed in Phase 3A/3B/3C/3D (superseded by Super Coordinators):
        - analysis: Superseded by ProcessingCoordinator
        - processing_config: Superseded by ProcessingCoordinator
        - zone_arena: Superseded by ProcessingCoordinator
        - calibration: Superseded by ProjectLifecycleCoordinator
        - model_diagnostics: Superseded by ModelDiagnosticsCoordinator (Phase 4.9)
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
            ui_state_controller: Controller for UI state.
        """
        # Assign with short, descriptive names
        self.ui_state = ui_state_controller

    def get_all_orchestrators(self) -> dict[str, object]:
        """Return dict with all registered orchestrators.

        Returns:
            Dict mapping short name to orchestrator instance.
        """
        return {
            "ui_state": self.ui_state,
        }

"""Orchestrators package.

Sprint 24+ - Extracted orchestrators from MainViewModel to reduce complexity.

This package contains specialized orchestrators for different workflows:
- UIStateController: UI state synchronization (Sprint 28)
- VideoProcessingOrchestrator: Video processing workflows (Sprint 24)

Removed (Phase 3A/3B/3C/3D - no production calls or superseded):
- AnalysisOrchestrator: Superseded by ProcessingCoordinator
- ProcessingConfigOrchestrator: Superseded by ProcessingCoordinator
- ZoneArenaOrchestrator: Superseded by ProcessingCoordinator
- CalibrationOrchestrator: Superseded by ProjectLifecycleCoordinator
- ModelDiagnosticsOrchestrator: Superseded by HardwareCoordinator
- ProjectOrchestrator: Superseded by ProjectLifecycleCoordinator
- RecordingSessionOrchestrator: Superseded by SessionCoordinator
"""

from zebtrack.orchestrators.ui_state_controller import UIStateController
from zebtrack.orchestrators.video_processing_orchestrator import VideoProcessingOrchestrator

__all__ = [
    "UIStateController",
    "VideoProcessingOrchestrator",
]

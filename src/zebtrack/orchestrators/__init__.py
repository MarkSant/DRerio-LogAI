"""Orchestrators package.

Sprint 24+ - Extracted orchestrators from MainViewModel to reduce complexity.

This package contains specialized orchestrators for different workflows:
- AnalysisOrchestrator: Analysis workflows (Sprint 25)
- CalibrationOrchestrator: Calibration scope and context management (Sprint 32)
- ModelDiagnosticsOrchestrator: Model diagnostics workflows (Sprint 29)
- ProcessingConfigOrchestrator: Processing configuration management (Sprint 31)
- ProjectOrchestrator: Project lifecycle operations (Sprint 27)
- RecordingSessionOrchestrator: Recording session lifecycle (Sprint 26)
- UIStateController: UI state synchronization (Sprint 28)
- VideoProcessingOrchestrator: Video processing workflows (Sprint 24)
- ZoneArenaOrchestrator: Zone and arena management workflows (Sprint 30)
"""

from zebtrack.orchestrators.analysis_orchestrator import AnalysisOrchestrator
from zebtrack.orchestrators.calibration_orchestrator import CalibrationOrchestrator
from zebtrack.orchestrators.model_diagnostics_orchestrator import ModelDiagnosticsOrchestrator
from zebtrack.orchestrators.processing_config_orchestrator import ProcessingConfigOrchestrator
from zebtrack.orchestrators.project_orchestrator import ProjectOrchestrator
from zebtrack.orchestrators.recording_session_orchestrator import RecordingSessionOrchestrator
from zebtrack.orchestrators.ui_state_controller import UIStateController
from zebtrack.orchestrators.video_processing_orchestrator import VideoProcessingOrchestrator
from zebtrack.orchestrators.zone_arena_orchestrator import ZoneArenaOrchestrator

__all__ = [
    "AnalysisOrchestrator",
    "CalibrationOrchestrator",
    "ModelDiagnosticsOrchestrator",
    "ProcessingConfigOrchestrator",
    "ProjectOrchestrator",
    "RecordingSessionOrchestrator",
    "UIStateController",
    "VideoProcessingOrchestrator",
    "ZoneArenaOrchestrator",
]

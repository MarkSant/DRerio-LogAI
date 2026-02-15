"""Video Processing Orchestrator — DEPRECATED (Phase 0.3).

Originally Sprint 24 - Extraction from MainViewModel.
Phase 3E Consolidation - Most methods moved to ProcessingCoordinator.
Phase 0.3 - Remaining method (start_project_processing_workflow) migrated
             to ProcessingCoordinator. This class is now a stub.

This module is kept for backward compatibility with the orchestrators/ package.
It will be fully removed in Phase 3.2 (Unificação Estrutural).
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.core.main_view_model import MainViewModel

log = structlog.get_logger()


class VideoProcessingOrchestrator:
    """DEPRECATED: All logic migrated to ProcessingCoordinator (Phase 0.3).

    This class is a stub kept for backward compatibility.
    Use ProcessingCoordinator.start_project_processing_workflow() instead.

    Will be removed in Phase 3.2.
    """

    def __init__(self, main_view_model: MainViewModel | None = None):
        """Initialize stub orchestrator.

        Args:
            main_view_model: No longer used. Kept for signature compatibility.
        """
        log.debug(
            "video_processing_orchestrator.init.deprecated",
            reason="Phase 0.3 - fully migrated to ProcessingCoordinator",
        )

    def register_event_handlers(self) -> None:
        """No-op: All event handlers are in ProcessingCoordinator."""

    def start_project_processing_workflow(self) -> None:
        """DEPRECATED: Use ProcessingCoordinator.start_project_processing_workflow()."""
        warnings.warn(
            "VideoProcessingOrchestrator.start_project_processing_workflow() is deprecated. "
            "Use ProcessingCoordinator.start_project_processing_workflow() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        log.warning(
            "video_processing_orchestrator.start_project_processing_workflow.deprecated",
            reason="Phase 0.3 - migrated to ProcessingCoordinator",
        )

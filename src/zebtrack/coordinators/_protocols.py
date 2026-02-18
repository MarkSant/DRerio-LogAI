"""Protocol definitions for coordinator mixin host contracts.

Phase 6: Created to provide type-safe mixin usage without # type: ignore.
Each Protocol specifies the minimal interface a coordinator must satisfy
to compose with a given mixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd

    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video.processing_worker import ProcessingWorker
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus import EventBus


@runtime_checkable
class UnifiedReportHost(Protocol):
    """Protocol for coordinators that compose with UnifiedReportMixin.

    Defines the minimal set of attributes that the host coordinator
    must provide so the mixin can access them without type: ignore.
    """

    project_manager: ProjectManager
    settings: Settings
    event_bus: EventBus | None

    def _publish_event(self, event: Any, data: Any) -> None: ...
    def _is_batch_processing(self) -> bool: ...
    def _enrich_unified_report_metadata(
        self, df: pd.DataFrame, meta: dict[str, Any], entry: dict[str, Any]
    ) -> pd.DataFrame: ...


@runtime_checkable
class VideoSelectionHost(Protocol):
    """Protocol for coordinators that compose with VideoSelectionMixin.

    Defines the minimal set of attributes that the host coordinator
    must provide so the mixin can access them without type: ignore.
    """

    project_manager: ProjectManager
    state_manager: StateManager
    settings: Settings
    event_bus: EventBus | None
    view: Any
    processing_worker: ProcessingWorker | None
    processing_thread: Any
    _multi_aquarium_coordinator: Any

    def _publish_event(self, event: Any, data: Any) -> None: ...

"""Protocol definitions for coordinator mixin host contracts.

Phase 6: Created to provide type-safe mixin usage without # type: ignore.
Each Protocol specifies the minimal interface a coordinator must satisfy
to compose with a given mixin.  Mixin-internal helpers that are called
from self-typed public methods are also listed so mypy can resolve them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd

    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.video.processing_worker import ProcessingWorker
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2


@runtime_checkable
class UnifiedReportHost(Protocol):
    """Protocol for coordinators that compose with UnifiedReportMixin.

    Defines the minimal set of attributes that the host coordinator
    must provide so the mixin can access them without type: ignore.
    Mixin-provided helpers are included so self-typed methods can call them.
    """

    project_manager: ProjectManager
    settings: Settings
    event_bus: EventBusV2 | None

    def _publish_event(self, event: Any, data: Any) -> None: ...
    def _is_batch_processing(self) -> bool: ...
    def _enrich_unified_report_metadata(
        self, df: pd.DataFrame, meta: dict[str, Any], entry: dict[str, Any]
    ) -> pd.DataFrame: ...

    # Mixin-provided helpers (declared here for self-typed resolution)
    def _cleanup_unified_reports(self, unified_dir: Path) -> None: ...
    def _align_and_concatenate_unified_dfs(self, dfs: list) -> tuple: ...
    def _export_unified_reports(
        self,
        final_df: Any,
        unified_dir: Path,
        roi_colors_map: dict,
        schema_mismatch: bool,
        all_columns: list,
        *,
        report_scope: str = ...,
    ) -> None: ...
    def _write_unified_run_manifest(self, **kwargs: Any) -> None: ...


@runtime_checkable
class VideoSelectionHost(Protocol):
    """Protocol for coordinators that compose with VideoSelectionMixin.

    Defines the minimal set of attributes that the host coordinator
    must provide so the mixin can access them without type: ignore.
    Mixin-provided helpers are included so self-typed methods can call them.
    """

    project_manager: ProjectManager
    state_manager: StateManager
    settings: Settings
    event_bus: EventBusV2 | None
    view: Any
    processing_worker: ProcessingWorker | None
    processing_thread: Any
    _multi_aquarium_coordinator: Any

    def _publish_event(self, event: Any, data: Any) -> None: ...

    # Mixin-provided helper (declared here for self-typed resolution)
    def _is_live_session_currently_active(self, processing_state: Any) -> bool: ...

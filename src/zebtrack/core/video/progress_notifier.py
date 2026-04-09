"""Progress notifier mixin — progress callbacks, metadata, and UI notifications.

Extracted from VideoProcessingService (Phase 2.3 decomposition).
Methods:
    create_progress_callback, _make_progress_callback,
    _build_metadata_context, _schedule_analysis_metadata_update,
    _notify_task_status_start, _compose_analysis_view_metadata
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import (
    AnalysisMetadataPayload,
    AnalysisTaskStatusPayload,
    DetectionOverlayPayload,
    FrameDisplayPayload,
    ProcessingStatsWrapperPayload,
    StatusPayload,
)

log = structlog.get_logger()


class ProgressNotifierMixin:
    """Mixin providing progress callbacks and UI notification helpers."""

    # ── Attribute stubs (provided by the facade __init__) ──
    project_manager: ProjectManager
    state_manager: StateManager
    ui_coordinator: UIScheduler
    ui_event_bus: EventBusV2
    cancel_event: threading.Event
    settings: Settings

    def create_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
        processing_report_callback: Callable[[], Any] | None = None,
    ) -> Callable[[float, str, np.ndarray | None, dict | None, list | None], None]:
        """Create progress callback for video processing.

        Args:
            index: Current video index (1-based)
            total_videos: Total number of videos
            experiment_id: Experiment identifier
            processing_report_callback: Optional callback to get current processing report

        Returns:
            Callable that accepts progress stats dict
        """

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            overall_progress = f"Processando {index + 1}/{total_videos}: {experiment_id}"
            step_status = f"Etapa: {status_message}"

            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.SET_STATUS,
                    data=StatusPayload(message=f"{overall_progress} - {step_status}"),
                )
            )
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                    data=AnalysisTaskStatusPayload(
                        index=index,
                        total=total_videos,
                        experiment_id=experiment_id,
                        step=status_message,
                        progress=progress_fraction,
                    ),
                )
            )

            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                    data=AnalysisTaskStatusPayload(
                        index=index,
                        total=total_videos,
                        experiment_id=experiment_id,
                        step=status_message,
                        progress_fraction=float(progress_fraction),
                    ),
                )
            )

            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_PROCESSING_STATS,
                            data=ProcessingStatsWrapperPayload(stats=stats),
                        )
                    )

            processing_report = None
            if processing_report_callback:
                try:
                    processing_report = processing_report_callback()
                # except Exception justified: user-provided callback execution
                except Exception as exc:
                    log.warning("progress_callback.report_failed", error=str(exc))

            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_DETECTION_OVERLAY,
                            data=DetectionOverlayPayload(
                                detections=detections,
                                report=processing_report,
                            ),
                        )
                    )

            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_DISPLAY_FRAME,
                            data=FrameDisplayPayload(
                                frame=frame,
                                detections=detections or [],
                            ),
                        )
                    )

        return progress_callback

    def _make_progress_callback(
        self,
        *,
        index: int,
        total_videos: int,
        experiment_id: str,
        processing_report_callback: Callable[[], Any] | None = None,
    ) -> Callable[[float, str, np.ndarray | None, dict | None, list | None], None]:
        """Create progress callback for video processing (variant)."""

        def progress_callback(
            progress_fraction,
            status_message,
            frame=None,
            stats=None,
            detections=None,
        ):
            if self.cancel_event.is_set():
                return

            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                    data=AnalysisTaskStatusPayload(
                        index=index,
                        total=total_videos,
                        experiment_id=experiment_id,
                        step=status_message,
                    ),
                )
            )

            if stats:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_PROCESSING_STATS,
                            data=ProcessingStatsWrapperPayload(stats=stats),
                        )
                    )

            processing_report = None
            if processing_report_callback:
                try:
                    processing_report = processing_report_callback()
                # except Exception justified: user-provided callback execution
                except Exception as exc:
                    log.warning("progress_callback.report_failed", error=str(exc))

            if detections is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_UPDATE_DETECTION_OVERLAY,
                            data=DetectionOverlayPayload(
                                detections=detections,
                                report=processing_report,
                            ),
                        )
                    )

            if frame is not None:
                if self.ui_event_bus:
                    self.ui_event_bus.publish(
                        Event(
                            type=UIEvents.UI_DISPLAY_FRAME,
                            data=FrameDisplayPayload(
                                frame=frame,
                                detections=detections or [],
                            ),
                        )
                    )

        return progress_callback

    def _build_metadata_context(
        self,
        *,
        video_info: dict,
        single_video_config: dict | None,
        experiment_id: str,
        video_path: str,
    ) -> dict | None:
        """Build metadata context for processing."""
        if single_video_config:
            return None

        metadata_context = dict(video_info.get("metadata") or {})
        try:
            derived_metadata = self.project_manager.derive_processing_metadata(
                experiment_id,
                video_path,
            )
            metadata_context.update(derived_metadata)
        except Exception:  # pragma: no cover - defensive fallback
            log.debug(
                "controller.processing.metadata_derive_failed",
                experiment=experiment_id,
                video_path=video_path,
            )

        return metadata_context

    def _schedule_analysis_metadata_update(self, metadata: dict) -> None:
        """Schedule analysis metadata update via event bus on the main thread.

        This method is typically called from the worker thread.  Publishing
        directly on the worker would execute EventBus handlers (which set
        Tkinter StringVars) on a non-main thread — violating Tkinter's
        thread-safety contract.  We therefore defer the publish via
        ``ui_coordinator.schedule_after(0, ...)`` so the handler runs on the
        main thread.
        """
        if not self.ui_event_bus:
            return

        def _publish() -> None:
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_METADATA,
                    data=AnalysisMetadataPayload(metadata=metadata),
                )
            )

        if self.ui_coordinator:
            self.ui_coordinator.schedule_after(0, _publish)
        else:
            # Fallback: publish directly (may be on worker thread)
            _publish()

    def _notify_task_status_start(self, *, index: int, total: int, experiment_id: str) -> None:
        """Notify UI of task start via event bus."""
        if self.ui_event_bus:
            self.ui_event_bus.publish(
                Event(
                    type=UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                    data=AnalysisTaskStatusPayload(
                        index=index,
                        total=total,
                        experiment_id=experiment_id,
                    ),
                )
            )

    def _compose_analysis_view_metadata(
        self,
        *,
        experiment_id: str,
        video_path: str,
        metadata_context: dict | None,
        single_video_config: dict | None,
        analysis_profile: dict | None,
    ) -> dict:
        """Compose metadata for analysis view display."""
        combined: dict = {}

        entry = self.project_manager.find_video_entry(
            path=video_path,
            experiment_id=experiment_id,
        )
        if entry:
            combined.update(dict(entry.get("metadata") or {}))
            for key in ("group", "group_display_name", "day", "subject"):
                value = entry.get(key)
                if value not in (None, "") and key not in combined:
                    combined[key] = value

        if metadata_context:
            for key, value in metadata_context.items():
                if value in (None, ""):
                    continue
                combined[key] = value

        if single_video_config:
            mapping = {
                "group_display_name": "group_display_name",
                "group_label": "group_display_name",
                "group_name": "group_display_name",
                "group_id": "group",
                "group": "group",
                "day": "day",
                "day_id": "day",
                "subject": "subject",
                "subject_id": "subject",
                "animal": "subject",
                "cobaia": "subject",
            }
            for source_key, target_key in mapping.items():
                value = single_video_config.get(source_key)
                if value in (None, ""):
                    continue
                combined.setdefault(target_key, value)

        combined.setdefault("experiment_id", experiment_id)

        if analysis_profile and isinstance(analysis_profile, dict):
            profile_name = analysis_profile.get("name")
            if profile_name:
                combined["analysis_profile"] = profile_name
            track_ids = analysis_profile.get("track_ids")
            if track_ids:
                combined["analysis_profile_tracks"] = list(track_ids)

        return combined

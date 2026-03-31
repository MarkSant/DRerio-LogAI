"""Progress tracking coordinator for video processing lifecycle.

Phase 4: Extracted from ProcessingCoordinator.
Handles batch context management, processing lifecycle callbacks
(started, progress, error, fatal_error, complete), cancellation,
and progress callback factories.

Estimated size: ~480 lines (target <800).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from threading import Event

    from zebtrack.core.state_manager import StateManager
    from zebtrack.core.ui_scheduler import UIScheduler
    from zebtrack.settings import Settings
    from zebtrack.ui.event_bus_v2 import EventBusV2

log = structlog.get_logger()


class ProgressTrackingCoordinator(BaseCoordinator):
    """Coordinator for processing progress lifecycle and batch context.

    Responsibilities:
        - Batch context management (init, update, finalize, dialog suppression)
        - Processing lifecycle callbacks (started, progress, frame_processed,
          error, fatal_error, complete)
        - Progress callback factory (make_progress_callback)
        - Processing cancellation

    Phase 4: All methods moved from ProcessingCoordinator without logic changes.
    """

    def __init__(
        self,
        state_manager: StateManager,
        settings_obj: Settings,
        ui_coordinator: UIScheduler,
        cancel_event: Event,
        event_bus: EventBusV2 | None = None,
        # UI components (gradually being removed)
        view: Any = None,
        root: Any = None,
    ) -> None:
        super().__init__(state_manager, event_bus)
        self.settings = settings_obj
        self.ui_coordinator = ui_coordinator
        self.cancel_event = cancel_event
        self.view = view
        self.root = root

        # Batch processing context - suppresses per-video dialogs during batch
        self._batch_context: dict | None = None

        # Cross-coordinator references (set post-construction)
        self._video_processing_coordinator: Any = None

        log.info("progress_tracking_coordinator.initialized")

    # ========================================================================
    # Batch Context Management
    # ========================================================================

    def _is_batch_processing(self) -> bool:
        """Return True if we are inside a batch‑processing workflow."""
        return self._batch_context is not None

    def _init_batch_context(self, total_videos: int) -> None:
        """Initialize batch processing context to suppress per-video dialogs."""
        self._batch_context = {
            "total": total_videos,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "start_time": time.time(),
        }
        log.info("processing_coordinator.batch_context.initialized", total=total_videos)

    def _update_batch_context(
        self,
        *,
        completed: bool = False,
        failed: bool = False,
        skipped: bool = False,
        error_msg: str | None = None,
    ) -> None:
        """Update batch context counters."""
        if not self._batch_context:
            return

        if completed:
            self._batch_context["completed"] += 1
        if failed:
            self._batch_context["failed"] += 1
        if skipped:
            self._batch_context["skipped"] += 1
        if error_msg:
            self._batch_context.setdefault("errors", []).append(error_msg)

    def _finalize_batch_context(self) -> dict | None:
        """Finalize and return batch context, then clear it."""
        ctx = self._batch_context
        self._batch_context = None
        if ctx:
            ctx["elapsed"] = time.time() - ctx.get("start_time", time.time())
            log.info(
                "processing_coordinator.batch_context.finalized",
                completed=ctx["completed"],
                failed=ctx["failed"],
                skipped=ctx["skipped"],
                elapsed=f"{ctx['elapsed']:.1f}s",
            )
        return ctx

    def _set_dialog_suppression(self, suppress: bool) -> None:
        """Enable/disable dialog suppression for batch processing."""
        if suppress and not self._batch_context:
            self._init_batch_context(total_videos=0)
        elif not suppress and self._batch_context:
            self._finalize_batch_context()

    # ========================================================================
    # Processing Lifecycle Callbacks
    # ========================================================================

    def _on_processing_started(self, video_path: Path | str) -> None:
        """Handle processing start event (callback from ProcessingWorker)."""
        video_path_str = str(video_path)
        video_name = os.path.basename(video_path_str)
        log.info("processing_coordinator.processing_started", video=video_name)

        self.state_manager.update_processing_state(
            source="processing_coordinator._on_processing_started",
            is_processing=True,
            current_video=video_path,
        )

        if self.view and self.root:
            self.root.after(
                0,
                lambda: self._update_ui_for_processing_start(video_name, video_path_str),
            )

    def _update_ui_for_processing_start(
        self, video_name: str, video_path: Path | str | None = None
    ) -> None:
        """Update UI when processing starts (must run on main thread)."""
        if self.view:
            self.ui_coordinator.update_view(self.view, "start_analysis_view_mode")
            status_text = f"Processando: {video_name}"
            self.ui_coordinator.set_status(self.view, status_text)

            analysis_controller = getattr(self.view, "analysis_view_controller", None)
            if analysis_controller and hasattr(analysis_controller, "update_analysis_progress"):
                analysis_controller.update_analysis_progress(0.0, status_text=status_text)

            self._publish_analysis_metadata_for_video(video_path)

    def _publish_analysis_metadata_for_video(self, video_path: Path | str | None) -> None:
        """Publish analysis metadata after view mode initialization.

        This must run after `start_analysis_view_mode` so defaults are not kept.
        """
        if not video_path:
            return

        vpc = self._video_processing_coordinator
        project_manager = getattr(vpc, "project_manager", None) if vpc else None
        if project_manager is None or not hasattr(project_manager, "find_video_entry"):
            return

        entry = project_manager.find_video_entry(path=video_path)
        combined: dict = {}
        if entry:
            combined.update(dict(entry.get("metadata") or {}))
            for key in ("group", "group_display_name", "day", "subject"):
                value = entry.get(key)
                if value not in (None, "") and key not in combined:
                    combined[key] = value
        if combined:
            self._publish_event(
                UIEvents.UI_UPDATE_ANALYSIS_METADATA,
                payloads.AnalysisMetadataPayload(metadata=combined),
            )

    def _on_processing_progress(self, progress_data: dict) -> None:
        """Handle processing progress updates (callback from ProcessingWorker)."""
        total = progress_data.get("total_frames", 0)
        processed = progress_data.get("processed_frames", progress_data.get("current_frame", 0))
        detected = progress_data.get("detected_frames", 0)
        fraction = progress_data.get("fraction", -1)

        # Thread-safe state update
        self.state_manager.update_processing_state(
            source="controller.processing_progress",
            current_frame=processed,
            total_frames=total,
        )

        self._publish_event(
            UIEvents.UI_UPDATE_PROCESSING_STATS,
            payloads.ProcessingStatsWrapperPayload(stats=progress_data),
        )

        if total > 0 and self.view and self.root:
            # Use worker's pre-computed fraction (frame_num / total_frames);
            # fall back to processed/total only if fraction is unavailable.
            if fraction >= 0:
                progress_fraction = float(fraction)
            else:
                progress_fraction = processed / total

            self._publish_event(
                UIEvents.UI_UPDATE_ANALYSIS_TASK_STATUS,
                payloads.AnalysisTaskStatusPayload(
                    index=progress_data.get("idx"),
                    total=progress_data.get("total_videos"),
                    experiment_id=progress_data.get("exp_id"),
                    step=f"Processando quadros: {processed}/{total}",
                    progress_fraction=progress_fraction,
                ),
            )

            self.root.after(
                0,
                lambda: self._update_ui_progress(progress_fraction, processed, total, detected),
            )
        elif total == 0:
            log.debug(
                "progress_tracking.skipped_ui_update",
                total_frames=total,
                has_view=bool(self.view),
                has_root=bool(self.root),
                fraction=fraction,
                progress_keys=list(progress_data.keys()),
            )

    def _update_ui_progress(
        self, fraction: float, processed: int, total: int, detected: int
    ) -> None:
        """Update progress bar and status (must run on main thread).

        Args:
            fraction: Progress as 0.0-1.0 float (matches UIScheduler/AnalysisDisplay contract).
            processed: Number of detector-analyzed frames.
            total: Total video frames.
            detected: Number of frames with detections.
        """
        if self.view:
            pct = int(fraction * 100)
            status_text = (
                f"Processando: {processed}/{total} quadros ({pct}%) - {detected} detecções"
            )
            self.ui_coordinator.update_progress(self.view, fraction)
            self.ui_coordinator.set_status(self.view, status_text)

            analysis_controller = getattr(self.view, "analysis_view_controller", None)
            if analysis_controller and hasattr(analysis_controller, "update_analysis_progress"):
                analysis_controller.update_analysis_progress(fraction, status_text=status_text)

    def _on_frame_processed(self, frame_data: dict) -> None:
        """Handle per-frame processing updates for real-time overlay."""
        if not self.view or not self.root:
            return

        detections = frame_data.get("detections", [])
        frame = frame_data.get("frame")
        frame_number = frame_data.get("frame_number", 0)

        if frame is not None:
            self.root.after(
                0,
                lambda f=frame, d=detections, n=frame_number: self._update_frame_display(f, d, n),
            )

    def _update_frame_display(self, frame: Any, detections: list, frame_number: int) -> None:
        """Update frame display with detections overlay (must run on main thread)."""
        if not self.view:
            return
        try:
            canvas_manager = getattr(self.view, "canvas_manager", None)
            if canvas_manager and hasattr(canvas_manager, "update_video_frame"):
                canvas_manager.update_video_frame(frame, detections)
        except Exception:  # except Exception justified: Tkinter canvas + getattr fallible
            log.debug("progress_tracking.frame_display.suppressed", exc_info=True)

    def _on_processing_error(self, error_data: dict) -> None:
        """Handle non-fatal processing errors.

        These errors are recoverable and processing continues.
        """
        error_msg = error_data.get("error", "Erro desconhecido")
        video = error_data.get("video_path", "")
        log.warning(
            "processing_coordinator.processing_error",
            error=error_msg,
            video=os.path.basename(video) if video else "unknown",
        )

        if self._is_batch_processing():
            self._update_batch_context(failed=True, error_msg=error_msg)
        else:
            self._publish_event(
                UIEvents.UI_SHOW_WARNING,
                payloads.MessagePayload(title="Erro no Processamento", message=error_msg),
            )

    def _on_processing_fatal_error(self, error_data: dict) -> None:
        """Handle fatal processing errors that require stopping."""
        error_msg = error_data.get("error", "Erro fatal desconhecido")
        video = error_data.get("video_path", "")
        log.error(
            "processing_coordinator.processing_fatal_error",
            error=error_msg,
            video=os.path.basename(video) if video else "unknown",
        )

        # Reset processing state
        self.state_manager.update_processing_state(
            source="processing_coordinator._on_processing_fatal_error",
            is_processing=False,
            current_video=None,
        )

        if self.view and self.root:
            self.root.after(0, lambda: self._update_ui_for_processing_stop())

        self._publish_event(
            UIEvents.UI_SHOW_ERROR,
            payloads.MessagePayload(title="Erro Fatal", message=error_msg),
        )

    def _update_ui_for_processing_stop(self) -> None:
        """Reset UI after processing stops (must run on main thread)."""
        if self.view:
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)
            self.ui_coordinator.set_status(self.view, "Pronto.")

    def _finalize_progress_and_stop(self) -> None:
        """Set progress to 100%, brief pause, then reset UI (runs on main thread)."""
        if self.view:
            self.ui_coordinator.update_progress(self.view, 1.0)
            self.ui_coordinator.set_status(self.view, "Finalizando...")
        # Small delay so user sees 100% before the bar disappears
        if self.root:
            self.root.after(500, self._update_ui_for_processing_stop)

    def _on_processing_complete(self, result_data: dict) -> None:
        """Handle processing completion for a single video or batch.

        Args:
            result_data: Dict with keys like 'videos_to_process', 'success',
                         'output_dir', 'on_completed_callback'
        """
        videos_to_process = result_data.get("videos_to_process", [])
        video_path = ""
        if videos_to_process and len(videos_to_process) == 1:
            video_path = videos_to_process[0].get("path", "")
        success = result_data.get("success", True)
        output_dir = result_data.get("output_dir", "")

        log.info(
            "processing_coordinator.processing_complete",
            video=os.path.basename(video_path) if video_path else "batch",
            success=success,
            output_dir=output_dir,
        )

        # Reset processing state
        self.state_manager.update_processing_state(
            source="processing_coordinator._on_processing_complete",
            is_processing=False,
            current_video=None,
        )

        # Ensure progress bar shows 100% before hiding it
        if self.view and self.root:
            self.root.after(0, lambda: self._finalize_progress_and_stop())

        # Handle batch context
        if self._is_batch_processing():
            if success:
                self._update_batch_context(completed=True)
            else:
                self._update_batch_context(failed=True)

            # Check if batch is complete
            ctx = self._batch_context
            if ctx:
                total = ctx.get("total", 0)
                done = ctx["completed"] + ctx["failed"] + ctx["skipped"]
                if done >= total and total > 0:
                    final_ctx = self._finalize_batch_context()
                    self._show_batch_summary(final_ctx)
        else:
            # Single video completion
            if success:
                msg = "Processamento concluído com sucesso."
                if output_dir:
                    msg += f"\nResultados em: {output_dir}"
                self._publish_event(
                    UIEvents.UI_SHOW_INFO,
                    payloads.MessagePayload(
                        title="Concluído",
                        message=msg,
                    ),
                )

        self._publish_event(
            UIEvents.UI_REFRESH_PROJECT_VIEWS,
            payloads.ProjectViewsRefreshRequestedPayload(),
        )

        # Invoke caller-provided completion callback (e.g. wizard post-processing)
        on_completed_callback = result_data.get("on_completed_callback")
        if callable(on_completed_callback):
            try:
                on_completed_callback()
            except Exception:
                log.error(
                    "processing_coordinator.on_completed_callback_failed",
                    exc_info=True,
                )

    def _show_batch_summary(self, ctx: dict | None) -> None:
        """Show summary dialog after batch processing finishes."""
        if not ctx:
            return

        completed = ctx.get("completed", 0)
        failed = ctx.get("failed", 0)
        skipped = ctx.get("skipped", 0)
        elapsed = ctx.get("elapsed", 0)
        errors = ctx.get("errors", [])

        msg_parts = [f"Processamento em lote concluído em {elapsed:.0f}s."]
        msg_parts.append(f"\n✅ Concluídos: {completed}")
        if failed:
            msg_parts.append(f"❌ Falhas: {failed}")
        if skipped:
            msg_parts.append(f"⏭️ Ignorados: {skipped}")
        if errors:
            msg_parts.append("\nErros:")
            for err in errors[:5]:
                msg_parts.append(f"  • {err}")
            if len(errors) > 5:
                msg_parts.append(f"  ... (+{len(errors) - 5} erros)")

        event_name = UIEvents.UI_SHOW_WARNING if failed else UIEvents.UI_SHOW_INFO
        self._publish_event(
            event_name,
            payloads.MessagePayload(
                title="Processamento em Lote",
                message="\n".join(msg_parts),
            ),
        )

    # ========================================================================
    # Cancellation
    # ========================================================================

    def cancel_processing(self) -> None:
        """Request cancellation of the current processing operation."""
        log.info("processing_coordinator.cancel_requested")

        if self.cancel_event:
            self.cancel_event.set()

        vpc = self._video_processing_coordinator
        if vpc:
            worker = getattr(vpc, "processing_worker", None)
            if worker and hasattr(worker, "stop"):
                worker.stop()

        self.state_manager.update_processing_state(
            source="processing_coordinator.cancel_processing",
            cancel_requested=True,
        )

        if self.view and self.root:
            self.root.after(0, lambda: self._update_ui_for_cancel())

    def _update_ui_for_cancel(self) -> None:
        """Update UI for cancellation (must run on main thread)."""
        if self.view:
            self.ui_coordinator.set_status(self.view, "Cancelando processamento...")

    # ========================================================================
    # Progress Callback Factory
    # ========================================================================

    def make_progress_callback(
        self,
        total_frames: int,
        *,
        video_name: str = "",
        start_time: float | None = None,
    ) -> Any:
        """Create a progress callback function for a processing operation.

        Args:
            total_frames: Total number of frames to process
            video_name: Name of the video being processed
            start_time: Start time for ETA calculation

        Returns:
            A callable that accepts (processed_frames, detected_frames) and updates UI
        """
        _start_time = start_time or time.time()
        _video_name = video_name or "vídeo"

        def progress_callback(processed_frames: int, detected_frames: int = 0) -> None:
            if total_frames <= 0:
                return

            pct = int((processed_frames / total_frames) * 100)
            elapsed = time.time() - _start_time

            # Calculate ETA
            eta_str = ""
            if processed_frames > 0 and elapsed > 1.0:
                fps = processed_frames / elapsed
                remaining = total_frames - processed_frames
                if fps > 0:
                    eta_seconds = remaining / fps
                    if eta_seconds < 60:
                        eta_str = f" | ETA: {eta_seconds:.0f}s"
                    else:
                        eta_str = f" | ETA: {eta_seconds / 60:.1f}min"

            status_msg = (
                f"Processando {_video_name}: {processed_frames}/{total_frames} "
                f"({pct}%) - {detected_frames} detecções{eta_str}"
            )

            self._on_processing_progress(
                {
                    "total_frames": total_frames,
                    "processed_frames": processed_frames,
                    "detected_frames": detected_frames,
                    "start_time": _start_time,
                }
            )

            # Also update status text
            if self.view and self.root:
                self.root.after(
                    0,
                    lambda msg=status_msg: (
                        self.ui_coordinator.set_status(self.view, msg) if self.view else None
                    ),
                )

        return progress_callback

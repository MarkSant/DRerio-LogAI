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
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.coordinators.base_coordinator import BaseCoordinator
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

    def _on_processing_started(self, video_path: str) -> None:
        """Handle processing start event (callback from ProcessingWorker)."""
        video_name = os.path.basename(video_path)
        log.info("processing_coordinator.processing_started", video=video_name)

        self.state_manager.update_processing_state(
            source="processing_coordinator._on_processing_started",
            is_processing=True,
            current_video=video_path,
        )

        if self.view and self.root:
            self.root.after(0, lambda: self._update_ui_for_processing_start(video_name))

    def _update_ui_for_processing_start(self, video_name: str) -> None:
        """Update UI when processing starts (must run on main thread)."""
        if self.view:
            self.ui_coordinator.update_view(self.view, "start_analysis_view_mode")
            self.ui_coordinator.set_status(self.view, f"Processando: {video_name}")

    def _on_processing_progress(self, progress_data: dict) -> None:
        """Handle processing progress updates (callback from ProcessingWorker)."""
        total = progress_data.get("total_frames", 0)
        processed = progress_data.get("processed_frames", progress_data.get("current_frame", 0))
        detected = progress_data.get("detected_frames", 0)

        # Thread-safe state update
        self.state_manager.update_processing_state(
            source="controller.processing_progress",
            current_frame=processed,
            total_frames=total,
        )

        if total > 0 and self.view and self.root:
            pct = int((processed / total) * 100)
            self.root.after(
                0,
                lambda: self._update_ui_progress(pct, processed, total, detected),
            )

    def _update_ui_progress(self, pct: int, processed: int, total: int, detected: int) -> None:
        """Update progress bar and status (must run on main thread)."""
        if self.view:
            self.ui_coordinator.update_progress(self.view, pct)
            self.ui_coordinator.set_status(
                self.view,
                f"Processando: {processed}/{total} quadros ({pct}%) - {detected} detecções",
            )

    def _on_frame_processed(self, frame_data: dict) -> None:
        """Handle per-frame processing updates for real-time overlay."""
        if not self.view or not self.root:
            return

        detections = frame_data.get("detections", [])
        frame = frame_data.get("frame")
        frame_number = frame_data.get("frame_number", 0)

        if frame is not None and detections:
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
            if canvas_manager and hasattr(canvas_manager, "display_detection_frame"):
                canvas_manager.display_detection_frame(frame, detections, frame_number)
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
                {"title": "Erro no Processamento", "message": error_msg},
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
            {"title": "Erro Fatal", "message": error_msg},
        )

    def _update_ui_for_processing_stop(self) -> None:
        """Reset UI after processing stops (must run on main thread)."""
        if self.view:
            self.ui_coordinator.update_view(self.view, "stop_analysis_view_mode")
            self.ui_coordinator.hide_progress_bar(self.view)
            self.ui_coordinator.set_status(self.view, "Pronto.")

    def _on_processing_complete(self, result_data: dict) -> None:
        """Handle processing completion for a single video or batch.

        Args:
            result_data: Dict with keys like 'video_path', 'success', 'output_dir'
        """
        video_path = result_data.get("video_path", "")
        success = result_data.get("success", True)

        log.info(
            "processing_coordinator.processing_complete",
            video=os.path.basename(video_path) if video_path else "batch",
            success=success,
        )

        # Reset processing state
        self.state_manager.update_processing_state(
            source="processing_coordinator._on_processing_complete",
            is_processing=False,
            current_video=None,
        )

        if self.view and self.root:
            self.root.after(0, lambda: self._update_ui_for_processing_stop())

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
                self._publish_event(
                    UIEvents.UI_SHOW_INFO,
                    {"title": "Concluído", "message": "Processamento concluído com sucesso."},
                )

        self._publish_event(UIEvents.UI_REFRESH_PROJECT_VIEWS, {})

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
            {"title": "Processamento em Lote", "message": "\n".join(msg_parts)},
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

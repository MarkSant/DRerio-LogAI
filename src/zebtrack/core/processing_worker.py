"""
ProcessingWorker: Dedicated thread worker for video processing.

This module implements the background processing logic for video analysis,
decoupled from the main Controller. It uses Python's threading with callbacks
to communicate results back to the UI thread in a thread-safe manner.

Architecture:
    - ProcessingWorker: Encapsulates the processing loop
    - Signal-like callbacks: For status, progress, frames, errors, completion
    - Thread-safe: All UI updates scheduled via root.after()
    - Cancellable: Supports clean cancellation via threading.Event
"""

from __future__ import annotations

import gc
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger()


@dataclass
class ProcessingCallbacks:
    """
    Callbacks for communicating processing events back to the controller.

    All callbacks will be invoked from the worker thread, so implementations
    must use thread-safe mechanisms (e.g., root.after()) for UI updates.
    """

    on_started: Callable[[], None] | None = None
    """Called when processing begins."""

    on_progress: Callable[[float, str, dict | None], None] | None = None
    """
    Called periodically with progress updates.
    Args:
        progress_fraction: 0.0 to 1.0
        status_message: Human-readable status
        stats: Optional dict with processing statistics
    """

    on_frame_processed: Callable[[object, list | None, dict | None], None] | None = None
    """
    Called when a frame is processed and ready for display.
    Args:
        frame: The processed frame (numpy array)
        detections: List of detection tuples
        processing_info: Optional dict with processing mode/context
    """

    on_video_completed: Callable[[int, int, str, bool], None] | None = None
    """
    Called when a single video finishes processing.
    Args:
        index: Video index in batch
        total: Total videos in batch
        experiment_id: Experiment identifier
        success: Whether processing succeeded
    """

    on_error: Callable[[Exception, str], None] | None = None
    """
    Called when an error occurs.
    Args:
        error: The exception that occurred
        context: Human-readable context about what was being done
    """
    on_fatal_error: Callable[[Exception, str, dict], None] | None = None
    """
    Args:
        error: The exception
        context: Human-readable context
        recovery_info: Dict with {can_retry: bool, affected_videos: list, state_snapshot: dict}
    """

    on_completed: Callable[..., None] | None = None
    """
    Called when all processing completes or is cancelled.
    Args:
        was_cancelled: Whether processing was cancelled
        output_dir: Final output directory path
        summary: Optional dict with:
            - total_videos, successful, failed, skipped, failed_list
    """


@dataclass
class ProcessingContext:
    """
    All context needed for the worker to process videos independently.

    This allows the worker to operate without direct controller references.
    """

    videos_to_process: list[dict]
    """List of video info dicts with 'path' and optional 'metadata'."""

    output_base_dir: str
    """Base directory for saving results."""

    cancel_event: threading.Event
    """Event to signal cancellation request."""

    single_video_config: dict | None = None
    """Optional config for single-video mode (overrides project settings)."""

    analysis_interval_frames: int = 10
    """How often to run analysis (every N frames)."""

    display_interval_frames: int = 10
    """How often to display frames to UI (every N frames)."""

    # References to controller methods that worker needs to call
    # These should be thread-safe or schedule work on the UI thread
    process_single_video_func: Callable | None = None
    """Reference to controller._process_single_video method."""

    apply_project_settings_func: Callable | None = None
    """Reference to controller.apply_project_settings_to_batch method."""

    determine_intervals_func: Callable | None = None
    """Reference to controller._determine_processing_intervals method."""

    retry_strategy: str = "continue"  # "continue", "stop"
    failed_videos: list[dict] = field(default_factory=list)
    processed_count: int = 0


class ProcessingWorker:
    """
    Worker class that runs video processing in a dedicated thread.

    This class encapsulates all processing logic and communicates back to
    the controller/UI via callbacks. It's designed to be run in a separate
    thread to keep the UI responsive during long-running operations.

    Usage:
        # Create context and callbacks
        context = ProcessingContext(...)
        callbacks = ProcessingCallbacks(...)

        # Create worker and thread
        worker = ProcessingWorker(context, callbacks)
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()

        # Later, to cancel:
        context.cancel_event.set()
        thread.join(timeout=5.0)
    """

    def __init__(self, context: ProcessingContext, callbacks: ProcessingCallbacks):
        """
        Initialize the worker with processing context and callbacks.

        Args:
            context: All information needed for processing
            callbacks: Callbacks for communicating events
        """
        self.context = context
        self.callbacks = callbacks
        self._thread: threading.Thread | None = None

    def run(self):
        """
        Run main processing loop in worker thread.

        This method should be called as the target of a threading.Thread.
        """
        log.info(
            "worker.processing.start",
            count=len(self.context.videos_to_process),
            thread=threading.current_thread().name,
        )

        # Notify start
        if self.callbacks.on_started:
            self.callbacks.on_started()

        was_cancelled = False
        final_output_dir = self.context.output_base_dir

        try:
            # Determine processing intervals
            if self.context.determine_intervals_func:
                intervals = self.context.determine_intervals_func(self.context.single_video_config)
                if intervals:
                    (
                        self.context.analysis_interval_frames,
                        self.context.display_interval_frames,
                    ) = intervals

            # Apply project settings if not in single-video mode
            if not self.context.single_video_config and self.context.apply_project_settings_func:
                settings_success = self.context.apply_project_settings_func(
                    self.context.videos_to_process
                )
                if not settings_success:
                    log.warning("worker.processing.settings_partial_failure")

            # Process each video
            total_videos = max(len(self.context.videos_to_process), 1)

            for index, video_info in enumerate(self.context.videos_to_process):
                # Check for cancellation
                if self.context.cancel_event.is_set():
                    was_cancelled = True
                    log.info("worker.processing.cancelled_by_user")
                    break

                video_path = video_info.get("path")
                experiment_id = (
                    os.path.splitext(os.path.basename(video_path))[0]
                    if isinstance(video_path, str) and video_path
                    else f"video_{index + 1}"
                )

                log.info(
                    "worker.processing.video_start",
                    index=index,
                    total=total_videos,
                    experiment_id=experiment_id,
                )

                # Report progress
                overall_progress = (index + 0.5) / total_videos
                self._report_progress(
                    overall_progress,
                    f"Processando {index + 1}/{total_videos}: {experiment_id}",
                    None,
                )

                # Process the video using controller's method
                try:
                    processed = False
                    results_dir = None

                    if self.context.process_single_video_func:
                        processed, results_dir = self.context.process_single_video_func(
                            index=index,
                            total_videos=total_videos,
                            video_info=video_info,
                            single_video_config=self.context.single_video_config,
                            analysis_interval_frames=self.context.analysis_interval_frames,
                            display_interval_frames=self.context.display_interval_frames,
                            output_base_dir=self.context.output_base_dir,
                            experiment_id=experiment_id,
                            metadata_context=None,  # Will be built inside
                            analysis_profile=None,  # Will be resolved inside
                        )

                    if results_dir:
                        final_output_dir = results_dir

                    # Notify video completion
                    if self.callbacks.on_video_completed:
                        self.callbacks.on_video_completed(
                            index, total_videos, experiment_id, processed
                        )

                    if processed:
                        self.context.processed_count += 1
                    elif self.context.cancel_event.is_set():
                        # If not processed and cancel is set, it's a cancellation
                        was_cancelled = True
                        break

                except Exception as exc:
                    log.error(
                        "worker.processing.video_error",
                        experiment_id=experiment_id,
                        error=str(exc),
                        exc_info=True,
                    )

                    if self.callbacks.on_error:
                        self.callbacks.on_error(exc, f"Erro ao processar {experiment_id}")

                    # Record failure
                    self.context.failed_videos.append(
                        {
                            "index": index,
                            "path": video_path,
                            "error": str(exc),
                            "experiment_id": experiment_id,
                        }
                    )

                    # Decide next action based on strategy
                    if self.context.retry_strategy == "stop":
                        log.info("worker.processing.stop_on_error", experiment_id=experiment_id)
                        break
                    # "continue" → just go to next video
                finally:
                    self._cleanup_after_video_processing()

        except Exception as exc:
            log.error("worker.processing.fatal_error", error=str(exc), exc_info=True)
            recovery_info = {
                "can_retry": False,  # Fatal errors are not retryable by default
                "affected_videos": [v.get("path") for v in self.context.videos_to_process],
                "state_snapshot": {
                    "total_videos": len(self.context.videos_to_process),
                    "analysis_interval_frames": self.context.analysis_interval_frames,
                    "display_interval_frames": self.context.display_interval_frames,
                    "single_video_mode": bool(self.context.single_video_config),
                    "output_base_dir": self.context.output_base_dir,
                },
            }
            if self.callbacks.on_fatal_error:
                self.callbacks.on_fatal_error(exc, "Erro fatal no processamento", recovery_info)
            elif self.callbacks.on_error:
                self.callbacks.on_error(exc, "Erro fatal no processamento")
        finally:
            # Always notify completion
            log.info(
                "worker.processing.complete",
                was_cancelled=was_cancelled,
                output_dir=final_output_dir,
            )
            if self.callbacks.on_completed:
                total_videos = len(self.context.videos_to_process)
                failed_count = len(self.context.failed_videos)
                # successful_count is now just the count of videos that returned `processed=True`
                successful_count = self.context.processed_count
                # skipped_count is the remainder
                skipped_count = total_videos - successful_count - failed_count

                final_summary = {
                    "total_videos": total_videos,
                    "successful": successful_count,
                    "failed": failed_count,
                    "skipped": skipped_count,
                    "failed_list": self.context.failed_videos,
                }
                self.callbacks.on_completed(was_cancelled, final_output_dir, summary=final_summary)

    def _report_progress(self, fraction: float, message: str, stats: dict | None) -> None:
        """Report progress through callback."""
        if self.callbacks.on_progress:
            self.callbacks.on_progress(fraction, message, stats)

    def _cleanup_after_video_processing(self):
        """Force garbage collection after processing each video."""
        collected = gc.collect()
        log.debug("memory.gc.collected", objects=collected)

    def start_in_thread(self) -> threading.Thread:
        """
        Start the worker in a new daemon thread.

        Returns:
            The thread object (already started)
        """
        if self._thread and self._thread.is_alive():
            log.warning("worker.start.already_running")
            return self._thread

        self._thread = threading.Thread(target=self.run, daemon=True, name="ProcessingWorker")
        self._thread.start()
        log.info("worker.start.thread_created", thread_id=self._thread.ident)
        return self._thread

    def cancel(self, timeout: float = 5.0) -> bool:
        """
        Request cancellation and optionally wait for worker to finish.

        Args:
            timeout: How long to wait for thread to finish (seconds).
                    If None, don't wait. If 0, wait indefinitely.

        Returns:
            True if thread finished within timeout, False otherwise
        """
        self.context.cancel_event.set()
        log.info("worker.cancel.requested")

        if self._thread and self._thread.is_alive() and timeout is not None:
            self._thread.join(timeout=timeout if timeout > 0 else None)
            finished = not self._thread.is_alive()
            log.info("worker.cancel.join_complete", finished=finished)
            return finished

        return True

    @property
    def is_running(self) -> bool:
        """Check if the worker thread is currently running."""
        return self._thread is not None and self._thread.is_alive()

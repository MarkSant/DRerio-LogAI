"""Coordinator for background thread management.

Extracted from MainViewModel as part of Phase 1 of the refactoring
plan (PLANO_REFATORACAO_MAINVIEWMODEL.md).
Responsible for managing the lifecycle of background threads.
"""

import threading
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.io.camera import Camera

log = structlog.get_logger()


class ThreadCoordinator:
    """Coordinator for managing background threads.

    Centralizes thread lifecycle management,
    including join, cleanup, and resource release.

    Attributes:
        program_exit_event: Event to signal program exit.
        processing_thread: Video processing thread.
        capture_thread: Frame capture thread (optional).
        camera: Camera instance (optional).
    """

    def __init__(self) -> None:
        """Initialize the thread coordinator."""
        self.program_exit_event = threading.Event()
        self.processing_thread: threading.Thread | None = None
        self.capture_thread: threading.Thread | None = None
        self.camera: Camera | None = None
        self.log = structlog.get_logger()

    def register_processing_thread(self, thread: threading.Thread) -> None:
        """Register a processing thread.

        Args:
            thread: Processing thread to register.
        """
        self.processing_thread = thread
        self.log.debug("thread_coordinator.processing_thread_registered")

    def register_capture_thread(self, thread: threading.Thread) -> None:
        """Register a capture thread.

        Args:
            thread: Capture thread to register.
        """
        self.capture_thread = thread
        self.log.debug("thread_coordinator.capture_thread_registered")

    def register_camera(self, camera: "Camera") -> None:
        """Register a camera instance.

        Args:
            camera: Camera instance to register.
        """
        self.camera = camera
        self.log.debug("thread_coordinator.camera_registered")

    def signal_exit(self) -> None:
        """Signal all threads to stop."""
        self.log.info("thread_coordinator.signal_exit")
        self.program_exit_event.set()

    def join_threads(self) -> None:
        """Signal all threads to stop and wait for completion.

        Performs:
        - Sets the exit event
        - Waits for thread completion with timeout
        - Releases camera resources
        - Prevents deadlocks with a 2-second timeout per thread

        Note:
            If threads do not finish within the timeout, warning logs are emitted
            and the program continues shutdown (avoids indefinite blocking).
        """
        self.log.info("thread_coordinator.shutdown.start")
        self.program_exit_event.set()

        # Join background threads (video processing) with timeout
        if self.processing_thread is not None and self.processing_thread.is_alive():
            self.log.info("thread_coordinator.join_processing_thread")
            self.processing_thread.join(timeout=2.0)
            if self.processing_thread.is_alive():
                self.log.warning(
                    "thread_coordinator.processing_thread.timeout",
                    message="Processing thread did not exit within 2 seconds",
                )
            self.processing_thread = None

        if self.capture_thread is not None and self.capture_thread.is_alive():
            self.log.info("thread_coordinator.join_capture_thread")
            self.capture_thread.join(timeout=2.0)
            if self.capture_thread.is_alive():
                self.log.warning(
                    "thread_coordinator.capture_thread.timeout",
                    message="Capture thread did not exit within 2 seconds",
                )
            self.capture_thread = None

        # Release camera resources
        self._release_camera()

        self.log.info("thread_coordinator.shutdown.complete")

    def _release_camera(self) -> None:
        """Release camera resources."""
        if self.camera:
            self.log.info("thread_coordinator.release_camera")
            try:
                self.camera.release()
            # except Exception justified: thread cleanup boundary
            except Exception as e:
                self.log.warning(
                    "thread_coordinator.camera_release_error",
                    error=str(e),
                )
            finally:
                self.camera = None

    def cleanup(self) -> None:
        """Clean up all resources and threads.

        Convenience method that calls join_threads().
        """
        self.join_threads()

    def is_processing_active(self) -> bool:
        """Check if the processing thread is active.

        Returns:
            True if the processing thread is alive, False otherwise.
        """
        return self.processing_thread is not None and self.processing_thread.is_alive()

    def is_capture_active(self) -> bool:
        """Check if the capture thread is active.

        Returns:
            True if the capture thread is alive, False otherwise.
        """
        return self.capture_thread is not None and self.capture_thread.is_alive()

    def get_active_thread_count(self) -> int:
        """Return the number of active threads.

        Returns:
            Number of active threads (processing + capture).
        """
        count = 0
        if self.is_processing_active():
            count += 1
        if self.is_capture_active():
            count += 1
        return count

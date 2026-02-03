import threading
import time
from collections import deque
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal

import cv2
import numpy as np
import structlog

from zebtrack.io.frame_source import FrameSource

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class Camera(FrameSource):
    """
    Camera resource manager with automatic cleanup support.

    Supports context manager protocol for automatic resource cleanup.

    Example:
        with Camera(settings_obj=settings) as camera:
            ret, frame = camera.get_frame()
            # Process frame...
        # Camera automatically released on exit
    """

    def __init__(self, settings_obj: "Settings | None" = None):
        """Initialize Camera with settings dependency injection.

        Args:
            settings_obj: Settings instance (injected, optional for backward compatibility).
        """
        self.settings = settings_obj
        if self.settings is None:
            raise RuntimeError(
                "Camera: Settings not injected. "
                "Camera requires settings_obj parameter in constructor. "
                "Use: Camera(settings_obj=load_settings()) or "
                "Camera(settings_obj=create_mock_settings())"
            )

        self._camera_index = self.settings.camera.index

        log.info(
            "camera.initializing",
            camera_index=self._camera_index,
            desired_width=self.settings.camera.desired_width,
            desired_height=self.settings.camera.desired_height,
        )

        # Use DirectShow backend on Windows for better reliability and consistency with wizard
        import sys

        if sys.platform == "win32":
            self.cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self._camera_index)

        if not self.cap.isOpened():
            raise OSError(f"Cannot open camera at index {self._camera_index}")

        self._desired_width = self.settings.camera.desired_width
        self._desired_height = self.settings.camera.desired_height
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)

        self._lock = threading.Lock()

        # Protect initial reads with the lock
        with self._lock:
            self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS) or self.settings.video_processing.fps

        log.info(
            "camera.initialized",
            index=self._camera_index,
            width=self.actual_width,
            height=self.actual_height,
            fps=self.actual_fps,
        )

        # Frame buffer for lag management - keep 2 most recent frames
        self._frame_buffer: deque[np.ndarray] = deque(maxlen=2)
        self._frame_timestamps: deque[float] = deque(maxlen=2)
        self._frame_available = False  # Track if any frame has been captured
        self._stopped = threading.Event()
        self._shutdown_requested = threading.Event()  # v2.2: Atomic shutdown signal
        self._reconnect_state_ready = threading.Event()
        self._reconnect_state_ready.set()

        # Reconnect tracking attributes
        self._reconnect_attempts_raw = 0
        self._reconnect_attempts_public = 0
        self._max_reconnect_attempts = self.settings.camera.max_reconnect_attempts
        self._reconnect_timeout_seconds = self.settings.camera.reconnect_timeout_seconds
        retry_delay = getattr(self.settings.camera, "reconnect_retry_seconds", 0.05)
        try:
            retry_delay = float(retry_delay)
        except (TypeError, ValueError):
            retry_delay = 0.05
        self._reconnect_retry_delay = max(0.01, retry_delay)
        self._first_failure_time: float | None = None
        self._consecutive_failures = 0

        # Start the thread as the final step
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()

    @property
    def _reconnect_attempts(self) -> int:
        """Attempts exposed to tests (public-facing metric)."""
        return int(self._reconnect_attempts_public)

    @_reconnect_attempts.setter
    def _reconnect_attempts(self, value: int) -> None:
        self._reconnect_attempts_raw = int(value)
        self._reconnect_attempts_public = int(value)

    def _reader_thread(self):
        """Background loop that captures frames and manages reconnect attempts.

        v2.2: Only this thread calls cap.release() (single ownership pattern).
        Checks _shutdown_requested at each iteration for atomic shutdown.
        """
        try:
            while not self._stopped.is_set():
                # v2.2: Check shutdown signal at beginning of each iteration
                if self._shutdown_requested.is_set():
                    break

                if not self.cap.isOpened():
                    if not self._attempt_reconnect():
                        break
                    continue

                self._reset_reconnect_state()

                if not self._capture_frame():
                    continue
        finally:
            # v2.2: ONLY _reader_thread calls cap.release() (prevents deadlock)
            try:
                if self.cap.isOpened():
                    self.cap.release()
                    log.info("camera.released_by_reader_thread")
            except Exception as e:
                log.error("camera.reader_thread.release_failed", error=str(e))

        log.info("camera.reader_thread.stopped")

    def _attempt_reconnect(self) -> bool:
        """Try to reconnect the camera. Returns False when the thread should exit."""
        if self._first_failure_time is None:
            self._first_failure_time = time.time()
            self._reconnect_attempts_public = self._reconnect_attempts_raw
            self._reconnect_state_ready.clear()

        if self._should_abort_reconnect():
            return False

        self._reconnect_attempts_raw += 1
        self._reconnect_attempts_public = self._reconnect_attempts_raw
        elapsed = time.time() - self._first_failure_time
        log.warning(
            "camera.reconnect.attempt",
            attempt=self._reconnect_attempts_raw,
            elapsed_seconds=elapsed,
        )

        self.cap.open(self._camera_index)
        # Public counter resets immediately so observers know a reconnect was attempted
        self._reconnect_attempts_public = 0

        # Allow shutdown requests to interrupt reconnect waits immediately
        if self._stopped.wait(timeout=self._reconnect_retry_delay):
            self._reconnect_state_ready.set()
            return False

        if self._should_abort_reconnect():
            return False

        return True

    def _should_abort_reconnect(self) -> bool:
        """Check max attempts and timeout constraints for reconnects."""
        if (
            self._max_reconnect_attempts > 0
            and self._reconnect_attempts_raw >= self._max_reconnect_attempts
        ):
            log.error(
                "camera.reconnect.max_attempts",
                attempts=self._reconnect_attempts_raw,
                max_attempts=self._max_reconnect_attempts,
            )
            self._handle_reconnect_abort()
            return True

        if self._first_failure_time is not None:
            elapsed = time.time() - self._first_failure_time
        else:
            elapsed = 0

        if self._reconnect_timeout_seconds > 0 and elapsed > self._reconnect_timeout_seconds:
            log.error(
                "camera.reconnect.timeout",
                elapsed_seconds=elapsed,
                max_seconds=self._reconnect_timeout_seconds,
            )
            self._handle_reconnect_abort()
            return True

        return False

    def _handle_reconnect_abort(self) -> None:
        """Cleanup buffers when reconnect attempts should stop."""
        with self._lock:
            self._frame_buffer.clear()
            self._frame_timestamps.clear()
            self._frame_available = False
        try:
            if self.cap.isOpened():
                self.cap.release()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("camera.reconnect.force_release_failed", error=str(exc))
        self._stopped.set()
        self._reconnect_state_ready.set()

    def _reset_reconnect_state(self) -> None:
        """Reset counters and reapply settings once the camera comes back online."""
        if self._first_failure_time is None:
            return

        downtime = time.time() - self._first_failure_time
        total_attempts = self._reconnect_attempts_raw
        log.info(
            "camera.reconnect.recovered",
            total_attempts=total_attempts,
            total_downtime_seconds=downtime,
        )

        # Re-apply desired settings after reconnect
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)

        with self._lock:
            self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            default_fps = self.settings.video_processing.fps if self.settings else 30.0
            self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS) or default_fps

        log.info(
            "camera.reconnected.dimensions_updated",
            width=self.actual_width,
            height=self.actual_height,
            fps=self.actual_fps,
        )

        self._reconnect_attempts_raw = 0
        self._reconnect_attempts_public = 0
        self._first_failure_time = None
        self._consecutive_failures = 0
        self._reconnect_state_ready.set()

    def _capture_frame(self) -> bool:
        """Capture a frame and update buffers. Returns False when no frame captured."""
        ret, frame = self.cap.read()

        if not ret:
            self._consecutive_failures += 1
            log.warning(
                "camera.frame_read.failed",
                consecutive_failures=self._consecutive_failures,
            )

            # Use a dynamic sleep to prevent CPU spinning
            time.sleep(0.1)

            # If we exceed the threshold, consider the camera disconnected
            if self._consecutive_failures >= 5:
                log.error("camera.disconnected", failures=self._consecutive_failures)
                self.cap.release()
                with self._lock:
                    self._frame_buffer.clear()
                    self._frame_timestamps.clear()
                    self._frame_available = False
            return False

        # Reset failure counters on success
        self._consecutive_failures = 0
        self._reconnect_attempts_raw = 0
        self._reconnect_attempts_public = 0

        now = time.time()
        max_lag_ms = 100.0
        if self.settings:
            candidate = getattr(self.settings.camera, "max_frame_lag_ms", None)
            if isinstance(candidate, int | float):
                max_lag_ms = float(candidate)
        with self._lock:
            if self._frame_timestamps:
                lag_ms = (now - self._frame_timestamps[-1]) * 1000
                if lag_ms > max_lag_ms:
                    log.warning(
                        "camera.lag.threshold_exceeded",
                        lag_ms=lag_ms,
                        threshold_ms=max_lag_ms,
                    )
            self._frame_buffer.append(frame)
            self._frame_timestamps.append(now)
            self._frame_available = True

        return True

    def get_frame(self) -> tuple[bool, np.ndarray | None]:
        """
        Returns the most recent frame read by the background thread.

        Also monitors frame lag and logs warnings if lag exceeds threshold.
        """
        with self._lock:
            if not self._frame_available or not self._frame_buffer:
                return (False, None)

            # Get most recent frame
            frame = self._frame_buffer[-1].copy()
            frame_time = self._frame_timestamps[-1]

            # Calculate lag in milliseconds
            lag_ms = (time.time() - frame_time) * 1000

            # Log warning if lag exceeds threshold
            max_lag_ms = self.settings.camera.max_frame_lag_ms if self.settings else 100.0
            if lag_ms > max_lag_ms:
                log.warning(
                    "camera.lag.threshold_exceeded",
                    lag_ms=lag_ms,
                    threshold_ms=max_lag_ms,
                )

            return (True, frame)

    def release(self) -> None:
        """
        Signals the reader thread to stop and releases the camera resource.

        Task 1.6: Robust thread termination with timeout and forced cleanup.
        """
        log.info("camera.release.started")
        self._stopped.set()
        self._reconnect_state_ready.set()

        # Wait for thread to finish with timeout
        self._thread.join(timeout=2)

        # Task 1.6: Check if thread actually terminated
        if self._thread.is_alive():
            log.error(
                "camera.release.thread_timeout",
                message="Thread did not terminate after 2s, forcing camera close",
            )
            # Force close the capture to unblock thread stuck in read()
            try:
                if self.cap.isOpened():
                    self.cap.release()
            except Exception as e:
                log.error("camera.release.force_close_failed", error=str(e))

            # Give thread more time to finish after forced close
            self._thread.join(timeout=1)

            if self._thread.is_alive():
                log.critical(
                    "camera.release.thread_zombie",
                    message="Thread still alive after forced close - potential resource leak",
                )
        else:
            # Thread terminated normally, safe to release capture if not already done
            try:
                if self.cap.isOpened():
                    self.cap.release()
                    log.info("camera.released")
            except Exception as e:
                log.error("camera.release.normal_close_failed", error=str(e))

    def __enter__(self) -> "Camera":
        """Enter context manager - camera is already initialized."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        """
        Exit context manager - cleanup camera resources.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            self.release()
        except Exception as e:
            log.warning("camera.cleanup.failed", error=str(e))
        return False  # Don't suppress exceptions

    def is_opened(self) -> bool:
        """
        Check if the camera is currently opened.

        Returns:
            True if camera is opened, False otherwise.
        """
        with self._lock:
            return self.cap.isOpened()

    def get_properties(self) -> dict[str, Any]:
        """
        Returns the actual properties of the camera feed, guaranteed to be thread-safe.
        """
        wait_timeout = (
            self._reconnect_timeout_seconds if self._reconnect_timeout_seconds > 0 else 2.0
        )
        self._reconnect_state_ready.wait(timeout=wait_timeout)

        with self._lock:
            return {
                "width": self.actual_width,
                "height": self.actual_height,
                "fps": self.actual_fps,
            }


if __name__ == "__main__":
    # Example usage for testing the camera module
    camera = None
    try:
        camera = Camera()
        print("Camera properties:", camera.get_properties())

        time.sleep(1)

        while True:
            ret, frame = camera.get_frame()
            if not ret:
                print("Failed to grab frame, waiting...")
                time.sleep(0.5)
                continue

            if frame is not None:
                cv2.imshow("Camera Test", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except OSError as e:
        print(e)
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        if camera:
            camera.release()
        cv2.destroyAllWindows()
        print("Test finished.")

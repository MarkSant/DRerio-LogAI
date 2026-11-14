import threading
import time
from collections import deque
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import cv2
import numpy as np
import structlog

from zebtrack.io.frame_source import FrameSource

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class CapturedFrame(NamedTuple):
    """One sensor frame as :meth:`Camera.read_next_frame` hands it out."""

    frame: np.ndarray
    seq: int  # 1-based count of successful reads of this Camera
    t_perf: float  # time.perf_counter() when cap.read returned it
    t_wall: float  # time.time() of the same instant


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
        # Every successful ``cap.read`` gets a sequence number and the instant it
        # returned (#637). ``get_frame()`` hands out the newest frame WITHOUT
        # consuming it, so a consumer polling it faster than the sensor turned
        # one sensor frame into two pipeline frames, stamped at the POLL. The
        # live capture thread uses ``read_next_frame()`` instead: one sensor
        # frame, at most once, with its real read instant.
        self._frame_seq = 0
        self._last_read_perf = 0.0
        self._last_read_wall = 0.0
        self._read_perfs: deque[float] = deque(maxlen=120)
        self._new_frame = threading.Condition(self._lock)
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
        v2.3: Added GC-safety guards so daemon threads don't crash during
        interpreter shutdown or when test Mock objects are garbage-collected.
        """
        try:
            while not self._stopped.is_set():
                # v2.2: Check shutdown signal at beginning of each iteration
                if self._shutdown_requested.is_set():
                    break

                try:
                    if not self.cap.isOpened():
                        if not self._attempt_reconnect():
                            break
                        continue

                    self._reset_reconnect_state()

                    if not self._capture_frame():
                        continue
                except (AttributeError, TypeError, RuntimeError, OSError):
                    # v2.3: During interpreter shutdown or GC, self.cap may
                    # become a garbage-collected Mock or None, raising
                    # AttributeError/TypeError. Exit the loop gracefully.
                    break
        # except Exception justified: reader thread catch-all — cv2 GC/shutdown race conditions
        except Exception:
            # v2.3: Catch-all for any shutdown/GC race conditions
            log.debug("camera.reader_thread.shutdown_race", exc_info=True)
        finally:
            # v2.2: ONLY _reader_thread calls cap.release() (prevents deadlock)
            try:
                if hasattr(self, "cap") and self.cap is not None and self.cap.isOpened():
                    self.cap.release()
                    log.info("camera.released_by_reader_thread")
            # except Exception justified: cap.release() during shutdown — cv2 errors unpredictable
            except Exception:
                # v2.3: Log errors during cleanup (GC/shutdown)
                log.debug("camera.cleanup.release_error", exc_info=True)

        try:
            log.info("camera.reader_thread.stopped")
        # except Exception justified: logging during thread teardown — structlog may be torn down
        except Exception:
            log.debug("camera.reader_thread.stopped_log_error", exc_info=True)

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
        """Capture a frame and update buffers. Returns False when no frame captured.

        v2.3: Wrapped cap.read() in try/except for GC-safety on test teardown.
        """
        try:
            ret, frame = self.cap.read()
        except (AttributeError, TypeError, RuntimeError, OSError):
            # v2.3: self.cap may be invalid during GC/shutdown
            return False
        # The capture instant is when ``read`` RETURNED the frame: stamped
        # before anything else so the lag checks below do not delay it.
        read_perf = time.perf_counter()

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
            self._frame_seq += 1
            self._last_read_perf = read_perf
            self._last_read_wall = now
            self._read_perfs.append(read_perf)
            self._new_frame.notify_all()

        return True

    def read_next_frame(self, after_seq: int, timeout: float = 0.5) -> CapturedFrame | None:
        """Block until a frame newer than ``after_seq`` was read, and return it.

        Unlike :meth:`get_frame`, a frame is handed out at most once per
        consumer: pass back the ``seq`` you last received. The returned stamps
        are the instant ``cap.read`` returned (``perf_counter`` and ``time``),
        not the instant of this call.

        Returns:
            The newest frame (a copy), or ``None`` when no newer frame arrived
            within ``timeout`` seconds (camera stalled or disconnected).
        """
        with self._new_frame:
            ready = self._new_frame.wait_for(
                lambda: self._frame_available and self._frame_seq > after_seq,
                timeout=max(0.0, float(timeout)),
            )
            if not ready or not self._frame_buffer:
                return None
            return CapturedFrame(
                frame=self._frame_buffer[-1].copy(),
                seq=self._frame_seq,
                t_perf=self._last_read_perf,
                t_wall=self._last_read_wall,
            )

    def measured_fps(self, min_samples: int = 10) -> float | None:
        """Rate the sensor is really delivering, from the last ~120 reads.

        ``actual_fps`` is what the driver REPORTS (``CAP_PROP_FPS``), and many
        webcams report 30 while delivering 39-41 fps. ``None`` with fewer than
        ``min_samples`` reads or a non-positive span.
        """
        with self._lock:
            stamps = list(self._read_perfs)
        if len(stamps) < max(2, int(min_samples)):
            return None
        span = stamps[-1] - stamps[0]
        if span <= 0:
            return None
        return (len(stamps) - 1) / span

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
            # except Exception justified: camera close after timeout
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
            # except Exception justified: normal cap.release() in shutdown — cv2 errors in cleanup
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
        # except Exception justified: context manager exit — wraps release() facade boundary
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

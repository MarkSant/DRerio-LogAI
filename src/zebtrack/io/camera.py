import threading
import time
from collections import deque
from typing import Any

import cv2
import numpy as np
import structlog

from zebtrack.io.frame_source import FrameSource
from zebtrack.settings import settings

log = structlog.get_logger()


class Camera(FrameSource):
    def __init__(self):
        self._camera_index = settings.camera.index
        self.cap = cv2.VideoCapture(self._camera_index)
        if not self.cap.isOpened():
            raise OSError(f"Cannot open camera at index {self._camera_index}")

        self._desired_width = settings.camera.desired_width
        self._desired_height = settings.camera.desired_height
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)

        self._lock = threading.Lock()

        # Protect initial reads with the lock
        with self._lock:
            self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS) or settings.video_processing.fps

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

        # Reconnect tracking attributes
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = settings.camera.max_reconnect_attempts
        self._reconnect_timeout_seconds = settings.camera.reconnect_timeout_seconds
        self._first_failure_time: float | None = None

        # Start the thread as the final step
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()

    def _reader_thread(self):
        """
        The main loop for the background thread that continuously reads
        frames and handles camera reconnections.
        """
        while not self._stopped.is_set():
            if not self.cap.isOpened():
                if self._first_failure_time is None:
                    self._first_failure_time = time.time()

                # Check attempt limit
                if (
                    self._max_reconnect_attempts > 0
                    and self._reconnect_attempts >= self._max_reconnect_attempts
                ):
                    log.error(
                        "camera.reconnect.max_attempts",
                        attempts=self._reconnect_attempts,
                        max_attempts=self._max_reconnect_attempts,
                    )
                    with self._lock:
                        self._latest_frame = (False, None)
                    break  # Exit thread

                elapsed = time.time() - self._first_failure_time

                self._reconnect_attempts += 1
                log.warning(
                    "camera.reconnect.attempt",
                    attempt=self._reconnect_attempts,
                    elapsed_seconds=elapsed,
                )
                self.cap.open(self._camera_index)
                time.sleep(2)

                elapsed = time.time() - self._first_failure_time

                if (
                    self._reconnect_timeout_seconds > 0
                    and elapsed > self._reconnect_timeout_seconds
                ):
                    log.error(
                        "camera.reconnect.timeout",
                        elapsed_seconds=elapsed,
                        max_seconds=self._reconnect_timeout_seconds,
                    )
                    with self._lock:
                        self._frame_buffer.clear()
                        self._frame_timestamps.clear()
                        self._frame_available = False
                    break  # Exit thread
                continue
            else:
                # Reset counters on successful connection
                if self._first_failure_time is not None:
                    log.info(
                        "camera.reconnect.recovered",
                        total_attempts=self._reconnect_attempts,
                        total_downtime_seconds=time.time() - self._first_failure_time,
                    )
                    # Re-apply settings on successful reconnect
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)

                    # Update actual dimensions and FPS after reconnect, under lock
                    with self._lock:
                        self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        self.actual_fps = (
                            self.cap.get(cv2.CAP_PROP_FPS) or settings.video_processing.fps
                        )
                    log.info(
                        "camera.reconnected.dimensions_updated",
                        width=self.actual_width,
                        height=self.actual_height,
                        fps=self.actual_fps,
                    )

                self._reconnect_attempts = 0
                self._first_failure_time = None

            ret, frame = self.cap.read()

            if not ret:
                self.cap.release()
                log.warning("camera.frame_read.failed")
                with self._lock:
                    self._frame_buffer.clear()
                    self._frame_timestamps.clear()
                    self._frame_available = False
                # Add a short sleep to prevent a tight loop on continuous read errors
                time.sleep(0.1)
                continue

            with self._lock:
                self._frame_buffer.append(frame)
                self._frame_timestamps.append(time.time())
                self._frame_available = True
        log.info("camera.reader_thread.stopped")

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
            if lag_ms > settings.camera.max_frame_lag_ms:
                log.warning(
                    "camera.lag.threshold_exceeded",
                    lag_ms=lag_ms,
                    threshold_ms=settings.camera.max_frame_lag_ms,
                )

            return (True, frame)

    def release(self) -> None:
        """
        Signals the reader thread to stop and releases the camera resource.
        """
        self._stopped.set()
        self._thread.join(timeout=2)
        if self.cap.isOpened():
            self.cap.release()
            log.info("camera.released")

    def get_properties(self) -> dict[str, Any]:
        """
        Returns the actual properties of the camera feed, guaranteed to be thread-safe.
        """
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

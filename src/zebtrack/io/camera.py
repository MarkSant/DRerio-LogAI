import threading
import time
from typing import Any, Dict, Tuple

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

        self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        log.info(
            "camera.initialized",
            index=self._camera_index,
            width=self.actual_width,
            height=self.actual_height,
        )

        self._lock = threading.Lock()
        self._latest_frame: Tuple[bool, np.ndarray | None] = (False, None)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._reader_thread, daemon=True)
        self._thread.start()

    def _reader_thread(self):
        """
        The main loop for the background thread that continuously reads
        frames and handles camera reconnections.
        """
        while not self._stopped.is_set():
            if not self.cap.isOpened():
                log.warning("camera.reconnect.start")
                self.cap.open(self._camera_index)
                if self.cap.isOpened():
                    log.info("camera.reconnect.success")
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)
                else:
                    with self._lock:
                        self._latest_frame = (False, None)
                    time.sleep(2)
                    continue

            ret, frame = self.cap.read()

            if not ret:
                self.cap.release()
                log.warning("camera.frame_read.failed")
                with self._lock:
                    self._latest_frame = (False, None)
                # Add a short sleep to prevent a tight loop on continuous read errors
                time.sleep(0.1)
                continue

            with self._lock:
                self._latest_frame = (ret, frame)
        log.info("camera.reader_thread.stopped")

    def get_frame(self) -> Tuple[bool, np.ndarray | None]:
        """
        Returns the most recent frame read by the background thread.
        """
        with self._lock:
            ret, frame = self._latest_frame
            return ret, frame.copy() if ret else None

    def release(self) -> None:
        """
        Signals the reader thread to stop and releases the camera resource.
        """
        self._stopped.set()
        self._thread.join(timeout=2)
        if self.cap.isOpened():
            self.cap.release()
            log.info("camera.released")

    def get_properties(self) -> Dict[str, Any]:
        """
        Returns the actual properties of the camera feed.
        """
        return {
            "width": self.actual_width,
            "height": self.actual_height,
            "fps": self.cap.get(cv2.CAP_PROP_FPS) or settings.video_processing.fps,
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

from typing import Any, Dict, Tuple
import cv2
import numpy as np
import threading
import time

from zebtrack.io.frame_source import FrameSource
from zebtrack.settings import settings


class Camera(FrameSource):
    def __init__(self):
        self._camera_index = settings.camera.index
        self.cap = cv2.VideoCapture(self._camera_index)
        if not self.cap.isOpened():
            # This is a hard failure on startup, so we raise an exception
            raise IOError(f"Cannot open camera at index {self._camera_index}")

        self._desired_width = settings.camera.desired_width
        self._desired_height = settings.camera.desired_height
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)

        self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(
            f"Camera initialized with resolution: "
            f"{self.actual_width}x{self.actual_height}"
        )

        # Threading attributes
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
                print("Camera connection lost. Attempting to reconnect...")
                self.cap.open(self._camera_index)
                if self.cap.isOpened():
                    print("Camera reconnected successfully.")
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._desired_width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._desired_height)
                else:
                    with self._lock:
                        self._latest_frame = (False, None)
                    time.sleep(2)  # Wait before next attempt
                    continue

            ret, frame = self.cap.read()

            if not ret:
                # Frame read failed, likely due to a disconnect
                self.cap.release()
                print("Frame read failed. Assuming disconnect, will try to reconnect.")
                with self._lock:
                    self._latest_frame = (False, None)
                continue  # Let the next loop iteration handle reconnection

            with self._lock:
                self._latest_frame = (ret, frame)
        print("Reader thread stopped.")

    def get_frame(self) -> Tuple[bool, np.ndarray | None]:
        """
        Returns the most recent frame read by the background thread.
        This method is non-blocking.
        """
        with self._lock:
            # Return a copy to prevent race conditions if the consumer modifies the frame
            ret, frame = self._latest_frame
            return ret, frame.copy() if ret else None

    def release(self) -> None:
        """
        Signals the reader thread to stop and releases the camera resource.
        """
        self._stopped.set()
        self._thread.join(timeout=2)  # Wait for the thread to finish
        if self.cap.isOpened():
            self.cap.release()
            print("Camera released.")

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

        # Give the reader thread a moment to start and grab the first frame
        time.sleep(1)

        while True:
            ret, frame = camera.get_frame()
            if not ret:
                print("Failed to grab frame, waiting...")
                time.sleep(0.5)  # Wait a bit before trying again
                continue

            cv2.imshow("Camera Test", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except IOError as e:
        print(e)
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        if camera:
            camera.release()
        cv2.destroyAllWindows()
        print("Test finished.")

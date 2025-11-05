"""
LiveStreamSource: Wrapper around Camera for time-limited analysis workflows.

This module provides a FrameSource implementation that captures from a camera
with duration limits and frame counting, making it compatible with the video
processing pipeline that expects a finite frame count.
"""

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.io.camera import Camera
from zebtrack.io.frame_source import FrameSource

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class LiveStreamSource(FrameSource):
    """
    A FrameSource that wraps Camera for time-limited capture sessions.

    Unlike Camera which runs indefinitely, LiveStreamSource provides:
    - Maximum duration limit (seconds)
    - Estimated frame count for progress tracking
    - Compatible interface with video file processing

    This allows live camera feeds to be processed using the same pipeline
    as pre-recorded video files.
    """

    def __init__(
        self,
        camera_index: int = 0,
        max_duration_s: float = 300.0,
        settings_obj: "Settings | None" = None,
    ):
        """
        Initialize live stream source with duration limit.

        Args:
            camera_index: Camera device index (default 0)
            max_duration_s: Maximum capture duration in seconds (default 300 = 5 min)
            settings_obj: Settings instance (required for Camera initialization)
        """
        if settings_obj is None:
            raise RuntimeError(
                "LiveStreamSource: Settings not injected. "
                "Use: LiveStreamSource(settings_obj=load_settings())"
            )

        self.camera_index = camera_index
        self.max_duration_s = max_duration_s
        self.settings = settings_obj

        # Create underlying camera
        self.camera = Camera(settings_obj=settings_obj)

        # Track timing
        self.start_time = time.time()
        self.frame_number = 0

        # Calculate estimated frame count based on duration and FPS
        self.estimated_fps = self.camera.actual_fps
        self.estimated_frame_count = int(max_duration_s * self.estimated_fps)

        # Cache properties
        self.width = self.camera.actual_width
        self.height = self.camera.actual_height
        self.fps = self.camera.actual_fps

        log.info(
            "live_stream.initialized",
            camera_index=camera_index,
            max_duration_s=max_duration_s,
            estimated_frames=self.estimated_frame_count,
            width=self.width,
            height=self.height,
            fps=self.fps,
        )

    def get_frame(self) -> tuple[bool, Any | None]:
        """
        Read the next frame from the camera.

        Returns:
            (success, frame) tuple. Returns (False, None) when duration limit reached.
        """
        # Check if duration limit exceeded
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_duration_s:
            log.info(
                "live_stream.duration_limit_reached",
                elapsed_s=elapsed,
                max_duration_s=self.max_duration_s,
                frames_captured=self.frame_number,
            )
            return False, None

        # Get frame from camera
        ret, frame = self.camera.get_frame()
        if ret:
            self.frame_number += 1

        return ret, frame

    def get_current_frame_number(self) -> float:
        """
        Returns the current frame number.

        This mimics VideoFileSource.get_current_frame_number() for compatibility
        with the processing pipeline.
        """
        return float(self.frame_number)

    def get_properties(self) -> dict[str, Any]:
        """
        Returns properties compatible with video file processing.

        Returns:
            Dictionary with width, height, fps, and frame_count (estimated).
        """
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.estimated_frame_count,
            "camera_index": self.camera_index,
            "max_duration_s": self.max_duration_s,
            "is_live_stream": True,
        }

    def release(self) -> None:
        """Release camera resources."""
        if self.camera:
            self.camera.release()
            log.info(
                "live_stream.released",
                camera_index=self.camera_index,
                frames_captured=self.frame_number,
                duration_s=time.time() - self.start_time,
            )

    def get_elapsed_time(self) -> float:
        """Get elapsed time since capture started."""
        return time.time() - self.start_time

    def get_remaining_time(self) -> float:
        """Get remaining time until duration limit."""
        return max(0.0, self.max_duration_s - self.get_elapsed_time())


if __name__ == "__main__":
    """Test LiveStreamSource with mock settings."""
    import cv2
    import numpy as np

    from zebtrack.settings import load_settings

    print("Testing LiveStreamSource...")

    try:
        settings = load_settings()
        stream = LiveStreamSource(
            camera_index=0, max_duration_s=10.0, settings_obj=settings  # 10 second test
        )

        print(f"Stream properties: {stream.get_properties()}")
        print(f"Estimated frames: {stream.estimated_frame_count}")

        frame_count = 0
        start = time.time()

        while True:
            ret, frame = stream.get_frame()
            if not ret:
                print("\nStream ended (duration limit or camera error)")
                break

            frame_count += 1

            # Display frame
            if frame is not None:
                # Add frame info overlay
                text = f"Frame {frame_count} | {stream.get_remaining_time():.1f}s left"
                cv2.putText(
                    frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
                )
                cv2.imshow("LiveStreamSource Test", frame)

            # Break on 'q' key
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\nUser interrupted")
                break

            # Log progress every 30 frames
            if frame_count % 30 == 0:
                print(
                    f"Frame {frame_count}/{stream.estimated_frame_count} "
                    f"({stream.get_remaining_time():.1f}s remaining)"
                )

        elapsed = time.time() - start
        print(f"\nCaptured {frame_count} frames in {elapsed:.2f}s")
        print(f"Actual FPS: {frame_count / elapsed:.2f}")

        stream.release()
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    print("\nLiveStreamSource test finished.")

"""Service for retrieving video metadata."""

from pathlib import Path

import cv2
import structlog

log = structlog.get_logger()


class VideoMetadataService:
    """Service responsible for extracting metadata from video files."""

    @staticmethod
    def get_video_dimensions(video_path: Path | str) -> tuple[int, int] | None:
        """Get the dimensions of a video.

        Args:
            video_path: Path to the video file.

        Returns:
            Tuple (width, height) or None on failure.

        Raises:
            ValueError: If the video cannot be opened.
        """
        try:
            cap = cv2.VideoCapture(str(video_path))
            # ``finally``: an error between open and release left the handle open,
            # and on Windows that keeps the video locked for a move or delete
            # (A5-S-011).
            try:
                if not cap.isOpened():
                    raise ValueError(f"Could not open video: {video_path}")

                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            finally:
                cap.release()

            if width <= 0 or height <= 0:
                raise ValueError(f"Invalid dimensions: {width}x{height}")

            log.debug(
                "video_metadata.dimensions_retrieved",
                video_path=str(video_path),
                width=width,
                height=height,
            )

            return width, height

        # except Exception justified: cv2 VideoCapture - re-raises
        except Exception as e:
            log.error(
                "video_metadata.dimensions_error",
                video_path=str(video_path),
                error=str(e),
            )
            raise

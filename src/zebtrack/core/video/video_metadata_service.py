"""Service for retrieving video metadata."""

import cv2
import structlog

log = structlog.get_logger()


class VideoMetadataService:
    """Service responsible for extracting metadata from video files."""

    @staticmethod
    def get_video_dimensions(video_path: str) -> tuple[int, int] | None:
        """Get the dimensions of a video.

        Args:
            video_path: Path to the video file.

        Returns:
            Tuple (width, height) or None on failure.

        Raises:
            ValueError: If the video cannot be opened.
        """
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            if width <= 0 or height <= 0:
                raise ValueError(f"Invalid dimensions: {width}x{height}")

            log.debug(
                "video_metadata.dimensions_retrieved",
                video_path=video_path,
                width=width,
                height=height,
            )

            return width, height

        # except Exception justified: cv2 VideoCapture - re-raises
        except Exception as e:
            log.error(
                "video_metadata.dimensions_error",
                video_path=video_path,
                error=str(e),
            )
            raise

    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """Get comprehensive information about a video.

        Args:
            video_path: Path to the video file.

        Returns:
            Dict with width, height, fps, frame_count.
        """
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                raise ValueError(f"Could not open video: {video_path}")

            info = {
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
                "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            }

            cap.release()
            return info

        # except Exception justified: cv2 VideoCapture - re-raises
        except Exception as e:
            log.error(
                "video_metadata.info_error",
                video_path=video_path,
                error=str(e),
            )
            raise
